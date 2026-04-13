# -*- coding: utf-8 -*-
print("Hello from the very top")
import json
import requests
import os
import subprocess
import tempfile
import re
from utils import call_dashscope_api, clean_and_parse_json

def process_large_scene(scene_name, scene_data, total_words_in_dict, current_word_count, story_content):
    """独立的函数：处理超过 900 字的场景拆分"""
    target_words = scene_data.get("目标字数", 0)
    print(f"Scene '{scene_name}' has {target_words} words (>900). Splitting via LLM...")
    
    split_count = (target_words // 800) + 1
    
    extracted_original_text = scene_data.get("参考原文", "")
    if extracted_original_text and len(extracted_original_text) > 50:
        scene_original_text = extracted_original_text
    else:
        start_ratio = current_word_count / max(1, total_words_in_dict)
        end_ratio = (current_word_count + target_words) / max(1, total_words_in_dict)
        start_idx = max(0, int(len(story_content) * (start_ratio - 0.05)))
        end_idx = min(len(story_content), int(len(story_content) * (end_ratio + 0.05)))
        scene_original_text = story_content[start_idx:end_idx]
        
    split_sub_prompt = f'''你是一个专业的小说编辑。
目前有一个场景（情绪点）的内容过于粗糙庞大，目标字数高达 {target_words} 字。
请将这个大场景进一步细化，拆分为 {split_count} 个连续的子场景/子情绪点。

【原场景信息】：
- 场景名：{scene_name}
- 情绪点：{scene_data.get("情绪点", "")}
- 剧情细纲：{scene_data.get("剧情细纲", "")}

【拆分要求】：
1. 必须根据拆分后的剧情内容，**自主为每一个子场景起一个全新的、准确概括内容的“场景名”**，绝对不要使用“{scene_name}_1”这种生硬的后缀编号。
2. 目标字数：该子场景分配到的【参考原文】的实际字数。你不需要自己编造，直接根据切分出的原文长度填写。
3. 参考原文（完整的原文切分）：你必须将传入的【该场景对应的部分小说原文】**完整地、毫无遗漏地**切分到各个子场景的“参考原文”字段中。所有子场景的“参考原文”按顺序拼接起来，必须与传入的原文字段一字不差！绝对不允许只提取片段或概括！
4. 必须且只能输出合法的 JSON 格式。
5. 绝对不要出现真实姓名，全部统一使用角色代称。

【JSON 格式要求示例】：
{{
  "拆分结果": [
    {{
      "场景名": "（你新起的场景名1，如：假装摔倒试探）",
      "目标字数": 400,
      "情绪点": "（细化后的前半部分情绪）",
      "剧情细纲": "（细化后的前半部分动作和剧情）",
      "参考原文": "（此处填入该子场景对应的完整原文切分，必须毫无遗漏）"
    }},
    {{
      "场景名": "（你新起的场景名2，如：察觉真相绝望）",
      "目标字数": 600,
      "情绪点": "（细化后的后半部分情绪）",
      "剧情细纲": "（细化后的后半部分动作和剧情）",
      "参考原文": "（此处填入该子场景对应的完整原文切分，必须毫无遗漏）"
    }}
  ]
}}

【该场景对应的部分小说原文（请参考这段原文进行细腻拆分）】：
{scene_original_text}
'''
    sub_split_content = call_dashscope_api(split_sub_prompt, system_prompt="你是一个专业的小说编辑，擅长将大段剧情拆分为更细致的情绪波折。")
    result_scenes = []
    
    if sub_split_content:
        sub_split_json = clean_and_parse_json(sub_split_content)
        if sub_split_json and "拆分结果" in sub_split_json:
            split_results = sub_split_json["拆分结果"]
            
            if isinstance(split_results, list):
                sub_scenes_items = []
                for item in split_results:
                    if isinstance(item, dict) and "场景名" in item:
                        sub_scenes_items.append((item.pop("场景名"), item))
            elif isinstance(split_results, dict):
                sub_scenes_items = list(split_results.items())
            else:
                sub_scenes_items = []
            
            for sub_name, sub_data in sub_scenes_items:
                original_text = sub_data.get("参考原文", "")
                if original_text:
                    sub_target_words = len(original_text)
                else:
                    ratio = sub_data.get("字数占比", 0)
                    if isinstance(ratio, (int, float)) and ratio > 0:
                        sub_target_words = int(target_words * (ratio / 100.0))
                    else:
                        sub_target_words = sub_data.get("目标字数", target_words // max(1, len(sub_scenes_items)))
                
                sub_data["目标字数"] = sub_target_words
                if "字数占比" in sub_data:
                    del sub_data["字数占比"]
                
                result_scenes.append((sub_name, sub_data))
            print(f"Successfully split '{scene_name}' into {len(sub_scenes_items)} sub-scenes.")
            return result_scenes
        else:
            print(f"Failed to parse split result for '{scene_name}', keeping original.")
    else:
        print(f"LLM failed to split '{scene_name}', keeping original.")
        
    return [(scene_name, scene_data)]

def extract_scene_elements(scene_name, original_text, global_storyline_str, index, total):
    """独立的函数：处理场景四要素（爽点、钩子、泪点、迷之操作）的并发提取"""
    print(f"  [{index}/{total}] Extracting elements for scene: {scene_name} ...")
    
    element_prompt = f'''你是一个专业的小说分析师。请结合下面提供的【全局故事线上下文】，仔细阅读该小说某个具体场景的【完整的参考原文切分】。
你的任务是：从这段【完整的参考原文切分】中提取以下四个关键信息要素：【爽点】、【钩子】、【泪点】、【迷之操作】。

【提取要求】：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称（如：女主、女配、男主等）。
2. 每种要素可能存在 **0个、1个或多个**。如果该段落中完全没有某个要素，请返回一个空数组 `[]`。如果有多个，请拆分为数组的多个元素。
3. 提取的内容必须具体、有画面感，说明具体发生了什么事，而不是含糊的概括。
4. 必须输出为合法的 JSON 格式，不要包含 Markdown 标记。

【要素定义及示例】：
- 钩子：给人期待感，有反转，有悬念，能吸引读者迫不及待继续往下看的情节。例如：“男主哭了，对我疯狂表白，拒绝跟我离婚。女配这时走了出来。” 或者 “但是她却不知道，我家手艺一脉传两支，我姐姐化的是活人阳妆，我化的是死人阴妆。”
- 爽点：打脸反派、反转后主角扬眉吐气、反派吃瘪、获得极大优势的瞬间。
- 泪点：极度委屈、绝望、令人心疼的情感爆发点。
- 迷之操作：角色做出的让人极其不解、降智或出人意料的行为。

【JSON 格式要求】：
{{
  "爽点": ["..."],
  "钩子": ["..."],
  "泪点": [],
  "迷之操作": ["...", "..."]
}}

【全局故事线上下文（仅供你了解背景，不要从这里提取要素）】：
{global_storyline_str}

【你需要分析提取的完整的参考原文切分】：
{original_text}
'''
    element_content = call_dashscope_api(element_prompt, system_prompt="你是一个专业的小说分析师，擅长精准提炼剧情的爽点和钩子。")
    extracted_data = {}
    
    if element_content:
        element_json = clean_and_parse_json(element_content)
        if element_json:
            for key in ["爽点", "钩子", "泪点", "迷之操作"]:
                val = element_json.get(key)
                if isinstance(val, list) and len(val) > 0 and val[0] and val[0] != "无":
                    extracted_data[key] = val
                elif isinstance(val, str) and val and val != "无" and val != "[]":
                    extracted_data[key] = [val]
            print(f"    -> Successfully extracted elements for {scene_name}")
        else:
            print(f"    -> Failed to parse elements JSON for {scene_name}")
    else:
        print(f"    -> LLM failed to return elements for {scene_name}")
        
    return scene_name, extracted_data

def extract_storyline(story_path):
    print("Start execution")
    
    # 2. 加载小说内容
    try:
        with open(story_path, 'r', encoding='utf-8') as f:
            story_content = f.read()
    except Exception as e:
        print(f"Error reading story: {e}")
        return None

    print(f"Story loaded, length: {len(story_content)}")

    # --- 新增：提取正文前的“高潮引子” ---
    import re
    # 匹配开头到单独成行的一个 "1"、"一"、"第1章"、"第一章"、"01" 等标志
    # 使用 multiline 模式，寻找单独成行的序号
    prologue_pattern = re.compile(r'^(.*?)(?:\n\s*(?:1|一|01|第[一1]章)\s*\n)', re.DOTALL)
    match = prologue_pattern.match(story_content)
    
    prologue_text = ""
    if match:
        prologue_text = match.group(1).strip()
        if prologue_text:
            print(f"Found prologue (引子) length: {len(prologue_text)} chars.")
            # 从原始文本中剔除引子，只保留正文内容供后续提取
            story_content = story_content[match.end():].strip()

    # 3. 构建 Prompt
    prompt = '''你是一个专业的小说分析助手。
请阅读下面的短篇小说，并提取故事摘要（完整故事线）。

【重要硬性要求】：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称，如：女主、女配、男主、男配、女主生母、男主养父、男主生父等。
2. 必须完整保留所有关键人物身世、过往经历、背景前史，不得省略任何影响主线逻辑的成因与动机。（特别是：失散的完整因果，真假千金/少爷造成的原因）
3. 必须输出为合法的 JSON 格式。
4. 保证逻辑完整、因果清晰，从开端、发展、反转到结局，链条不能断裂。
5. 请根据小说内容，提炼一个抓人眼球的、极具吸引力的短篇小说书名。
6. 提取小说中的核心人物，以列表形式返回。注意：必须且只能使用角色代称（如：女主、女配、男主、男配等），绝对不能出现真实姓名！
7. 提取核心人物的性格特征，返回一个字典，Key 为角色代称，Value 为该角色的核心性格描述（例如：“坚韧独立，外柔内刚”）。

【JSON 格式要求】：
请返回以下 JSON 结构：
{
  "书名": "（你生成的小说名，例如：闪婚后婆婆竟是我生母）",
  "核心人物": ["女主", "男主", "女主生母", "男主养父"],
  "人物性格": {
    "女主": "",
    "男主": ""
  },
  "故事线提取": {
    "起": "...",
    "承": "...",
    "转": "...",
    "合": "..."
  }
}
务必只返回 JSON 字符串，不要包含任何 Markdown 标记（如 ```json ）或额外文本。

【小说内容】：
''' + story_content

    print("Sending request to Aliyun DashScope API for storyline via curl...")
    storyline_content = call_dashscope_api(prompt, system_prompt="你是一个专业的小说分析Agent。")
    
    final_result = {}
    
    def remove_empty_values(data):
        """递归清理字典中值为'无'、'无。'或空字符串的项，直接删除该 Key"""
        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                if isinstance(v, str) and v.strip() in ["无", "无。", "", "没有", "无明显情绪"]:
                    continue  # 直接跳过，不加入 new_dict
                
                if isinstance(v, (dict, list)):
                    cleaned_v = remove_empty_values(v)
                    if cleaned_v:  # 如果清理后不是空字典/空列表，则保留
                        new_dict[k] = cleaned_v
                else:
                    new_dict[k] = v
            return new_dict
        elif isinstance(data, list):
            new_list = []
            for item in data:
                if isinstance(item, str) and item.strip() in ["无", "无。", "", "没有", "无明显情绪"]:
                    continue
                
                if isinstance(item, (dict, list)):
                    cleaned_item = remove_empty_values(item)
                    if cleaned_item:
                        new_list.append(cleaned_item)
                else:
                    new_list.append(item)
            return new_list
        else:
            return data
    
    if storyline_content:
        try:
            storyline_json = json.loads(storyline_content)
            final_result.update(storyline_json)
            print("Successfully parsed Storyline JSON.")
        except Exception as e:
            print("Failed to parse Storyline JSON:", e)
            
            # 尝试提取被 markdown 包裹的 json
            import re
            match = re.search(r'```json\s*(.*?)\s*```', storyline_content, re.DOTALL)
            if match:
                try:
                    storyline_json = json.loads(match.group(1))
                    final_result.update(storyline_json)
                    print("Successfully parsed Storyline JSON from markdown.")
                except Exception as e2:
                    final_result["故事线提取"] = storyline_content
            else:
                final_result["故事线提取"] = storyline_content
        
        # 4. 场景切分、情绪点提取与结构优化 (一次 LLM 调用合并完成)
        print("Start splitting scenes, extracting emotions and optimizing structure...")
        split_prompt = f'''你是一个专业的小说分析助手与网文主编。请结合以下小说的【完整故事线】和【小说原文】，完成以下两个核心任务：

【任务一：小说结构诊断与优化建议】
作为网文主编，请指出原小说在“情绪反差与结构”上存在的问题，并给出优化建议。
优秀的网文情绪依赖于结构反差（例如：事件发生 -> 燃起希望 -> 突发意外 -> 出现转机 -> 再次希望 -> 希望破灭 -> 陷入绝望 -> 绝地反击/完美结局）。
请给出一个优化后的“情绪结构重构建议”（不要修改核心结局，但可以建议在中间增加哪些拉扯和反差）。

【任务二：基于结构优化的场景切分与情绪点提取】
请将【小说原文】切分为至少 15 到 20 个极细微的转折点/场景，并将每个场景的“目标字数”、“情绪点”和“剧情细纲”合并提取出来。
要求：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称（如：女主、男主、反派女、男主母亲等），禁止使用任何具体人名。
2. 情绪点必须是以“人物 + 发生了什么事 + 内心感受”为结构的详细描述，需极致细致！
3. 剧情细纲：请在撰写每个场景的“剧情细纲”时，必须严格参考并吸纳你在【任务一】中给出的网文主编结构优化建议！如果建议在某处增加波折、拉扯或反差（如期待落空、突发意外），你必须在对应场景的细纲中直接加上具体的波折事件或反转动作！不要照搬原文平淡的叙述，把反差感做足。
4. 目标字数：直接统计该场景切分到的【参考原文】的实际字数。原文这段是多少字，目标字数就是多少。
5. 参考原文（完整的原文切分）：你必须将【小说原文】**完整地、毫无遗漏地**切分到各个场景的“参考原文”字段中。所有场景的“参考原文”按时间顺序拼接起来，必须与传入的【小说原文】一字不差！绝对不允许只提取片段、概括或省略任何一句话！
6. **严格遵循原文时间线**：你必须从小说原文的**第一段开始，从头到尾、按时间先后顺序**依次提取每一个场景！绝对不允许跳跃、倒叙或打乱事件发生的先后顺序！

【JSON 格式要求】：
请严格返回以下 JSON 结构，并确保它是一个合法的 JSON 对象，不要包含任何 Markdown 标记（如 ```json ）或额外文本。
注意："场景切分与建议"必须是一个**数组（List）**，以严格保证场景的先后顺序与原文发展完全一致！

{{
  "结构优化建议": "（在这里写出你对小说结构的诊断，以及如何增加反差、期待、破灭等情绪拉扯的具体建议，限300字以内）",
  "场景切分与建议": [
    {{
      "场景名": "初见婆婆审视",
      "目标字数": 190,
      "情绪点": "女主第一次见婆婆，发现婆婆看她的眼神异常古怪，内心充满疑惑、猜测，还有隐隐的不安。",
      "剧情细纲": "女主刚进门，男主母亲用审视的目光打量她，女主内心感到局促不安。",
      "参考原文": "（此处填入该场景对应的完整原文切分，毫无遗漏）"
    }},
    {{
      "场景名": "浏览热帖恐慌",
      "目标字数": 450,
      "情绪点": "女主偶然看到婆婆发的寻亲贴，感到震惊、荒谬，以及对自己身世的恐惧。",
      "剧情细纲": "女主翻看手机时，突然看到了男主母亲发的寻亲热帖，震惊之余不小心打翻了水杯。",
      "参考原文": "（此处填入该场景对应的完整原文切分，毫无遗漏）"
    }}
  ]
}}

【完整故事线】：
{storyline_content}

【小说原文】：
{story_content}
'''
        
        print("Sending request to Aliyun DashScope API for scenes, emotions and structure via curl...")
        split_content = call_dashscope_api(split_prompt, system_prompt="你是一个专业的小说分析Agent和网文主编。")
        
        if split_content:
            split_json = clean_and_parse_json(split_content)
            if split_json:
                final_result.update(split_json)
                print("Successfully parsed Splitting and Emotion JSON.")
            else:
                print("Failed to parse JSON, saving raw text.")
                final_result["场景切分与建议"] = split_content
        else:
            print("Failed to extract scenes and emotions.")
            
        # 将单独提取出的“引子”插入到结果中
        if prologue_text:
            final_result["引子/楔子"] = prologue_text
            
        # 5. 计算字数并生成对比结果
        if "场景切分与建议" in final_result:
            split_data = final_result["场景切分与建议"]
            new_split_dict = {}
            
            # 处理嵌套的情况
            if isinstance(split_data, dict) and "场景切分与建议" in split_data:
                split_data = split_data["场景切分与建议"]
            
            # 如果大模型返回的是列表，我们手动将其转换为需要的字典格式
            if isinstance(split_data, list):
                for item in split_data:
                    if isinstance(item, dict):
                        scene_name = item.get("场景名", "")
                        original_text = item.get("参考原文", "")
                        # 目标字数直接由参考原文统计得出
                        target_words = len(original_text) if original_text else item.get("目标字数", 0)
                        outline = item.get("剧情细纲", "")
                        emotion_point = item.get("情绪点", "")
                        if scene_name:
                            new_split_dict[scene_name] = {"目标字数": target_words, "情绪点": emotion_point, "剧情细纲": outline, "参考原文": original_text}
            # 如果大模型返回的是字典，提取目标字数和细纲
            elif isinstance(split_data, dict):
                for k, v in split_data.items():
                    if isinstance(v, dict):
                        original_text = v.get("参考原文", "")
                        tw = len(original_text) if original_text else v.get("目标字数", 0)
                        outline = v.get("剧情细纲", "")
                        emotion_point = v.get("情绪点", "")
                        new_split_dict[k] = {"目标字数": tw, "情绪点": emotion_point, "剧情细纲": outline, "参考原文": original_text}
                    elif isinstance(v, (int, str)):
                        try:
                            new_split_dict[k] = {"目标字数": int(v), "情绪点": "", "剧情细纲": "", "参考原文": ""}
                        except:
                            pass
                            
            # 替换为纯净的字典
            if new_split_dict:
                final_result["场景切分与建议"] = new_split_dict

        # 在保存前，递归清理所有值为“无”或“无。”的空场景/情绪
        final_result = remove_empty_values(final_result)
        
        # --- 新增逻辑：对超过 900 字的场景进行二次 LLM 拆分（多线程处理） ---
        if "场景切分与建议" in final_result and isinstance(final_result["场景切分与建议"], dict):
            scenes = final_result["场景切分与建议"]
            new_scenes = {}
            needs_update = False
            
            # 计算总字数，用于估算每个场景在原文中的位置
            total_words_in_dict = sum([v.get("目标字数", 0) for v in scenes.values() if isinstance(v, dict)])
            current_word_count = 0
            
            import concurrent.futures
            
            # 收集需要拆分的任务和不需要拆分的任务，以保证最终顺序
            # 列表元素格式: {"type": "normal", "name": name, "data": data} 或 {"type": "large", "name": name, "data": data, "future": future}
            processing_tasks = []
            
            # 创建线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for scene_name, scene_data in scenes.items():
                    if not isinstance(scene_data, dict):
                        processing_tasks.append({"type": "normal", "name": scene_name, "data": scene_data})
                        continue
                        
                    target_words = scene_data.get("目标字数", 0)
                    
                    if target_words > 900:
                        needs_update = True
                        # 提交到线程池
                        future = executor.submit(
                            process_large_scene, 
                            scene_name, 
                            scene_data, 
                            total_words_in_dict, 
                            current_word_count, 
                            story_content
                        )
                        processing_tasks.append({"type": "large", "name": scene_name, "future": future})
                    else:
                        processing_tasks.append({"type": "normal", "name": scene_name, "data": scene_data})
                        
                    current_word_count += target_words
                
                # 收集并按原顺序合并结果
                if needs_update:
                    for task in processing_tasks:
                        if task["type"] == "normal":
                            new_scenes[task["name"]] = task["data"]
                        elif task["type"] == "large":
                            # 等待线程执行完毕并获取结果
                            try:
                                sub_scenes_list = task["future"].result()
                                for sub_name, sub_data in sub_scenes_list:
                                    new_scenes[sub_name] = sub_data
                            except Exception as e:
                                print(f"Error processing large scene '{task['name']}': {e}")
                                # 如果报错，降级保留原场景
                                new_scenes[task["name"]] = scenes.get(task["name"], {})
                                
                    final_result["场景切分与建议"] = new_scenes
        # --- 二次拆分逻辑结束 ---

        # --- 新增逻辑：遍历所有场景，针对参考原文逐个调用大模型提取【爽点、钩子、泪点、迷之操作】 ---
        if "场景切分与建议" in final_result and isinstance(final_result["场景切分与建议"], dict):
            scenes = final_result["场景切分与建议"]
            print(f"\nStart extracting elements (爽点/钩子/泪点/迷之操作) for {len(scenes)} scenes...")
            
            # 将全局故事线转为字符串，作为上下文提供给大模型
            global_storyline_str = json.dumps(final_result.get("故事线提取", {}), ensure_ascii=False)
            
            # 使用多线程并发提取四大要素
            element_tasks = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for i, (scene_name, scene_data) in enumerate(scenes.items()):
                    if not isinstance(scene_data, dict):
                        continue
                    
                    original_text = scene_data.get("参考原文", "")
                    if not original_text or len(original_text) < 20:
                        continue
                        
                    future = executor.submit(
                        extract_scene_elements,
                        scene_name,
                        original_text,
                        global_storyline_str,
                        i + 1,
                        len(scenes)
                    )
                    element_tasks.append((scene_name, future))
                
                # 收集提取结果并合并到 scene_data 中
                for scene_name, future in element_tasks:
                    try:
                        _, extracted_data = future.result()
                        if extracted_data:
                            scenes[scene_name].update(extracted_data)
                    except Exception as e:
                        print(f"Error extracting elements for '{scene_name}': {e}")
                        
        # --- 元素提取结束 ---

        # 移除不需要的多余字段
        if "字数统计总结" in final_result:
            del final_result["字数统计总结"]
        
        # 尝试获取书名作为文件名，如果不存在则使用默认名
        book_title = final_result.get("书名", "result")
        # 清理文件名中可能不合法的字符
        import re
        book_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
        
        # 获取大纲目录路径
        writer_dir = os.path.dirname(os.path.abspath(__file__))
        outline_dir = os.path.join(writer_dir, "大纲")
        if not os.path.exists(outline_dir):
            os.makedirs(outline_dir)
            
        output_file_path = os.path.join(outline_dir, f"{book_title}.json")
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)
        print(f"Success! Final combined JSON written to {output_file_path}")
        return output_file_path
            
    else:
        print("Failed to extract storyline.")
        return None

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Novel Extractor")
    parser.add_argument("txt_path", nargs="?", default=r"e:\worksapce\short_stories\writer\《DNA骗局：总裁的契约娇妻》.txt", help="Path to the input TXT file")
    
    args = parser.parse_args()
    
    extract_storyline(args.txt_path)
