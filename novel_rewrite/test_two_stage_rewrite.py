import json
import re
import time
from pathlib import Path

import requests

import rewrite


API_KEY = "sk-9a9a2078201148059d9611e03e7e8423"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-plus"
TIMEOUT_S = 600


def extract_inputs_from_prompt(prompt: str) -> dict:
    def must(pattern: str) -> re.Match:
        m = re.search(pattern, prompt, flags=re.S)
        if not m:
            raise AssertionError(f"Pattern not found: {pattern}")
        return m

    summary = must(r"【全局摘要】：(.*?)\n【人物关系】：").group(1).strip()
    relations_raw = must(r"【人物关系】：(.*?)\n【文风要求】：").group(1).strip()
    relations = json.loads(relations_raw)

    writing_style = must(r"【文风要求】：(.*?)\n【剧情增强提示】：").group(1).strip()
    plot_block = must(r"【剧情增强提示】：\n(.*?)\n【人物性格与对话】：").group(1)
    plot_enhancements = [ln[2:] for ln in plot_block.splitlines() if ln.startswith("- ")]

    char_block = must(r"【人物性格与对话】：\n(.*?)\n【上一块内容】：").group(1)
    character_analysis = []
    for ln in char_block.splitlines():
        if not ln.startswith("- "):
            continue
        m = re.match(r"- (.+?)：(.+?)（风格：(.+)）$", ln)
        if not m:
            raise AssertionError(f"Bad character tip line: {ln}")
        character_analysis.append(
            {"name": m.group(1), "personality": m.group(2), "dialogue_style": m.group(3)}
        )

    prev_text_line = must(r"【上一块内容】：(.*?)\n【本块参考原文】：").group(1).strip()
    prev_text = "" if prev_text_line == "无" else prev_text_line
    ref_text = must(r"【本块参考原文】：\n(.*?)\n【目标字数】：").group(1)
    target_chars = int(must(r"【目标字数】：(\d+)").group(1))

    enhancements = {
        "plot_enhancements": plot_enhancements,
        "character_analysis": character_analysis,
        "writing_style": writing_style,
    }

    return {
        "summary": summary,
        "relations": relations,
        "prev_text": prev_text,
        "ref_text": ref_text,
        "target_chars": target_chars,
        "enhancements": enhancements,
    }


def load_expected_prompt() -> str:
    cached_prompt_path = Path(__file__).resolve().parent / "debug_outputs" / "two_stage_prompt2.txt"
    if not cached_prompt_path.exists():
        raise FileNotFoundError(f"未找到数据文件: {cached_prompt_path}")
    return cached_prompt_path.read_text(encoding="utf-8")


def call_llm(prompt: str) -> tuple[str, float]:
    endpoint = BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "你是资深女频短篇小说创作者。"},
            {"role": "user", "content": prompt},
        ],
    }
    t0 = time.perf_counter()
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=TIMEOUT_S)
    dt = time.perf_counter() - t0
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return content, dt


def preview(text: str, max_len: int = 900) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n...(truncated, total={len(text)} chars)"


def main() -> None:
    source_prompt = load_expected_prompt()
    inputs = extract_inputs_from_prompt(source_prompt)

    prompt1 = rewrite.build_perspective_rewrite_prompt(
        ref_text=inputs["ref_text"],
        perspective="第二人称",
    )
    print(f"=== PROMPT1 人称转换 (chars={len(prompt1)}) ===")
    print(preview(prompt1))
    converted_ref_text, dt1 = call_llm(prompt1)
    print(f"=== OUTPUT1 人称转换结果 (seconds={dt1:.2f}, chars={len(converted_ref_text)}) ===")
    print(preview(converted_ref_text))

    prompt2 = rewrite.build_rewrite_prompt(
        summary=inputs["summary"],
        relations=inputs["relations"],
        prev_text=inputs["prev_text"],
        ref_text=converted_ref_text,
        target_chars=inputs["target_chars"],
        enhancements=inputs["enhancements"],
    )
    print(f"=== PROMPT2 正文改写 (chars={len(prompt2)}) ===")
    print(preview(prompt2))
    rewritten_text, dt2 = call_llm(prompt2)
    print(f"=== OUTPUT2 正文结果 (seconds={dt2:.2f}, chars={len(rewritten_text)}) ===")
    print(preview(rewritten_text))

    out_dir = Path(__file__).resolve().parent / "debug_outputs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "two_stage_prompt1.txt").write_text(prompt1, encoding="utf-8")
    (out_dir / "two_stage_output1_converted_ref.txt").write_text(converted_ref_text, encoding="utf-8")
    (out_dir / "two_stage_prompt2.txt").write_text(prompt2, encoding="utf-8")
    (out_dir / "two_stage_output2_rewrite.txt").write_text(rewritten_text, encoding="utf-8")
    print(f"已写入结果目录: {out_dir}")


if __name__ == "__main__":
    main()
