# -*- coding: utf-8 -*-
print("Hello from the very top")
import json
import requests
import os
import subprocess
import tempfile
import re
from utils import call_dashscope_api, clean_and_parse_json

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
4. 字数调整：根据每个场景的原文真实字数，如果你认为该段落节奏正好请给原字数；如果情绪铺垫不够请适当增加字数；如果过于啰嗦请适当删减字数。
5. 参考原文：请从传入的【小说原文】中，将支撑这个场景/情绪点的**对应的原始段落文本**完整提取出来，放入“参考原文”字段中，以便后续二次拆分或写作时精准参考。
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
      "参考原文": "（此处填入该场景对应的具体原文片段，保持原汁原味）"
    }},
    {{
      "场景名": "浏览热帖恐慌",
      "目标字数": 450,
      "情绪点": "女主偶然看到婆婆发的寻亲贴，感到震惊、荒谬，以及对自己身世的恐惧。",
      "剧情细纲": "女主翻看手机时，突然看到了男主母亲发的寻亲热帖，震惊之余不小心打翻了水杯。",
      "参考原文": "（此处填入该场景对应的具体原文片段，保持原汁原味）"
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
                        target_words = item.get("目标字数", 0)
                        outline = item.get("剧情细纲", "")
                        emotion_point = item.get("情绪点", "")
                        original_text = item.get("参考原文", "")
                        if scene_name:
                            new_split_dict[scene_name] = {"目标字数": target_words, "情绪点": emotion_point, "剧情细纲": outline, "参考原文": original_text}
            # 如果大模型返回的是字典，提取目标字数和细纲
            elif isinstance(split_data, dict):
                for k, v in split_data.items():
                    if isinstance(v, dict):
                        tw = v.get("目标字数", 0)
                        outline = v.get("剧情细纲", "")
                        emotion_point = v.get("情绪点", "")
                        original_text = v.get("参考原文", "")
                        new_split_dict[k] = {"目标字数": tw, "情绪点": emotion_point, "剧情细纲": outline, "参考原文": original_text}
                    elif isinstance(v, (int, str)):
                        try:
                            new_split_dict[k] = {"目标字数": int(v), "情绪点": "", "剧情细纲": "", "参考原文": ""}
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
                    print(f"LLM calculated total ({total_calculated}) is deviated from actual total ({actual_total}). Scaling by {ratio:.2f}...")
                    adjusted_dict = {}
                    for k, v in valid_dict.items():
                        if isinstance(v, dict):
                            calculated_words = int(v.get("目标字数", 0) * ratio)
                            adjusted_dict[k] = {
                                "目标字数": calculated_words,
                                "情绪点": v.get("情绪点", ""),
                                "剧情细纲": v.get("剧情细纲", ""),
                                "参考原文": v.get("参考原文", "")
                            }
                        else:
                            adjusted_dict[k] = v
                    final_result["场景切分与建议"] = adjusted_dict

        # 在保存前，递归清理所有值为“无”或“无。”的空场景/情绪
        final_result = remove_empty_values(final_result)
        
        # --- 新增逻辑：对超过 900 字的场景进行二次 LLM 拆分 ---
        if "场景切分与建议" in final_result and isinstance(final_result["场景切分与建议"], dict):
            scenes = final_result["场景切分与建议"]
            new_scenes = {}
            needs_update = False
            
            # 计算总字数，用于估算每个场景在原文中的位置
            total_words_in_dict = sum([v.get("目标字数", 0) for v in scenes.values() if isinstance(v, dict)])
            current_word_count = 0
            
            for scene_name, scene_data in scenes.items():
                if not isinstance(scene_data, dict):
                    new_scenes[scene_name] = scene_data
                    continue
                    
                target_words = scene_data.get("目标字数", 0)
                
                if target_words > 900:
                    needs_update = True
                    print(f"Scene '{scene_name}' has {target_words} words (>900). Splitting via LLM...")
                    
                    # 计算需要拆分成几个子场景
                    split_count = (target_words // 800) + 1
                    
                    # 优先使用大模型提取的参考原文，如果为空则降级使用比例截取
                    extracted_original_text = scene_data.get("参考原文", "")
                    if extracted_original_text and len(extracted_original_text) > 50:
                        scene_original_text = extracted_original_text
                    else:
                        # 估算当前场景在原文中的起始和结束比例
                        start_ratio = current_word_count / max(1, total_words_in_dict)
                        end_ratio = (current_word_count + target_words) / max(1, total_words_in_dict)
                        # 根据比例截取对应的原文片段，前后多扩展 5% 的缓冲内容，以防截断
                        start_idx = max(0, int(len(story_content) * (start_ratio - 0.05)))
                        end_idx = min(len(story_content), int(len(story_content) * (end_ratio + 0.05)))
                        scene_original_text = story_content[start_idx:end_idx]
                        
                    current_word_count += target_words
                    
                    split_sub_prompt = f'''你是一个专业的小说编辑。
目前有一个场景（情绪点）的内容过于粗糙庞大，目标字数高达 {target_words} 字。
请将这个大场景进一步细化，拆分为 {split_count} 个连续的子场景/子情绪点。

【原场景信息】：
- 场景名：{scene_name}
- 情绪点：{scene_data.get("情绪点", "")}
- 剧情细纲：{scene_data.get("剧情细纲", "")}

【拆分要求】：
1. 必须根据拆分后的剧情内容，**自主为每一个子场景起一个全新的、准确概括内容的“场景名”**，绝对不要使用“{scene_name}_1”这种生硬的后缀编号。
2. **字数分配比例**：你必须评估每个子场景在原文中所占的篇幅比例，并输出一个 1-100 之间的整数作为【字数占比】。所有子场景的“字数占比”相加必须等于 100。
3. 从传入的【该场景对应的部分小说原文】中，将支撑这个子场景/子情绪点的**对应的原始段落文本**完整提取出来，放入“参考原文”字段中。
4. 必须且只能输出合法的 JSON 格式。
5. 绝对不要出现真实姓名，全部统一使用角色代称。

【JSON 格式要求示例】：
{{
  "拆分结果": [
    {{
      "场景名": "（你新起的场景名1，如：假装摔倒试探）",
      "字数占比": 40,
      "情绪点": "（细化后的前半部分情绪）",
      "剧情细纲": "（细化后的前半部分动作和剧情）",
      "参考原文": "（此处填入该子场景对应的具体原文片段，保持原汁原味）"
    }},
    {{
      "场景名": "（你新起的场景名2，如：察觉真相绝望）",
      "字数占比": 60,
      "情绪点": "（细化后的后半部分情绪）",
      "剧情细纲": "（细化后的后半部分动作和剧情）",
      "参考原文": "（此处填入该子场景对应的具体原文片段，保持原汁原味）"
    }}
  ]
}}

【该场景对应的部分小说原文（请参考这段原文进行细腻拆分）】：
{scene_original_text}
'''
                    sub_split_content = call_dashscope_api(split_sub_prompt, system_prompt="你是一个专业的小说编辑，擅长将大段剧情拆分为更细致的情绪波折。")
                    if sub_split_content:
                        sub_split_json = clean_and_parse_json(sub_split_content)
                        if sub_split_json and "拆分结果" in sub_split_json:
                            # 兼容大模型返回列表或字典的情况
                            split_results = sub_split_json["拆分结果"]
                            
                            # 如果返回的是列表，将每个对象转换为键值对形式
                            if isinstance(split_results, list):
                                sub_scenes_items = []
                                for item in split_results:
                                    if isinstance(item, dict) and "场景名" in item:
                                        sub_scenes_items.append((item.pop("场景名"), item))
                            elif isinstance(split_results, dict):
                                sub_scenes_items = list(split_results.items())
                            else:
                                sub_scenes_items = []
                            
                            # 将拆分出来的多个子场景插入到新的字典中，保持顺序
                            for sub_name, sub_data in sub_scenes_items:
                                # 实际程序统计：根据大模型给的占比，结合父场景的字数，计算子场景的“目标字数”
                                ratio = sub_data.get("字数占比", 0)
                                if isinstance(ratio, (int, float)) and ratio > 0:
                                    sub_target_words = int(target_words * (ratio / 100.0))
                                else:
                                    # Fallback to evenly distributing if ratio is missing or invalid
                                    sub_target_words = target_words // max(1, len(sub_scenes_items))
                                
                                sub_data["目标字数"] = sub_target_words
                                # Remove the ratio field as it's no longer needed in the final JSON
                                if "字数占比" in sub_data:
                                    del sub_data["字数占比"]
                                
                                new_scenes[sub_name] = sub_data
                            print(f"Successfully split '{scene_name}' into {len(sub_scenes_items)} sub-scenes.")
                        else:
                            print(f"Failed to parse split result for '{scene_name}', keeping original.")
                            new_scenes[scene_name] = scene_data
                    else:
                        print(f"LLM failed to split '{scene_name}', keeping original.")
                        new_scenes[scene_name] = scene_data
                else:
                    # 不超过 900 字的正常场景，直接保留
                    new_scenes[scene_name] = scene_data
            
            if needs_update:
                final_result["场景切分与建议"] = new_scenes
        # --- 二次拆分逻辑结束 ---

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
