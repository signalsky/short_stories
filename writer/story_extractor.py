# -*- coding: utf-8 -*-
print("Hello from the very top")
import json
import requests
import os
import subprocess
import tempfile

def call_dashscope_api(prompt, api_key, base_url, model):
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的小说分析Agent。"},
            {"role": "user", "content": prompt}
        ]
    }
    
    payload_file = os.path.join(os.path.dirname(__file__), "payload.json")
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
        
    result = json.loads(result_process.stdout)
    if "choices" in result and len(result["choices"]) > 0:
        return result['choices'][0]['message']['content']
    else:
        print("API Response format error:", result)
        return None

def extract_storyline():
    print("Start execution")
    config_path = r"e:\worksapce\short_stories\novel_rewrite\config.json"
    
    # 1. 加载配置
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading config: {e}")
        return

    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model = config.get("model", "qwen3.5-plus")
    
    # 2. 加载小说内容
    story_path = r"e:\worksapce\short_stories\writer\《DNA骗局：总裁的契约娇妻》.txt"
    try:
        with open(story_path, 'r', encoding='utf-8') as f:
            story_content = f.read()
    except Exception as e:
        print(f"Error reading story: {e}")
        return

    print(f"Story loaded, length: {len(story_content)}")

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
    storyline_content = call_dashscope_api(prompt, api_key, base_url, model)
    
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
        
        # 4. 情绪点提取
        print("Start extracting emotion points...")
        emotion_prompt = f'''你是一个专业的小说分析助手。请结合以下小说的【完整故事线】和【小说原文】，提取这篇小说的所有关键情绪点。

【重要硬性要求】：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称（如：女主、男主、反派女、男主母亲等），禁止使用任何具体人名。
2. 禁止描述任何“情境、行为、情节细节”，仅提取纯粹的情绪词、内心状态和体感，避免AI重写时出现抄袭风险。
3. 情绪点需极致细致！为了保证细腻度，必须将小说的剧情切分为至少 15 到 20 个极细微的转折点/场景。在每个场景中，提取出所有的隐性情绪、细微情绪、内心波动，不要笼统表述。
4. 必须输出为合法的 JSON 格式。
5. 角色覆盖及重点区分：必须包含女主、男主以及对剧情推动最大的1-2个核心配角。
   - 主角（女主、男主）的情绪和体感必须极其详细、颗粒度极细，【强制要求】：主角的关键场景情绪列表必须大于或等于 15 项！
   - 核心配角的情绪可以相对简略，但也不能少于 8 项。
6. 增强通用性：你的输出 JSON 的 Key 必须根据具体小说的实际剧情动态生成，绝对不要生搬硬套示例中的场景名！必须要根据原文，切分出 15-20 个极其详细的微小场景！

【JSON 格式要求】：
请严格返回以下 JSON 结构，并确保它是一个合法的 JSON 对象，不要包含任何 Markdown 标记（如 ```json ）或额外文本。注意，"关键场景情绪" 里面的 key 必须是你根据小说内容动态生成的场景名（对于主角，强制要求至少 15 个动态场景）。
{{
  "情绪点提取": {{
    "女主": {{
      "核心主线": "（提炼贯穿该角色全文的核心情绪，用“+”连接，体现情绪变化）",
      "关键场景情绪": {{
        "场景1(动态提取如:初见婆婆对视)": "（详细列出该场景下的情绪词，用“、”连接，必须细致）",
        "场景2(动态提取)": "...",
        "场景3(动态提取)": "...",
        "场景4(动态提取)": "...",
        "场景5(动态提取)": "...",
        "场景6(动态提取)": "...",
        "场景7(动态提取)": "...",
        "场景8(动态提取)": "...",
        "场景9(动态提取)": "...",
        "场景10(动态提取)": "...",
        "场景11(动态提取)": "...",
        "场景12(动态提取)": "...",
        "场景13(动态提取)": "...",
        "场景14(动态提取)": "...",
        "场景15(动态提取)": "..."
      }},
      "内心矛盾": [
        "（内心拉扯点1，如：想靠近 vs 恐惧）",
        "（内心拉扯点2）"
      ],
      "体感细节": [
        "（所有情绪对应的生理反应词，如：手心冒汗、喉咙发紧）"
      ]
    }},
    "男主": {{
      "核心主线": "...",
      "关键场景情绪": {{
        "动态场景名1": "...",
        "动态场景名2": "..."
      }},
      "内心矛盾": [],
      "体感细节": []
    }},
    "核心配角代称(如:女主生母)": {{
      "核心主线": "...",
      "关键场景情绪": {{
        "动态场景名1": "..."
      }},
      "内心矛盾": [],
      "体感细节": []
    }}
  }}
}}

【完整故事线】：
{storyline_content}

【小说原文】：
{story_content}
'''
        
        print("Sending request to Aliyun DashScope API for emotion points via curl...")
        emotion_content = call_dashscope_api(emotion_prompt, api_key, base_url, model)
        
        if emotion_content:
            try:
                emotion_json = json.loads(emotion_content)
                final_result.update(emotion_json)
                print("Successfully parsed Emotion JSON.")
            except Exception as e:
                print("Failed to parse Emotion JSON:", e)
                
                # 尝试提取被 markdown 包裹的 json
                import re
                match = re.search(r'```json\s*(.*?)\s*```', emotion_content, re.DOTALL)
                
                # 定义一个通用的清理函数来修复大模型可能产生的 JSON 语法错误
                def clean_and_parse(json_str):
                    # 针对大模型经常把 "关键场景情绪": { ... ] 的大括号写错成中括号的修复
                    json_str = re.sub(r'("关键场景情绪"\s*:\s*\{[^\}]*?)\s*\]', r'\1}', json_str, flags=re.DOTALL)
                    # 尝试直接解析
                    try:
                        return json.loads(json_str)
                    except Exception as e:
                        # 尝试使用 json_repair 库，如果没装就算了
                        try:
                            import json_repair
                            return json_repair.loads(json_str)
                        except:
                            # 暴力替换字典末尾的 ]
                            json_str = re.sub(r'\}\s*\]', '} }', json_str)
                            return json.loads(json_str)

                if match:
                    try:
                        emotion_json = json.loads(match.group(1))
                        final_result.update(emotion_json)
                        print("Successfully parsed Emotion JSON from markdown.")
                    except Exception as e2:
                        print("Failed to parse Emotion JSON from markdown:", e2)
                        # 如果真的解析失败了，尝试清理一些常见错误再试一次
                        try:
                            # 尝试使用自定义的清理函数
                            emotion_json = clean_and_parse(match.group(1))
                            final_result.update(emotion_json)
                            print("Successfully parsed Emotion JSON after aggressive cleaning.")
                        except Exception as e3:
                            print("Aggressive cleaning failed:", e3)
                            final_result["情绪点提取"] = emotion_content
                else:
                    # 如果没有 ```json 标签，可能大模型直接返回了文本，尝试直接解析
                    try:
                        emotion_json = json.loads(emotion_content)
                        final_result.update(emotion_json)
                        print("Successfully parsed Emotion JSON directly in fallback.")
                    except:
                        try:
                            emotion_json = clean_and_parse(emotion_content)
                            final_result.update(emotion_json)
                            print("Successfully parsed Emotion JSON directly after aggressive cleaning.")
                        except:
                            final_result["情绪点提取"] = emotion_content
        else:
            print("Failed to extract emotion points.")
            
        # 5. 基于情绪点切分原文并给出调整建议及场景细纲
        print("Start splitting story by emotion scenes...")
        
        # 提取刚刚生成的“女主”关键场景情绪字典
        female_lead_scenes = final_result.get("情绪点提取", {}).get("女主", {}).get("关键场景情绪", {})
        
        if not female_lead_scenes:
            print("Failed to find female lead scenes for splitting.")
        else:
            split_prompt = f'''你是一个专业的小说编辑。
请根据以下提取出的【女主关键场景情绪列表】，将【小说原文】严格按这些场景进行切分。
同时，请以专业的网文编辑视角，对每一段切分出来的原文内容给出“字数调整建议”，并且【提取该场景的详细剧情细纲】。

【字数调整建议规则】：
- 如果你认为该段落节奏正好、情绪饱满，请给出 `0`。
- 如果你认为该段落情绪铺垫不够、需要扩写，请给出正数，例如 `10` 表示建议增加 10% 的字数，`20` 表示增加 20%。
- 如果你认为该段落过于啰嗦、节奏拖沓，请给出负数，例如 `-8` 表示建议删减 8% 的字数，`-15` 表示删减 15%。

【重要硬性要求】：
1. 必须且只能输出合法的 JSON 格式，不要包含任何 Markdown 标记（如 ```json ）或额外文本。
2. 你的切分必须覆盖【全部小说原文】。
3. 请在后台先计算出每个场景对应的【当前原文真实字数】，然后根据你的“调整建议（比例）”计算出【目标字数】。
4. 必须为每个场景提取一段【剧情细纲】，清晰说明该场景中到底发生了什么事。
   - 【防抄袭强制要求】：剧情细纲中绝对不能出现主角的真实姓名（统一用女主、男主、男主母亲等代称），并且必须模糊化具体地点和特定名词（比如不要写“沙发”，写“某处”或直接忽略地点；不要写“马尔代夫”，写“度假地”）。
5. 返回的 JSON 必须且只能是一个字典，包含一个 "场景切分与建议" 的键。它的值必须是一个字典，Key 是场景名，Value 也是一个字典，包含 "目标字数"（整数）和 "剧情细纲"（字符串）两个字段。绝对不要返回多余字段。

【JSON 格式要求示例】：
{{
  "场景切分与建议": {{
    "（对应列表中的场景名1）": {{
      "目标字数": 190,
      "剧情细纲": "女主刚进门，男主母亲用审视的目光打量她，女主内心感到局促不安。"
    }},
    "（对应列表中的场景名2）": {{
      "目标字数": 450,
      "剧情细纲": "女主翻看手机时，突然看到了男主母亲发的寻亲热帖，震惊之余不小心打翻了水杯。"
    }}
  }}
}}

【女主关键场景情绪列表】：
{json.dumps(female_lead_scenes, ensure_ascii=False, indent=2)}

【小说原文】：
{story_content}
'''
            print("Sending request to Aliyun DashScope API for story splitting via curl...")
            split_content = call_dashscope_api(split_prompt, api_key, base_url, model)
            
            if split_content:
                try:
                    split_json = json.loads(split_content)
                    final_result.update(split_json)
                    print("Successfully parsed Splitting JSON.")
                except Exception as e:
                    print("Failed to parse Splitting JSON:", e)
                    import re
                    match = re.search(r'```json\s*(.*?)\s*```', split_content, re.DOTALL)
                    if match:
                        try:
                            split_json = clean_and_parse(match.group(1))
                            final_result.update(split_json)
                            print("Successfully parsed Splitting JSON from markdown.")
                        except:
                            final_result["场景切分与建议"] = split_content
                    else:
                        try:
                            split_json = clean_and_parse(split_content)
                            final_result.update(split_json)
                            print("Successfully parsed Splitting JSON directly after aggressive cleaning.")
                        except:
                            final_result["场景切分与建议"] = split_content
            else:
                print("Failed to extract splitting info.")

        # 6. 计算字数并生成对比结果
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
                        target_words = item.get("目标字数", 0)
                        outline = item.get("剧情细纲", "")
                        if scene_name:
                            new_split_dict[scene_name] = {"目标字数": target_words, "剧情细纲": outline}
            # 如果大模型返回的是字典，提取目标字数和细纲
            elif isinstance(split_data, dict):
                for k, v in split_data.items():
                    if isinstance(v, dict):
                        tw = v.get("目标字数", 0)
                        outline = v.get("剧情细纲", "")
                        new_split_dict[k] = {"目标字数": tw, "剧情细纲": outline}
                    elif isinstance(v, (int, str)):
                        try:
                            new_split_dict[k] = {"目标字数": int(v), "剧情细纲": ""}
                        except:
                            pass
                            
            # 替换为纯净的字典
            if new_split_dict:
                final_result["场景切分与建议"] = new_split_dict
            
            # 增加基于原文长度按比例重新分配字数的逻辑，防止大模型计算出来的总和太少
            if isinstance(final_result.get("场景切分与建议"), dict):
                valid_dict = final_result["场景切分与建议"]
                total_calculated = sum([v.get("目标字数", 0) for v in valid_dict.values() if isinstance(v, dict)])
                actual_total = len(story_content)
                
                # 无论大模型计算的总和是多少，只要它偏离实际字数超过 10%，我们就按比例强制缩放
                if total_calculated > 0 and (total_calculated < actual_total * 0.9 or total_calculated > actual_total * 1.1):
                    ratio = actual_total / total_calculated
                    print(f"LLM target total ({total_calculated}) is deviated from actual total ({actual_total}). Scaling by {ratio:.2f}...")
                    adjusted_dict = {}
                    for k, v in valid_dict.items():
                        if isinstance(v, dict):
                            adjusted_dict[k] = {
                                "目标字数": int(v.get("目标字数", 0) * ratio),
                                "剧情细纲": v.get("剧情细纲", "")
                            }
                        else:
                            adjusted_dict[k] = v
                    final_result["场景切分与建议"] = adjusted_dict

        # 在保存前，递归清理所有值为“无”或“无。”的空场景/情绪
        final_result = remove_empty_values(final_result)
        
        # 移除不需要的多余字段
        if "字数统计总结" in final_result:
            del final_result["字数统计总结"]
        
        # 尝试获取书名作为文件名，如果不存在则使用默认名
        book_title = final_result.get("书名", "result")
        # 清理文件名中可能不合法的字符
        import re
        book_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
        
        output_file_path = os.path.join(r"e:\worksapce\short_stories\writer", f"{book_title}.json")
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)
        print(f"Success! Final combined JSON written to {book_title}.json")
            
    else:
        print("Failed to extract storyline.")

if __name__ == "__main__":
    extract_storyline()
