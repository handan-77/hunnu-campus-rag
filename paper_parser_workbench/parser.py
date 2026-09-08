"""
文档解析模块
功能：解析PDF和DOCX文档，提取元数据和正文内容
"""
import re
import jieba
import jieba.analyse
from typing import Dict, List, Tuple, Optional
import pdfplumber
from docx import Document


def extract_text_from_pdf(file_path: str) -> str:
    """从PDF文件提取文本内容"""
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF解析错误: {e}")
    return text


def extract_text_from_docx(file_path: str) -> str:
    """从DOCX文件提取文本内容"""
    text = ""
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
    except Exception as e:
        print(f"DOCX解析错误: {e}")
    return text


def clean_text(text: str) -> str:
    """清洗文本，去除多余空白和特殊字符"""
    # 去除多余空白
    text = re.sub(r'\s+', ' ', text)
    # 去除特殊字符，保留中文、英文、数字和基本标点
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、；：""''（）\[\]【】\-—…\s]', '', text)
    return text.strip()


def extract_metadata(text: str) -> Dict[str, str]:
    """提取文档元数据：标题、作者、摘要、关键词、主要结论"""
    metadata = {
        "title": "",
        "authors": "",
        "abstract": "",
        "keywords": "",
        "conclusions": ""
    }
    
    lines = text.split('\n')
    
    # 提取标题（通常在前几行，且长度适中）
    for i, line in enumerate(lines[:10]):
        line = line.strip()
        if len(line) > 5 and len(line) < 100 and not re.search(r'[a-zA-Z]', line[:3]):
            metadata["title"] = line
            break
    
    # 提取摘要
    abstract_pattern = r'(?:摘要|摘\s*要|Abstract)[：:]\s*(.*?)(?:关键词|Keywords|Key\s*words|$)'
    abstract_match = re.search(abstract_pattern, text, re.DOTALL | re.IGNORECASE)
    if abstract_match:
        metadata["abstract"] = abstract_match.group(1).strip()[:500]
    
    # 提取关键词
    keywords_pattern = r'(?:关键词|Keywords|Key\s*words)[：:]\s*(.*?)(?:\n|$)'
    keywords_match = re.search(keywords_pattern, text, re.IGNORECASE)
    if keywords_match:
        keywords_text = keywords_match.group(1).strip()
        # 清理关键词
        keywords_text = re.sub(r'[;；,，、]', '；', keywords_text)
        metadata["keywords"] = keywords_text
    
    # 提取作者（在标题附近寻找）
    author_pattern = r'(?:作者|Author|By)[：:]\s*(.*?)(?:\n|$)'
    author_match = re.search(author_pattern, text[:2000], re.IGNORECASE)
    if author_match:
        metadata["authors"] = author_match.group(1).strip()
    else:
        # 尝试从标题后寻找可能的作者信息
        for i, line in enumerate(lines[:15]):
            if metadata["title"] in line:
                for j in range(i+1, min(i+5, len(lines))):
                    if re.search(r'[\u4e00-\u9fa5]{2,4}(?:\s|,|，|;|；|和|与|&)', lines[j]) and len(lines[j]) < 50:
                        metadata["authors"] = lines[j].strip()
                        break
                break
    
    # 提取主要结论
    conclusion_pattern = r'(?:结论|Conclusion|总结)[：:]\s*(.*?)(?:致谢|参考文献|References|Appendix|$)'
    conclusion_match = re.search(conclusion_pattern, text, re.DOTALL | re.IGNORECASE)
    if conclusion_match:
        metadata["conclusions"] = conclusion_match.group(1).strip()[:500]
    
    return metadata


def extract_keywords_with_jieba(text: str, top_k: int = 15) -> List[Tuple[str, float]]:
    """使用jieba提取关键词和权重"""
    # 使用TF-IDF算法提取关键词
    keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
    return keywords


def calculate_text_stats(text: str) -> Dict[str, int]:
    """计算文本统计指标"""
    # 去除空白后计算字符数
    clean_text_no_space = re.sub(r'\s', '', text)
    char_count = len(clean_text_no_space)
    
    # 按段落分割计算段落数
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    paragraph_count = len(paragraphs)
    
    # 按空格分割计算词数（中文按字符，英文按空格）
    word_count = 0
    for para in paragraphs:
        # 中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', para))
        # 英文单词数
        english_words = len(re.findall(r'[a-zA-Z]+', para))
        word_count += chinese_chars + english_words
    
    return {
        "char_count": char_count,
        "word_count": word_count,
        "paragraph_count": paragraph_count
    }


def parse_document(file_path: str) -> Dict:
    """主解析函数：解析文档并返回所有提取信息"""
    # 根据文件类型提取文本
    if file_path.lower().endswith('.pdf'):
        raw_text = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.docx'):
        raw_text = extract_text_from_docx(file_path)
    else:
        raise ValueError("不支持的文件格式，请上传PDF或DOCX文件")
    
    # 清洗文本
    cleaned_text = clean_text(raw_text)
    
    # 提取元数据
    metadata = extract_metadata(raw_text)
    
    # 提取关键词
    keywords = extract_keywords_with_jieba(cleaned_text, top_k=15)
    
    # 计算文本统计
    stats = calculate_text_stats(cleaned_text)
    
    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "metadata": metadata,
        "keywords": keywords,
        "stats": stats
    }


# 预留API调用入口：用于后续接入大模型自动生成文献评述
def generate_review_with_llm(text: str, api_key: str = None) -> str:
    """
    预留接口：调用大模型生成文献评述
    参数：
        text: 文档文本
        api_key: API密钥
    返回：
        生成的文献评述文本
    """
    # TODO: 接入大模型API（如OpenAI、智谱等）
    # 示例代码结构：
    # import openai
    # openai.api_key = api_key
    # response = openai.ChatCompletion.create(
    #     model="gpt-3.5-turbo",
    #     messages=[
    #         {"role": "system", "content": "你是一个学术文献分析助手"},
    #         {"role": "user", "content": f"请分析以下文献并生成评述：{text[:2000]}"}
    #     ]
    # )
    # return response.choices[0].message.content
    
    return "【API调用入口】请在此处接入大模型API，自动生成文献评述。"
