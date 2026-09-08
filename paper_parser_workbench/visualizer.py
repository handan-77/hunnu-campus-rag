"""
可视化模块
功能：生成词云图等可视化内容
"""
import io
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import streamlit as st
from typing import List, Tuple, Dict


def generate_wordcloud(keywords: List[Tuple[str, float]], 
                      width: int = 800, 
                      height: int = 400) -> io.BytesIO:
    """
    根据关键词生成词云图
    参数：
        keywords: 关键词列表，每个元素为(词, 权重)元组
        width: 图片宽度
        height: 图片高度
    返回：
        图片的BytesIO对象
    """
    # 将关键词转换为字典格式
    word_dict = {word: weight for word, weight in keywords}
    
    # 尝试使用系统中文字体
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",  # 黑体
        "C:/Windows/Fonts/simsun.ttc",  # 宋体
        "C:/Windows/Fonts/msyh.ttc",    # 微软雅黑
        "C:/Windows/Fonts/simfang.ttf", # 仿宋
    ]
    
    font_path = None
    for path in font_paths:
        try:
            with open(path, 'rb') as f:
                font_path = path
                break
        except:
            continue
    
    # 创建词云对象
    if font_path:
        wordcloud = WordCloud(
            font_path=font_path,
            width=width,
            height=height,
            background_color='white',
            max_words=100,
            max_font_size=100,
            colormap='Reds',  # 使用红色系，呼应师大红主题
            prefer_horizontal=0.7,
            margin=10
        )
    else:
        # 如果没有找到中文字体，使用默认设置
        wordcloud = WordCloud(
            width=width,
            height=height,
            background_color='white',
            max_words=100,
            colormap='Reds'
        )
    
    # 生成词云
    wordcloud.generate_from_frequencies(word_dict)
    
    # 转换为图片
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis('off')
    plt.tight_layout(pad=0)
    
    # 保存到内存
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', 
                pad_inches=0, dpi=100)
    img_buffer.seek(0)
    plt.close(fig)
    
    return img_buffer


def display_wordcloud_in_streamlit(keywords: List[Tuple[str, float]], 
                                  title: str = "关键词词云"):
    """
    在Streamlit中展示词云图
    参数：
        keywords: 关键词列表
        title: 展示标题
    """
    if not keywords:
        st.warning("暂无关键词数据，无法生成词云")
        return
    
    # 生成词云
    img_buffer = generate_wordcloud(keywords)
    
    # 展示标题
    st.markdown(f"**{title}**")
    
    # 展示图片
    st.image(img_buffer, use_container_width=True)


def display_keyword_table(keywords: List[Tuple[str, float]], 
                         top_k: int = 15):
    """
    展示关键词表格
    参数：
        keywords: 关键词列表
        top_k: 展示前N个关键词
    """
    if not keywords:
        st.warning("暂无关键词数据")
        return
    
    st.markdown("**关键词权重表**")
    
    # 创建表格数据
    table_data = []
    for i, (word, weight) in enumerate(keywords[:top_k], 1):
        table_data.append({
            "排名": i,
            "关键词": word,
            "权重": f"{weight:.4f}"
        })
    
    # 使用Streamlit表格展示
    st.table(table_data)


def create_stats_chart(stats: Dict[str, int]):
    """
    创建统计指标图表
    参数：
        stats: 统计指标字典
    """
    fig, ax = plt.subplots(figsize=(8, 3))
    
    # 准备数据
    labels = ['字符数', '词数', '段落数']
    values = [stats['char_count'], stats['word_count'], stats['paragraph_count']]
    
    # 创建柱状图
    bars = ax.bar(labels, values, color=['#C8102E', '#E63946', '#FF6B6B'])
    
    # 设置样式
    ax.set_title('文本统计指标', fontsize=14, fontweight='bold', color='#333333')
    ax.set_ylabel('数量', fontsize=12)
    
    # 在柱子上显示数值
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{value:,}', ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    
    return fig
