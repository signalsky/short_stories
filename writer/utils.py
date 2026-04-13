# -*- coding: utf-8 -*-
import json
import os
import subprocess
import re

def load_config():
    """加载 writer 目录下的 config.json"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading config at {config_path}: {e}")
        return {}

def call_dashscope_api(prompt, system_prompt="你是一个专业的小说分析Agent。"):
    """通用的 DashScope API 调用函数"""
    config = load_config()
    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model = config.get("model", "qwen3.5-plus")
    
    if not api_key or not base_url:
        print("Missing API key or base URL in config.")
        return None

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }
    
    import urllib.request
    import urllib.error
    
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 使用随机的 payload 文件名防止并发冲突
    import tempfile
    import uuid
    temp_dir = tempfile.gettempdir()
    payload_file = os.path.join(temp_dir, f"writer_payload_{uuid.uuid4().hex}.json")
    
    try:
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
        
        if result_process.returncode != 0:
            print(f"Error during curl call: {result_process.stderr}")
            return None
            
        result = json.loads(result_process.stdout)
        if "choices" in result and len(result["choices"]) > 0:
            return result['choices'][0]['message']['content']
        else:
            print("API Response format error:", result)
            return None
            
    except json.JSONDecodeError:
        print("Failed to decode JSON from curl stdout.")
        return None
    except Exception as e:
        print(f"Unexpected error in API call: {e}")
        return None
    finally:
        if os.path.exists(payload_file):
            try:
                os.remove(payload_file)
            except:
                pass

def clean_and_parse_json(text):
    """通用的 JSON 清理和解析函数"""
    if not text:
        return None
        
    # 尝试提取 markdown 包裹的 json
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
        
    # 尝试修复大模型经常犯的括号错误
    text = re.sub(r'("关键场景情绪"\s*:\s*\{[^\}]*?)\s*\]', r'\1}', text, flags=re.DOTALL)
    text = re.sub(r'\}\s*\]', '} }', text)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试使用 json_repair 库（如果有的话）
        try:
            import json_repair
            return json_repair.loads(text)
        except:
            return None