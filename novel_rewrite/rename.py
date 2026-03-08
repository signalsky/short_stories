import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in response")
    return json.loads(match.group(0))

def build_rename_prompt(novel_text: str) -> str:
    return (
        "请处理下面这篇女频短篇小说，严格只返回JSON对象，不要输出解释文字。\n"
        "JSON结构必须是：\n"
        "{\n"
        '  "characters": [\n'
        "    {\n"
        '      "name": "原名",\n'
        '      "aliases": ["小名1","昵称1"],\n'
        '      "new_name": "新名字",\n'
        '      "new_aliases": ["新小名1","新昵称1"],\n'
        '      "relations": [\n'
        "        {\n"
        '          "type": "关系类型，如母亲-子女/父亲-子女/兄弟姐妹/夫妻/同事",\n'
        '          "target": "关系对方原名",\n'
        '          "same_surname": true\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "new_title": "吸睛标题",\n'
        '  "time_changes": [\n'
        '    {"original_time": "5年", "new_time": "4年", "reason": "逻辑修正"}\n'
        '  ]\n'
        "}\n"
        "要求：\n"
        "1）提取全部主要人物及其小名昵称，建立对应关系。\n"
        "2）只有有名有姓的才需要取新名字；只有姓的（如林夫人）改姓即可；昵称（如阿弃、阿娘）保持原样，不要修改。\n"
        "3）必须补充人物关系，尤其母亲和子女、父亲和子女、兄弟姐妹。\n"
        "4）same_surname 字段表示该关系下是否应同姓。\n"
        "5）重命名时，same_surname=true 的关系要保持同姓。\n"
        "6）新标题要情绪强烈、女性读者偏好、有传播感。\n"
        "7）提取文中出现的关键时间点（如“5年”、“3个月”等），并建议修改后的时间。修改时必须考虑逻辑合理性（如孩子年龄、事件间隔等）。如果时间无需修改，new_time可与original_time相同。\n"
        "小说全文如下：\n"
        f"{novel_text}"
    )

def normalize_mapping(payload: dict) -> dict:
    characters = payload.get("characters") or []
    cleaned = []
    for item in characters:
        old_name = str(item.get("name", "")).strip()
        if not old_name: continue
        new_name = str(item.get("new_name", "")).strip() or old_name
        
        aliases = [str(x).strip() for x in item.get("aliases", []) if str(x).strip()]
        new_aliases = [str(x).strip() for x in item.get("new_aliases", []) if str(x).strip()]
        
        if len(new_aliases) < len(aliases):
            new_aliases += [new_name] * (len(aliases) - len(new_aliases))
        new_aliases = new_aliases[:len(aliases)]

        cleaned.append({
            "name": old_name,
            "aliases": aliases,
            "new_name": new_name,
            "new_aliases": new_aliases,
            "relations": item.get("relations", [])
        })
    
    time_changes = payload.get("time_changes") or []
    cleaned_times = []
    for t in time_changes:
        orig = str(t.get("original_time", "")).strip()
        new_t = str(t.get("new_time", "")).strip()
        if orig and new_t and orig != new_t:
            cleaned_times.append({"original_time": orig, "new_time": new_t})

    return {
        "characters": cleaned, 
        "new_title": payload.get("new_title", "改写小说"),
        "time_changes": cleaned_times
    }

def replace_times(text: str, time_changes: List[dict]) -> str:
    """
    Replace times in text.
    """
    rep = {}
    
    for item in time_changes:
        orig = str(item["original_time"]).strip()
        new_t = str(item["new_time"]).strip()
        
        if not orig or not new_t: continue

        # 1. Add direct mapping
        rep[orig] = new_t
    
    if not rep:
        return text
        
    keys = sorted(rep.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return pattern.sub(lambda m: rep[m.group(0)], text)

def replace_names(text: str, mapping: dict) -> str:
    rep = {}
    for char in mapping["characters"]:
        rep[char["name"]] = char["new_name"]
        for old, new in zip(char["aliases"], char["new_aliases"]):
            if len(old) >= 1:
                rep[old] = new
    
    if not rep:
        return text
        
    keys = sorted(rep.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return pattern.sub(lambda m: rep[m.group(0)], text)

def run_rename(
    input_path: Path, 
    output_path: Path, 
    chat_func: Callable, 
    trace_logger: Callable[[str], None]
) -> str:
    trace_logger(f"[RENAME] Reading input from {input_path}")
    novel_text = input_path.read_text(encoding="utf-8", errors="ignore")
    prompt = build_rename_prompt(novel_text)
    
    raw_response = chat_func(
        prompt=prompt,
        call_tag="RENAME_ANALYSIS",
        trace_logger=trace_logger,
        json_mode=True,
        model="qwen-plus"
    )
    
    mapping = normalize_mapping(extract_json_object(raw_response))
    
    # 1. Replace Times first
    trace_logger(f"[RENAME] Replacing times... {len(mapping.get('time_changes', []))} changes found.")
    text_with_new_times = replace_times(novel_text, mapping.get("time_changes", []))
    
    # 2. Replace Names
    renamed_text = replace_names(text_with_new_times, mapping)
    
    output_path.write_text(renamed_text, encoding="utf-8")
    trace_logger(f"[RENAME] Renamed file saved to: {output_path}")
    trace_logger(f"[RENAME] New title: {mapping.get('new_title', '改写小说')}")
    return renamed_text, mapping.get("new_title", "改写小说")
