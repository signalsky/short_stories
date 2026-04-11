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
    character_personalities = story_data.get("人物性格", {})
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
    
    # 3. 第一次 LLM 调用：为角色取名 & 重构防抄袭细纲
    print("\n--- Step 1: Assigning real names to characters and rewriting outlines ---")
    
    if "name_map" in progress_data and "rewritten_outlines" in progress_data:
        name_map = progress_data["name_map"]
        rewritten_outlines = progress_data["rewritten_outlines"]
        print("Using cached names and outlines.")
    else:
        # 提取所有的旧细纲
        original_outlines = {k: v.get("剧情细纲", "") for k, v in scenes_dict.items() if isinstance(v, dict)}
        
        naming_prompt = f'''你是一个专业的小说作者。我有一篇短篇小说的核心人物代称列表和各个场景的【原剧情细纲】。

【任务一：取名】
请根据这些代称，为他们每个人取一个符合现代都市/言情小说风格的真实姓名。
核心人物列表：{json.dumps(core_characters, ensure_ascii=False)}

【任务二：重构防抄袭细纲（非常重要！）】
为了防止抄袭，我需要你把原本的【原剧情细纲】进行彻底的“洗稿换皮”。
要求：
1. 绝对保留原本细纲要表达的【核心情绪】和【剧情推进目的】（比如：目的是让女主难堪、目的是发现真相等）。
2. 但是，必须彻底更换发生这些情绪的【具体场景、具体地点、具体事件起因】！
   - 例如：原细纲是在“沙发上”见婆婆，你可以改成在“高档餐厅的包厢里”或者“家宴的餐桌上”。
   - 例如：原细纲是“看手机热帖”，你可以改成“不小心听到亲戚议论”或者“无意中看到一份文件”。
3. 重构后的细纲中，直接使用你刚刚为他们取好的真实姓名！

【输出要求】：
请务必只返回一个合法的 JSON 字典，包含 "角色姓名" 和 "重构细纲" 两个 Key。不要返回任何其他内容或 Markdown 标记。

示例：
{{
  "角色姓名": {{
    "女主": "苏念",
    "男主": "陆泽",
    "女主生母": "姜岚"
  }},
  "重构细纲": {{
    "原场景名1": "苏念刚走进高档餐厅包厢，姜岚便用极其挑剔的目光将她从头到脚扫视了一遍，苏念手心出汗，感到极度局促。",
    "原场景名2": "苏念在整理陆泽的外套时，无意中从口袋里掉出一张医院的缴费单，震惊之余不小心碰倒了旁边的花瓶。"
  }}
}}

【原剧情细纲（请逐一重构）】：
{json.dumps(original_outlines, ensure_ascii=False, indent=2)}
'''
        name_response = call_dashscope_api(naming_prompt, system_prompt="你是一个专业的小说作者。")
        step1_data = clean_and_parse_json(name_response)
        
        name_map = {}
        rewritten_outlines = {}
        
        if not step1_data or not isinstance(step1_data, dict):
            print("Failed to get names and outlines from LLM, using fallback.")
            name_map = {role: f"[{role}的名字]" for role in core_characters}
            rewritten_outlines = original_outlines
        else:
            name_map = step1_data.get("角色姓名", {})
            rewritten_outlines = step1_data.get("重构细纲", {})
            print(f"Successfully generated names and rewritten outlines.")
        
        # 缓存第一步结果
        progress_data["name_map"] = name_map
        progress_data["rewritten_outlines"] = rewritten_outlines
        progress_data["generated_paragraphs"] = progress_data.get("generated_paragraphs", [])
        
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
    # 准备公共数据字符串，用于传递给后续的每次写作请求
    public_context = f'''
【小说书名】：{book_title}

【角色姓名与性格对照表】：
'''
    for role in core_characters:
        name = name_map.get(role, role)
        personality = character_personalities.get(role, "（未提供性格描述）")
        public_context += f"- {role}：姓名【{name}】，性格：【{personality}】\n"

    public_context += f'''
【完整故事线】：
{json.dumps(storyline, ensure_ascii=False, indent=2)}

【主要角色核心主线情绪】：
'''
    for role, role_data in emotions.items():
        if isinstance(role_data, dict) and "核心主线" in role_data:
            public_context += f"- {name_map.get(role, role)} ({role}): {role_data['核心主线']}\n"
            
    # 4. 循环调用大模型，逐段生成小说
    print("\n--- Step 2: Writing scenes one by one ---")
    
    # 恢复已有段落
    generated_paragraphs = progress_data.get("generated_paragraphs", [])
    
    # 获取女主的情绪点字典，方便在场景中查找对应情绪
    female_emotions = emotions.get("女主", {}).get("关键场景情绪", {})
    
    for i, (scene_name, scene_data) in enumerate(scenes_dict.items()):
        # 如果传入了 target_scene_index 且当前索引不匹配，则跳过生成
        # target_scene_index 是基于 1 的索引，i 是基于 0 的索引
        if target_scene_index is not None and (i + 1) != target_scene_index:
            continue
            
        # 如果没有传入 target_scene_index，并且当前段落已经生成过，则跳过
        if target_scene_index is None and i < len(generated_paragraphs):
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
        
        # 查找该场景对应的情绪（尝试模糊匹配）
        scene_emotion = "（自由发挥符合剧情的细腻情绪）"
        for k, v in female_emotions.items():
            if scene_name in k or k in scene_name:
                scene_emotion = v
                break
        
        # 构建当前段落的写作 prompt
        intro_instruction = ""
        if i == 0:
            intro_instruction = "这是小说的开篇，请开局直接用精炼的语言交代核心背景、人物身份和冲突，比如“我叫XXX，今天是我闪婚的第十天”，或者通过几句激烈的对话直接交代人物关系，绝不拖泥带水！"
        else:
            intro_instruction = "请紧接前文剧情自然往下写，绝对不要再次重复自我介绍（如“我叫XXX”）或重新交代背景！"
            
        # 如果用户提供了重写的额外要求，加粗强调
        user_instruction_block = ""
        if target_scene_index is not None and user_instruction:
            user_instruction_block = f"\n【用户特别修改要求（优先级最高！）】：\n{user_instruction}\n"

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
8. 注意使用真实姓名，不要出现“女主”、“男主”等代称。但是称呼女主自己时用“我”。

请直接输出小说正文内容，不要包含任何多余的开头问候、分析说明或字数统计！直接开始写正文！
'''
        
        scene_text = call_dashscope_api(write_prompt, system_prompt="你是一个专业的小说作家，擅长通过具体的事件和动作细节来展现情绪，极少使用纯心理描写。")
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
                # 如果是单场景测试，打印结果并退出
                print(f"\n--- Test Generation Result for Scene {target_scene_index} ---")
                print(scene_text)
                print(f"\nProgress saved to: {output_json_path}")
                return
            
            print(f"Scene written successfully. Length: {len(scene_text)}. Progress saved.")
        else:
            print(f"Failed to generate scene: {scene_name}. Appending placeholder.")
            if target_scene_index is None:
                generated_paragraphs.append(f"【生成失败的场景：{scene_name}】")
                progress_data["generated_paragraphs"] = generated_paragraphs
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, ensure_ascii=False, indent=2)
            else:
                return
            
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
    default_json_path = os.path.join(current_dir, "大纲", "闪婚第十天，婆婆疑我是她失散多年的亲女儿.json")
    
    parser = argparse.ArgumentParser(description="Novel Writer")
    parser.add_argument("json_path", nargs="?", default=default_json_path, help="Path to the input JSON file")
    parser.add_argument("--scene", type=int, help="Optional: Specify the scene index (1-based) to test generating a single scene", default=None)
    parser.add_argument("--context", type=int, help="Optional: Number of previous paragraphs to provide as context (default 2)", default=2)
    parser.add_argument("--instruction", type=str, help="Optional: Custom instructions for rewriting the scene", default="")
    
    args = parser.parse_args()
    
    write_story(args.json_path, target_scene_index=args.scene, context_level=args.context, user_instruction=args.instruction)
