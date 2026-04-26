# -*- coding: utf-8 -*-
import json
import os
import re

from utils import call_dashscope_api, load_config


DEFAULT_REFERENCE_HINT = """更换背景：可以将现代都市替换为年代文、古代言情、仙侠修真等背景。
重塑人设：保留核心冲突，但给角色赋予新身份自带矛盾（如：霸总换特种兵、平凡女主换战地医生、白月光换成男主牺牲战友的妹妹）。
融入新元素：例如增加“弹幕”或“读心术”设定，让女主从被动承受变为拥有上帝视角，更直观地放大委屈感与男主带来的伤害。"""


def _truncate_text(text, max_len=220):
    if not isinstance(text, str):
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len].rstrip() + "..."


def _extract_scene_lines(scenes_dict, max_scenes=8):
    if not isinstance(scenes_dict, dict):
        return []

    scene_lines = []
    items = list(scenes_dict.items())
    if len(items) > max_scenes:
        items = items[: max_scenes - 1] + items[-1:]

    for idx, (scene_name, scene_data) in enumerate(items, start=1):
        if not isinstance(scene_data, dict):
            continue
        scene_lines.append(
            (
                f"{idx}. {scene_name}\n"
                f"   - 情绪点：{_truncate_text(scene_data.get('情绪点', ''), 70)}\n"
                f"   - 剧情细纲：{_truncate_text(scene_data.get('剧情细纲', ''), 150)}"
            )
        )
    return scene_lines


def _build_outline_context(outline_data):
    scenes_dict = outline_data.get("场景切分与建议", {})
    scene_text = "\n".join(_extract_scene_lines(scenes_dict)) or "暂无场景摘要"

    context = {
        "书名": outline_data.get("书名", ""),
        "核心人物": outline_data.get("核心人物", []),
        "人物人设": outline_data.get("人物人设", outline_data.get("人物性格", {})),
        "故事线提取": outline_data.get("故事线提取", {}),
        "原文问题诊断": outline_data.get("原文问题诊断", []),
        "结构优化建议": outline_data.get("结构优化建议", ""),
        "引子/楔子": _truncate_text(outline_data.get("引子/楔子", ""), 280),
    }

    return (
        f"【小说基础信息】\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"【场景摘要】\n{scene_text}"
    )


def _clean_response_text(text):
    if not isinstance(text, str):
        return ""

    cleaned = text.strip()
    fenced_match = re.search(r"```(?:text|markdown)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()

    cleaned = cleaned.strip().strip('"')
    return cleaned


def generate_global_rewrite_instruction(outline_path, reference_hint=""):
    if not outline_path or not os.path.exists(outline_path):
        raise FileNotFoundError("未找到所选大纲文件")

    config = load_config()
    if not config.get("api_key") or not config.get("base_url"):
        raise ValueError("请先在配置页面填写 API Key 和 Base URL")

    with open(outline_path, "r", encoding="utf-8") as f:
        outline_data = json.load(f)

    outline_context = _build_outline_context(outline_data)
    effective_hint = (reference_hint or DEFAULT_REFERENCE_HINT).strip()

    prompt = f"""你是一名资深网文改编编辑。请基于下面这份小说大纲，生成一段可直接填写到“全局重写建议”输入框里的中文改写指令。

【核心目标】
这段建议是给后续小说生成模型看的，目标是避免抄袭和降低相似度，但输出必须有实际改写价值，重点是给出具体可落地的新方案，而不是空泛口号。

【最重要的要求】
1. 严禁输出空话、套话、正确废话，例如：
   - “彻底规避版权风险”
   - “保留核心冲突并完成结构性重构”
   - “不能沿用原文表达”
   这些话可以隐含在建议里，但不要当成正文主体。
2. 必须给出具体改法，像真人编辑在提案，而不是在写原则。
3. 建议方向不必全部都有，可以只选最适合这本书的 1 到 3 类来写：
   - 推荐背景
   - 新元素 / 新机制
   - 人设替换
   - 其他你认为更有效的改法
4. 不需要解释“为什么适合这本书”，直接给方案本身。
5. 保留原故事最核心的冲突钩子、关系拉扯和情绪爽虐感，但必须把外部设定、身份组合、推进方式改出明显差异。

【你要尽量产出的内容风格】
- 如果推荐背景，就直接写成“可改成 80/90 年代县城背景”或“可改成侯府宅斗背景”，不要只写“更换背景”。
- 如果做人设替换，就具体到角色级别，例如“男主改成退伍军官 / 女主改成乡镇卫生院医生 / 婆婆改成当年被拐返城知青”。
- 如果加新元素，就明确机制，例如“加入弹幕视角”“加入读心误读”“加入论坛舆论场改成家属院流言链”。
- 如果有更好的改法，也可以直接给，例如“把亲子鉴定改成旧档案、接生记录、寻亲登记、胎记信物、老照片比对”等。

【参考改写方向】
{effective_hint}

【输出要求】
1. 只输出最终建议正文，不要写前言、总结、标题、解释或 Markdown 代码块。
2. 使用 4 到 6 条分点建议，每条单独一行。
3. 每条都必须具体，能看出你到底建议改什么。
4. 尽量多给“可直接替换”的具体设定，不要写抽象原则。
5. 不要照抄我给你的参考改写方向原句，要结合大纲重新生成。

{outline_context}
"""

    response = call_dashscope_api(
        prompt,
        system_prompt="你是擅长网文拆解、反套路改编与避相似度重写的小说总编。输出必须是可直接执行的中文写作指令。"
    )
    cleaned_response = _clean_response_text(response)
    if not cleaned_response:
        raise RuntimeError("AI 未返回有效的重写建议，请稍后重试")

    return cleaned_response
