# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
import subprocess

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 禁用 Flask 默认的 JSON 键排序，保证前端显示的顺序与文件一致
app.config['JSON_SORT_KEYS'] = False
if hasattr(app, 'json'):
    app.json.sort_keys = False

# 统一配置文件路径
WRITER_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WRITER_DIR, 'config.json')
OUTLINE_DIR = os.path.join(WRITER_DIR, '大纲')
REWRITE_DIR = os.path.join(WRITER_DIR, '重写')

# 确保必要的目录存在
os.makedirs(OUTLINE_DIR, exist_ok=True)
os.makedirs(REWRITE_DIR, exist_ok=True)

@app.route('/')
def index():
    """提供前端静态页面"""
    return render_template('index.html')

@app.route('/extract')
def extract_page():
    """提供提取大纲页面"""
    return render_template('extract.html')

@app.route('/write')
def write_page():
    """提供生成小说页面"""
    return render_template('write.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """读取配置文件"""
    if not os.path.exists(CONFIG_FILE):
        # 如果文件不存在，返回默认配置
        return jsonify({
            "api_key": "",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3.5-plus"
        })
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return jsonify(config)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """保存配置文件"""
    try:
        new_config = request.json
        
        # 确保 writer 目录存在
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)
            
        return jsonify({"message": "Success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines', methods=['GET'])
def list_outlines():
    """获取所有大纲文件列表"""
    try:
        files = [f for f in os.listdir(OUTLINE_DIR) if f.endswith('.json')]
        # 按照修改时间排序，最新的在前面
        files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTLINE_DIR, x)), reverse=True)
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines/<filename>', methods=['GET'])
def get_outline(filename):
    """获取指定大纲的内容"""
    try:
        filepath = os.path.join(OUTLINE_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/outlines/<filename>', methods=['POST'])
def save_outline(filename):
    """保存编辑后的大纲内容"""
    try:
        data = request.json
        filepath = os.path.join(OUTLINE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"message": "Success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/extract', methods=['POST'])
def start_extraction():
    """上传TXT并调用抽取脚本"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        # 将上传的文件保存到临时目录
        temp_dir = os.path.join(WRITER_DIR, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        
        # 调用 story_extractor.py
        extractor_script = os.path.join(WRITER_DIR, 'story_extractor.py')
        
        # 使用 subprocess 运行脚本，并捕获输出
        # 注意：实际生产中这应该是异步任务，这里为了简化先做同步阻塞调用
        result = subprocess.run(
            ['python', extractor_script, temp_path],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        # 尝试清理临时文件
        try:
            os.remove(temp_path)
        except:
            pass
            
        if result.returncode != 0:
            return jsonify({"error": f"Extraction failed", "logs": result.stderr}), 500
            
        return jsonify({"message": "Extraction completed successfully", "logs": result.stdout})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rewrites', methods=['GET'])
def list_rewrites():
    """获取所有重写进度文件列表"""
    try:
        files = [f for f in os.listdir(REWRITE_DIR) if f.endswith('_进度.json')]
        # 按照修改时间排序，最新的在前面
        files.sort(key=lambda x: os.path.getmtime(os.path.join(REWRITE_DIR, x)), reverse=True)
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rewrites/<filename>', methods=['GET'])
def get_rewrite(filename):
    """获取指定重写进度的内容"""
    try:
        filepath = os.path.join(REWRITE_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rewrites/<filename>', methods=['POST'])
def save_rewrite(filename):
    """保存编辑后的重写内容"""
    try:
        data = request.json
        filepath = os.path.join(REWRITE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # 同步更新对应的 txt 文件
        try:
            txt_filename = filename.replace('_进度.json', '.txt')
            txt_filepath = os.path.join(REWRITE_DIR, txt_filename)
            paragraphs = data.get("generated_paragraphs", [])
            final_story_text = "\n\n".join(paragraphs)
            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write(final_story_text)
        except Exception as txt_e:
            print(f"Warning: Failed to update txt file: {txt_e}")
            
        return jsonify({"message": "Success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def start_generation():
    """选择大纲并启动生成脚本"""
    try:
        data = request.json
        outline_filename = data.get('outline_filename')
        
        if not outline_filename:
            return jsonify({"error": "No outline selected"}), 400
            
        outline_path = os.path.join(OUTLINE_DIR, outline_filename)
        if not os.path.exists(outline_path):
            return jsonify({"error": "Selected outline file not found"}), 404
        
        # 调用 story_writer.py
        writer_script = os.path.join(WRITER_DIR, 'story_writer.py')
        
        # 使用 subprocess 运行脚本，并捕获输出
        # 注意：实际生产中这应该是异步任务，这里为了简化先做同步阻塞调用
        result = subprocess.run(
            ['python', writer_script, outline_path],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
            
        if result.returncode != 0:
            return jsonify({"error": f"Generation failed", "logs": result.stderr}), 500
            
        # 尝试推断生成的进度文件名返回给前端
        safe_title = outline_filename.replace('.json', '')
        import re
        safe_title = re.sub(r'[\\/*?:"<>|]', "", safe_title)
        expected_progress_file = f"{safe_title}_进度.json"
            
        return jsonify({
            "message": "Generation completed successfully", 
            "logs": result.stdout,
            "progress_file": expected_progress_file
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rewrite_scene', methods=['POST'])
def rewrite_single_scene():
    """重写指定的单个场景"""
    try:
        data = request.json
        filename = data.get('filename')  # _进度.json 文件名
        scene_index = data.get('scene_index')  # 基于 0 的索引
        context_level = data.get('context_level', 2)
        instruction = data.get('instruction', '')
        
        if not filename or scene_index is None:
            return jsonify({"error": "Missing parameters"}), 400
            
        # 根据进度文件名推导大纲文件名
        outline_filename = filename.replace('_进度.json', '.json')
        outline_path = os.path.join(OUTLINE_DIR, outline_filename)
        
        if not os.path.exists(outline_path):
            return jsonify({"error": "Original outline not found"}), 404
            
        writer_script = os.path.join(WRITER_DIR, 'story_writer.py')
        
        # 调用 subprocess，传入单段重写所需的参数
        # 注意传给脚本的 scene 是 1-based index，所以要 +1
        cmd = [
            'python', writer_script, outline_path,
            '--scene', str(scene_index + 1),
            '--context', str(context_level)
        ]
        
        if instruction:
            cmd.extend(['--instruction', instruction])
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
            
        if result.returncode != 0:
            return jsonify({"error": "Scene rewrite failed", "logs": result.stderr}), 500
            
        return jsonify({"message": "Scene rewritten successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"Starting Web Server...")
    print(f"Frontend URL: http://127.0.0.1:5000/")
    print(f"Config Path: {CONFIG_FILE}")
    # 设置 host='0.0.0.0' 以允许外部访问
    app.run(host='0.0.0.0', port=5000, debug=True)