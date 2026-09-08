# 学术文献解析与报告生成系统

基于 Streamlit 的学术文献解析与报告生成 Harness 工作台，课程作业项目。

## 功能特性

- 支持 PDF、DOCX 格式文献上传
- 自动提取标题、作者、摘要、关键词、主要结论
- jieba 分词生成关键词词云图
- 文本预览与统计分析
- 一键导出 docx 文献阅读笔记
- 预留大模型 API 调用接口

## 项目结构

```
paper_parser_workbench/
├── app.py              # 主应用文件（UI交互模块）
├── parser.py           # 文档解析模块
├── visualizer.py       # 可视化模块
├── exporter.py         # 文档导出模块
├── requirements.txt    # 依赖清单
├── start.bat           # Windows启动脚本
└── README.md           # 项目说明
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动应用

**Windows:**
```bash
start.bat
```

**或直接运行:**
```bash
streamlit run app.py
```

### 3. 访问应用

打开浏览器访问: http://localhost:8501

## 模块说明

### parser.py - 文档解析模块
- `extract_text_from_pdf()`: PDF文本提取
- `extract_text_from_docx()`: DOCX文本提取
- `extract_metadata()`: 元数据提取
- `extract_keywords_with_jieba()`: jieba关键词提取
- `generate_review_with_llm()`: 预留AI评述接口

### visualizer.py - 可视化模块
- `generate_wordcloud()`: 词云图生成
- `display_wordcloud_in_streamlit()`: Streamlit词云展示
- `display_keyword_table()`: 关键词表格展示

### exporter.py - 文档导出模块
- `export_to_docx()`: 导出docx文献笔记
- `get_download_filename()`: 生成下载文件名

## 主色调

师大红 #C8102E

## 技术栈

- Streamlit - Web UI框架
- jieba - 中文分词
- pdfplumber - PDF解析
- python-docx - DOCX生成
- wordcloud - 词云生成
- matplotlib - 可视化
