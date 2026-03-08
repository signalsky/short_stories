import json
import re
from pathlib import Path
from typing import Callable, List


def get_target_perspective(perspective: str) -> str:
    if "一" in perspective:
        return "第二人称"
    return "第一人称"


def build_perspective_rewrite_prompt(ref_text: str, perspective: str = "第一人称") -> str:
    target_perspective = get_target_perspective(perspective)
    return (
        f"请将下面【原文】统一转换为{target_perspective}写法。\n"
        "要求：\n"
        "1) 保留原段落结构与主要句意。\n"
        "2) 修正所有视角漂移和代词不一致问题。\n"
        "3) 只输出改写后的正文，不要输出说明。\n"
        "4) 修正可能存在的语病。\n"
        f"【原文】：\n{ref_text}\n"
    )


def build_character_tips(enhancements: dict = None) -> str:
    enhancements = enhancements or {}
    return "\n".join([
        f"- {c['name']}：{c['personality']}（风格：{c['dialogue_style']}）"
        for c in enhancements.get("character_analysis", [])
    ])


def build_dialogue_rewrite_prompt(ref_text: str, char_tips: str) -> str:
    return (
        "请只处理下面文本中的人物对话内容，按要求逐句改写，只要是对话内容都修改。\n"
        "要求：\n"
        "1) 对话必须结合【人物性格与对话】，明确说话人、语气、措辞与潜台词。\n"
        "2) 只输出改写后的完整正文，不要输出说明。\n"
        "3) 对话内容禁止出现...等不符合书写规范的符号，特别是一句话的开头。\n"
        f"【人物性格与对话】：\n{char_tips}\n"
        f"【原文】：\n{ref_text}\n"
    )


def build_rewrite_prompt(
    summary: str,
    relations: List[dict],
    prev_text: str,
    ref_text: str,
    target_chars: int,
    enhancements: dict = None
) -> str:
    enhancements = enhancements or {}
    plot_tips = "\n".join([f"- {tip}" for tip in enhancements.get("plot_enhancements", [])])
    style_tip = enhancements.get("writing_style", "保持原风")

    return (
        f"请按要求修改【原文】，只输出最终正文。\n"
        f"【全局摘要】：{summary}\n"
        f"【人物关系】：{json.dumps(relations, ensure_ascii=False)}\n"
        f"【文风要求】：{style_tip}\n"
        f"【剧情增强】：\n{plot_tips}\n"
        f"【前文内容】：{prev_text if prev_text else '无'}\n"
        f"【原文】：\n{ref_text}\n"
        f"【目标字数】：{target_chars}\n\n"
        "强制要求：\n"
        "1) 重点修改场景与细节，比如把酒店的床上改成别的床上（场所要符合角色身份，比如：穷/富等），非重要人物等。\n"
        "2) 结合【剧情增强】加强情绪冲突与推进节奏，补足动作、心理与环境细节，但不要流水账。\n"
        "3) 保持与上一块的自然衔接，保留原结构与事件顺序。\n"
        "4) 有点黄的地方要加强，加强性暗示。\n"
        "输出：\n"
        "只输出纯净正文：不要输出任何说明/分析/标题/分隔线。\n"
        "强烈禁止：\n"
        "1) 禁止使用不是/没...而是， 不是...不是/没...是，这种否定...肯定的明显AI味的语句。\n"
        "2) 输出纯文本，禁止带有markdown格式。\n"
    )

def run_rewrite(
    plan: dict,
    output_path: Path,
    chat_func: Callable,
    trace_logger: Callable[[str], None]
) -> None:
    trace_logger("[REWRITE] Processing plan...")
    chunks_plan = plan.get("chunks", [])
    
    # Initialize file with empty content or clear existing file
    output_path.write_text("", encoding="utf-8")
    
    final_chunks = []
    
    for i, chunk_def in enumerate(chunks_plan):
        idx = i + 1
        target = chunk_def.get("target_chars", 1200)
        ref_text = chunk_def.get("content", "")
        prev_text = final_chunks[-1] if final_chunks else ""

        trace_logger(f"[REWRITE] Converting perspective for chunk {idx}/{len(chunks_plan)}...")
        perspective_prompt = build_perspective_rewrite_prompt(
            ref_text=ref_text,
            perspective=plan.get("perspective", "第一人称")
        )
        ref_text = chat_func(
            prompt=perspective_prompt,
            call_tag=f"REWRITE_PERSPECTIVE_{idx}",
            trace_logger=trace_logger,
            json_mode=False
        )

        char_tips = build_character_tips(plan.get("enhancements", {}))
        dialogue_prompt = build_dialogue_rewrite_prompt(ref_text=ref_text, char_tips=char_tips)
        trace_logger(f"[REWRITE] Optimizing dialogues for chunk {idx}/{len(chunks_plan)}...")
        ref_text = chat_func(
            prompt=dialogue_prompt,
            call_tag=f"REWRITE_DIALOGUE_{idx}",
            trace_logger=trace_logger,
            json_mode=False
        )
        
        prompt = build_rewrite_prompt(
            summary=plan.get("summary", ""),
            relations=plan.get("relations", []),
            prev_text=prev_text,
            ref_text=ref_text,
            target_chars=target,
            enhancements=plan.get("enhancements", {})
        )
        
        trace_logger(f"[REWRITE] Generating chunk {idx}/{len(chunks_plan)}...")
        content = chat_func(
            prompt=prompt, 
            call_tag=f"REWRITE_CHUNK_{idx}", 
            trace_logger=trace_logger, 
            json_mode=False
        )
        
        final_chunks.append(content)
        
        # Append to file immediately
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{idx}\n\n{content}\n\n")
            
        trace_logger(f"[REWRITE] Chunk {idx} completed and saved. Length: {len(content)}")

    trace_logger(f"[REWRITE] Final novel saved to: {output_path}")
