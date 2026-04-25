# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
from typing import List, Tuple

from utils import call_dashscope_api


MIN_CHUNK_WORDS = 1200
MAX_CHUNK_WORDS = 2800
IDEAL_CHUNK_WORDS = 1600
DEFAULT_PROLOGUE_WORDS = 180


def get_writer_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def get_export_dir() -> str:
    export_dir = os.path.join(get_writer_dir(), "导出")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def get_progress_title(progress_path: str) -> str:
    filename = os.path.basename(progress_path)
    title = filename.replace("_进度.json", "")
    return re.sub(r'[\\/*?:"<>|]', "", title).strip() or "未命名导出"


def normalize_text_block(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return ""

    paragraphs = []
    for part in re.split(r"\n\s*\n", text):
        cleaned = re.sub(r"[ \t]+", " ", part).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return "\n\n".join(paragraphs)


def build_prologue_prompt(raw_prologue: str, target_words: int) -> str:
    return f"""你是一名擅长短篇网文出版整理的编辑。

现在要把一段小说开头整理成导出版的“引子/楔子”。

【目标】
1. 保留原始戏剧冲突、悬念和钩子。
2. 文风自然，像成熟网文正文，不要写成总结、简介或宣传文案。
3. 只输出引子正文，不要加标题，不要加引号，不要解释。
4. 字数尽量控制在 {target_words} 字左右，允许上下浮动 30 字。
5. 保持第一人称叙述和阅读张力，结尾要有明确的钩子感。
6. 不要擅自新增关键设定，不要改变人物关系和事实。

【原始引子】
{raw_prologue}
"""


def rewrite_prologue(raw_prologue: str, target_words: int = DEFAULT_PROLOGUE_WORDS) -> str:
    raw_prologue = normalize_text_block(raw_prologue)
    if not raw_prologue:
        return ""

    prompt = build_prologue_prompt(raw_prologue, max(80, int(target_words)))
    response = call_dashscope_api(
        prompt,
        system_prompt="你是一个擅长短篇网文开篇打磨的编辑，输出必须是可直接发布的正文片段。"
    )
    if not response:
        return raw_prologue

    cleaned = normalize_text_block(response)
    return cleaned or raw_prologue


def split_oversized_text(text: str, max_words: int = MAX_CHUNK_WORDS) -> List[str]:
    text = normalize_text_block(text)
    if not text:
        return []
    if len(text) <= max_words:
        return [text]

    sentences = re.split(r"(?<=[。！？!?])", text)
    segments = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current and len(current) + len(sentence) > max_words:
            segments.append(current.strip())
            current = sentence
        else:
            current += sentence

    if current.strip():
        segments.append(current.strip())

    if len(segments) <= 1:
        hard_segments = []
        remaining = text
        while len(remaining) > max_words:
            cut_pos = remaining.rfind("。", 0, max_words)
            if cut_pos < int(max_words * 0.6):
                cut_pos = max_words
            hard_segments.append(remaining[:cut_pos + (1 if cut_pos < len(remaining) and remaining[cut_pos] == "。" else 0)].strip())
            remaining = remaining[cut_pos + (1 if cut_pos < len(remaining) and remaining[cut_pos] == "。" else 0):].strip()
        if remaining:
            hard_segments.append(remaining)
        return [seg for seg in hard_segments if seg]

    return [seg for seg in segments if seg]


def normalize_generated_paragraphs(paragraphs: List[str]) -> List[str]:
    normalized = []
    for item in paragraphs or []:
        if not isinstance(item, str):
            continue
        cleaned = normalize_text_block(item)
        if not cleaned:
            continue
        if cleaned.startswith("【待生成") or cleaned.startswith("【生成失败"):
            continue
        normalized.append(cleaned)
    return normalized


def merge_body_chunks(paragraphs: List[str]) -> List[str]:
    chunks = []
    current_parts: List[str] = []
    current_len = 0

    def flush_current():
        nonlocal current_parts, current_len
        if not current_parts:
            return
        merged = normalize_text_block("\n\n".join(current_parts))
        for piece in split_oversized_text(merged):
            chunks.append(piece)
        current_parts = []
        current_len = 0

    for paragraph in normalize_generated_paragraphs(paragraphs):
        para_len = len(paragraph)

        if not current_parts:
            current_parts = [paragraph]
            current_len = para_len
            continue

        projected_len = current_len + 2 + para_len
        should_flush = False

        if current_len >= MIN_CHUNK_WORDS and projected_len > IDEAL_CHUNK_WORDS:
            if projected_len > MAX_CHUNK_WORDS:
                should_flush = True
            else:
                delta_if_keep = abs(projected_len - IDEAL_CHUNK_WORDS)
                delta_if_flush = abs(current_len - IDEAL_CHUNK_WORDS)
                should_flush = delta_if_flush <= delta_if_keep

        if projected_len > MAX_CHUNK_WORDS and current_len >= MIN_CHUNK_WORDS:
            should_flush = True

        if should_flush:
            flush_current()
            current_parts = [paragraph]
            current_len = para_len
            continue

        current_parts.append(paragraph)
        current_len = projected_len

    flush_current()

    if len(chunks) >= 2 and len(chunks[-1]) < MIN_CHUNK_WORDS:
        combined = normalize_text_block(chunks[-2] + "\n\n" + chunks[-1])
        if len(combined) <= MAX_CHUNK_WORDS:
            chunks[-2] = combined
            chunks.pop()

    return chunks


def resolve_outline_path(progress_path: str, progress_data: dict) -> str:
    outline_dir = os.path.join(get_writer_dir(), "大纲")

    outline_filename = progress_data.get("source_outline_filename")
    if not outline_filename:
        outline_filename = os.path.basename(progress_path).replace("_进度.json", ".json")

    return os.path.join(outline_dir, outline_filename)


def load_outline_data(progress_path: str, progress_data: dict) -> Tuple[dict, str]:
    outline_path = resolve_outline_path(progress_path, progress_data)
    if not os.path.exists(outline_path):
        return {}, outline_path

    with open(outline_path, "r", encoding="utf-8") as f:
        return json.load(f), outline_path


def build_output_path(progress_path: str, progress_data: dict, outline_data: dict) -> str:
    del progress_data, outline_data
    output_basename = get_progress_title(progress_path)
    return os.path.join(get_export_dir(), f"{output_basename}.txt")


def compose_export_text(prologue_text: str, body_chunks: List[str]) -> str:
    sections = []
    if prologue_text:
        sections.append(normalize_text_block(prologue_text))

    for idx, chunk in enumerate(body_chunks, start=1):
        sections.append(f"{idx}\n{normalize_text_block(chunk)}")

    return "\n\n".join([section for section in sections if section]).strip() + "\n"


def export_story(progress_path: str, prologue_words: int = DEFAULT_PROLOGUE_WORDS) -> dict:
    if not os.path.exists(progress_path):
        raise FileNotFoundError(f"Progress file not found: {progress_path}")

    with open(progress_path, "r", encoding="utf-8") as f:
        progress_data = json.load(f)

    outline_data, outline_path = load_outline_data(progress_path, progress_data)
    raw_prologue = outline_data.get("引子/楔子", "")
    exported_prologue = rewrite_prologue(raw_prologue, target_words=prologue_words) if raw_prologue else ""
    export_title = get_progress_title(progress_path)

    paragraphs = progress_data.get("generated_paragraphs", [])
    body_chunks = merge_body_chunks(paragraphs)
    if not body_chunks:
        raise ValueError("No valid generated_paragraphs found for export.")

    final_text = compose_export_text(exported_prologue, body_chunks)
    output_path = build_output_path(progress_path, progress_data, outline_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    return {
        "title": export_title,
        "output_filename": os.path.basename(output_path),
        "output_path": output_path,
        "outline_path": outline_path,
        "chunk_count": len(body_chunks),
        "chunk_lengths": [len(chunk) for chunk in body_chunks],
        "prologue_length": len(exported_prologue),
        "has_prologue": bool(exported_prologue),
        "preview": final_text[:1200]
    }


def main():
    parser = argparse.ArgumentParser(description="Export rewrite progress JSON to formatted TXT.")
    parser.add_argument("progress_path", help="Path to the *_进度.json file")
    parser.add_argument("--prologue-words", type=int, default=DEFAULT_PROLOGUE_WORDS, help="Target word count for exported prologue")
    args = parser.parse_args()

    result = export_story(args.progress_path, prologue_words=max(80, args.prologue_words))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
