# -*- coding: utf-8 -*-
import re
import time
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面与工具函数
# -----------------------------------------------------------------------------
st.set_page_config(page_title="亚马逊数据分析(特调版)", layout="wide")
st.title("📊 亚马逊市场分析 (针对你的文件优化版)")

def clean_numeric(val):
    """强力清洗函数：专门处理 '$12.99', '1,000', '评分数' 等格式"""
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == "" or s.lower() == "nan": return 0.0
    
    # 1. 针对你的文件：移除货币符号、逗号、空格
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "")
    
    # 2. 提取数字
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return 0.0
    
    # 3. 处理区间 "10-20" -> 取平均
    if len(nums) >= 2 and ("-" in str(val) or "to" in str(val)):
        return (float(nums[0]) + float(nums[1])) / 2.0
        
    return float(nums[0])

# -----------------------------------------------------------------------------
# 2. 针对你文件的列名匹配逻辑
# -----------------------------------------------------------------------------
def find_col(columns, keywords):
    """在列名中寻找关键词"""
    for col in columns:
        for kw in keywords:
            # 忽略大小写和空格的精确匹配
            if kw in str(col).replace(" ", ""):
                return col
    return None

# -----------------------------------------------------------------------------
# 3. 主逻辑
# -----------------------------------------------------------------------------
st.sidebar.header("📂 第一步：上传文件")
uploaded_file = st.sidebar.file_uploader("上传 US.csv 或 Brands.csv", type=["xlsx", "csv"])

if uploaded_file:
    # --- 读取文件 ---
    try:
        if uploaded_file.name.endswith('.csv'):
            # 尝试多种编码防止乱码
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8')
            except:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='gbk')
        else:
            df = pd.read_excel(uploaded_file)
            
        # 去除列名空格
        df.columns = df.columns.astype(str).str.strip()
        
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    st.success(f"成功读取 {len(df)} 行数据！正在进行分析...")

    # --- 自动对应列名 (针对你的文件头) ---
    all_cols = df.columns.tolist()
    
    # 这里是你的文件里会出现的列名关键词
    col_price = find_col(all_cols, ['价格', 'Price', '售价'])
    col_sales = find_col(all_cols, ['销量', 'Sales', 'Sold'])
    col_rev = find_col(all_cols, ['销售额', 'Revenue'])
    col_rating = find_col(all_cols, ['评分', 'Rating', 'Stars'])      # 注意：Rating 是分数 (4.5)
    col_reviews = find_col(all_cols, ['评分数', 'Reviews', '评论数', 'Q&A']) # 注意：Reviews 是数量 (1000)
    col_brand = find_col(all_cols, ['品牌', 'Brand'])
    col_title = find_col(all_cols, ['标题', 'Title', 'Name'])

    # --- 侧边栏：手动修正 (如果自动没对上) ---
    with st.sidebar.expander("⚙️ 字段手动修正 (图表为空请点这里)", expanded=True):
        st.info("系统已自动猜测列名，请确认是否正确：")
        c_p = st.selectbox("价格列", [None] + all_cols, index=all_cols.index(col_price) + 1 if col_price else 0)
        c_s = st.selectbox("销量列", [None] + all_cols, index=all_cols.index(col_sales) + 1 if col_sales else 0)
        c_r = st.selectbox("评分列 (分数)", [None] + all_cols, index=all_cols.index(col_rating) + 1 if col_rating else 0)
        c_v = st.selectbox("评论数列 (数量)", [None] + all_cols, index=all_cols.index(col_reviews) + 1 if col_reviews else 0)
        c_b = st.selectbox("品牌列", [None] + all_cols, index=all_cols.index(col_brand) + 1 if col_brand else 0)

    # --- 数据清洗 ---
    data = df.copy()
    
    # 必须有价格和销量才能画基础图
    if c_p and c_s:
        data['clean_price'] = data[c_p].apply(clean_numeric)
        data['clean_sales'] = data[c_s].apply(clean_numeric)
    else:
        st.error("❌ 无法找到[价格]或[销量]列，无法生成图表。请在侧边栏手动选择。")
        st.stop()
        
    # 如果有评分数据
    if c_r: data['clean_rating'] = data[c_r].apply(clean_numeric)
    if c_v: data['clean_reviews'] = data[c_v].apply(clean_numeric)
    
    # --- 顶部 KPI ---
    k1, k2, k3, k4 = st.columns(4)
    total_sales = data['clean_sales'].sum()
    avg_price = data['clean_price'].replace(0, np.nan).mean()
    
    k1.metric("总销量", f"{total_sales:,.0f}")
    k2.metric("平均价格", f"${avg_price:.2f}")
    
    if c_r and 'clean_rating' in data:
        k3.metric("平均评分", f"{data['clean_rating'].replace(0, np.nan).mean():.1f} ⭐")
    
    st.divider()

    # --- 图表区域 1: 价格分布 (最稳的图) ---
    st.subheader("1. 价格分布分析")
    # 过滤掉价格为0的数据，避免图表错误
    valid_price_data = data[data['clean_price'] > 0]
    
    if len(valid_price_data) > 0:
        fig1 = px.histogram(valid_price_data, x='clean_price', nbins=20, title="产品价格区间分布")
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.warning("⚠️ 价格列全是 0 或空值，无法画图。请检查侧边栏是否选对了‘价格’列。")

    # --- 图表 2: 机会矩阵 (最容易空的图) ---
    st.subheader("2. 市场机会矩阵 (销量 vs 评分)")
    
    # 只有当 评分、评论数、销量 都有的时候，才能画这个图
    if c_r and c_v and 'clean_rating' in data and 'clean_reviews' in data:
        # 过滤数据
        scatter_data = data[
            (data['clean_sales'] > 0) & 
            (data['clean_rating'] > 0)
        ]
        
        if len(scatter_data) > 0:
            fig2 = px.scatter(
                scatter_data,
                x="clean_rating",
                y="clean_sales",
                size="clean_price", # 气泡大小
                color="clean_rating",
                hover_data=[c_b] if c_b else None, # 悬停显示品牌
                title="评分 vs 销量 (气泡越大价格越高)",
                labels={"clean_rating": "评分", "clean_sales": "月销量"}
            )
            st.plotly_chart(fig2, use_container_width=True)
            st.caption("💡 气泡越靠右上方，说明销量高且评价好（明星产品）。")
        else:
            st.warning("⚠️ 数据不足：没有同时包含有效[销量]和[评分]的数据行，无法生成散点图。")
    else:
        st.info("ℹ️ 此图表需要[评分]和[评论数]数据。如果你上传的是 Brands.csv，通常没有评分数据，所以此图不显示是正常的。")

    # --- 图表 3: 品牌份额 ---
    if c_b:
        st.subheader("3. 品牌销量排行")
        brand_agg = data.groupby(c_b)['clean_sales'].sum().sort_values(ascending=False).head(15).reset_index()
        fig3 = px.bar(brand_agg, x=c_b, y='clean_sales', title="Top 15 品牌销量")
        st.plotly_chart(fig3, use_container_width=True)

    # --- 数据预览 ---
    with st.expander("查看原始数据 (用于排查问题)"):
        st.dataframe(data.head(50))

else:
    st.info("👈 请在左侧上传文件")
