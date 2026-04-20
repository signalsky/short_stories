# -*- coding: utf-8 -*-
import json
import os
import re
from utils import call_dashscope_api, clean_and_parse_json

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
        
        if isinstance(scene_data, dict):
            target_words = scene_data.get("目标字数", 0)
            # 优先使用第一步重构后的“防抄袭细纲”，如果没有则回退到原细纲
            scene_outline = rewritten_outlines.get(scene_name, scene_data.get("剧情细纲", scene_outline))
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
            intro_instruction = "这是小说的开篇，请开局直接用精炼的语言交代核心背景、人物身份和冲突，比如“我叫XXX，今天是我闪婚的第十天，是第一次见婆婆xxx”，或者通过几句激烈的对话直接交代人物关系，绝不拖泥带水！"
        else:
            intro_instruction = "请紧接前文剧情自然往下写，绝对不要再次重复自我介绍（如“我叫XXX”）或重新交代背景！"
            
        # 如果用户提供了重写的额外要求，加粗强调
        user_instruction_block = ""
        if user_instruction:
            user_instruction_block = f"\n【用户特别修改要求（优先级最高！）】：\n{user_instruction}\n"

        # 提取当前场景的四大要素（爽点、钩子、泪点、迷之操作）
        elements_instruction = ""
        if isinstance(scene_data, dict):
            elements_list = []
            missing_elements = []
            for el_name in ["爽点", "钩子", "泪点", "迷之操作"]:
                el_val = scene_data.get(el_name)
                is_missing = True
                if el_val and el_val != "无" and el_val != "[]":
                    # 兼容字符串或列表格式
                    if isinstance(el_val, list):
                        if len(el_val) > 0 and el_val[0] and el_val[0] != "无":
                            elements_list.append(f"- 【{el_name}】：\n  " + "\n  ".join([f"* {v}" for v in el_val]))
                            is_missing = False
                    elif isinstance(el_val, str):
                        elements_list.append(f"- 【{el_name}】：{el_val}")
                        is_missing = False
                
                if is_missing:
                    missing_elements.append(el_name)
                
            elements_instruction = "9. 【核心看点与张力设计（极其重要）】：\n"
            if elements_list:
                elements_instruction += "   🚨🚨🚨【强制要求】：以下要素是当前场景的灵魂！你必须通过【具体的冲突、人物动作和对话】将它们**自然且隐蔽**地融入剧情中。绝不能生硬地贴标签或直接陈述，而是要让读者在阅读事件的发展时自己体会到这些看点。如果遗漏任何一个要素，本次写作将被判定为严重失败！请务必重点刻画：\n   " + "\n   ".join(elements_list) + "\n"
            
            # 温和地建议大模型补充缺失的要素，不强制
            if missing_elements:
                elements_instruction += f"   （建议）：当前场景原剧情缺乏以下要素：【{'、'.join(missing_elements)}】。如果在不破坏剧情合理性的前提下，你可以发挥创造力，自然地为其补充一些设定（例如顺手埋个悬念钩子、或制造一点爽点/泪点），让剧情更好看。但不强制，顺其自然即可。\n"

        write_prompt = f'''你正在创作一篇爆款短篇小说，现在需要撰写其中的一个场景片段。
你的写作核心是【用事件体现情绪】。必须以事件描写和动作描写为主，极少使用纯心理描写。让情绪通过具体的事件冲突、人物的动作和神态自然流露出来，事件服务于情绪。

【全局公共设定（不可偏离）】：
{public_context}

【前文内容（为了保持连贯，这是前文内容，请接着往下写）】：
{context_paragraphs if context_paragraphs else "（这是小说的开头第一个场景，请直接开始创作）"}
{user_instruction_block}
------------------------
【本次写作任务要求】：
1. 必须使用【第一人称（“我”）】视角进行创作，代入女主的视角！
2. 绝对禁止任何写景和环境渲染（如阳光、空气、微风等废话）！
3. {intro_instruction}
4. 本次需要撰写的场景是：【{scene_name}】
5. 【核心剧情细纲（你必须按照这个细纲来推进事件）】：{scene_outline}
6. 本次场景必须体现的核心情绪是：【{scene_emotion}】（必须将情绪融入到具体的事件、对话和动作中，不要大段的内心独白）
7. 目标字数要求：请严格控制在【{target_words}字】左右！不要太短，必须通过人物动作、对话和事件细节把字数拉满！
8. 人物称呼要求：请根据第一人称视角，在适当的地方使用更自然、符合身份的称呼（如“婆婆”、“老公”、“我妈”等），**不要总是生硬地直呼其名**。但是绝对不要出现“女主”、“男主”这种大纲代称，称呼女主自己时用“我”。
{elements_instruction}

请直接输出小说正文内容，不要包含任何多余的开头问候、分析说明或字数统计！直接开始写正文！
'''
        
        scene_text = None
        for attempt in range(3):
            print(f"Attempt {attempt + 1}/3 to generate scene...")
            scene_text = call_dashscope_api(write_prompt, system_prompt="你是一个专业的小说作家，擅长通过具体的事件和动作细节来展现情绪，极少使用纯心理描写。你会极度重视并严格执行剧情中设定的'泪点'、'爽点'、'钩子'和'迷之操作'要素，绝不遗漏。")
            if scene_text:
                break
            print("Generation failed. Retrying...")

        if scene_text:
            # 清理可能的 markdown 标记
            scene_text = re.sub(r'```[a-zA-Z]*\n', '', scene_text)
            scene_text = re.sub(r'```', '', scene_text)
            scene_text = scene_text.strip()
            
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
    default_json_path = os.path.join(current_dir, "大纲", "婆婆发帖寻亲，闪婚老公竟非亲弟.json")
    
    parser = argparse.ArgumentParser(description="Novel Writer")
    parser.add_argument("json_path", nargs="?", default=default_json_path, help="Path to the input JSON file")
    parser.add_argument("--scene", type=int, help="Optional: Specify the scene index (1-based) to test generating a single scene", default=None)
    parser.add_argument("--context", type=int, help="Optional: Number of previous paragraphs to provide as context (default 2)", default=2)
    parser.add_argument("--instruction", type=str, help="Optional: Custom instructions for rewriting the scene", default="")
    
    args = parser.parse_args()
    
    write_story(args.json_path, target_scene_index=args.scene, context_level=args.context, user_instruction=args.instruction)
