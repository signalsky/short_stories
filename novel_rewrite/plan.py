import json
import re
from pathlib import Path
from typing import Callable, List

def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))

def build_combined_plan_prompt(text: str) -> str:
    return (
        "请阅读下面小说，进行全面分析并提出改进建议。严格只返回JSON。\n"
        "JSON结构：\n"
        "{\n"
        '  "perspective": "第几人称写法，主角用我是第一人称，主角用你是第二人称，剩下就是第三人称",\n'
        '  "protagonist": "主角名字",\n'
        '  "villains": ["反派名字1", "反派名字2"],\n'
        '  "relations": [{"name":"名字","relations":[{"target":"名字", "type":"关系"}]}]\n'
        "}\n"
        f"要求：\n"
        "1) 提取准确的人物关系。\n"
        f"小说全文：\n{text}"
    )

def split_text_into_chunks(text: str, target_chars: int = 1200) -> List[dict]:
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = []
    current_len = 0
    
    for para in paragraphs:
        para_len = len(para) + 1 # +1 for newline
        if current_len + para_len > target_chars and current_len > target_chars * 0.5:
            # Finish current chunk
            content = "\n".join(current_chunk)
            chunks.append({
                "index": len(chunks) + 1,
                "content": content,
                "target_chars": len(content)
            })
            current_chunk = [para]
            current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len
            
    # Last chunk
    if current_chunk:
        content = "\n".join(current_chunk)
        chunks.append({
            "index": len(chunks) + 1,
            "content": content,
            "target_chars": len(content)
        })
        
    return chunks



def run_plan(
    input_text: str,
    chat_func: Callable,
    trace_logger: Callable[[str], None]
) -> dict:
    trace_logger("[PLAN] Starting combined analysis and enhancement...")
    
    # 1. Combined Analysis & Enhancement
    prompt = build_combined_plan_prompt(input_text)
    # Using qwen-plus for planning as requested
    raw_response = chat_func(prompt=prompt, call_tag="PLAN_COMBINED", trace_logger=trace_logger, json_mode=True, model="qwen-plus")
    final_plan = extract_json_object(raw_response)
    
    # 2. Python-based Chunking (after LLM call)
    trace_logger("[PLAN] Splitting text into chunks locally...")
    chunks = split_text_into_chunks(input_text, target_chars=1200)
    final_plan["chunks"] = chunks
    trace_logger(f"[PLAN] Created {len(chunks)} chunks.")
    
    return final_plan
