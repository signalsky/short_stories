# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template, redirect, send_from_directory
from flask_cors import CORS
import json
import os
import subprocess
from story_exporter import export_story

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
EXPORT_DIR = os.path.join(WRITER_DIR, '导出')

# 确保必要的目录存在
os.makedirs(OUTLINE_DIR, exist_ok=True)
os.makedirs(REWRITE_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# 记录正在运行的生成任务进程 { outline_filename: subprocess.Popen }
active_generate_processes = {}

@app.route('/')
def index():
    """提供前端静态页面，默认重定向到提取大纲"""
    return redirect('/workspace/extract')

@app.route('/workspace/<tab>')
def workspace(tab):
    """工作台路由，支持 restful 的标签页"""
    if tab not in ['extract', 'write', 'export', 'config']:
        tab = 'extract'
    return render_template('index.html', active_tab=tab)

@app.route('/extract')
def extract_page():
    """提供提取大纲页面"""
    return render_template('extract.html')

@app.route('/write')
def write_page():
    """提供生成小说页面"""
    return render_template('write.html')

@app.route('/export')
def export_page():
    """提供小说导出页面"""
    return render_template('export.html')

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

@app.route('/api/outlines/<filename>', methods=['DELETE'])
def delete_outline(filename):
    """删除指定大纲文件"""
    try:
        filepath = os.path.join(OUTLINE_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"message": "File deleted successfully"})
        else:
            return jsonify({"error": "File not found"}), 404
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

@app.route('/api/rewrites/<filename>', methods=['DELETE'])
def delete_rewrite(filename):
    """删除指定重写文件及对应的 txt 文件"""
    try:
        filepath = os.path.join(REWRITE_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            
            # 尝试删除对应的 txt 文件
            txt_filename = filename.replace('_进度.json', '.txt')
            txt_filepath = os.path.join(REWRITE_DIR, txt_filename)
            if os.path.exists(txt_filepath):
                os.remove(txt_filepath)
                
            return jsonify({"message": "File deleted successfully"})
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def start_generation():
    """选择大纲并启动生成脚本"""
    try:
        data = request.json
        outline_filename = data.get('outline_filename')
        instruction = data.get('instruction', '')
        
        if not outline_filename:
            return jsonify({"error": "No outline selected"}), 400
            
        # 如果当前大纲正在生成中，直接返回
        if outline_filename in active_generate_processes:
            return jsonify({"error": "该小说正在生成中，请先停止或等待完成"}), 400
            
        outline_path = os.path.join(OUTLINE_DIR, outline_filename)
        if not os.path.exists(outline_path):
            return jsonify({"error": "Selected outline file not found"}), 404
        
        # 调用 story_writer.py
        writer_script = os.path.join(WRITER_DIR, 'story_writer.py')
        
        # 为了解决 Windows 下可能出现的终端编码问题，这里强制使用 utf-8 运行 python 并捕获输出
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        cmd = ['python', writer_script, outline_path]
        if instruction:
            cmd.extend(['--instruction', instruction])
            
        # 使用 subprocess.Popen 启动进程，以便支持打断
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        # 记录进程
        active_generate_processes[outline_filename] = process
        
        # 阻塞等待进程完成
        stdout_bytes, stderr_bytes = process.communicate()
        
        # 手动解码，忽略错误
        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
        
        returncode = process.returncode
        
        # 进程结束后移除记录
        if outline_filename in active_generate_processes:
            del active_generate_processes[outline_filename]
            
        # 判断是被手动打断还是发生了错误
        if returncode != 0:
            # 可能是手动 terminate (负数)，或者是 python 脚本内部 exit(1)
            if returncode < 0 or "Generation aborted due to repeated failures" in stdout or "Generation aborted due to repeated failures" in stderr:
                return jsonify({"error": "生成已中断或失败", "logs": stdout + "\n" + stderr}), 500
            else:
                return jsonify({"error": f"Generation failed with code {returncode}", "logs": stderr}), 500
            
        # 尝试推断生成的进度文件名返回给前端
        safe_title = outline_filename.replace('.json', '')
        import re
        safe_title = re.sub(r'[\\/*?:"<>|]', "", safe_title)
        expected_progress_file = f"{safe_title}_进度.json"
            
        return jsonify({
            "message": "Generation completed successfully", 
            "logs": stdout,
            "progress_file": expected_progress_file
        })
        
    except Exception as e:
        # 清理可能残留的记录
        if 'outline_filename' in locals() and outline_filename in active_generate_processes:
            del active_generate_processes[outline_filename]
        return jsonify({"error": str(e)}), 500

@app.route('/api/cancel_generate', methods=['POST'])
def cancel_generation():
    """中断生成过程"""
    try:
        data = request.json
        outline_filename = data.get('outline_filename')
        
        if not outline_filename:
            return jsonify({"error": "No outline specified"}), 400
            
        if outline_filename in active_generate_processes:
            process = active_generate_processes[outline_filename]
            # 终止进程
            process.terminate()
            del active_generate_processes[outline_filename]
            return jsonify({"message": "已成功中断生成过程"})
        else:
            return jsonify({"message": "未找到正在运行的生成任务"})
            
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
            
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        stdout_bytes, stderr_bytes = process.communicate()
        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
            
        if process.returncode != 0:
            return jsonify({"error": "Scene rewrite failed", "logs": stderr}), 500
            
        return jsonify({"message": "Scene rewritten successfully", "logs": stdout})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/export_novel', methods=['POST'])
def export_novel():
    """根据重写进度文件导出整理后的小说 TXT"""
    try:
        data = request.json or {}
        filename = data.get('filename')
        prologue_words = int(data.get('prologue_words', 180) or 180)

        if not filename:
            return jsonify({"error": "No progress file selected"}), 400

        if not filename.endswith('_进度.json'):
            return jsonify({"error": "Invalid progress filename"}), 400

        progress_path = os.path.join(REWRITE_DIR, filename)
        if not os.path.exists(progress_path):
            return jsonify({"error": "Progress file not found"}), 404

        result = export_story(progress_path, prologue_words=max(80, prologue_words))
        return jsonify({
            "message": "Export completed successfully",
            **result
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exports', methods=['GET'])
def list_exports():
    """获取所有导出的小说 txt 文件列表"""
    try:
        files = [f for f in os.listdir(EXPORT_DIR) if f.endswith('.txt')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(EXPORT_DIR, x)), reverse=True)
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exports/<filename>', methods=['GET'])
def get_export(filename):
    """获取指定导出小说的内容"""
    try:
        if not filename.endswith('.txt'):
            return jsonify({"error": "Invalid export filename"}), 400

        filepath = os.path.join(EXPORT_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            "filename": filename,
            "title": filename[:-4],
            "content": content,
            "path": filepath
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exports/<filename>', methods=['POST'])
def save_export(filename):
    """保存编辑后的导出小说内容"""
    try:
        if not filename.endswith('.txt'):
            return jsonify({"error": "Invalid export filename"}), 400

        filepath = os.path.join(EXPORT_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404

        data = request.json or {}
        content = data.get("content", "")
        if not isinstance(content, str):
            return jsonify({"error": "Invalid content"}), 400

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({"message": "Success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exports/<filename>', methods=['DELETE'])
def delete_export(filename):
    """删除指定导出小说"""
    try:
        if not filename.endswith('.txt'):
            return jsonify({"error": "Invalid export filename"}), 400

        filepath = os.path.join(EXPORT_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404

        os.remove(filepath)
        return jsonify({"message": "File deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exports/<filename>/download', methods=['GET'])
def download_export(filename):
    """下载导出小说"""
    try:
        if not filename.endswith('.txt'):
            return jsonify({"error": "Invalid export filename"}), 400

        filepath = os.path.join(EXPORT_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404

        return send_from_directory(EXPORT_DIR, filename, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"Starting Web Server...")
    print(f"Frontend URL: http://127.0.0.1:5000/")
    print(f"Config Path: {CONFIG_FILE}")
    # 设置 host='0.0.0.0' 以允许外部访问
    app.run(host='0.0.0.0', port=5000, debug=True)
