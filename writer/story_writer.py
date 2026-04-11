# -*- coding: utf-8 -*-
import json
import os
import subprocess
import re

def call_dashscope_api(prompt, api_key, base_url, model):
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的小说作家，擅长通过动作、心理和细节描写来展现极致细腻的情绪。"},
            {"role": "user", "content": prompt}
        ]
    }
    
    payload_file = os.path.join(os.path.dirname(__file__), "writer_payload.json")
    with open(payload_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        
    cmd = [
        "curl.exe", "-s", "-X", "POST",
        f"{base_url}/chat/completions",
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {api_key}",
        "-d", f"@{payload_file}"
    ]
    
    result_process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    
    if os.path.exists(payload_file):
        os.remove(payload_file)
        
    if result_process.returncode != 0:
        print(f"Error during curl call: {result_process.stderr}")
        return None
        
    try:
        result = json.loads(result_process.stdout)
        if "choices" in result and len(result["choices"]) > 0:
            return result['choices'][0]['message']['content']
        else:
            print("API Response format error:", result)
            return None
    except json.JSONDecodeError:
        print("Failed to decode JSON from curl stdout:", result_process.stdout)
        return None

def clean_json_response(text):
    """尝试从模型返回的文本中提取合法的 JSON"""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试暴力修复常见的括号错误
        text = re.sub(r'\}\s*\]', '} }', text)
        try:
            return json.loads(text)
        except:
            return None

def write_story(json_path):
    print(f"Loading input JSON: {json_path}")
    
    # 1. 加载配置
    config_path = r"e:\worksapce\short_stories\novel_rewrite\config.json"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading config: {e}")
        return

    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model = config.get("model", "qwen3.5-plus")

    # 2. 加载提取好的小说大纲数据
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
    
    # 3. 第一次 LLM 调用：为角色取名 & 重构防抄袭细纲
    print("\n--- Step 1: Assigning real names to characters and rewriting outlines ---")
    
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
    name_response = call_dashscope_api(naming_prompt, api_key, base_url, model)
    step1_data = clean_json_response(name_response)
    
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
    generated_paragraphs = []
    
    # 获取女主的情绪点字典，方便在场景中查找对应情绪
    female_emotions = emotions.get("女主", {}).get("关键场景情绪", {})
    
    for i, (scene_name, scene_data) in enumerate(scenes_dict.items()):
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
        
        # 获取前文两段（如果存在）
        context_paragraphs = ""
        if i > 0:
            start_idx = max(0, i - 2)
            context_paragraphs = "\n\n".join(generated_paragraphs[start_idx:i])
        
        # 查找该场景对应的情绪（尝试模糊匹配）
        scene_emotion = "（自由发挥符合剧情的细腻情绪）"
        for k, v in female_emotions.items():
            if scene_name in k or k in scene_name:
                scene_emotion = v
                break
        
        # 构建当前段落的写作 prompt
        write_prompt = f'''你正在创作一篇爆款短篇小说，现在需要撰写其中的一个场景片段。
你的写作核心是【体现情绪】，绝对不能干巴巴地平铺直叙。必须通过极其细腻的动作、神态、心理描写、感官细节（如视觉、听觉、温度、痛感等）来展现角色的情绪波动。

【全局公共设定（不可偏离）】：
{public_context}

【前文内容（为了保持连贯，这是前一个或两个场景的内容，请接着往下写）】：
{context_paragraphs if context_paragraphs else "（这是小说的开头第一个场景，请直接开始创作）"}

------------------------
【本次写作任务要求】：
1. 必须使用【第一人称（“我”）】视角进行创作，代入女主的内心世界，增强读者代入感！
2. 绝对禁止任何写景和环境渲染（如阳光、空气、微风等废话）！开局直接用精炼的语言交代核心背景、人物身份和冲突，比如“我叫XXX，今天是我闪婚的第十天”，或者通过几句激烈的对话直接交代人物关系（比如真假千金的冲突），绝不拖泥带水！
3. 本次需要撰写的场景是：【{scene_name}】
4. 【核心剧情细纲（你必须按照这个细纲来写）】：{scene_outline}
5. 本次场景必须体现的核心情绪是：【{scene_emotion}】（必须将这些情绪词具象化为身体反应和微小动作，不要直接把情绪词念出来）
6. 目标字数要求：请严格控制在【{target_words}字】左右！不要太短，必须通过人物动作、对话和心理活动把细节拉满！
7. 注意使用真实姓名，不要出现“女主”、“男主”等代称。但是称呼女主自己时用“我”。

请直接输出小说正文内容，不要包含任何多余的开头问候、分析说明或字数统计！直接开始写正文！
'''
        
        scene_text = call_dashscope_api(write_prompt, api_key, base_url, model)
        if scene_text:
            # 清理可能的 markdown 标记
            scene_text = re.sub(r'```[a-zA-Z]*\n', '', scene_text)
            scene_text = re.sub(r'```', '', scene_text)
            scene_text = scene_text.strip()
            
            generated_paragraphs.append(scene_text)
            print(f"Scene written successfully. Length: {len(scene_text)}")
        else:
            print(f"Failed to generate scene: {scene_name}. Appending placeholder.")
            generated_paragraphs.append(f"【生成失败的场景：{scene_name}】")
            
    # 5. 保存最终生成的小说文本
    print("\n--- Step 3: Saving final story ---")
    final_story_text = "\n\n".join(generated_paragraphs)
    
    # 清理文件名中可能不合法的字符
    safe_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
    output_txt_path = os.path.join(os.path.dirname(json_path), f"【重写】{safe_title}.txt")
    
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(final_story_text)
        
    print(f"Success! The rewritten story has been saved to: {output_txt_path}")
    print(f"Total length: {len(final_story_text)} characters.")

if __name__ == "__main__":
    import sys
    target_json = r"e:\worksapce\short_stories\writer\闪婚第十天，婆婆疑我是她失散多年的亲女儿.json"
    if len(sys.argv) > 1:
        target_json = sys.argv[1]
    write_story(target_json)
