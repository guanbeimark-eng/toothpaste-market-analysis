# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# =============================================================================
# 1. 基础配置与通用清洗函数
# =============================================================================
st.set_page_config(page_title="亚马逊全维分析系统 (终极版)", layout="wide", page_icon="📊")

st.title("📊 亚马逊全维分析系统 (多工作表・多维度)")
st.markdown("""
**系统已激活全量分析模式：**
系统会自动遍历您上传的每一个工作表，根据数据特征智能匹配分析模型：
1.  **📦 产品开发模型**：分析 SKU 结构、配方技术、价格锚点、供应链源头等。
2.  **🏢 品牌竞争模型**：分析市场垄断度 (CR5)、品牌价格定位、竞争矩阵。
3.  **🏪 渠道卖家模型**：分析卖家国籍分布、渠道掌控力、头部效应。
""")

# --- 通用清洗函数 ---
def clean_numeric(val):
    """稳健数值清洗，失败返回 NaN"""
    if pd.isna(val): return np.nan
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return np.nan
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    if "%" in s:
        try: return float(s.replace("%", "")) / 100.0
        except: pass
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return np.nan
    if len(nums) >= 2 and ("-" in s or "to" in s.lower()):
        try: return (float(nums[0]) + float(nums[1])) / 2.0
        except: pass
    try: return float(nums[0])
    except: return np.nan

def clean_country(val):
    """清洗国家代码"""
    if pd.isna(val): return "Unknown"
    s = str(val).strip().upper()
    if "CN" in s or "CHINA" in s or "HONG" in s or "HK" in s: return "CN (中国)"
    if "US" in s or "UNITED STATES" in s or "AMERICA" in s: return "US (美国)"
    if "KR" in s or "KOREA" in s: return "KR (韩国)"
    if "JP" in s or "JAPAN" in s: return "JP (日本)"
    if "DE" in s or "GERMANY" in s: return "DE (德国)"
    if "UK" in s or "BRITAIN" in s: return "UK (英国)"
    return s

def find_col(columns, keywords):
    """模糊匹配列名"""
    for col in columns:
        col_norm = str(col).lower().replace(" ", "")
        for kw in keywords:
            if kw.lower().replace(" ", "") in col_norm:
                return col
    return None

def numeric_diagnose(series):
    parsed = series.apply(clean_numeric)
    rate = parsed.notna().mean()
    med = parsed.median() if parsed.notna().any() else np.nan
    return rate, med

# =============================================================================
# 2. 模式识别引擎
# =============================================================================
def detect_sheet_mode(df):
    cols = [str(c).lower() for c in df.columns]
    col_str = " ".join(cols)
    
    has_asin = ("asin" in col_str) or ("sku" in col_str)
    has_title = ("title" in col_str) or ("标题" in col_str) or ("name" in col_str)
    has_seller = ("seller" in col_str) or ("卖家" in col_str)
    has_brand = ("brand" in col_str) or ("品牌" in col_str)
    has_share = ("share" in col_str) or ("份额" in col_str)
    has_trade = ("price" in col_str) or ("价格" in col_str) or ("sales" in col_str) or ("销量" in col_str)
    
    if (has_asin or has_title) and has_trade: return "PRODUCT"
    if has_seller and (not has_asin): return "SELLER"
    if has_brand and has_share: return "BRAND"
    return "GENERIC"

# =============================================================================
# 3. 分析模块 A: 产品开发模型 (9大维度)
# =============================================================================
def render_product_dashboard(df, sheet_name):
    st.info(f"📦 **产品开发模式** | 数据源: `{sheet_name}`")
    all_cols = df.columns.tolist()
    
    # 1. 字段映射
    col_map = {
        "title": find_col(all_cols, ["title", "标题", "name", "商品名"]),
        "brand": find_col(all_cols, ["brand", "品牌"]),
        "price": find_col(all_cols, ["price", "价格", "售价", "currentprice"]),
        "sales": find_col(all_cols, ["sales", "销量", "sold", "units"]),
        "revenue": find_col(all_cols, ["revenue", "销售额", "amount"]),
        "rating": find_col(all_cols, ["rating", "评分", "stars"]),
        "reviews": find_col(all_cols, ["reviews", "评论数", "评价数", "count"]),
        "country": find_col(all_cols, ["country", "region", "卖家所属地", "所属地", "location", "origin"]),
        "size": find_col(all_cols, ["size", "净含量", "规格", "oz", "ml", "gram"]),
        "flavor": find_col(all_cols, ["flavor", "味", "口味", "variant"]),
    }
    
    # 2. 映射修正 (Key = sheet_name + field)
    with st.expander("🛠️ 字段映射设置", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        col_map["title"] = c1.selectbox("标题 Title*", cols, index=cols.index(col_map["title"]) if col_map["title"] in cols else 0, key=f"{sheet_name}_title")
        col_map["brand"] = c2.selectbox("品牌 Brand", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0, key=f"{sheet_name}_brand")
        col_map["country"] = c3.selectbox("卖家地 Country", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0, key=f"{sheet_name}_country")
        col_map["price"] = c4.selectbox("价格 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0, key=f"{sheet_name}_price")
        
        c5, c6, c7, c8 = st.columns(4)
        col_map["sales"] = c5.selectbox("销量 Sales", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0, key=f"{sheet_name}_sales")
        col_map["revenue"] = c6.selectbox("销售额 Revenue", cols, index=cols.index(col_map["revenue"]) if col_map["revenue"] in cols else 0, key=f"{sheet_name}_rev")
        col_map["rating"] = c7.selectbox("评分 Rating", cols, index=cols.index(col_map["rating"]) if col_map["rating"] in cols else 0, key=f"{sheet_name}_rating")
        col_map["reviews"] = c8.selectbox("评论数 Reviews", cols, index=cols.index(col_map["reviews"]) if col_map["reviews"] in cols else 0, key=f"{sheet_name}_reviews")
        
        c9, c10 = st.columns(2)
        col_map["size"] = c9.selectbox("规格 Size", cols, index=cols.index(col_map["size"]) if col_map["size"] in cols else 0, key=f"{sheet_name}_size")
        col_map["flavor"] = c10.selectbox("口味 Flavor", cols, index=cols.index(col_map["flavor"]) if col_map["flavor"] in cols else 0, key=f"{sheet_name}_flavor")

    if not col_map["title"]:
        st.error("缺少标题列，无法分析。")
        return

    # 3. 清洗与特征工程
    data = df.copy()
    data["Title_Str"] = data[col_map["title"]].astype(str)
    for k in ["price", "sales", "revenue", "rating", "reviews"]:
        data[f"clean_{k}"] = data[col_map[k]].apply(clean_numeric) if col_map[k] else np.nan
        
    # 评分校验
    if col_map["rating"]:
        _, med = numeric_diagnose(data["clean_rating"])
        if med > 6.0: data["clean_rating"] = np.nan # 疑似错误

    # 国家/Pack/Flavor
    data["Origin"] = data[col_map["country"]].apply(clean_country) if col_map["country"] else "Unknown"
    
    def extract_pack(t):
        m = re.search(r"(pack\s*of\s*\d+|\d+\s*pack\b|\d+\s*count\b|\bx\s*\d+)", t.lower())
        return int(re.findall(r"\d+", m.group(0))[0]) if m else 1
    data["Pack_Count"] = data["Title_Str"].apply(extract_pack)
    data["Is_Multipack"] = data["Pack_Count"] > 1

    # 技术提取
    TECH_KW = ["nano", "hydroxyapatite", "hap", "fluoride-free", "xylitol", "charcoal", "probiotic"]
    EFF_KW = ["remineral", "sensitivity", "whitening", "enamel", "gum", "cavity"]
    def get_tag(t, kws): return next((k for k in kws if k in str(t).lower()), np.nan)
    data["Tech_Main"] = data["Title_Str"].apply(lambda x: get_tag(x, TECH_KW))
    data["Eff_Main"] = data["Title_Str"].apply(lambda x: get_tag(x, EFF_KW))

    # 4. 可视化 Tabs
    t1, t2, t3, t4, t5, t6 = st.tabs(["🌏 供应链", "📦 形态规格", "🧪 卖点技术", "💰 价格体系", "🗣️ 内容策略", "✅ 决策清单"])
    
    with t1: # 供应链
        c1, c2 = st.columns(2)
        with c1:
            if col_map["country"]:
                vc = data["Origin"].value_counts().reset_index()
                vc.columns = ["Origin", "Count"]
                st.plotly_chart(px.pie(vc, values="Count", names="Origin", title="卖家所属地分布", hole=0.4), use_container_width=True)
            else: st.warning("未检测到卖家所属地列")
        with c2:
            if col_map["country"]:
                pb = data.groupby("Origin", dropna=False)["clean_price"].mean().reset_index()
                st.plotly_chart(px.bar(pb, x="Origin", y="clean_price", title="各产地卖家均价", color="Origin"), use_container_width=True)
                
    with t2: # 规格
        c1, c2 = st.columns(2)
        with c1:
            pd_dist = data.groupby("Pack_Count")["clean_sales"].sum().reset_index()
            st.plotly_chart(px.bar(pd_dist, x="Pack_Count", y="clean_sales", title="Pack数销量分布"), use_container_width=True)
        with c2:
            # 简单的 Flavor 提取展示（如果有列）
            if col_map["flavor"]:
                flav = data[col_map["flavor"]].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(flav, x=col_map["flavor"], y="count", title="口味分布"), use_container_width=True)
            else:
                st.info("未映射 Flavor 列")
                
    with t3: # 技术
        c1, c2 = st.columns(2)
        with c1:
            th = data["Tech_Main"].value_counts().head(10).reset_index()
            st.plotly_chart(px.bar(th, x="count", y="Tech_Main", orientation='h', title="技术热词"), use_container_width=True)
        with c2:
            tmp = data.dropna(subset=["clean_price"])
            tp = tmp.groupby("Tech_Main")["clean_price"].mean().sort_values(ascending=False).head(10).reset_index()
            st.plotly_chart(px.bar(tp, x="clean_price", y="Tech_Main", orientation='h', title="技术溢价"), use_container_width=True)

    with t4: # 价格
        st.plotly_chart(px.histogram(data, x="clean_price", nbins=20, color="Origin", title="价格区间"), use_container_width=True)
    
    with t5: # 内容
        data["Title_Len"] = data["Title_Str"].str.len()
        st.plotly_chart(px.histogram(data, x="Title_Len", title="标题长度分布"), use_container_width=True)
    
    with t6: # 决策
        total_sales = data["clean_sales"].sum()
        multi_share = data[data["Is_Multipack"]]["clean_sales"].sum() / total_sales if total_sales>0 else 0
        cn_share = (data["Origin"].str.contains("CN")).mean()
        
        st.markdown(f"""
        ### 🤖 智能决策建议
        1.  **供应链**: 中国卖家占比 **{cn_share:.1%}**。{'注意成本战' if cn_share>0.5 else '存在降本切入机会'}。
        2.  **规格**: 多支装销量占比 **{multi_share:.1%}**。{'建议做组合装' if multi_share>0.3 else '建议单支切入'}。
        3.  **定价**: 市场均价 **${data['clean_price'].mean():.2f}**。
        """)

# =============================================================================
# 4. 分析模块 B: 品牌竞争模型 (3大维度)
# =============================================================================
def render_brand_dashboard(df, sheet_name):
    st.info(f"🏢 **品牌竞争模式** | 数据源: `{sheet_name}`")
    all_cols = df.columns.tolist()
    col_map = {
        "brand": find_col(all_cols, ["brand", "品牌"]),
        "share": find_col(all_cols, ["share", "份额"]),
        "rev": find_col(all_cols, ["revenue", "销售额", "gmv"]),
        "price": find_col(all_cols, ["price", "价格", "均价"])
    }
    
    with st.expander("🛠️ 字段映射设置", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        col_map["brand"] = c1.selectbox("品牌 Brand", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0, key=f"{sheet_name}_brand_b")
        col_map["share"] = c2.selectbox("份额 Share", cols, index=cols.index(col_map["share"]) if col_map["share"] in cols else 0, key=f"{sheet_name}_share_b")
        col_map["rev"] = c3.selectbox("销售额 Revenue", cols, index=cols.index(col_map["rev"]) if col_map["rev"] in cols else 0, key=f"{sheet_name}_rev_b")
        col_map["price"] = c4.selectbox("均价 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0, key=f"{sheet_name}_price_b")

    if not col_map["brand"]: st.error("缺少品牌列"); return
    
    data = df.copy()
    data["clean_rev"] = data[col_map["rev"]].apply(clean_numeric) if col_map["rev"] else np.nan
    data["clean_share"] = data[col_map["share"]].apply(clean_numeric) if col_map["share"] else np.nan
    data["clean_price"] = data[col_map["price"]].apply(clean_numeric) if col_map["price"] else np.nan
    
    val_col = "clean_rev" if data["clean_rev"].notna().any() else "clean_share"
    data = data.sort_values(val_col, ascending=False)
    
    # 维度 Tabs
    t1, t2, t3 = st.tabs(["📊 市场格局 (Landscape)", "💲 价格定位 (Positioning)", "🔎 竞争矩阵 (Matrix)"])
    
    with t1:
        st.subheader("维度 1: 市场垄断度分析")
        top5 = data.head(5)[val_col].sum()
        total = data[val_col].sum()
        cr5 = top5/total if total>0 else 0
        
        c1, c2 = st.columns(2)
        c1.metric("CR5 (Top5 集中度)", f"{cr5:.1%}")
        c1.write(f"判定：{'🔴 高度垄断' if cr5>0.6 else ('🟢 市场分散' if cr5<0.3 else '🟡 竞争适中')}")
        
        fig = px.pie(data.head(10), values=val_col, names=col_map["brand"], title="Top 10 品牌份额", hole=0.4)
        c2.plotly_chart(fig, use_container_width=True)
        
    with t2:
        st.subheader("维度 2: 品牌价格定位")
        if data["clean_price"].notna().any():
            top_brands = data.head(15)
            fig = px.bar(top_brands, x=col_map["brand"], y="clean_price", title="头部品牌均价对比", color="clean_price")
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("未提供价格数据")
        
    with t3:
        st.subheader("维度 3: 竞争矩阵 (价格 vs 规模)")
        if data["clean_price"].notna().any() and data[val_col].notna().any():
            fig = px.scatter(data.head(30), x="clean_price", y=val_col, size=val_col, hover_name=col_map["brand"], 
                             title="品牌定位矩阵 (X=价格, Y=规模)", labels={"clean_price":"均价", val_col:"规模"})
            st.plotly_chart(fig, use_container_width=True)
            st.info("💡 寻找空白点：高价但规模尚小的区域可能是‘高端新品牌’的机会点。")
        else: st.warning("缺少必要数据绘制矩阵")

# =============================================================================
# 5. 分析模块 C: 渠道卖家模型 (3大维度)
# =============================================================================
def render_seller_dashboard(df, sheet_name):
    st.info(f"🏪 **渠道卖家模式** | 数据源: `{sheet_name}`")
    all_cols = df.columns.tolist()
    col_map = {
        "seller": find_col(all_cols, ["seller", "卖家"]),
        "sales": find_col(all_cols, ["sales", "销量"]),
        "country": find_col(all_cols, ["country", "region", "所属地", "国家"]),
    }
    
    with st.expander("🛠️ 字段映射设置", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3 = st.columns(3)
        col_map["seller"] = c1.selectbox("卖家 Seller*", cols, index=cols.index(col_map["seller"]) if col_map["seller"] in cols else 0, key=f"{sheet_name}_sel_s")
        col_map["sales"] = c2.selectbox("销量 Sales", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0, key=f"{sheet_name}_sal_s")
        col_map["country"] = c3.selectbox("所属地 Country", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0, key=f"{sheet_name}_cou_s")
    
    data = df.copy()
    if col_map["sales"]: data["clean_sales"] = data[col_map["sales"]].apply(clean_numeric)
    if col_map["country"]: data["Origin"] = data[col_map["country"]].apply(clean_country)
    
    t1, t2, t3 = st.tabs(["🌍 地缘分布 (Geography)", "🏆 头部效应 (Leaders)", "📊 渠道掌控 (Channel)"])
    
    with t1:
        st.subheader("维度 1: 卖家国籍分布")
        if col_map["country"]:
            vc = data["Origin"].value_counts().reset_index()
            vc.columns = ["Origin", "Count"]
            st.plotly_chart(px.pie(vc, values="Count", names="Origin", title="卖家所属地占比 (店铺数)"), use_container_width=True)
        else: st.warning("未检测到所属地列")
        
    with t2:
        st.subheader("维度 2: Top 卖家排行")
        if col_map["seller"] and "clean_sales" in data:
            top = data.sort_values("clean_sales", ascending=False).head(10)
            st.plotly_chart(px.bar(top, x="clean_sales", y=col_map["seller"], orientation="h", title="Top 10 卖家销量"), use_container_width=True)
            
    with t3:
        st.subheader("维度 3: 渠道掌控力")
        if "clean_sales" in data:
            total = data["clean_sales"].sum()
            top10 = data.sort_values("clean_sales", ascending=False).head(10)["clean_sales"].sum()
            share = top10/total if total>0 else 0
            st.metric("Top 10 卖家销量占比", f"{share:.1%}")
            st.progress(min(share, 1.0))
            st.caption("反映了渠道是否被少数大卖家把持。")

# =============================================================================
# 6. 主程序入口
# =============================================================================
st.sidebar.header("📂 上传数据")
uploaded_file = st.sidebar.file_uploader("Excel/CSV", type=["xlsx", "csv"])

if uploaded_file:
    dfs = {}
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            try: df = pd.read_csv(uploaded_file, encoding="utf-8")
            except: 
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding="gbk")
            dfs["Sheet1"] = df
        else:
            xl = pd.ExcelFile(uploaded_file)
            for sheet in xl.sheet_names:
                dfs[sheet] = pd.read_excel(uploaded_file, sheet_name=sheet)
                dfs[sheet].columns = dfs[sheet].columns.astype(str).str.strip()
    except Exception as e:
        st.error(f"读取失败: {e}")
        st.stop()
        
    st.success(f"成功读取 {len(dfs)} 个工作表")
    
    # 遍历每个 Sheet 进行多维度分析
    tabs = st.tabs([f"📑 {n}" for n in dfs.keys()])
    for i, (name, df) in enumerate(dfs.items()):
        with tabs[i]:
            mode = detect_sheet_mode(df)
            st.caption(f"工作表: `{name}` | 识别模式: `{mode}`")
            
            if mode == "PRODUCT":
                render_product_dashboard(df, name)
            elif mode == "BRAND":
                render_brand_dashboard(df, name)
            elif mode == "SELLER":
                render_seller_dashboard(df, name)
            else:
                st.info("未识别出特定模式，展示数据预览。")
                st.dataframe(df.head())
else:
    st.info("👈 请上传 Excel/CSV 文件开始分析")
