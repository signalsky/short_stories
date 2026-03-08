from pathlib import Path
from typing import Callable
from utils import format_novel_text


def get_target_perspective(perspective: str) -> str:
    if "一" in perspective:
        return "第二人称"
    return "第一人称"


def build_perspective_rewrite_prompt(ref_text: str, plan: dict) -> str:
    perspective = plan.get("perspective", "第一人称")
    protagonist = plan.get("protagonist", "主角")
    villains = plan.get("villains", [])
    villains_str = "、".join(villains) if villains else "反派"
    
    target_perspective = get_target_perspective(perspective)
    return (
        f"请将下面【原文】中{protagonist}的视角转换为{target_perspective}写法。\n"
        "要求：\n"
        "1) 保留原段落结构与主要句意。\n"
        "2) 修正所有视角漂移和代词不一致问题。\n"
        "3) 只输出改写后的正文，不要输出说明。\n"
        "4) 有点黄的地方要加强，加强性暗示。\n"
        f"5) 强化女主（{protagonist}）的遭遇、强化男主爱女主，强化反派（{villains_str}）的可恶。\n"
        f"【原文】：\n{ref_text}\n"
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
    
    for i, chunk_def in enumerate(chunks_plan):
        idx = i + 1
        ref_text = chunk_def.get("content", "")

        trace_logger(f"[REWRITE] Converting perspective for chunk {idx}/{len(chunks_plan)}...")
        perspective_prompt = build_perspective_rewrite_prompt(
            ref_text=ref_text,
            plan=plan
        )
        ref_text = chat_func(
            prompt=perspective_prompt,
            call_tag=f"REWRITE_PERSPECTIVE_{idx}",
            trace_logger=trace_logger,
            json_mode=False
        )

        content = ref_text
        
        # Format content before writing
        content = format_novel_text(content)
        
        # Append to file immediately
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{idx}\n\n{content}\n\n")
            
        trace_logger(f"[REWRITE] Chunk {idx} completed and saved. Length: {len(content)}")

    trace_logger(f"[REWRITE] Final novel saved to: {output_path}")
