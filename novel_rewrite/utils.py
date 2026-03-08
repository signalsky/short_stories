import re

def format_novel_text(text: str) -> str:
    """
    格式化小说文本：
    1. 去除多余空行
    2. 合并被错误断行的段落（非标点结尾的行自动合并）
    3. 统一段落间距（段与段之间空一行）
    4. 去除行首尾空格
    """
    if not text:
        return ""
        
    lines = text.splitlines()
    formatted_paragraphs = []
    current_paragraph = []
    
    # 标点符号集合，用于判断是否自然段结束
    # 包含中文和英文的常见结束符，以及引号（可能是对话结束）
    sentence_endings = {'。', '！', '？', '…', '”', '"', '.', '!', '?'}
    
    for line in lines:
        line = line.strip()
        if not line:
            # 空行表示段落分隔
            if current_paragraph:
                formatted_paragraphs.append("".join(current_paragraph))
                current_paragraph = []
            continue
            
        if current_paragraph:
            prev_line = current_paragraph[-1]
            if not prev_line: # Should not happen due to logic above but safety check
                current_paragraph.append(line)
            else:
                # 检查上一行是否以结束符结尾
                if prev_line[-1] in sentence_endings:
                    # 上一行是完整句子，当前行另起一段
                    formatted_paragraphs.append("".join(current_paragraph))
                    current_paragraph = [line]
                else:
                    # 上一行不是完整句子，合并当前行
                    current_paragraph.append(line)
        else:
            current_paragraph = [line]
            
    # 处理最后一个段落
    if current_paragraph:
        formatted_paragraphs.append("".join(current_paragraph))
        
    # 统一用双换行符连接段落
    return "\n\n".join(formatted_paragraphs)
