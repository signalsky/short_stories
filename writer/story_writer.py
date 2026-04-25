# -*- coding: utf-8 -*-
import json
import os
import re
import time
from utils import call_dashscope_api, clean_and_parse_json
from story_scene_checker import check_and_rewrite

def compress_prompt_hint(text, max_len=80):
    if not isinstance(text, str):
        return text
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_len:
        return normalized

    parts = re.split(r"[；;。！？\n]", normalized)
    selected = []
    current_len = 0
    for part in parts:
        part = part.strip(" ，、；：-")
        if not part:
            continue
        if selected and current_len + len(part) > max_len:
            break
        selected.append(part)
        current_len += len(part)
        if len(selected) >= 2:
            break

    compressed = "；".join(selected) if selected else normalized[:max_len]
    return compressed[:max_len].rstrip("，、；： ")


def build_style_guardrails():
    return """【文风红线与质量要求】：
- 质量优先，不要追求夸张刺激感，更不要为了像“爆款网文”而过度表演。
- 克制不等于发虚。该炸的节点要炸进去，但只炸在真正该炸的一两下；靠刺激升级和人物反应提强度，不靠堆形容词。
- 语言要有亲近感，像在跟读者聊天、讲八卦、说自己的事，不能端着，更不能写出“作文感”“总结感”“获奖感言感”。
- 少写那种“看起来像小说、其实不像人话”的作者腔套句，比如“像突然断了电”“面上没露怯”“震惊里压着发慌的戒备”“空气凝固了几秒”“眼底翻涌着复杂情绪”。能改成更直接的主观反应，就改直接。
- 每个场景只允许一个主要情绪峰值，其余情绪点到即止，要有轻重缓急和透气口。
- 叙述以白描、动作、对话为主，句子要自然干净，允许平实，不必句句有力。
- 比喻和意象要极少使用；整段最多点到一次，能不用就不用，禁止连续比喻、排比、堆叠形容词和成语。
- 不要重复同类反应词和意象，例如反复写发抖、窒息、刺痛、发紧、酸涩、像什么一样。
- 大纲里的“情绪点/爽点/虐点/钩子”只是结构提示，不是可直接照抄进正文的文案；请转化成具体事件。
- 如果一个动作、对话已经足够成立，就不要再追加解释性心理描写；宁可少写一句，也不要把情绪写满。
- 第一人称必须像活人在讲自己的事，允许自然的吐槽、自嘲和小心思，不要写成冷硬悬疑片旁白。
- 女主不能只是“受害”和“解释”，她要有招人偏爱的生命力。可以有心机、有盘算、有反击、有小得意，也可以柔软、可爱、讨喜，但不能木、苦、寡淡。
- 要有网文梗感和阅读趣味，允许一点俏皮、损人、内心吐槽、恋爱拉扯，不要把都市狗血文写得过于一本正经。
- 节奏要顺口，长短句穿插，避免连续很多“短句+重细节+重音效”的分镜式写法。
- 关系推进优先于镜头调度，重点写人和人的互动，不要沉迷门把手、材质、声响、冷光、骨节这类装饰性特写。
- 除非细纲明确要求，否则不要擅自发明关键证据、侦探式工具或专业术语，例如录音、快递单、检测术语、取证机关等。
- 论坛评论、群聊和日常对白要像真人，会有网感、情绪和身份差异，不要都写成同一种冷冰冰的腔调。
- 关键节点优先写成“刺激落下 -> 我立刻有反应 -> 我说话/动作/决定 -> 关系或风险发生变化”，不要只停在“我很震惊”“我心里很乱”。
- 如果当前剧情有爱情线，要写出恋爱甜度、拉扯感和偏爱感；如果是男主背叛或追妻题材，要让后悔感落在“女主值得被爱、失去她很痛”上，而不是只会空喊后悔。"""


def trim_reference_excerpt(text, max_len=1200):
    if not isinstance(text, str):
        return ""
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len].rstrip() + "\n……"


def build_elements_instruction(scene_data):
    if not isinstance(scene_data, dict):
        return ""

    compact_items = []
    for el_name in ["爽点", "钩子", "泪点", "虐点"]:
        el_val = scene_data.get(el_name)
        if isinstance(el_val, list):
            first_valid = next((item for item in el_val if item and item != "无"), "")
        else:
            first_valid = el_val if isinstance(el_val, str) else ""

        if first_valid and first_valid not in ("无", "[]"):
            compact_items.append(f"- {el_name}：{compress_prompt_hint(first_valid, max_len=42)}")

    if not compact_items:
        return ""

    compact_items = compact_items[:3]
    compact_text = "\n   ".join(compact_items)
    return (
        "12. 【本场景看点倾向】\n"
        "   以下只是幕后提醒，帮助你判断这段更该突出什么。不要把这些提示直接翻译成旁白、总结句或文案腔，通常抓住 1 个主打点即可，其余轻触即止：\n"
        f"   {compact_text}\n"
    )


def build_emotion_progress_instruction(scene_data, scene_emotion):
    progress = []
    if isinstance(scene_data, dict):
        raw_progress = scene_data.get("情绪推进")
        if isinstance(raw_progress, list):
            progress = [compress_prompt_hint(item, max_len=34) for item in raw_progress if item]

    if progress:
        progress_text = "\n   ".join([f"- {item}" for item in progress[:4]])
        return (
            "13. 【本场景情绪推进台阶】\n"
            "   请尽量按顺序把这些台阶写出来，让情绪通过事件一级级顶上去，而不是直接口头宣布人物很崩溃、很心动、很痛：\n"
            f"   {progress_text}\n"
        )

    fallback_steps = [
        f"- 先让刺激真正落到我身上：{compress_prompt_hint(scene_emotion, max_len=34)}",
        "- 紧接着给出我的第一反应，优先用动作、卡壳、嘴硬、试探、失手或打断",
        "- 然后让我做出一句话、一个动作或一个决定，把关系往前推",
        "- 结尾留一个新风险、新误会、新期待或新拉扯，不要平着收",
    ]
    fallback_text = "\n   ".join(fallback_steps)
    return (
        "13. 【本场景情绪推进台阶】\n"
        "   如果细纲没有单列步骤，也要至少补齐下面这条反应链：\n"
        f"   {fallback_text}\n"
    )


def write_story(json_path, target_scene_index=None, context_level=2, user_instruction=""):
    print(f"Loading input JSON: {json_path}")
    
    # 1. 加载提取好的小说大纲数据
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            story_data = json.load(f)
    except Exception as e:
        print(f"Error reading input JSON: {e}")
        return
        
    book_title = story_data.get("书名", "未命名小说")
    core_characters = story_data.get("核心人物", [])
    character_personalities = story_data.get("人物人设", story_data.get("人物性格", {}))
    storyline = story_data.get("故事线提取", {})
    emotions = story_data.get("情绪点提取", {})
    scenes_dict = story_data.get("场景切分与建议", {})
    
    if not core_characters or not scenes_dict:
        print("Missing required data (core_characters or scenes_dict) in input JSON.")
        return
        
    print(f"Starting to write: {book_title}")
    
    # 确定输出 JSON 文件路径
    safe_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
    
    # 获取项目根目录 (writer 目录)
    # 因为目前脚本在 writer 目录下，如果传入的 json_path 也是绝对路径，我们需要找到统一的 base_dir
    # 这里直接使用 writer 目录作为基准来构建 '重写' 文件夹路径
    writer_dir = os.path.dirname(os.path.abspath(__file__))
    rewrite_dir = os.path.join(writer_dir, "重写")
    
    # 确保 '重写' 目录存在
    if not os.path.exists(rewrite_dir):
        os.makedirs(rewrite_dir)
        
    output_json_path = os.path.join(rewrite_dir, f"{safe_title}_进度.json")
    
    # 尝试加载已有进度
    progress_data = {}
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            print(f"Loaded existing progress from {output_json_path}")
        except Exception as e:
            print(f"Failed to load existing progress: {e}")
            
    # 记录原始大纲文件名，方便前端进行续写时能找到源文件
    progress_data["source_outline_filename"] = os.path.basename(json_path)
    
    # 记录全局用户指令，方便后续续写时保持一致
    if user_instruction:
        progress_data["global_instruction"] = user_instruction
    elif "global_instruction" in progress_data:
        # 如果当前没有传指令，但之前保存过，则恢复
        user_instruction = progress_data["global_instruction"]
    
    # 3. 第一次 LLM 调用：为角色取名，并将大纲/情绪点中的代称替换为真实姓名
    print("\n--- Step 1: Assigning real names to characters ---")
    
    if "name_map" in progress_data and "rewritten_outlines" in progress_data and "rewritten_emotions" in progress_data:
        name_map = progress_data["name_map"]
        rewritten_outlines = progress_data["rewritten_outlines"]
        rewritten_emotions = progress_data["rewritten_emotions"]
        print("Using cached names, outlines, and emotions.")
    else:
        # 提取所有的旧细纲
        original_outlines = {k: v.get("剧情细纲", "") for k, v in scenes_dict.items() if isinstance(v, dict)}
        
        # 提取原情绪点
        original_emotions = emotions if isinstance(emotions, list) else []
        
        naming_prompt = f'''你是一个专业的小说作者。我有一篇小说的核心人物代称列表。

【任务一：取名】
请根据这些代称，为他们每个人取一个符合该小说类型风格的真实姓名。
核心人物列表：{json.dumps(core_characters, ensure_ascii=False)}

【任务二：替换剧情细纲中的代称】
请将以下【原剧情细纲】中出现的所有角色代称，全部替换为你刚刚为他们取好的真实姓名。
细纲的剧情内容绝对不能有任何修改，仅仅替换名字！

【任务三：替换情绪点中的代称】
请将以下【原情绪点列表】中出现的所有角色代称，全部替换为你刚刚为他们取好的真实姓名。
情绪点的内容绝对不能有任何修改，仅仅替换名字！

【输出要求】：
请务必只返回一个合法的 JSON 字典，包含 "角色姓名"、"重构细纲" 和 "重构情绪点" 三个 Key。不要返回任何其他内容或 Markdown 标记，也不要加上任何前缀。你的回答必须能够直接被 json.loads 解析！

示例：
{{
  "角色姓名": {{
    "女主": "苏婉",
    "男主": "顾寒城",
    "女主生母": "林雅"
  }},
  "重构细纲": {{
    "原场景名1": "...",
    "原场景名2": "..."
  }},
  "重构情绪点": [
  ]
}}

【原剧情细纲】：
{json.dumps(original_outlines, ensure_ascii=False, indent=2)}

【原情绪点列表】：
{json.dumps(original_emotions, ensure_ascii=False, indent=2)}
'''
        step1_data = None
        for attempt in range(3):
            print(f"Attempt {attempt + 1}/3 to generate names and outlines...")
            name_response = call_dashscope_api(naming_prompt, system_prompt="你是一个专业的小说作者。必须且只能输出合法的 JSON 数据。")
            step1_data = clean_and_parse_json(name_response)
            if step1_data and isinstance(step1_data, dict):
                break
            print("Failed to parse names JSON. Retrying...")
            
        name_map = {}
        rewritten_outlines = {}
        rewritten_emotions = []
        
        if not step1_data or not isinstance(step1_data, dict):
            print("Failed to get names from LLM after 3 attempts, using fallback.")
            name_map = {role: f"[{role}的名字]" for role in core_characters}
            rewritten_outlines = original_outlines
            rewritten_emotions = original_emotions
        else:
            name_map = step1_data.get("角色姓名", {})
            
            # 根据原大纲的场景顺序，重新排序生成的 rewritten_outlines
            raw_rewritten = step1_data.get("重构细纲", {})
            rewritten_outlines = {k: raw_rewritten.get(k, original_outlines.get(k, "")) for k in original_outlines.keys()}
            
            # 获取重构后的情绪点
            rewritten_emotions = step1_data.get("重构情绪点", original_emotions)
            
            print(f"Successfully generated names and replaced character names in outlines and emotions.")
        
        # 缓存第一步结果
        progress_data["name_map"] = name_map
        progress_data["rewritten_outlines"] = rewritten_outlines
        progress_data["rewritten_emotions"] = rewritten_emotions
        progress_data["generated_paragraphs"] = progress_data.get("generated_paragraphs", [])
        
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
    # 准备公共数据字符串，用于传递给后续的每次写作请求
    public_context = f'''
【小说书名】：{book_title}

【角色姓名与人设对照表】：
'''
    for role in core_characters:
        name = name_map.get(role, role)
        personality = character_personalities.get(role, "（未提供人设描述）")
        public_context += f"- {role}：姓名【{name}】，人设：【{personality}】\n"

    public_context += f'''
【完整故事线】：
{json.dumps(storyline, ensure_ascii=False, indent=2)}
'''

    # 添加结构优化建议
    structure_advice = story_data.get("结构优化建议", "")
    if structure_advice:
        public_context += f'''
【小说全局结构优化方向】：
{structure_advice}
'''

    public_context += f'''
【全局情绪点列表】：
'''
    if rewritten_emotions:
        for emotion_point in rewritten_emotions:
            public_context += f"- {emotion_point}\n"
    elif isinstance(emotions, list):
        for emotion_point in emotions:
            public_context += f"- {emotion_point}\n"
    elif isinstance(emotions, dict):
        # 兼容老格式
        for role, role_data in emotions.items():
            if isinstance(role_data, dict) and "核心主线" in role_data:
                public_context += f"- {name_map.get(role, role)} ({role}): {role_data['核心主线']}\n"
            
    # 4. 循环调用大模型，逐段生成小说
    print("\n--- Step 2: Writing scenes one by one ---")
    
    # 恢复已有段落
    generated_paragraphs = progress_data.get("generated_paragraphs", [])
    
    for i, (scene_name, scene_data) in enumerate(scenes_dict.items()):
        # 如果传入了 target_scene_index 且当前索引不匹配，则跳过生成
        # target_scene_index 是基于 1 的索引，i 是基于 0 的索引
        if target_scene_index is not None and (i + 1) != target_scene_index:
            continue
            
        # 如果没有传入 target_scene_index，并且当前段落已经生成过且不是待生成状态，则跳过
        if target_scene_index is None and i < len(generated_paragraphs):
            # 只有当段落真实存在且不是失败/占位符时才跳过
            if not generated_paragraphs[i].startswith("【待生成") and not generated_paragraphs[i].startswith("【生成失败"):
                print(f"Skipping Scene {i+1}/{len(scenes_dict)}: {scene_name} (Already generated)")
                continue
        # 处理旧版本 JSON（只有数字）和新版本 JSON（字典包含目标字数和细纲）的兼容
        target_words = 0
        scene_outline = "（请根据故事线自行发挥该场景的具体剧情）"
        scene_rewrite_hint = ""
        reference_excerpt = ""
        
        if isinstance(scene_data, dict):
            target_words = scene_data.get("目标字数", 0)
            scene_outline = scene_data.get("剧情细纲", scene_outline)
            scene_rewrite_hint = rewritten_outlines.get(scene_name, "")
            if scene_rewrite_hint == scene_outline:
                scene_rewrite_hint = ""
            reference_excerpt = trim_reference_excerpt(scene_data.get("参考原文", ""))
        else:
            target_words = int(scene_data)
            
        print(f"\nWriting Scene {i+1}/{len(scenes_dict)}: {scene_name} (Target words: {target_words})")
        
        # 获取前文内容
        context_paragraphs = ""
        # 默认参考前文，但如果是在单段重写模式下，通过 context_level 控制参考段数
        # target_scene_index 是基于 1 的，所以不为 None 代表单段重写
        actual_context_level = context_level if target_scene_index is not None else 2
        
        if i > 0 and actual_context_level > 0:
            start_idx = max(0, i - actual_context_level)
            # 过滤掉待生成的占位符
            valid_paragraphs = [p for p in generated_paragraphs[start_idx:i] if p != "【待生成】"]
            context_paragraphs = "\n\n".join(valid_paragraphs)
        
        # 查找该场景对应的情绪
        scene_emotion = "（自由发挥符合剧情的细腻情绪）"
        
        # 首先尝试从新版 JSON 的场景细纲字典中直接读取情绪点
        if isinstance(scene_data, dict) and "情绪点" in scene_data and scene_data["情绪点"]:
            scene_emotion = scene_data["情绪点"]
        elif rewritten_emotions:
            # 如果存在重构后的情绪点（全局列表），尝试模糊查找
            for ep in rewritten_emotions:
                if isinstance(ep, str) and (scene_name in ep or ep in scene_name):
                    scene_emotion = ep
                    break
        elif isinstance(emotions, list):
            # 兼容老格式：原始的全局列表情绪点
            for ep in emotions:
                if isinstance(ep, str) and (scene_name in ep or ep in scene_name):
                    scene_emotion = ep
                    break
        elif isinstance(emotions, dict):
            # 兼容老格式：从女主字典里找
            female_emotions = emotions.get("女主", {}).get("关键场景情绪", {})
            for k, v in female_emotions.items():
                if scene_name in k or k in scene_name:
                    scene_emotion = v
                    break
        
        # 构建当前段落的写作 prompt
        intro_instruction = ""
        if i == 0:
            intro_instruction = "这是小说的开篇，请尽快交代核心背景、人物关系和眼前冲突。可以从一句自然的自述或一段带信息量的对话切入，但不要喊口号，不要故作抓马。"
        else:
            intro_instruction = "请紧接前文剧情自然往下写，绝对不要再次重复自我介绍（如“我叫XXX”）或重新交代背景！"
            
        # 如果用户提供了重写的额外要求，加粗强调
        user_instruction_block = ""
        if user_instruction:
            user_instruction_block = f"\n【用户特别修改要求（优先级最高！）】：\n{user_instruction}\n"

        elements_instruction = build_elements_instruction(scene_data)
        emotion_progress_instruction = build_emotion_progress_instruction(scene_data, scene_emotion)

        condensed_scene_emotion = compress_prompt_hint(scene_emotion, max_len=90)
        style_guardrails = build_style_guardrails()
        write_prompt = f'''你正在创作一篇短篇小说，现在需要撰写其中的一个场景片段。
你的任务不是写“用力很猛的网文”，而是写一个可读性高、情绪准确、语言干净的小说场景。
写作核心是【用事件体现情绪，行文克制，语言不堆砌】。必须以事件描写、动作描写和有效对话为主，少写解释型心理描写。情绪要藏在事件推进里，而不是靠密集修辞去顶。

{style_guardrails}

【优先学习的成稿优点】：
- 先追求“好读、顺口、能一口气看下去”，再追求所谓高级感。
- 女主内心要聪明、有反应、有人味，能自然带出一点吐槽感和判断，不要一直绷着。
- 语言要亲近，像在跟读者聊天，不要像写作文、写总结、写命题范文。
- 女主要有让人想偏爱的点。可以精明，可以会拿捏，可以嘴甜心黑一点，也可以明媚可爱，但总之不能寡、钝、苦到底。
- 要有网文梗感和轻微的俏皮，不要过于正经；能用一句自然吐槽写活的地方，就不要上价值。
- 优先写“我脑子里会怎么冒出这句话”，而不是“作者觉得这句很像小说”。多用直接判断句、短吐槽、小念头，少用抽象总结句。
- 对话要像都市言情里的真人交流，人物之间有试探、有火花、有生活感，不是人人都阴沉克制。
- 论坛、群聊内容要有真实网友的杂音、八卦感和区分度，能推动阅读趣味。
- 每一小段都要推动信息、关系或悬念中的至少一项，避免只靠气氛和特写拖行文。
- 关键位不要温吞。该慌时要有一秒失手，该甜时要有一下心动，该堵时要有一句怼回去；强度来自反应够快、动作够准。
- 可以写得通俗，但不能写得油腻；可以写得紧张，但不要写成刑侦、惊悚或文艺片腔调。
- 如果当前场景含恋爱互动，要让甜度可感，写出被偏爱、被哄、被在意的细节；如果是背叛/追妻路数，要让女主的好和稀缺被看见，让“失去她”这件事本身有痛感。

【全局公共设定（不可偏离）】：
{public_context}

【前文内容（为了保持连贯，这是前文内容，请接着往下写）】：
{context_paragraphs if context_paragraphs else "（这是小说的开头第一个场景，请直接开始创作）"}
{user_instruction_block}
------------------------
【本次写作任务要求】：
1. 必须使用【第一人称（“我”）】视角进行创作，代入女主的视角！
2. 不要空写景和无效氛围渲染；环境只在推动动作、关系或情绪时顺手带一句即可。
3. {intro_instruction}
4. 本次需要撰写的场景是：【{scene_name}】
5. 【本场景原始剧情骨架（这是你必须完成的事件顺序）】：{scene_outline}
6. 【本场景结构微调建议（只吸收有用的一两处，不要被它牵着跑）】：{scene_rewrite_hint if scene_rewrite_hint else "（无）"}
7. 【本场景参考原文（只学习语气、节奏、吐槽感、对话感和评论区写法，严禁照抄句子）】：
{reference_excerpt if reference_excerpt else "（无参考原文，按全局要求写）"}
8. 本次场景必须体现的核心情绪是：【{condensed_scene_emotion}】。注意只保留这段最核心的情绪落点，情绪要融入具体事件、对话和动作中，不要大段解释。
9. 目标字数要求：请控制在【{target_words}字】左右。宁可略短一点，也不要为了凑字数重复解释、反复渲染情绪、堆砌比喻或添加无效动作。
10. 人物称呼要求：请根据第一人称视角，在适当的地方使用更自然、符合身份的称呼（如“婆婆”、“老公”、“我妈”等），**不要总是生硬地直呼其名**。但是绝对不要出现“女主”、“男主”这种大纲代称，称呼女主自己时用“我”。
11. 不要把普通家庭伦理冲突写成“冷硬悬疑大片”。除非细纲明确要求，否则不要加入额外证物、专业名词、侦探动作或电影化调度。
{elements_instruction}
{emotion_progress_instruction}
14. 如果“结构微调建议”和“参考原文”的自然写法发生冲突，优先保留参考原文那种顺口、有人味、像真人在讲事的路数，再吸收建议中真正有用的一小处。
15. 少写抽象情绪总结和作者腔套话。比起“她目光复杂、空气凝固、我没露怯”，更优先写“她盯着我不说话，我心里咯噔一下，但还是先笑着叫人”这种活句。
16. 真到爆点时，不要只写“我心里一沉”“我很乱”。请把那一下失衡落在可见动作上，比如卡壳、打断、回避、嘴硬、反问、装镇定、顺手掩饰、故意试探。

请直接输出小说正文内容，不要包含任何多余的开头问候、分析说明或字数统计！直接开始写正文！
'''
        
        scene_text = None
        write_started_at = time.perf_counter()
        for attempt in range(3):
            print(f"Attempt {attempt + 1}/3 to generate scene...")
            scene_text = call_dashscope_api(write_prompt, system_prompt="你是一个成熟的网文作者，优先追求文本质量、节奏和自然度。你的文字亲近、顺口、有聊天感，不会写成作文、总结或命题范文。你擅长用白描、动作和对话承载情绪，避免解释腔、避免华丽辞藻堆砌、避免连环比喻、避免重复意象。你知道真正有力度的情绪来自克制、停顿和留白，但克制不等于发虚，该炸的节点要能一下扎进去。你尤其讨厌那种看起来像小说、其实不像人脑内话的作者腔套句，比如“像突然断了电”“没露怯”“复杂情绪翻涌”。你会优先把句子写成主观、直接、带一点吐槽的小念头，并把强情绪落成可见反应和动作。你笔下的女主有脑子、有生命力、值得被爱，不是干瘪的受苦工具人。你会保留网文该有的梗感、甜度和拉扯感，把'泪点'、'虐点'、'爽点'和'钩子'当作结构提示，自然嵌入情节，不会把它们写成标签化文案。")
            if scene_text:
                break
            print("Generation failed. Retrying...")
        write_elapsed = time.perf_counter() - write_started_at

        if scene_text:
            # 清理可能的 markdown 标记
            scene_text = re.sub(r'```[a-zA-Z]*\n', '', scene_text)
            scene_text = re.sub(r'```', '', scene_text)
            scene_text = scene_text.strip()
            check_started_at = time.perf_counter()
            scene_text, review_record = check_and_rewrite(
                scene_text=scene_text,
                scene_name=scene_name,
                target_words=target_words,
                scene_outline=scene_outline,
                scene_emotion=scene_emotion,
                scene_data=scene_data,
                public_context=public_context,
                context_paragraphs=context_paragraphs,
                user_instruction=user_instruction,
                reference_excerpt=reference_excerpt,
            )
            check_elapsed = time.perf_counter() - check_started_at
            timing = review_record.get("timing", {}) if isinstance(review_record, dict) else {}
            quick_seconds = float(timing.get("quick_review_seconds", 0.0) or 0.0)
            full_seconds = float(timing.get("full_review_seconds", 0.0) or 0.0)
            rewrite_seconds = float(timing.get("rewrite_seconds", 0.0) or 0.0)
            comparison_seconds = float(timing.get("comparison_seconds", 0.0) or 0.0)
            rewrite_decision = review_record.get("rewrite_decision", "unknown") if isinstance(review_record, dict) else "unknown"
            selected_source = review_record.get("selected_source", "unknown") if isinstance(review_record, dict) else "unknown"
            print(
                "Timing -> "
                f"write: {write_elapsed:.1f}s, "
                f"check_total: {check_elapsed:.1f}s, "
                f"quick_check: {quick_seconds:.1f}s, "
                f"full_check: {full_seconds:.1f}s, "
                f"rewrite: {rewrite_seconds:.1f}s, "
                f"compare: {comparison_seconds:.1f}s, "
                f"decision: {rewrite_decision}, "
                f"source: {selected_source}"
            )
            
            # 处理已有段落列表的长度，确保能够正确插入/替换当前场景
            if len(generated_paragraphs) > i:
                generated_paragraphs[i] = scene_text
            else:
                # 如果跳过了某些段落，用占位符补齐
                while len(generated_paragraphs) < i:
                    generated_paragraphs.append("【待生成】")
                generated_paragraphs.append(scene_text)
                
            progress_data["generated_paragraphs"] = generated_paragraphs
            
            # 写一段存一段，更新进度 JSON
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
                
            if target_scene_index is not None:
                # 单场景重写时，也要同步更新 txt 文件，这样前端才能看到最新的文本
                try:
                    txt_output_path = output_json_path.replace('_进度.json', '.txt')
                    with open(txt_output_path, "w", encoding="utf-8") as f:
                        f.write("\n\n".join(generated_paragraphs))
                except Exception as e:
                    print(f"Warning: Failed to update txt file during single scene rewrite: {e}")
                    
                # 如果是单场景测试，打印结果并退出
                print(f"\n--- Test Generation Result for Scene {target_scene_index} ---")
                print(scene_text)
                print(f"\nProgress saved to: {output_json_path}")
                return
            
            print(f"Scene written successfully. Length: {len(scene_text)}. Progress saved.")
        else:
            print(f"Failed to generate scene: {scene_name} after 3 attempts. Stopping generation process.")
            
            if len(generated_paragraphs) > i:
                generated_paragraphs[i] = f"【生成失败的场景：{scene_name}】"
            else:
                while len(generated_paragraphs) < i:
                    generated_paragraphs.append("【待生成】")
                generated_paragraphs.append(f"【生成失败的场景：{scene_name}】")
                
            progress_data["generated_paragraphs"] = generated_paragraphs
            
            # 保存已有进度并中断后续生成
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
            if target_scene_index is not None:
                # 单场景重写时，由于 target_scene_index 是 1-based 的，但 i 是 0-based 循环变量，
                # 所以实际这里 target_scene_index 对应当前失败场景的话就会走这里退出。
                import sys
                sys.exit(1)
            else:
                print("Generation aborted due to repeated failures. Please try again later.")
                import sys
                sys.exit(1)
            
    # 5. 保存最终生成的小说文本
    print("\n--- Step 3: Saving final story ---")
    final_story_text = "\n\n".join(generated_paragraphs)
    
    # 清理文件名中可能不合法的字符
    safe_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
    
    # 获取 '重写' 目录路径
    writer_dir = os.path.dirname(os.path.abspath(__file__))
    rewrite_dir = os.path.join(writer_dir, "重写")
    
    output_txt_path = os.path.join(rewrite_dir, f"{safe_title}.txt")
    
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(final_story_text)
        
    print(f"Success! The rewritten story has been saved to: {output_txt_path}")
    print(f"Total length: {len(final_story_text)} characters.")

if __name__ == "__main__":
    import sys
    import argparse
    
    # 获取默认路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_json_path = os.path.join(current_dir, "大纲", "《DNA骗局：总裁的契约娇妻》.json")
    
    parser = argparse.ArgumentParser(description="Novel Writer")
    parser.add_argument("json_path", nargs="?", default=default_json_path, help="Path to the input JSON file")
    parser.add_argument("--scene", type=int, help="Optional: Specify the scene index (1-based) to test generating a single scene", default=None)
    parser.add_argument("--context", type=int, help="Optional: Number of previous paragraphs to provide as context (default 2)", default=2)
    parser.add_argument("--instruction", type=str, help="Optional: Custom instructions for rewriting the scene", default="")
    
    args = parser.parse_args()
    
    write_story(args.json_path, target_scene_index=args.scene, context_level=args.context, user_instruction=args.instruction)
