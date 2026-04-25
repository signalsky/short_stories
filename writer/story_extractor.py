# -*- coding: utf-8 -*-
import json
import requests
import os
import subprocess
import tempfile
import re
import math
from utils import call_dashscope_api, clean_and_parse_json

SCENE_TARGET_WORDS = 700
SCENE_MAX_WORDS = 900
ELEMENT_KEYS = ["爽点", "钩子", "泪点", "虐点"]


def estimate_scene_count(text_length, target_words=SCENE_TARGET_WORDS):
    """按目标字数动态估算场景数，尽量让单场景接近 target_words。"""
    if text_length <= 0:
        return 1
    return max(1, math.ceil(text_length / max(1, target_words)))


def shorten_text(text, max_length=48):
    """将模型或旧大纲里的长句压缩成更适合阅读的短句。"""
    if not isinstance(text, str):
        return ""

    cleaned = re.sub(r"\s+", " ", text).strip(" \n\r\t-:：;；，。")
    if not cleaned:
        return ""

    first_sentence = re.split(r"[。！？!?\n\r]", cleaned, maxsplit=1)[0].strip()
    if 0 < len(first_sentence) <= max_length:
        return first_sentence

    chunks = [part.strip(" -:：;；，。、") for part in re.split(r"[，、：；;]", first_sentence) if part.strip()]
    if not chunks:
        chunks = [first_sentence]

    concise = ""
    for chunk in chunks:
        candidate = chunk if not concise else f"{concise}，{chunk}"
        if len(candidate) > max_length:
            break
        concise = candidate

    concise = concise or first_sentence[:max_length]
    return concise.strip(" ，。；;")


def shorten_text_list(values, max_items=2, max_length=52):
    concise_items = []
    seen = set()
    for value in values or []:
        concise = shorten_text(value, max_length=max_length)
        if not concise or concise in seen:
            continue
        seen.add(concise)
        concise_items.append(concise)
        if len(concise_items) >= max_items:
            break
    return concise_items


def normalize_scene_progress(values, max_items=4, max_length=34):
    concise_items = []
    seen = set()
    if isinstance(values, str):
        values = re.split(r"[\n\r]+", values)

    for value in values or []:
        concise = shorten_text(value, max_length=max_length)
        if not concise or concise in seen:
            continue
        seen.add(concise)
        concise_items.append(concise)
        if len(concise_items) >= max_items:
            break
    return concise_items


def process_large_scene(scene_name, scene_data, total_words_in_dict, current_word_count, story_content, scene_target_words=SCENE_TARGET_WORDS):
    """独立的函数：处理超过单场景字数上限的场景拆分"""
    target_words = scene_data.get("目标字数", 0)
    print(f"Scene '{scene_name}' has {target_words} words (>900). Splitting via LLM...")
    
    split_count = max(2, math.ceil(target_words / max(1, scene_target_words)))
    
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
- 情绪推进：{json.dumps(scene_data.get("情绪推进", []), ensure_ascii=False)}

【拆分要求】：
1. 必须根据拆分后的剧情内容，**自主为每一个子场景起一个全新的、准确概括内容的“场景名”**，绝对不要使用“{scene_name}_1”这种生硬的后缀编号。
2. 目标字数：该子场景分配到的【参考原文】的实际字数。你不需要自己编造，直接根据切分出的原文长度填写。
3. 参考原文（完整的原文切分）：你必须将传入的【该场景对应的部分小说原文】**完整地、毫无遗漏地**切分到各个子场景的“参考原文”字段中。所有子场景的“参考原文”按顺序拼接起来，必须与传入的原文字段一字不差！绝对不允许只提取片段或概括！
4. 除了“情绪点”和“剧情细纲”，还要补充 2 到 4 条按顺序排列的“情绪推进”，写清楚这个子场景里“刺激落点 -> 人物反应 -> 对外动作/决定 -> 余波/新风险”的关键台阶。
5. “情绪推进”每条尽量控制在 12 到 28 个字，必须是具体事件或反应，不能写空泛评价。
6. 必须且只能输出合法的 JSON 格式。
7. 绝对不要出现真实姓名，全部统一使用角色代称。

【JSON 格式要求示例】：
{{
  "拆分结果": [
    {{
      "场景名": "（你新起的场景名1，如：假装摔倒试探）",
      "目标字数": 400,
      "情绪点": "（细化后的前半部分情绪）",
      "剧情细纲": "（细化后的前半部分动作和剧情）",
      "情绪推进": ["（刺激）", "（反应）", "（动作或决定）"],
      "参考原文": "（此处填入该子场景对应的完整原文切分，必须毫无遗漏）"
    }},
    {{
      "场景名": "（你新起的场景名2，如：察觉真相绝望）",
      "目标字数": 600,
      "情绪点": "（细化后的后半部分情绪）",
      "剧情细纲": "（细化后的后半部分动作和剧情）",
      "情绪推进": ["（刺激）", "（反应）", "（动作或决定）"],
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
                progress_steps = normalize_scene_progress(sub_data.get("情绪推进"))
                if progress_steps:
                    sub_data["情绪推进"] = progress_steps
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
    """独立的函数：处理场景要素（爽点、钩子、泪点、虐点）的并发提取"""
    print(f"  [{index}/{total}] Extracting elements for scene: {scene_name} ...")
    
    element_prompt = f'''你是一个专业的小说分析师。请结合下面提供的【全局故事线上下文】，仔细阅读该小说某个具体场景的【完整的参考原文切分】。
你的任务是：从这段【完整的参考原文切分】中提取以下四个关键信息要素：【爽点】、【钩子】、【泪点】、【虐点】。

【提取要求】：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称（如：女主、女配、男主等）。
2. 每种要素可能存在 **0个、1个或多个**。如果该段落中完全没有某个要素，请返回一个空数组 `[]`。如果有多个，请拆分为数组的多个元素。
3. 宁缺毋滥，没有就返回空数组，不要为了凑字段硬编。
4. 每个数组元素尽量控制在 18 到 40 个字，直接写成一句短句，不要扩写成长段分析。
5. 必须输出为合法的 JSON 格式，不要包含 Markdown 标记。

【要素定义及示例】：
- 钩子：给人期待感，有反转，有悬念，能吸引读者迫不及待继续往下看的情节。例如：“男主哭了，对我疯狂表白，拒绝跟我离婚。女配这时走了出来。” 或者 “但是她却不知道，我家手艺一脉传两支，我姐姐化的是活人阳妆，我化的是死人阴妆。”
- 爽点：打脸反派、反转后主角扬眉吐气、反派吃瘪、获得极大优势的瞬间。
- 泪点：极度委屈、绝望、令人心疼的情感爆发点。
- 虐点：让读者感到心痛、无奈、主角被误解或遭受不公对待的虐心情节。

【JSON 格式要求】：
{{
  "爽点": ["..."],
  "钩子": ["..."],
  "泪点": [],
  "虐点": ["..."]
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
            for key in ELEMENT_KEYS:
                val = element_json.get(key)
                if isinstance(val, list) and len(val) > 0 and val[0] and val[0] != "无":
                    concise_list = shorten_text_list(val)
                    if concise_list:
                        extracted_data[key] = concise_list
                elif isinstance(val, str) and val and val != "无" and val != "[]":
                    concise_list = shorten_text_list([val])
                    if concise_list:
                        extracted_data[key] = concise_list
            print(f"    -> Successfully extracted elements for {scene_name}")
        else:
            print(f"    -> Failed to parse elements JSON for {scene_name}")
    else:
        print(f"    -> LLM failed to return elements for {scene_name}")
        
    return scene_name, extracted_data

def extract_storyline(story_path, scene_target_words=SCENE_TARGET_WORDS):
    print("Start execution")
    
    # 确定输出文件路径并尝试加载断点
    base_name = os.path.splitext(os.path.basename(story_path))[0]
    writer_dir = os.path.dirname(os.path.abspath(__file__))
    outline_dir = os.path.join(writer_dir, "大纲")
    if not os.path.exists(outline_dir):
        os.makedirs(outline_dir)
        
    output_file_path = os.path.join(outline_dir, f"{base_name}.json")
    
    final_result = {}
    if os.path.exists(output_file_path):
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                final_result = json.load(f)
            print(f"Loaded checkpoint from {output_file_path}")
        except Exception as e:
            print(f"Failed to load checkpoint: {e}")

    def save_checkpoint():
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)
        print(f"Checkpoint saved to {output_file_path}")
        
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

    # 2. 加载小说内容
    try:
        with open(story_path, 'r', encoding='utf-8') as f:
            story_content = f.read()
    except Exception as e:
        print(f"Error reading story: {e}")
        return None

    full_story_content = story_content
    full_story_length = len(full_story_content)
    print(f"Story loaded, total length: {full_story_length}")

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

    body_story_length = len(story_content)
    estimated_scene_count = estimate_scene_count(body_story_length, scene_target_words)
    print(
        f"Story stats -> full: {full_story_length}, body: {body_story_length}, "
        f"target scene words: {scene_target_words}, estimated scenes: {estimated_scene_count}"
    )

    # 3. 提取故事线
    if "故事线提取" not in final_result:
        prompt = '''你是一个专业的小说分析助手。
请阅读下面的短篇小说，并提取故事摘要（完整故事线）。

【重要硬性要求】：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称，如：女主、女配、男主、男配、女主生母、男主养父、男主生父等。
2. 必须完整保留所有关键人物身世、过往经历、背景前史，不得省略任何影响主线逻辑的成因与动机。（特别是：失散的完整因果，真假千金/少爷造成的原因）
3. 必须输出为合法的 JSON 格式。
4. 保证逻辑完整、因果清晰，从开端、发展、反转到结局，链条不能断裂。
5. 请根据小说内容，提炼一个抓人眼球的、极具吸引力的短篇小说书名。
6. 提取小说中的核心人物，以列表形式返回。注意：必须且只能使用角色代称（如：女主、女配、男主、男配等），绝对不能出现真实姓名！
7. 提取核心人物的人设特征，返回一个字典，Key 为角色代称，Value 为该角色的核心人设描述（人设需要反差，比如：一个坚定的唯物主义者，为了生病的妻子，戒了所有的荤腥，听到什么寺庙灵验都要去走一遍。在爱人的病痛面前，所有的原则和坚持，都成了可以妥协的小事。当然如果原文人设就设计的不好，没有反差，也没必要硬提）。

【JSON 格式要求】：
请返回以下 JSON 结构：
{
  "书名": "（你生成的小说名，例如：闪婚后婆婆竟是我生母）",
  "核心人物": ["女主", "男主", "女主生母", "男主养父"],
  "人物人设": {
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
        
        if storyline_content:
            try:
                storyline_json = json.loads(storyline_content)
                final_result.update(storyline_json)
                print("Successfully parsed Storyline JSON.")
            except Exception as e:
                print("Failed to parse Storyline JSON:", e)
                match_json = re.search(r'```json\s*(.*?)\s*```', storyline_content, re.DOTALL)
                if match_json:
                    try:
                        storyline_json = json.loads(match_json.group(1))
                        final_result.update(storyline_json)
                        print("Successfully parsed Storyline JSON from markdown.")
                    except Exception as e2:
                        final_result["故事线提取"] = storyline_content
                else:
                    final_result["故事线提取"] = storyline_content
            save_checkpoint()
        else:
            print("Failed to extract storyline.")
            return None
            
    if "故事线提取" not in final_result:
        print("Storyline not found, aborting.")
        return None

    # 4. 场景切分、情绪点提取与结构优化
    if "_scenes_extracted" not in final_result:
        print("Start splitting scenes, extracting emotions and optimizing structure...")
        storyline_str = json.dumps(final_result.get("故事线提取", {}), ensure_ascii=False)
        split_prompt = f'''你是一个专业的小说分析助手与网文主编。请结合以下小说的【完整故事线】和【小说原文】，完成以下两个核心任务：

【任务一：原文问题诊断与结构优化建议】
作为网文主编，请指出原小说在“情绪反差、节奏、信息揭示顺序、人物动机表达”上的问题，并给出优化建议。
优秀的网文情绪依赖于结构反差和反应链，不是简单地说人物很震惊、很难过。请特别关注：关键刺激是否真的落到人物身上，人物是否立刻有动作、嘴硬、试探、失手、决定等可见反应。
请先输出 3 到 5 条简洁的“原文问题诊断”，再给出一个优化后的“情绪结构重构建议”（不要修改核心结局，但可以建议在中间增加哪些拉扯和反差）。

【任务二：基于结构优化的场景切分与情绪点提取】
这篇小说全文共 {full_story_length} 字，去掉引子后的正文共 {body_story_length} 字。请以“每个场景目标约 {scene_target_words} 字”为原则，动态切分为约 {estimated_scene_count} 个极细微的转折点/场景，并将每个场景的“目标字数”“情绪点”“剧情细纲”“情绪推进”合并提取出来。
要求：
1. 绝对不要出现主角或配角的真实姓名，全部统一使用角色代称（如：女主、男主、反派女、男主母亲等），禁止使用任何具体人名。
2. 情绪点写成一句短句，尽量控制在 25 到 50 字，结构为“人物 + 发生了什么 + 内心感受/判断”，简洁但准确。
3. 每个场景额外补充 2 到 4 条“情绪推进”，按时间顺序写清楚“刺激落点 -> 反应 -> 动作/决定 -> 余波/新风险”的台阶。每条 12 到 28 字，必须具体，不能只写“情绪升温”“气氛紧张”。
4. 剧情细纲请以原文真实内容为主，再吸纳【任务一】中的优化方向；可以点到为止地提示一个可增强的反差或拉扯，但不要脱离原文硬编出大段新剧情。
5. 目标字数：直接统计该场景切分到的【参考原文】的实际字数。原文这段是多少字，目标字数就是多少。
6. 参考原文（完整的原文切分）：你必须将【小说原文】**完整地、毫无遗漏地**切分到各个场景的“参考原文”字段中。所有场景的“参考原文”按时间顺序拼接起来，必须与传入的【小说原文】一字不差！绝对不允许只提取片段、概括或省略任何一句话！
7. **严格遵循原文时间线**：你必须从小说原文的**第一段开始，从头到尾、按时间先后顺序**依次提取每一个场景！绝对不允许跳跃、倒叙或打乱事件发生的先后顺序！

【JSON 格式要求】：
请严格返回以下 JSON 结构，并确保它是一个合法的 JSON 对象，不要包含任何 Markdown 标记（如 ```json ）或额外文本。
注意："场景切分与建议"必须是一个**数组（List）**，以严格保证场景的先后顺序与原文发展完全一致！

{{
  "原文问题诊断": [
    "（问题1）",
    "（问题2）"
  ],
  "结构优化建议": "（在这里写出你对小说结构的诊断，以及如何增加反差、期待、破灭等情绪拉扯的具体建议，限300字以内）",
  "场景切分与建议": [
    {{
      "场景名": "初见婆婆审视",
      "目标字数": 190,
      "情绪点": "女主第一次见婆婆，发现婆婆看她的眼神异常古怪，内心充满疑惑、猜测，还有隐隐的不安。",
      "剧情细纲": "女主刚进门，男主母亲用审视的目光打量她，女主内心感到局促不安。",
      "情绪推进": ["婆婆一见面就失态", "女主先稳住场面", "异常反应让女主起疑"],
      "参考原文": "（此处填入该场景对应的完整原文切分，毫无遗漏）"
    }},
    {{
      "场景名": "浏览热帖恐慌",
      "目标字数": 450,
      "情绪点": "女主偶然看到婆婆发的寻亲贴，感到震惊、荒谬，以及对自己身世的恐惧。",
      "剧情细纲": "女主翻看手机时，突然看到了男主母亲发的寻亲热帖，震惊之余不小心打翻了水杯。",
      "情绪推进": ["热帖内容和现实对上", "女主强撑着不露怯", "她意识到事情要失控"],
      "参考原文": "（此处填入该场景对应的完整原文切分，毫无遗漏）"
    }}
  ]
}}

【完整故事线】：
{storyline_str}

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
            
            if isinstance(split_data, list):
                for item in split_data:
                    if isinstance(item, dict):
                        scene_name = item.get("场景名", "")
                        original_text = item.get("参考原文", "")
                        target_words = len(original_text) if original_text else item.get("目标字数", 0)
                        outline = shorten_text(item.get("剧情细纲", ""), max_length=120)
                        emotion_point = shorten_text(item.get("情绪点", ""), max_length=60)
                        emotion_progress = normalize_scene_progress(item.get("情绪推进"))
                        if scene_name:
                            new_split_dict[scene_name] = {
                                "目标字数": target_words,
                                "情绪点": emotion_point,
                                "剧情细纲": outline,
                                "情绪推进": emotion_progress,
                                "参考原文": original_text,
                            }
            elif isinstance(split_data, dict):
                for k, v in split_data.items():
                    if isinstance(v, dict):
                        original_text = v.get("参考原文", "")
                        tw = len(original_text) if original_text else v.get("目标字数", 0)
                        outline = shorten_text(v.get("剧情细纲", ""), max_length=120)
                        emotion_point = shorten_text(v.get("情绪点", ""), max_length=60)
                        emotion_progress = normalize_scene_progress(v.get("情绪推进"))
                        new_split_dict[k] = {
                            "目标字数": tw,
                            "情绪点": emotion_point,
                            "剧情细纲": outline,
                            "情绪推进": emotion_progress,
                            "参考原文": original_text,
                        }
                    elif isinstance(v, (int, str)):
                        try:
                            new_split_dict[k] = {"目标字数": int(v), "情绪点": "", "剧情细纲": "", "参考原文": ""}
                        except:
                            pass
                            
            if new_split_dict:
                final_result["场景切分与建议"] = new_split_dict

        # 清理空数据并标记完成
        final_result = remove_empty_values(final_result)
        final_result["_scenes_extracted"] = True
        save_checkpoint()

    # --- 新增逻辑：对超过 900 字的场景进行二次 LLM 拆分（多线程处理） ---
    if "_large_scenes_processed" not in final_result:
        if "场景切分与建议" in final_result and isinstance(final_result["场景切分与建议"], dict):
            scenes = final_result["场景切分与建议"]
            new_scenes = {}
            needs_update = False
            
            total_words_in_dict = sum([v.get("目标字数", 0) for v in scenes.values() if isinstance(v, dict)])
            current_word_count = 0
            
            import concurrent.futures
            processing_tasks = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for scene_name, scene_data in scenes.items():
                    if not isinstance(scene_data, dict):
                        processing_tasks.append({"type": "normal", "name": scene_name, "data": scene_data})
                        continue
                        
                    target_words = scene_data.get("目标字数", 0)
                    if target_words > SCENE_MAX_WORDS:
                        needs_update = True
                        future = executor.submit(
                            process_large_scene, 
                            scene_name, 
                            scene_data, 
                            total_words_in_dict, 
                            current_word_count, 
                            story_content,
                            scene_target_words
                        )
                        processing_tasks.append({"type": "large", "name": scene_name, "future": future})
                    else:
                        processing_tasks.append({"type": "normal", "name": scene_name, "data": scene_data})
                        
                    current_word_count += target_words
                
                if needs_update:
                    for task in processing_tasks:
                        if task["type"] == "normal":
                            new_scenes[task["name"]] = task["data"]
                        elif task["type"] == "large":
                            try:
                                sub_scenes_list = task["future"].result()
                                for sub_name, sub_data in sub_scenes_list:
                                    new_scenes[sub_name] = sub_data
                            except Exception as e:
                                print(f"Error processing large scene '{task['name']}': {e}")
                                new_scenes[task["name"]] = scenes.get(task["name"], {})
                                
                    final_result["场景切分与建议"] = new_scenes
            final_result["_large_scenes_processed"] = True
            save_checkpoint()

    # --- 新增逻辑：遍历所有场景，针对参考原文逐个调用大模型提取【爽点、钩子、泪点、虐点】 ---
    if "场景切分与建议" in final_result and isinstance(final_result["场景切分与建议"], dict):
        scenes = final_result["场景切分与建议"]
        global_storyline_str = json.dumps(final_result.get("故事线提取", {}), ensure_ascii=False)
        
        needs_elements = []
        for i, (scene_name, scene_data) in enumerate(scenes.items()):
            if not isinstance(scene_data, dict):
                continue
            # 检查是否已经提取过要素
            if all(k in scene_data for k in ELEMENT_KEYS):
                continue
                
            original_text = scene_data.get("参考原文", "")
            if not original_text or len(original_text) < 20:
                continue
                
            needs_elements.append((scene_name, original_text, i + 1))
            
        if needs_elements:
            print(f"\nStart extracting elements (爽点/钩子/泪点/虐点) for {len(needs_elements)} scenes...")
            import concurrent.futures
            element_tasks = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for scene_name, original_text, idx in needs_elements:
                    future = executor.submit(
                        extract_scene_elements,
                        scene_name,
                        original_text,
                        global_storyline_str,
                        idx,
                        len(scenes)
                    )
                    element_tasks.append((scene_name, future))
                
                for scene_name, future in element_tasks:
                    try:
                        _, extracted_data = future.result()
                        if extracted_data:
                            scenes[scene_name].update(extracted_data)
                            # 每次成功提取后保存断点，防止意外中断丢失进度
                            save_checkpoint()
                    except Exception as e:
                        print(f"Error extracting elements for '{scene_name}': {e}")
                        
    # 移除不需要的多余字段
    if "字数统计总结" in final_result:
        del final_result["字数统计总结"]
        
    save_checkpoint()
    print(f"Success! Final combined JSON written to {output_file_path}")
    return output_file_path

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Novel Extractor")
    parser.add_argument("txt_path", nargs="?", default=r"e:\worksapce\short_stories\writer\《DNA骗局：总裁的契约娇妻》.txt", help="Path to the input TXT file")
    parser.add_argument("--scene-target-words", type=int, default=SCENE_TARGET_WORDS, help="Target words per extracted scene")
    
    args = parser.parse_args()
    
    extract_storyline(args.txt_path, scene_target_words=max(200, args.scene_target_words))
