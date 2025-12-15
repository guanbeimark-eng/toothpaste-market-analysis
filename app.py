# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# -----------------------------------------------------------------------------
# 1. 页面配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="全景市场分析系统", layout="wide")
st.title("📊 全景市场分析系统 (多工作表自动解析)")
st.markdown("""
**系统逻辑：**
1. 自动读取 Excel 中的**每一个工作表 (Sheet)**。
2. 针对每个 Sheet 独立识别列名并生成分析报告。
3. 支持产品明细(`US`)、品牌汇总(`Brands`)、卖家汇总(`Sellers`)等多种数据格式。
""")

# -----------------------------------------------------------------------------
# 2. 核心清洗函数
# -----------------------------------------------------------------------------
def clean_numeric(val):
    """超级清洗函数：处理货币、千分位、区间、百分比"""
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return 0.0
    
    # 移除常见干扰符
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    
    # 处理百分比
    if "%" in s:
        try:
            return float(s.replace("%", "")) / 100.0
        except:
            pass

    # 提取数字
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return 0.0
    
    # 处理价格区间 "10-20" -> 取平均
    if len(nums) >= 2 and ("-" in str(val) or "to" in str(val).lower()):
        try:
            return (float(nums[0]) + float(nums[1])) / 2.0
        except:
            pass
            
    return float(nums[0])

def find_col(columns, keywords):
    """模糊匹配列名"""
    for col in columns:
        for kw in keywords:
            # 移除符号和空格进行对比
            clean_col = str(col).replace(" ", "").replace("(", "").replace(")", "").replace("$", "").lower()
            clean_kw = kw.replace(" ", "").lower()
            if clean_kw in clean_col:
                return col
    return None

# -----------------------------------------------------------------------------
# 3. 单个工作表的分析逻辑
# -----------------------------------------------------------------------------
def analyze_sheet(df, sheet_name):
    st.markdown(f"### 📑 工作表分析: {sheet_name}")
    
    # --- 1. 列名识别 ---
    all_cols = df.columns.tolist()
    
    # 关键词库 (针对你的三个表：US, Brands, Sellers)
    col_map = {
        "brand": find_col(all_cols, ['品牌', 'Brand', '卖家', 'Seller', 'Manufacturer']), # 兼容卖家表
        "title": find_col(all_cols, ['标题', 'Title', 'Name', '商品名']),
        "price": find_col(all_cols, ['价格', 'Price', '售价', '均价']),
        "sales": find_col(all_cols, ['销量', 'Sales', 'Sold']),
        "revenue": find_col(all_cols, ['销售额', 'Revenue', 'Amount']),
        "rating": find_col(all_cols, ['评分', 'Rating', 'Stars']), # 分数
        "reviews": find_col(all_cols, ['评分数', 'Reviews', '评论数', 'Q&A']), # 数量
        "share": find_col(all_cols, ['市场份额', 'Share'])
    }
    
    # --- 2. 手动修正 (折叠起来，默认信任自动识别) ---
    with st.expander(f"🛠️ 字段映射设置 ({sheet_name}) - 识别不准点这里", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        # 生成唯一的 key 防止组件冲突
        k_prefix = f"{sheet_name}_"
        col_map["brand"] = c1.selectbox("品牌/卖家列", [None]+all_cols, index=all_cols.index(col_map["brand"])+1 if col_map["brand"] else 0, key=k_prefix+"br")
        col_map["price"] = c2.selectbox("价格列", [None]+all_cols, index=all_cols.index(col_map["price"])+1 if col_map["price"] else 0, key=k_prefix+"pr")
        col_map["sales"] = c3.selectbox("销量列", [None]+all_cols, index=all_cols.index(col_map["sales"])+1 if col_map["sales"] else 0, key=k_prefix+"sa")
        col_map["rating"] = c4.selectbox("评分/星级列", [None]+all_cols, index=all_cols.index(col_map["rating"])+1 if col_map["rating"] else 0, key=k_prefix+"ra")

    # --- 3. 数据清洗 ---
    data = df.copy()
    valid_data = True
    
    # 必须有 [品牌/卖家] 或者 [标题] 其中之一，且必须有 [销量] 或 [价格] 其中之一，否则没法分析
    if not (col_map["brand"] or col_map["title"]):
        st.warning(f"⚠️ {sheet_name}: 未找到‘品牌’或‘标题’列，跳过图表生成。")
        valid_data = False
    
    if valid_data:
        # 清洗数值列
        if col_map["price"]: data['clean_price'] = data[col_map["price"]].apply(clean_numeric)
        if col_map["sales"]: data['clean_sales'] = data[col_map["sales"]].apply(clean_numeric)
        if col_map["revenue"]: data['clean_revenue'] = data[col_map["revenue"]].apply(clean_numeric)
        if col_map["rating"]: data['clean_rating'] = data[col_map["rating"]].apply(clean_numeric)
        if col_map["reviews"]: data['clean_reviews'] = data[col_map["reviews"]].apply(clean_numeric)

        # 这里的 Entity 代表分析的主体（可能是品牌，可能是卖家，可能是产品标题）
        entity_col = col_map["brand"] if col_map["brand"] else col_map["title"]
        data['Entity'] = data[entity_col].astype(str).fillna("Unknown")

        # --- 4. 关键指标卡 (KPI) ---
        k1, k2, k3, k4 = st.columns(4)
        
        total_sales = data['clean_sales'].sum() if 'clean_sales' in data else 0
        avg_price = data['clean_price'].mean() if 'clean_price' in data else 0
        total_rev = data['clean_revenue'].sum() if 'clean_revenue' in data else 0
        
        k1.metric("总销量", f"{total_sales:,.0f}")
        k2.metric("平均价格", f"${avg_price:.2f}")
        if total_rev > 0:
            k3.metric("总销售额", f"${total_rev:,.0f}")
        else:
            # 如果没有直接的销售额列，尝试 销量*价格 计算
            if 'clean_sales' in data and 'clean_price' in data:
                 est_rev = (data['clean_sales'] * data['clean_price']).sum()
                 k3.metric("预估销售额", f"${est_rev:,.0f}")
        
        if 'clean_rating' in data:
            avg_rate = data[data['clean_rating']>0]['clean_rating'].mean()
            k4.metric("平均评分", f"{avg_rate:.2f} ⭐")

        st.divider()

        # --- 5. 图表生成 ---
        g1, g2 = st.columns(2)
        
        # 图表 A: 头部实体份额 (Top Brands/Sellers)
        with g1:
            if 'clean_sales' in data:
                st.subheader(f"🏆 Top 10 {col_map['brand'] if col_map['brand'] else '商品'} (按销量)")
                top_entities = data.groupby('Entity')['clean_sales'].sum().sort_values(ascending=False).head(10).reset_index()
                fig_bar = px.bar(top_entities, x='clean_sales', y='Entity', orientation='h', text_auto='.2s')
                st.plotly_chart(fig_bar, use_container_width=True)
            elif col_map['share']:
                # 如果只有市场份额列
                st.subheader("🏆 市场份额分布")
                # 清洗份额
                data['clean_share'] = data[col_map['share']].apply(clean_numeric)
                top_share = data.sort_values('clean_share', ascending=False).head(10)
                fig_pie = px.pie(top_share, values='clean_share', names='Entity')
                st.plotly_chart(fig_pie, use_container_width=True)

        # 图表 B: 价格分布
        with g2:
            if 'clean_price' in data:
                st.subheader("💰 价格区间分布")
                # 过滤掉异常值
                plot_data = data[(data['clean_price'] > 0) & (data['clean_price'] < 500)] 
                fig_hist = px.histogram(plot_data, x='clean_price', nbins=20, color_discrete_sequence=['#3366cc'])
                st.plotly_chart(fig_hist, use_container_width=True)

        # 图表 C: 气泡图 (仅当有评分和销量时)
        if 'clean_rating' in data and 'clean_sales' in data and 'clean_price' in data:
            st.subheader("🔎 机会探测矩阵 (销量 vs 评分)")
            # 过滤
            scatter_df = data[(data['clean_sales']>0) & (data['clean_rating']>0)]
            if len(scatter_df) > 0:
                fig_scat = px.scatter(
                    scatter_df, 
                    x='clean_rating', 
                    y='clean_sales', 
                    size='clean_price', 
                    color='clean_rating',
                    hover_name='Entity',
                    title="气泡大小 = 价格",
                    labels={'clean_rating': '评分', 'clean_sales': '月销量'}
                )
                st.plotly_chart(fig_scat, use_container_width=True)
                st.info("💡 分析提示：寻找右下角的点（评分高但销量还不大）作为潜力竞品，或左上角的点（销量大但评分低）作为改进机会。")

    with st.expander(f"查看 {sheet_name} 原始数据"):
        st.dataframe(df.head(50))

# -----------------------------------------------------------------------------
# 4. 主程序入口
# -----------------------------------------------------------------------------
st.sidebar.header("📂 文件上传")
uploaded_file = st.sidebar.file_uploader("上传 Excel (.xlsx) 或 CSV", type=['xlsx', 'csv'])

if uploaded_file:
    try:
        # 读取文件
        dfs = {}
        if uploaded_file.name.endswith('.csv'):
            # CSV 当作单个 Sheet
            try:
                dfs['Sheet1'] = pd.read_csv(uploaded_file, encoding='utf-8')
            except:
                uploaded_file.seek(0)
                dfs['Sheet1'] = pd.read_csv(uploaded_file, encoding='gbk')
        else:
            # Excel 读取所有 Sheet
            xl = pd.ExcelFile(uploaded_file)
            for sheet_name in xl.sheet_names:
                dfs[sheet_name] = pd.read_excel(uploaded_file, sheet_name=sheet_name)
                # 清理列名空格
                dfs[sheet_name].columns = dfs[sheet_name].columns.astype(str).str.strip()

        # 生成 Tabs
        sheet_names = list(dfs.keys())
        st.success(f"成功读取 {len(sheet_names)} 个工作表: {', '.join(sheet_names)}")
        
        # 创建 Tabs
        tabs = st.tabs([f"📊 {name}" for name in sheet_names])
        
        for i, name in enumerate(sheet_names):
            with tabs[i]:
                analyze_sheet(dfs[name], name)
                
    except Exception as e:
        st.error(f"文件读取严重错误: {e}")
else:
    st.info("👈 请在左侧上传文件开始分析")
