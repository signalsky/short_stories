# -*- coding: utf-8 -*-
import json
import re
import time

from utils import call_dashscope_api, clean_and_parse_json


QUICK_REVIEW_RETRIES = 1
REVIEW_RETRIES = 1
REWRITE_RETRIES = 3
COMPARISON_RETRIES = 3
MAX_REWRITE_ATTEMPTS = 2

REWRITE_SYSTEM_PROMPT = (
    "你是成熟的小说改稿作者，优先追求成稿质量、阅读舒适度和自然的人味。"
    "你的语言亲近、有聊天感、有网文阅读趣味，不写作文腔、总结腔和过度正经的说明腔。"
    "你擅长把情绪落在动作、对话和事件承接上，不靠密集修辞制造假张力。"
    "你会主动删除解释腔、夸张反应、重复意象、连环比喻、堆叠形容词和过饱和情绪。"
    "你知道真正高级的情绪来自克制、轻重缓急和留白，但克制不等于发虚，该炸的节点要有刀口。"
    "你会把女主改得更有脑子、有魅力、有被偏爱的价值，而不是寡淡的受苦工具人。"
    "你会把'泪点'、'虐点'、'爽点'和'钩子'当作结构提示，而不是把它们写成标签化话术。"
)


def normalize_scene_text(text):
    if not text:
        return ""
    text = re.sub(r"```[a-zA-Z]*\n", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def count_effective_chars(text):
    normalized = re.sub(r"\s+", "", text or "")
    return len(normalized)


def ensure_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [value]


def trim_for_prompt(text, max_chars):
    if not isinstance(text, str):
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "……"


def build_length_check(target_words, actual_chars):
    if not target_words or target_words <= 0:
        return {
            "target_words": target_words,
            "actual_chars": actual_chars,
            "delta": 0,
            "status": "unknown",
            "pass": True,
            "suggestion": "未提供有效目标字数，跳过硬性字数判定。"
        }

    tolerance = max(60, int(target_words * 0.2))
    delta = actual_chars - target_words

    if abs(delta) <= tolerance:
        status = "ok"
        passed = True
        suggestion = "字数基本达标，无需因篇幅单独返工。"
    elif delta > 0:
        status = "too_long"
        passed = False
        suggestion = "字数明显偏长，删掉重复解释、重复心理活动、堆砌修饰和不推动事件的对话。"
    else:
        status = "too_short"
        passed = False
        suggestion = "字数明显偏短，补足关键动作、人物来回、冲突推进和落地的情绪承接。"

    return {
        "target_words": target_words,
        "actual_chars": actual_chars,
        "delta": delta,
        "tolerance": tolerance,
        "status": status,
        "pass": passed,
        "suggestion": suggestion
    }


def extract_scene_elements(scene_data):
    elements = {}
    if not isinstance(scene_data, dict):
        return elements
    for el_name in ["爽点", "钩子", "泪点", "虐点"]:
        el_val = scene_data.get(el_name)
        if isinstance(el_val, list):
            cleaned = [item for item in el_val if item and item != "无"]
            if cleaned:
                elements[el_name] = cleaned
        elif isinstance(el_val, str) and el_val and el_val != "无" and el_val != "[]":
            elements[el_name] = [el_val]
    return elements


def call_json_response(prompt, system_prompt, retries):
    parsed = None
    raw_text = None
    for _ in range(retries):
        raw_text = call_dashscope_api(prompt, system_prompt=system_prompt)
        parsed = clean_and_parse_json(raw_text)
        if isinstance(parsed, dict):
            return parsed, raw_text
    return None, raw_text


def build_quick_review_prompt(scene_name, scene_outline, scene_emotion, target_words, actual_chars, scene_text):
    short_outline = trim_for_prompt(scene_outline, 180)
    short_emotion = trim_for_prompt(scene_emotion, 80)
    short_scene_text = trim_for_prompt(scene_text, 900)
    return f"""你是小说快审助手。请只做轻量判断，不要长篇分析。

你的任务：快速判断这段小说正文是否“基本可用”，给出一个总分即可。
重点只看：
1. 是否像人话，AI 味重不重。
2. 情绪有没有落到动作和对白上，而不是只会解释心情。
3. 视角、称呼、基本逻辑是否明显出错。
4. 字数是否离目标太远。

【场景名】：
{scene_name}

【场景细纲】：
{short_outline}

【主情绪】：
{short_emotion}

【目标字数】：
{target_words}

【实际有效字数】：
{actual_chars}

【正文】：
{short_scene_text}

请只返回一个合法 JSON：
{{
  "score": 84,
  "verdict": "good/enough/risky/bad",
  "reason": "一句话说明",
  "risk_tags": ["AI味/情绪写虚/逻辑/视角/称呼/字数"]
}}
不要输出 Markdown，不要补充解释。
"""


def build_review_prompt(
    public_context,
    context_paragraphs,
    scene_name,
    scene_outline,
    reference_excerpt,
    scene_emotion,
    target_words,
    actual_chars,
    length_check,
    scene_data,
    scene_text,
):
    elements = extract_scene_elements(scene_data)
    return f"""你是短篇小说质检编辑，请严格检查下面这个场景是否能直接通过。

你必须重点检查以下项目，并尽量引用原文具体片段：
1. 是否有明显 AI 味、用力过猛、堆砌形容词、像模型在解释剧情。
2. 情绪是否有效，当前场景的主情绪是否清晰、集中，是否存在整段持续高压、没有透气口、什么都想写导致读者疲劳的问题。
3. 情绪强度是否写到了点上。关键刺激来了以后，人物有没有“刺激 -> 瞬时反应 -> 对外动作/对白/决定 -> 新风险或关系变化”这条反应链；如果只是解释心情、强行总结，要指出。
4. 名字、称呼、代词是否错乱。该叫名字时叫名字，该用“婆婆”“老公”“我妈”等关系称呼时要自然准确。
5. 第一人称视角是否稳定。
6. 是否重复前文已交代的信息、重复表态、重复感叹。
7. 是否偏离场景细纲，是否出现因果不顺、人物反应不合理、承接突兀。
8. 对话是否太解释型、像总结，不像人物在说话。
9. 是否缺少口语感、活人感和网感，把都市言情写成了冷硬悬疑片或影视分镜。
10. 是否有多余写景或空泛铺垫，或沉迷门把手、材质、光线、声响、骨节等装饰性特写。
11. 比喻、意象、身体反应词是否过密或重复，例如连续出现“像什么一样”“心口发紧”“鼻尖发酸”“呼吸一滞”这类堆叠。
12. 是否把大纲里的“情绪点/泪点/虐点/钩子”等说明直接翻译成正文，导致文案感太重。
13. 是否擅自发明了细纲没有要求的关键证据、专业术语、侦探化操作或工具，导致剧情显得刻意。
14. 字数是否偏差太大。代码检测结果如下：
   - 目标字数：{target_words}
   - 实际有效字数：{actual_chars}
   - 偏差：{length_check.get("delta", 0)}
   - 判定：{length_check.get("status")}
   - 代码建议：{length_check.get("suggestion")}
15. 是否明显偏离了参考原文的语气底色。参考原文如果更顺口、更有吐槽感、更像活人讲事，而当前稿更冷、更硬、更像旁白，要明确指出。
16. 是否太正经、太端着、太像“作文”。如果语言不够亲近，没有聊天感、八卦感、网文感，要明确指出。
17. 女主是否有讨喜度、生命力、心机或值得被偏爱的魅力。如果女主只剩下受苦、解释、发愣和被动承受，也要指出。
18. 如果当前场景带有恋爱互动、偏爱关系、追妻火葬场或背叛余波，是否写出了甜度、偏爱感，或“失去女主”的痛感。
19. 是否出现了“像小说但不像人话”的作者腔套句，例如“像突然断了电”“面上没露怯”“空气凝固”“复杂情绪翻涌”“目光里压着某种情绪”。如果有，优先要求改成更直接的主观反应。

【全局设定】：
{public_context}

【前文内容】：
{context_paragraphs if context_paragraphs else "（无前文，这是首段）"}

【当前场景名】：
{scene_name}

【当前场景细纲】：
{scene_outline}

【本场景参考原文（用于校准语气，不是要求逐句一致）】：
{reference_excerpt if reference_excerpt else "（无参考原文）"}

【当前场景主情绪】：
{scene_emotion}

【当前场景关键要素】：
{json.dumps(elements, ensure_ascii=False, indent=2)}

【待检查正文】：
{scene_text}

请只返回一个合法 JSON：
{{
  "pass": true,
  "overall_score": 85,
  "summary": "一句话总结",
  "emotion_assessment": "情绪是否成立",
  "length_assessment": "对字数的判断",
  "issues": [
    {{
      "type": "AI味/情绪强度/称呼/逻辑/视角/字数/重复/写景/其它",
      "severity": "high/medium/low",
      "quote": "尽量引用原文，没有就写空字符串",
      "problem": "具体问题",
      "suggestion": "具体修改建议"
    }}
  ],
  "strengths": ["可保留的优点"],
  "rewrite_focus": ["按优先级列出具体可执行的修改动作"],
  "must_delete_or_shorten": ["如偏长或 AI 味重，直接指出该删什么；没有则空数组"]
}}
不要输出 Markdown，不要额外解释。
"""


def build_rewrite_prompt(
    public_context,
    context_paragraphs,
    scene_name,
    scene_outline,
    reference_excerpt,
    scene_emotion,
    target_words,
    scene_data,
    base_text,
    review_result,
    user_instruction="",
):
    review_summary = ""
    rewrite_focus = []
    must_delete = []
    if isinstance(review_result, dict):
        review_summary = review_result.get("summary", "")
        rewrite_focus = ensure_list(review_result.get("rewrite_focus"))
        must_delete = ensure_list(review_result.get("must_delete_or_shorten"))

    focus_text = "\n".join([f"- {item}" for item in rewrite_focus]) if rewrite_focus else "- 无"
    delete_text = "\n".join([f"- {item}" for item in must_delete]) if must_delete else "- 无"

    elements = extract_scene_elements(scene_data)
    elements_text = json.dumps(elements, ensure_ascii=False, indent=2) if elements else "{}"

    user_instruction_block = ""
    if user_instruction:
        user_instruction_block = f"\n【用户额外要求（优先级最高）】\n{user_instruction}\n"

    return f"""你现在要重写一个已经生成过的小说场景。
你的目标不是推翻重写，而是在保留有效信息的前提下，精准修复质检指出的问题，让文本更像成熟作者写的成稿。

【全局公共设定】：
{public_context}

【前文内容】：
{context_paragraphs if context_paragraphs else "（无前文，这是首段）"}

【场景名】：
{scene_name}

【场景细纲】：
{scene_outline}

【本场景参考原文（只学语气、节奏、吐槽感、对话感，不要照抄）】：
{reference_excerpt if reference_excerpt else "（无参考原文）"}

【场景主情绪】：
{scene_emotion}

【目标字数】：
{target_words}

【当前场景关键要素】：
{elements_text}

【上一版正文】：
{base_text}

【质检摘要】：
{review_summary}

【必须优先修正】：
{focus_text}

【必须删除或压缩】：
{delete_text}
{user_instruction_block}
【改稿原则】：
- 先删后补。先删掉解释腔、重复情绪、重复反应和堆砌修辞，再判断是否需要补动作或对话。
- 每段只保留一个最有效的情绪落点，不要让所有句子都处在高压状态。
- 情绪做强不是加形容词，而是把关键刺激写准、把人物反应写快、把动作或对白写出来。
- 关键节点至少完成一次明确外化：打断、回避、试探、嘴硬、沉默、失手、反问、决定中的一种，别只写“我很乱”。
- 允许在真正该炸的位置用短句、断句或突然收口，把刺感拎起来；但不要全段一直炸。
- 大纲里的情绪说明和看点只是幕后结构，不要把它们直接翻译成台词、旁白或总结句。
- 句子允许平实，允许短，允许留白。不要为了“有文学感”硬加比喻和意象。
- 若原文已有一句足够有力，就保留，不要为了重写而把它改得更花。
- 优先把文字拉回“都市言情第一人称”的自然语感，而不是“悬疑片分镜脚本”。
- 语言要有亲近感和聊天感，不要写得像作文、总结或道理输出。
- 可以保留一点口语、吐槽和网感，让人物像真人，不要让所有句子都冷、硬、紧。
- 少用作者替人物发言的抽象总结句。优先改成“我当下会怎么想、怎么损一句、怎么判断”的活句。
- 女主必须更讨喜一点。让她有脑子、有小心机、有被偏爱的价值，不要只剩苦情和被动。
- 如果当前场景涉及爱情线、暧昧、偏爱、追妻或背叛后余波，要补出甜度、拉扯感，或“失去她真的很亏”的体感。
- 对论坛、群聊、日常对白，要写出身份差异和真人杂音，不要整齐划一。
- 如果质检意见和参考原文的自然语感发生冲突，优先回到参考原文那种顺口、有人味的写法，再修正其它问题。

【硬性要求】：
1. 必须使用第一人称“我”视角。
2. 必须贴合场景细纲，不要跑偏。
3. 绝对不要出现“女主”“男主”等大纲代称。
4. 绝对不要输出修改说明，只输出正文。
5. 如果质检指出某些句子 AI 味重、过度用力、重复解释，就直接删或改，不要保留。
6. 如果字数偏长就压缩废话和重复，如果字数偏短就补足动作、对话与推进。
7. 行文克制，不要堆砌辞藻，不要写夸张失控的台词。
8. 整段最多允许一次轻微比喻；如果删掉比喻后更顺，就不要保留。
9. 优先消除重复的身体反应词、相近情绪词和“像什么一样”的句式。
10. 删掉不必要的电影化特写、装饰性音效和材质描写。
11. 若细纲没要求，不要额外添加录音、证物、专业检测术语、侦探式取证等机关。

请直接输出重写后的正文。
"""


def build_comparison_prompt(scene_name, scene_outline, reference_excerpt, scene_emotion, target_words, original_text, candidate_text):
    return f"""你是短篇小说改稿评审，只需要判断两个版本里哪一个更适合作为最终成稿。

评判标准按优先级排序：
1. 是否更自然、更像人写的，AI 味更轻。
2. 是否更贴合参考原文那种都市言情第一人称的口语感、吐槽感和可读性，而不是冷硬悬疑分镜腔。
3. 是否更贴合场景细纲，情绪更准，张力更有效，关键节点有没有写出清晰的反应链。
4. 是否称呼自然、逻辑顺、第一人称稳定。
5. 是否更克制，情绪密度更合理，不用力过猛，不靠空喊情绪，也不乱发明侦探机关。
6. 是否更适合目标字数。

【场景名】：
{scene_name}

【场景细纲】：
{scene_outline}

【本场景参考原文（用于判断哪版更接近原文语气）】：
{reference_excerpt if reference_excerpt else "（无参考原文）"}

【主情绪】：
{scene_emotion}

【目标字数】：
{target_words}

【A版：初版】：
{original_text}

【B版：重写版】：
{candidate_text}

请只返回一个合法 JSON：
{{
  "winner": "A/B/tie",
  "reason": "一句话说明为什么",
  "scores": {{
    "A": 78,
    "B": 84
  }},
  "better_points": ["胜出版本具体好在哪"],
  "worse_points": ["落败版本的主要问题"]
}}
不要输出 Markdown，不要补充其它说明。
"""


def merge_review_with_length(review_data, length_check):
    if not review_data or not isinstance(review_data, dict):
        review_data = {
            "pass": True,
            "overall_score": 70,
            "summary": "LLM 质检结果解析失败，仅保留代码级字数检查。",
            "emotion_assessment": "",
            "length_assessment": length_check.get("suggestion", ""),
            "issues": [],
            "strengths": [],
            "rewrite_focus": [],
            "must_delete_or_shorten": [],
        }

    review_data.setdefault("issues", [])
    review_data.setdefault("strengths", [])
    review_data.setdefault("rewrite_focus", [])
    review_data.setdefault("must_delete_or_shorten", [])

    review_data["code_length_check"] = length_check
    review_data["actual_chars"] = length_check.get("actual_chars", 0)

    if not length_check.get("pass", True):
        review_data["issues"].insert(
            0,
            {
                "type": "字数",
                "severity": "high",
                "quote": "",
                "problem": (
                    f"目标字数 {length_check.get('target_words')}，"
                    f"实际有效字数 {length_check.get('actual_chars')}，"
                    f"偏差 {length_check.get('delta')}。"
                ),
                "suggestion": length_check.get("suggestion", ""),
            }
        )
        review_data["rewrite_focus"].insert(0, length_check.get("suggestion", ""))

    review_focus = review_data["rewrite_focus"]
    if not any(isinstance(item, str) and "反应链" in item for item in review_focus):
        review_focus.append("检查关键节点是否具备“刺激 -> 反应 -> 动作/对白/决定 -> 新风险”的反应链；如果只有心理总结，没有当场动作，就把链条补出来。")
    if not any(isinstance(item, str) and "写虚" in item for item in review_focus):
        review_focus.append("检查情绪有没有写虚。该慌、该甜、该堵、该痛的地方，要落在一两个精准动作或对白上，不要只写笼统心情。")
    if not any(isinstance(item, str) and "情绪密度" in item for item in review_focus):
        review_focus.append("检查情绪密度是否失衡；如果整段句句都在拔高、句句都在痛感表达，请删掉一半解释句，只保留最有效的情绪落点。")
    if not any(isinstance(item, str) and "比喻" in item for item in review_focus):
        review_focus.append("检查比喻、意象和身体反应词是否重复；能改成平实动作或对白的地方，就不要继续用修辞硬顶。")
    if not any(isinstance(item, str) and "口语感" in item for item in review_focus):
        review_focus.append("检查是否缺少口语感、活人感和网感；如果像冷硬旁白或分镜脚本，改回更自然的都市言情第一人称。")
    if not any(isinstance(item, str) and "作文" in item for item in review_focus):
        review_focus.append("检查语言是否太正经、太端着、太像作文；把能改成聊天感、吐槽感、八卦感的句子改活。")
    if not any(isinstance(item, str) and "作者腔" in item for item in review_focus):
        review_focus.append("检查是否有“像小说但不像人话”的作者腔套句，如“像突然断了电”“没露怯”“复杂情绪翻涌”；有就改成更直接的主观反应。")
    if not any(isinstance(item, str) and "女主" in item and "讨喜" in item for item in review_focus):
        review_focus.append("检查女主是否足够讨喜、有脑子、有生命力；如果她只是在受苦和解释，就补一点心机、反应、可爱或值得偏爱的细节。")
    if not any(isinstance(item, str) and "甜度" in item for item in review_focus):
        review_focus.append("如果当前场景涉及感情推进、暧昧、偏爱或背叛后余波，检查甜度、拉扯感或后悔痛感是否成立；不成立就用细节补出来。")
    if not any(isinstance(item, str) and "侦探化" in item for item in review_focus):
        review_focus.append("检查是否擅自发明了侦探化操作、专业术语或关键证据；若非细纲要求，删掉这些显摆式设计。")

    review_data["pass"] = bool(review_data.get("pass")) and bool(length_check.get("pass", True))
    return review_data


def should_force_rewrite(review_data):
    if not isinstance(review_data, dict):
        return False, "no_review"

    issues = review_data.get("issues") or []
    high_issues = [item for item in issues if isinstance(item, dict) and item.get("severity") == "high"]
    severe_types = {str(item.get("type", "")) for item in high_issues}
    score = int(review_data.get("overall_score", 0) or 0)
    length_check = review_data.get("code_length_check") or {}
    length_failed = not bool(length_check.get("pass", True))

    critical_type_keywords = ["逻辑", "视角", "称呼", "情绪强度", "AI味", "字数"]
    has_critical_issue = any(
        any(keyword in issue_type for keyword in critical_type_keywords)
        for issue_type in severe_types
    )

    if score < 75:
        return True, "low_score"
    if has_critical_issue:
        return True, "critical_issue"
    if length_failed and score < 85:
        return True, "length_and_quality"
    return False, "good_enough"


def quick_review_scene(scene_name, scene_outline, scene_emotion, target_words, scene_text):
    actual_chars = count_effective_chars(scene_text)
    review_data, raw_text = call_json_response(
        build_quick_review_prompt(
            scene_name=scene_name,
            scene_outline=scene_outline,
            scene_emotion=scene_emotion,
            target_words=target_words,
            actual_chars=actual_chars,
            scene_text=scene_text,
        ),
        system_prompt="你是速度优先的小说快审助手。必须输出 JSON。",
        retries=QUICK_REVIEW_RETRIES,
    )

    if not isinstance(review_data, dict):
        review_data = {
            "score": 70,
            "verdict": "risky",
            "reason": "快审结果解析失败，转入完整质检。",
            "risk_tags": ["快审失败"],
        }
    review_data["raw_response"] = raw_text
    review_data["actual_chars"] = actual_chars
    return review_data


def should_run_full_review(quick_review, target_words, actual_chars):
    score = int((quick_review or {}).get("score", 0) or 0)
    verdict = str((quick_review or {}).get("verdict", "risky"))
    risk_tags = [str(item) for item in ensure_list((quick_review or {}).get("risk_tags"))]
    length_check = build_length_check(target_words, actual_chars)

    critical_type_keywords = ["逻辑", "视角", "称呼", "情绪", "AI味"]
    has_critical_risk = any(
        any(keyword in tag for keyword in critical_type_keywords)
        for tag in risk_tags
    )

    if score >= 88 and verdict in ("good", "enough") and length_check.get("pass", True):
        return False, "quick_pass"
    if score >= 82 and verdict == "good" and not has_critical_risk:
        return False, "quick_good_enough"
    if has_critical_risk:
        return True, "quick_critical_risk"
    if not length_check.get("pass", True):
        return True, "quick_length_risk"
    if score < 82 or verdict in ("risky", "bad"):
        return True, "quick_low_score"
    return False, "quick_pass"


def review_scene(
    public_context,
    context_paragraphs,
    scene_name,
    scene_outline,
    reference_excerpt,
    scene_emotion,
    target_words,
    scene_data,
    scene_text,
):
    actual_chars = count_effective_chars(scene_text)
    length_check = build_length_check(target_words, actual_chars)
    prompt = build_review_prompt(
        public_context=public_context,
        context_paragraphs=context_paragraphs,
        scene_name=scene_name,
        scene_outline=scene_outline,
        reference_excerpt=reference_excerpt,
        scene_emotion=scene_emotion,
        target_words=target_words,
        actual_chars=actual_chars,
        length_check=length_check,
        scene_data=scene_data,
        scene_text=scene_text,
    )
    review_data, raw_text = call_json_response(
        prompt,
        system_prompt="你是一个严苛、具体、可执行的小说质检编辑。必须输出 JSON。",
        retries=REVIEW_RETRIES,
    )
    merged = merge_review_with_length(review_data, length_check)
    merged["raw_response"] = raw_text
    return merged


def rewrite_scene(
    public_context,
    context_paragraphs,
    scene_name,
    scene_outline,
    reference_excerpt,
    scene_emotion,
    target_words,
    scene_data,
    base_text,
    review_result,
    user_instruction="",
):
    rewrite_prompt = build_rewrite_prompt(
        public_context=public_context,
        context_paragraphs=context_paragraphs,
        scene_name=scene_name,
        scene_outline=scene_outline,
        reference_excerpt=reference_excerpt,
        scene_emotion=scene_emotion,
        target_words=target_words,
        scene_data=scene_data,
        base_text=base_text,
        review_result=review_result,
        user_instruction=user_instruction,
    )

    for _ in range(REWRITE_RETRIES):
        rewrite_text = call_dashscope_api(rewrite_prompt, system_prompt=REWRITE_SYSTEM_PROMPT)
        rewrite_text = normalize_scene_text(rewrite_text)
        if rewrite_text:
            return rewrite_text
    return None


def compare_versions(scene_name, scene_outline, reference_excerpt, scene_emotion, target_words, original_text, candidate_text):
    comparison, raw_text = call_json_response(
        build_comparison_prompt(
            scene_name=scene_name,
            scene_outline=scene_outline,
            reference_excerpt=reference_excerpt,
            scene_emotion=scene_emotion,
            target_words=target_words,
            original_text=original_text,
            candidate_text=candidate_text,
        ),
        system_prompt="你是公正的小说改稿评审。必须输出 JSON。",
        retries=COMPARISON_RETRIES,
    )

    if not comparison or not isinstance(comparison, dict):
        comparison = {
            "winner": "tie",
            "reason": "版本对比结果解析失败，默认平局。",
            "scores": {"A": 0, "B": 0},
            "better_points": [],
            "worse_points": [],
        }
    comparison["raw_response"] = raw_text
    return comparison


def check_and_rewrite(
    scene_text,
    scene_name,
    target_words,
    scene_outline,
    scene_emotion,
    scene_data,
    public_context,
    context_paragraphs="",
    user_instruction="",
    reference_excerpt="",
):
    initial_text = normalize_scene_text(scene_text)
    attempts = []
    timing = {
        "quick_review_seconds": 0.0,
        "full_review_seconds": 0.0,
        "rewrite_seconds": 0.0,
        "comparison_seconds": 0.0,
    }

    quick_started_at = time.perf_counter()
    quick_review = quick_review_scene(
        scene_name=scene_name,
        scene_outline=scene_outline,
        scene_emotion=scene_emotion,
        target_words=target_words,
        scene_text=initial_text,
    )
    timing["quick_review_seconds"] = time.perf_counter() - quick_started_at
    actual_chars = quick_review.get("actual_chars", count_effective_chars(initial_text))
    need_full_review, quick_decision = should_run_full_review(quick_review, target_words, actual_chars)

    initial_review = None
    if need_full_review:
        full_started_at = time.perf_counter()
        initial_review = review_scene(
            public_context=public_context,
            context_paragraphs=context_paragraphs,
            scene_name=scene_name,
            scene_outline=scene_outline,
            reference_excerpt=reference_excerpt,
            scene_emotion=scene_emotion,
            target_words=target_words,
            scene_data=scene_data,
            scene_text=initial_text,
        )
        timing["full_review_seconds"] = time.perf_counter() - full_started_at

    attempts.append(
        {
            "version": "initial",
            "text": initial_text,
            "quick_review": quick_review,
            "review": initial_review,
        }
    )

    if not need_full_review:
        return initial_text, {
            "selected_source": "initial",
            "quick_review": quick_review,
            "rewrite_decision": quick_decision,
            "timing": timing,
            "attempts": attempts,
        }

    force_rewrite, rewrite_reason = should_force_rewrite(initial_review)
    if initial_review.get("pass") or not force_rewrite:
        return initial_text, {
            "selected_source": "initial",
            "quick_review": quick_review,
            "initial_review": initial_review,
            "rewrite_decision": rewrite_reason,
            "timing": timing,
            "attempts": attempts,
        }

    current_base_text = initial_text
    current_review = initial_review
    last_comparison = None

    for rewrite_round in range(1, MAX_REWRITE_ATTEMPTS + 1):
        rewrite_started_at = time.perf_counter()
        rewrite_text = rewrite_scene(
            public_context=public_context,
            context_paragraphs=context_paragraphs,
            scene_name=scene_name,
            scene_outline=scene_outline,
            reference_excerpt=reference_excerpt,
            scene_emotion=scene_emotion,
            target_words=target_words,
            scene_data=scene_data,
            base_text=current_base_text,
            review_result=current_review,
            user_instruction=user_instruction,
        )
        timing["rewrite_seconds"] += time.perf_counter() - rewrite_started_at

        if not rewrite_text:
            break

        review_started_at = time.perf_counter()
        rewrite_review = review_scene(
            public_context=public_context,
            context_paragraphs=context_paragraphs,
            scene_name=scene_name,
            scene_outline=scene_outline,
            reference_excerpt=reference_excerpt,
            scene_emotion=scene_emotion,
            target_words=target_words,
            scene_data=scene_data,
            scene_text=rewrite_text,
        )
        timing["full_review_seconds"] += time.perf_counter() - review_started_at
        comparison_started_at = time.perf_counter()
        comparison = compare_versions(
            scene_name=scene_name,
            scene_outline=scene_outline,
            reference_excerpt=reference_excerpt,
            scene_emotion=scene_emotion,
            target_words=target_words,
            original_text=initial_text,
            candidate_text=rewrite_text,
        )
        timing["comparison_seconds"] += time.perf_counter() - comparison_started_at
        last_comparison = comparison

        attempts.append(
            {
                "version": f"rewrite_{rewrite_round}",
                "text": rewrite_text,
                "review": rewrite_review,
                "comparison_to_initial": comparison,
            }
        )

        if comparison.get("winner") == "B" and rewrite_review.get("pass"):
            return rewrite_text, {
                "selected_source": f"rewrite_{rewrite_round}",
                "quick_review": quick_review,
                "initial_review": initial_review,
                "final_review": rewrite_review,
                "final_comparison": comparison,
                "rewrite_decision": rewrite_reason,
                "timing": timing,
                "attempts": attempts,
            }

        if rewrite_round < MAX_REWRITE_ATTEMPTS and comparison.get("winner") == "B":
            current_base_text = rewrite_text
            current_review = rewrite_review

    return initial_text, {
        "selected_source": "initial_after_rewrite_fallback",
        "quick_review": quick_review,
        "initial_review": initial_review,
        "final_review": initial_review,
        "final_comparison": last_comparison,
        "rewrite_decision": rewrite_reason,
        "timing": timing,
        "attempts": attempts,
    }
