# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# =============================================================================
# 1. 基础配置与通用函数
# =============================================================================
st.set_page_config(page_title="亚马逊全维分析 (含国家修复版)", layout="wide", page_icon="🌍")

st.title("🌍 亚马逊全维分析系统 (含国家/供应链分析)")
st.markdown("""
**本次更新修复：**
1.  ✅ **强制读取卖家国家**：精准识别 `卖家所属地`、`所属地`、`Region` 等列。
2.  ✅ **供应链地缘分析**：在产品分析中增加“卖家分布”图表（判断 CN vs US 占比）。
3.  ✅ **数据清洗**：自动将 `CN(HK)`、`CN` 归并为 `CN`，方便统计。
""")

# --- 通用清洗函数 ---
def clean_numeric(val):
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return 0.0
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    if "%" in s:
        try: return float(s.replace("%", "")) / 100.0
        except: pass
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return 0.0
    if len(nums) >= 2 and ("-" in str(val) or "to" in str(val).lower()):
        return (float(nums[0]) + float(nums[1])) / 2.0
    return float(nums[0])

def clean_country(val):
    """清洗国家/地区代码"""
    if pd.isna(val): return "Unknown"
    s = str(val).strip().upper()
    # 提取常见代码
    if "CN" in s or "CHINA" in s or "HONG" in s or "HK" in s:
        return "CN (中国)"
    if "US" in s or "UNITED STATES" in s or "AMERICA" in s:
        return "US (美国)"
    if "KR" in s or "KOREA" in s:
        return "KR (韩国)"
    if "JP" in s or "JAPAN" in s:
        return "JP (日本)"
    if "DE" in s or "GERMANY" in s:
        return "DE (德国)"
    return s # 其他保留原样

def find_col(columns, keywords):
    """模糊查找列名"""
    for col in columns:
        for kw in keywords:
            # 移除空格后对比
            if kw.lower() in str(col).lower().replace(" ", ""): return col
    return None

# =============================================================================
# 2. 模式识别引擎
# =============================================================================
def detect_sheet_mode(df):
    cols = [str(c).lower() for c in df.columns]
    col_str = " ".join(cols)
    if "asin" in col_str or "sku" in col_str or "标题" in col_str or "title" in col_str:
        return "PRODUCT"
    elif "seller" in col_str or "卖家" in col_str:
        # 如果是产品表但也有卖家列，优先算产品；只有纯卖家表才算 SELLER
        if "asin" not in col_str: return "SELLER"
        return "PRODUCT" # US表通常包含产品和卖家信息，归为产品模式更全
    elif ("brand" in col_str or "品牌" in col_str) and ("share" in col_str or "份额" in col_str):
        return "BRAND"
    else:
        return "GENERIC"

# =============================================================================
# 3. 专属分析模块 A: 产品开发模式 (含供应链分析)
# =============================================================================
def render_product_dashboard(df):
    st.info("📦 **产品开发模式** (已激活供应链源头分析)")
    
    all_cols = df.columns.tolist()
    # 1. 字段映射 (加入 Country)
    col_map = {
        'title': find_col(all_cols, ['title', '标题', 'name']),
        'price': find_col(all_cols, ['price', '价格', '售价']),
        'sales': find_col(all_cols, ['sales', '销量', 'sold']),
        'rating': find_col(all_cols, ['rating', '评分', 'stars']),
        'country': find_col(all_cols, ['country', 'region', '卖家所属地', '所属地', '国家', 'location']), # 关键修复
        'brand': find_col(all_cols, ['brand', '品牌']),
    }
    
    # 2. 数据清洗
    data = df.copy()
    if not col_map['title']: st.error("无法分析：缺少[标题]列"); return

    data['clean_price'] = data[col_map['price']].apply(clean_numeric) if col_map['price'] else 0
    data['clean_sales'] = data[col_map['sales']].apply(clean_numeric) if col_map['sales'] else 0
    data['clean_rating'] = data[col_map['rating']].apply(clean_numeric) if col_map['rating'] else 0
    data['Title_Str'] = data[col_map['title']].astype(str)
    
    # 国家清洗
    if col_map['country']:
        data['Origin'] = data[col_map['country']].apply(clean_country)
    else:
        data['Origin'] = "Unknown"

    # Pack 提取
    def extract_pack(t):
        m = re.search(r"(pack of \d+|\d+\s?count|\d+\s?pack)", t.lower())
        if m: 
            nums = re.findall(r"\d+", m.group(0))
            return int(nums[0]) if nums else 1
        return 1
    data['Pack_Count'] = data['Title_Str'].apply(extract_pack)

    # 3. 可视化 Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🌏 供应链与国家", "📦 规格与形态", "💰 价格体系", "✅ 决策建议"])
    
    with tab1:
        st.subheader("供应链源头分析 (Seller Location)")
        if col_map['country']:
            c1, c2 = st.columns(2)
            with c1:
                # 饼图：国家分布
                origin_counts = data['Origin'].value_counts().reset_index()
                origin_counts.columns = ['Origin', 'Count']
                fig = px.pie(origin_counts, values='Count', names='Origin', title="卖家所属地分布 (SKU数量)", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                # 柱状图：不同国家的均价
                price_by_country = data.groupby('Origin')['clean_price'].mean().reset_index()
                fig2 = px.bar(price_by_country, x='Origin', y='clean_price', title="不同产地卖家的平均售价 ($)", color='Origin')
                st.plotly_chart(fig2, use_container_width=True)
            
            cn_ratio = len(data[data['Origin'].str.contains("CN")]) / len(data)
            if cn_ratio > 0.6:
                st.warning(f"🔴 供应链预警：中国卖家占比高达 {cn_ratio:.1%}。这通常意味着供应链极其成熟，成本竞争（价格战）会非常激烈。")
            elif cn_ratio < 0.2:
                st.success(f"🟢 蓝海信号：中国卖家占比仅 {cn_ratio:.1%}。本土品牌为主，存在利用供应链优势打性价比的机会。")
        else:
            st.warning("⚠️ 未检测到 [卖家所属地] 列。请在侧边栏手动检查映射，或确认 Excel 中是否包含 Country/Region 列。")

    with tab2:
        st.subheader("SKU 结构分析")
        c1, c2 = st.columns(2)
        with c1:
            pack_dist = data.groupby('Pack_Count')['clean_sales'].sum().reset_index()
            fig = px.pie(pack_dist, values='clean_sales', names='Pack_Count', title='销量按 Pack 数分布')
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("**标题高频卖点词**")
            text = " ".join(data['Title_Str'].tolist()).lower()
            words = [w for w in re.split(r'\W+', text) if len(w)>3 and w not in ['toothpaste', 'with', 'pack', 'count', 'ounce']]
            top_words = pd.Series(words).value_counts().head(15)
            st.bar_chart(top_words)

    with tab3:
        st.subheader("价格分布")
        fig = px.histogram(data[data['clean_price']>0], x='clean_price', nbins=20, title="售价区间分布", color='Origin')
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.markdown(f"""
        ### 🤖 综合决策建议
        1.  **竞争对手画像**: 主要面对 **{data['Origin'].mode()[0]}** 的卖家竞争。
        2.  **定价策略**: 市场均价 **${data['clean_price'].mean():.2f}**。
            * 如果你是 CN 卖家：建议利用成本优势，定价在 ${data['clean_price'].quantile(0.3):.2f} 左右切入。
            * 如果你是 本土 卖家：需强调品牌故事，避开低价区。
        3.  **规格**: 主流是 **Pack {data.groupby('Pack_Count')['clean_sales'].sum().idxmax()}**。
        """)

# =============================================================================
# 4. 专属分析模块 B: 品牌格局模式
# =============================================================================
def render_brand_dashboard(df):
    st.info("🏢 **品牌格局模式**")
    all_cols = df.columns.tolist()
    col_map = {
        'brand': find_col(all_cols, ['brand', '品牌']),
        'share': find_col(all_cols, ['share', '份额']),
        'rev': find_col(all_cols, ['revenue', '销售额']),
        'price': find_col(all_cols, ['price', '价格', '均价'])
    }
    
    data = df.copy()
    if col_map['share']: data['clean_share'] = data[col_map['share']].apply(clean_numeric)
    if col_map['rev']: data['clean_rev'] = data[col_map['rev']].apply(clean_numeric)
    if col_map['price']: data['clean_price'] = data[col_map['price']].apply(clean_numeric)
    
    val_col = 'clean_rev' if col_map['rev'] else 'clean_share'
    if not val_col: st.error("缺少销售额或份额数据"); return
    
    data = data.sort_values(val_col, ascending=False)
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("品牌垄断度")
        top5 = data.head(5)[val_col].sum()
        total = data[val_col].sum()
        cr5 = top5/total if total>0 else 0
        st.metric("CR5 (Top 5 份额)", f"{cr5:.1%}")
        fig = px.pie(data.head(10), values=val_col, names=col_map['brand'], title="Top 10 品牌份额")
        st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        st.subheader("品牌价格带")
        if col_map['price']:
            fig = px.bar(data.head(15), x=col_map['brand'], y='clean_price', title="头部品牌均价对比")
            st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# 5. 专属分析模块 C: 渠道卖家模式 (含国家)
# =============================================================================
def render_seller_dashboard(df):
    st.info("🏪 **渠道卖家模式**")
    all_cols = df.columns.tolist()
    col_map = {
        'seller': find_col(all_cols, ['seller', '卖家']),
        'sales': find_col(all_cols, ['sales', '销量']),
        'country': find_col(all_cols, ['country', 'region', '国家', '属地', 'location']), # 关键
    }
    
    data = df.copy()
    if col_map['sales']: data['clean_sales'] = data[col_map['sales']].apply(clean_numeric)
    if col_map['country']: data['Origin'] = data[col_map['country']].apply(clean_country)
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("卖家国籍分布")
        if col_map['country']:
            cnt = data['Origin'].value_counts().reset_index()
            fig = px.pie(cnt, values='count', names='Origin', title="卖家所属地占比 (按店铺数)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未找到[卖家所属地]列")
            
    with c2:
        st.subheader("Top 卖家排行")
        if col_map['seller'] and col_map['sales']:
            top = data.sort_values('clean_sales', ascending=False).head(10)
            fig = px.bar(top, x='clean_sales', y=col_map['seller'], orientation='h')
            st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# 6. 主程序入口
# =============================================================================
st.sidebar.header("📂 上传文件")
uploaded_file = st.sidebar.file_uploader("上传 Excel/CSV", type=['xlsx', 'csv'])

if uploaded_file:
    dfs = {}
    try:
        if uploaded_file.name.endswith('.csv'):
            try: df = pd.read_csv(uploaded_file, encoding='utf-8')
            except: 
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='gbk')
            dfs["Sheet1"] = df
        else:
            xl = pd.ExcelFile(uploaded_file)
            for sheet in xl.sheet_names:
                dfs[sheet] = pd.read_excel(uploaded_file, sheet_name=sheet)
    except Exception as e:
        st.error(f"读取错误: {e}")
        st.stop()

    tabs = st.tabs([f"📑 {name}" for name in dfs.keys()])
    
    for i, (name, df_active) in enumerate(dfs.items()):
        with tabs[i]:
            mode = detect_sheet_mode(df_active)
            st.caption(f"工作表: {name} | 模式: {mode}")
            
            if mode == "PRODUCT":
                render_product_dashboard(df_active)
            elif mode == "BRAND":
                render_brand_dashboard(df_active)
            elif mode == "SELLER":
                render_seller_dashboard(df_active)
            else:
                st.dataframe(df_active.head())
else:
    st.info("👈 请上传数据文件")
