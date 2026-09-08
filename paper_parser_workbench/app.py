"""
学术文献解析与报告生成 Harness 工台
主界面：UI交互、文件上传、结果展示、文件导出
"""
import streamlit as st
import tempfile
import os
from datetime import datetime

# 导入自定义模块
from parser import parse_document, generate_review_with_llm
from visualizer import display_wordcloud_in_streamlit, display_keyword_table, create_stats_chart
from exporter import export_to_docx, get_download_filename


# 页面配置
st.set_page_config(
    page_title="学术文献解析与报告生成系统",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 自定义CSS样式 - 师大红主题
st.markdown("""
<style>
    /* 主色调定义 */
    :root {
        --primary-red: #C8102E;
        --light-red: #FFE8EC;
        --dark-red: #A00D24;
        --text-dark: #333333;
        --text-gray: #666666;
        --bg-light: #F8F9FA;
    }
    
    /* 全局样式 */
    .stApp {
        background-color: #FFFFFF;
    }
    
    /* 顶部导航栏 */
    header[data-testid="stHeader"] {
        background-color: var(--primary-red);
    }
    
    /* 主标题样式 */
    .main-title {
        color: var(--primary-red);
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        padding: 1rem 0;
        border-bottom: 3px solid var(--primary-red);
        margin-bottom: 2rem;
    }
    
    /* 副标题样式 */
    .section-title {
        color: var(--primary-red);
        font-size: 1.5rem;
        font-weight: bold;
        padding: 0.5rem 0;
        border-left: 4px solid var(--primary-red);
        padding-left: 1rem;
        margin: 1.5rem 0 1rem 0;
    }
    
    /* 卡片容器 */
    .card {
        background-color: var(--bg-light);
        border-radius: 8px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #E0E0E0;
    }
    
    /* 按钮样式 */
    .stButton > button {
        background-color: var(--primary-red);
        color: white;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 2rem;
        font-weight: bold;
        transition: background-color 0.3s;
    }
    
    .stButton > button:hover {
        background-color: var(--dark-red);
    }
    
    /* 信息框样式 */
    .info-box {
        background-color: var(--light-red);
        border-left: 4px solid var(--primary-red);
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    
    /* 统计指标卡片 */
    .metric-card {
        background-color: white;
        border: 2px solid var(--primary-red);
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: var(--primary-red);
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: var(--text-gray);
    }
    
    /* 文件上传区域 */
    .uploadedFile {
        border: 2px dashed var(--primary-red);
        border-radius: 8px;
        padding: 2rem;
        text-align: center;
    }
    
    /* 文本预览框 */
    .text-preview {
        background-color: #FAFAFA;
        border: 1px solid #E0E0E0;
        border-radius: 4px;
        padding: 1rem;
        max-height: 400px;
        overflow-y: auto;
        font-family: monospace;
        font-size: 0.9rem;
        line-height: 1.6;
    }
    
    /* 侧边栏样式 */
    [data-testid="stSidebar"] {
        background-color: var(--bg-light);
    }
    
    /* 隐藏Streamlit默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化会话状态"""
    if 'parsed_data' not in st.session_state:
        st.session_state.parsed_data = None
    if 'file_uploaded' not in st.session_state:
        st.session_state.file_uploaded = False
    if 'file_name' not in st.session_state:
        st.session_state.file_name = None


def render_header():
    """渲染页面头部"""
    st.markdown("""
    <div class="main-title">
        📄 学术文献解析与报告生成系统
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style="text-align: center; color: #666666; margin-bottom: 2rem;">
        上传学术文献，自动提取关键信息，生成可视化分析报告
    </div>
    """, unsafe_allow_html=True)


def render_upload_section():
    """渲染文件上传区域"""
    st.markdown('<div class="section-title">📁 文献上传</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "选择文献文件",
            type=['pdf', 'docx'],
            help="支持PDF和DOCX格式的学术文献",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            st.session_state.file_uploaded = True
            st.session_state.file_name = uploaded_file.name
            
            # 显示文件信息
            file_details = {
                "文件名": uploaded_file.name,
                "文件大小": f"{uploaded_file.size / 1024:.2f} KB",
                "文件类型": uploaded_file.type
            }
            st.json(file_details)
            
            return uploaded_file
    
    with col2:
        st.markdown("""
        <div class="info-box">
            <strong>支持格式：</strong><br>
            • PDF 文档<br>
            • DOCX 文档<br><br>
            <strong>功能说明：</strong><br>
            • 自动提取标题、作者、摘要<br>
            • 生成关键词词云图<br>
            • 导出文献阅读笔记
        </div>
        """, unsafe_allow_html=True)
    
    return None


def render_analysis_button():
    """渲染分析按钮"""
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 开始解析分析", use_container_width=True):
            return True
    return False


def render_results_section(parsed_data):
    """渲染分析结果"""
    st.markdown("---")
    st.markdown('<div class="section-title">📊 分析结果</div>', unsafe_allow_html=True)
    
    metadata = parsed_data['metadata']
    keywords = parsed_data['keywords']
    stats = parsed_data['stats']
    
    # 元数据展示
    st.markdown("### 📋 文档信息")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class="card">
            <strong>标题：</strong>{metadata.get('title', '未识别')}<br>
            <strong>作者：</strong>{metadata.get('authors', '未识别')}<br>
            <strong>关键词：</strong>{metadata.get('keywords', '未识别')}
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="card">
            <strong>摘要：</strong><br>
            {metadata.get('abstract', '未识别摘要')}
        </div>
        """, unsafe_allow_html=True)
    
    # 统计指标
    st.markdown("### 📈 文本统计")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['char_count']:,}</div>
            <div class="metric-label">总字符数</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['word_count']:,}</div>
            <div class="metric-label">总词数</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['paragraph_count']}</div>
            <div class="metric-label">段落数</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 词云图
    st.markdown("### ☁️ 关键词词云")
    display_wordcloud_in_streamlit(keywords, "高频关键词词云")
    
    # 关键词表格
    st.markdown("### 📝 关键词详情")
    display_keyword_table(keywords, top_k=15)


def render_text_preview(cleaned_text):
    """渲染文本预览"""
    st.markdown('<div class="section-title">📖 正文预览</div>', unsafe_allow_html=True)
    
    with st.expander("点击展开/收起正文内容", expanded=False):
        st.markdown(f"""
        <div class="text-preview">
            {cleaned_text[:5000]}{'...' if len(cleaned_text) > 5000 else ''}
        </div>
        """, unsafe_allow_html=True)
        
        st.caption(f"显示前5000字符，共{len(cleaned_text):,}字符")


def render_conclusions(metadata):
    """渲染核心结论"""
    conclusions = metadata.get('conclusions', '')
    if conclusions:
        st.markdown('<div class="section-title">💡 核心结论</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="card">
            {conclusions}
        </div>
        """, unsafe_allow_html=True)


def render_export_section(parsed_data):
    """渲染导出区域"""
    st.markdown("---")
    st.markdown('<div class="section-title">📥 导出报告</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 导出文献阅读笔记")
        st.markdown("包含摘要、关键词、要点摘录、核心结论等完整内容")
        
        # 生成docx文件
        docx_buffer = export_to_docx(
            metadata=parsed_data['metadata'],
            abstract=parsed_data['metadata'].get('abstract', ''),
            keywords=parsed_data['keywords'],
            conclusions=parsed_data['metadata'].get('conclusions', ''),
            text=parsed_data['cleaned_text']
        )
        
        filename = get_download_filename(parsed_data['metadata'])
        
        st.download_button(
            label="📄 下载DOCX笔记",
            data=docx_buffer,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
    
    with col2:
        st.markdown("### AI文献评述")
        st.markdown("预留API接口，可接入大模型自动生成文献评述")
        
        # 预留API调用入口
        if st.button("🤖 生成AI评述（预留功能）", use_container_width=True):
            with st.spinner("正在调用AI接口..."):
                review = generate_review_with_llm(parsed_data['cleaned_text'])
                st.info(review)


def render_api_section():
    """渲染API配置区域（预留）"""
    with st.sidebar:
        st.markdown('<div class="section-title">⚙️ API配置</div>', unsafe_allow_html=True)
        
        api_key = st.text_input(
            "API Key",
            type="password",
            help="用于接入大模型API（预留功能）"
        )
        
        api_provider = st.selectbox(
            "API提供商",
            ["智谱AI", "OpenAI", "其他"],
            help="选择要接入的大模型API"
        )
        
        if api_key:
            st.success("API Key 已配置")
            st.session_state.api_key = api_key
            st.session_state.api_provider = api_provider


def main():
    """主函数"""
    # 初始化
    init_session_state()
    
    # 渲染页面
    render_header()
    
    # API配置（侧边栏）
    render_api_section()
    
    # 文件上传
    uploaded_file = render_upload_section()
    
    # 处理上传的文件
    if uploaded_file is not None:
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
        
        try:
            # 解析按钮
            if render_analysis_button():
                with st.spinner("正在解析文档，请稍候..."):
                    # 调用解析模块
                    parsed_data = parse_document(tmp_file_path)
                    st.session_state.parsed_data = parsed_data
                    
                    # 显示成功消息
                    st.success("✅ 文档解析完成！")
                    st.rerun()
            
            # 显示结果（如果已解析）
            if st.session_state.parsed_data is not None:
                render_results_section(st.session_state.parsed_data)
                render_text_preview(st.session_state.parsed_data['cleaned_text'])
                render_conclusions(st.session_state.parsed_data['metadata'])
                render_export_section(st.session_state.parsed_data)
        
        finally:
            # 清理临时文件
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    # 页脚
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #999999; padding: 2rem;">
        学术文献解析与报告生成系统 | 课程作业项目<br>
        技术支持：Streamlit + jieba + python-docx
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
