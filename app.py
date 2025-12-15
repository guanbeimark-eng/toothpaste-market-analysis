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
st.set_page_config(page_title="亚马逊全维分析 (ID冲突修复版)", layout="wide", page_icon="🌍")

st.title("🌍 亚马逊全维分析系统（ID冲突修复版）")
st.markdown("""
**本次修复：**
✅ **修复 StreamlitDuplicateElementId 错误**：为每个工作表的选择框添加了唯一 Key（基于 Sheet 名），彻底解决多表分析时的组件冲突问题。
""")

# --- 通用清洗函数 ---
def clean_numeric(val):
    """稳健数值清洗，失败返回 NaN"""
    if pd.isna(val): return np.nan
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return np.nan
    
    # 清理符号
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    
    # 百分比
    if "%" in s:
        try: return float(s.replace("%", "")) / 100.0
        except: pass
        
    # 提取数字
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return np.nan
    
    # 区间取均值 (10-20)
    if len(nums) >= 2 and ("-" in s or "to" in s.lower()):
        try: return (float(nums[0]) + float(nums[1])) / 2.0
        except: pass
        
    try: return float(nums[0])
    except: return np.nan

def numeric_diagnose(series: pd.Series):
    """诊断列数据的解析率"""
    parsed = series.apply(clean_numeric)
    rate = float(parsed.notna().mean()) if len(parsed) else 0.0
    med = float(parsed.median()) if parsed.notna().any() else np.nan
    p90 = float(parsed.quantile(0.9)) if parsed.notna().any() else np.nan
    return rate, med, p90

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
# 3. PRODUCT 模块 (9大维度 + 供应链)
# =============================================================================
# 关键修复：增加了 sheet_name 参数
def render_product_dashboard(df, sheet_name):
    st.info(f"📦 **产品开发模式** (来源表: {sheet_name})")
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
    
    # 2. 映射修正面板 (关键修复：为每个 selectbox 增加了 key)
    with st.expander("🛠️ 字段映射设置 (如有误请修正)", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        # Key 格式：{sheet_name}_{field_name}_prod
        col_map["title"] = c1.selectbox("标题 Title*", cols, index=cols.index(col_map["title"]) if col_map["title"] in cols else 0, key=f"{sheet_name}_title_prod")
        col_map["brand"] = c2.selectbox("品牌 Brand", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0, key=f"{sheet_name}_brand_prod")
        col_map["country"] = c3.selectbox("卖家地 Country", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0, key=f"{sheet_name}_country_prod")
        col_map["price"] = c4.selectbox("价格 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0, key=f"{sheet_name}_price_prod")
        
        c5, c6, c7, c8 = st.columns(4)
        col_map["sales"] = c5.selectbox("销量 Sales", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0, key=f"{sheet_name}_sales_prod")
        col_map["revenue"] = c6.selectbox("销售额 Revenue", cols, index=cols.index(col_map["revenue"]) if col_map["revenue"] in cols else 0, key=f"{sheet_name}_rev_prod")
        col_map["rating"] = c7.selectbox("评分 Rating", cols, index=cols.index(col_map["rating"]) if col_map["rating"] in cols else 0, key=f"{sheet_name}_rating_prod")
        col_map["reviews"] = c8.selectbox("评论数 Reviews", cols, index=cols.index(col_map["reviews"]) if col_map["reviews"] in cols else 0, key=f"{sheet_name}_reviews_prod")
        
        c9, c10 = st.columns(2)
        col_map["size"] = c9.selectbox("规格 Size", cols, index=cols.index(col_map["size"]) if col_map["size"] in cols else 0, key=f"{sheet_name}_size_prod")
        col_map["flavor"] = c10.selectbox("口味 Flavor", cols, index=cols.index(col_map["flavor"]) if col_map["flavor"] in cols else 0, key=f"{sheet_name}_flavor_prod")

    if not col_map["title"]:
        st.error("无法分析：必须包含【标题】列。")
        return

    # 3. 数据清洗与特征工程
    data = df.copy()
    data["Title_Str"] = data[col_map["title"]].astype(str)
    
    # 数值清洗
    for k in ["price", "sales", "revenue", "rating", "reviews"]:
        data[f"clean_{k}"] = data[col_map[k]].apply(clean_numeric) if col_map[k] else np.nan
        
    # 评分强校验 (防止选错)
    if col_map["rating"]:
        _, med, p90 = numeric_diagnose(data["clean_rating"])
        if (not np.isfinite(med)) or med > 5.5 or p90 > 6.0:
            st.warning("⚠️ 评分列数值异常(>5)，已自动禁用该列分析。")
            data["clean_rating"] = np.nan

    # 国家清洗
    data["Origin"] = data[col_map["country"]].apply(clean_country) if col_map["country"] else "Unknown"

    # Pack / Size / Flavor 提取
    def extract_pack(t):
        m = re.search(r"(pack\s*of\s*\d+|\d+\s*pack\b|\d+\s*count\b|\bx\s*\d+)", t.lower())
        if m:
            nums = re.findall(r"\d+", m.group(0))
            return int(nums[0]) if nums else 1
        return 1
    data["Pack_Count"] = data["Title_Str"].apply(extract_pack)
    data["Is_Multipack"] = data["Pack_Count"] > 1

    # Flavor
    FLAVOR_KW = ["mint", "spearmint", "peppermint", "cinnamon", "strawberry", "bubblegum", "lemon", "orange", "watermelon", "charcoal", "coconut"]
    if col_map["flavor"]:
        data["Flavor"] = data[col_map["flavor"]].astype(str)
    else:
        data["Flavor"] = data["Title_Str"].apply(lambda t: next((k for k in FLAVOR_KW if k in str(t).lower()), np.nan))

    # Size
    if col_map["size"]:
        data["Size_Str"] = data[col_map["size"]].astype(str)
    else:
        data["Size_Str"] = data["Title_Str"].apply(lambda t: (re.search(r"(\d+(?:\.\d+)?)\s*(oz|g|ml)\b", str(t).lower()) or [None,None])[0])

    # 技术/功效提取
    TECH_KW = ["nano", "hydroxyapatite", "hap", "fluoride-free", "fluoride free", "xylitol", "charcoal", "probiotic"]
    EFF_KW = ["remineral", "sensitivity", "sensitive", "whitening", "stain", "enamel", "gum", "fresh", "cavity"]
    
    def get_main_tag(text, kws):
        hits = [k for k in kws if k in str(text).lower()]
        return hits[0] if hits else np.nan
        
    data["Tech_Main"] = data["Title_Str"].apply(lambda x: get_main_tag(x, TECH_KW))
    data["Eff_Main"] = data["Title_Str"].apply(lambda x: get_main_tag(x, EFF_KW))
    data["Is_Tech_Heavy"] = data["Title_Str"].apply(lambda x: len([k for k in TECH_KW if k in str(x).lower()]) >= 2)

    # 价格带
    data["Price_Band"] = pd.cut(data["clean_price"], bins=[0,10,15,20,30,1000], labels=["<10","10-15","15-20","20-30","30+"])
    data["Unit_Price"] = data["clean_price"] / data["Pack_Count"].replace(0, np.nan)

    # 品牌背书
    MED_KW = ["dr.", "doctor", "clinical", "dentist", "professional"]
    data["Brand_Type"] = "Unknown"
    if col_map["brand"]:
        data["Brand_Type"] = data[col_map["brand"]].astype(str).apply(lambda x: "Medical" if any(k in x.lower() for k in MED_KW) else "Consumer")

    # 成熟度分
    score = 0
    if data["clean_price"].std() <= 5: score += 30
    if data["Tech_Main"].notna().mean() > 0.5: score += 30
    if data["Pack_Count"].nunique() <= 5: score += 40
    maturity_score = min(score, 100)

    # 4. 可视化展示
    # KPI
    k1, k2, k3, k4 = st.columns(4)
    total_sales = data["clean_sales"].sum()
    k1.metric("SKU数", len(data))
    k2.metric("总销量", f"{total_sales:,.0f}")
    k3.metric("平均价格", f"${data['clean_price'].mean():.2f}")
    k4.metric("平均评分", f"{data['clean_rating'].mean():.2f}")

    # Tabs
    tabs = st.tabs(["🌏 供应链", "📦 规格形态", "🧪 技术功效", "💰 价格体系", "🗣️ 内容策略", "✅ 决策清单"])

    # Tab 1: 供应链
    with tabs[0]:
        st.subheader("供应链源头 (Seller Origin)")
        c1, c2 = st.columns(2)
        with c1:
            if col_map["country"]:
                vc = data["Origin"].value_counts().reset_index()
                vc.columns = ["Origin", "Count"]
                st.plotly_chart(px.pie(vc, values="Count", names="Origin", title="卖家所属地分布", hole=0.4), use_container_width=True)
            else:
                st.warning("未检测到卖家所属地列")
        with c2:
            if col_map["country"]:
                pb = data.groupby("Origin", dropna=False)["clean_price"].mean().reset_index()
                st.plotly_chart(px.bar(pb, x="Origin", y="clean_price", title="不同产地均价", color="Origin"), use_container_width=True)

    # Tab 2: SKU
    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            pd_dist = data.groupby("Pack_Count")["clean_sales"].sum().reset_index()
            st.plotly_chart(px.bar(pd_dist, x="Pack_Count", y="clean_sales", title="Pack数分布(按销量)"), use_container_width=True)
        with c2:
            flav = data["Flavor"].dropna().value_counts().head(10).reset_index()
            flav.columns = ["Flavor", "Count"]
            st.plotly_chart(px.bar(flav, x="Count", y="Flavor", orientation='h', title="口味分布"), use_container_width=True)

    # Tab 3: Tech
    with tabs[2]:
        c1, c2 = st.columns(2)
        with c1:
            th = data["Tech_Main"].value_counts().head(10).reset_index()
            th.columns = ["Tech", "Count"]
            st.plotly_chart(px.bar(th, x="Count", y="Tech", orientation='h', title="技术主词"), use_container_width=True)
        with c2:
            # Tech Premium
            tmp = data.dropna(subset=["clean_price"])
            tp = tmp.groupby("Tech_Main")["clean_price"].mean().sort_values(ascending=False).head(10).reset_index()
            st.plotly_chart(px.bar(tp, x="clean_price", y="Tech_Main", orientation='h', title="技术溢价分析"), use_container_width=True)

    # Tab 4: Price
    with tabs[3]:
        st.plotly_chart(px.histogram(data, x="clean_price", nbins=20, color="Origin", title="价格区间分布"), use_container_width=True)
        
        pb_cnt = data.groupby("Price_Band", dropna=False).size().reset_index(name="Count")
        st.plotly_chart(px.bar(pb_cnt, x="Price_Band", y="Count", title="价格带SKU数"), use_container_width=True)

    # Tab 5: Messaging
    with tabs[4]:
        data["Title_Len"] = data["Title_Str"].str.len()
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.histogram(data, x="Title_Len", title="标题长度分布"), use_container_width=True)
        with c2:
            # Word Cloud alternative
            all_text = " ".join(data["Title_Str"].tolist()).lower()
            tokens = [t for t in re.split(r"\W+", all_text) if len(t)>3]
            freq = pd.Series(tokens).value_counts().head(20)
            st.bar_chart(freq)

    # Tab 6: Decision
    with tabs[5]:
        st.subheader("🤖 智能开发建议")
        
        multi_share = data[data["Is_Multipack"]]["clean_sales"].sum() / total_sales if total_sales>0 else 0
        cn_share = (data["Origin"].str.contains("CN")).mean()
        
        st.markdown(f"""
        1. **供应链**: 中国卖家占比 **{cn_share:.1%}**。{'红海竞争，拼成本' if cn_share>0.5 else '存在本土化溢价机会'}。
        2. **规格**: 多支装销量占比 **{multi_share:.1%}**。{'建议做组合装' if multi_share>0.3 else '建议单支切入'}。
        3. **定价**: 市场均价 **${data['clean_price'].mean():.2f}**。建议起步价 **${data['clean_price'].quantile(0.3):.2f}**。
        4. **成熟度**: 得分 **{maturity_score}**。{'市场成熟，需强差异化' if maturity_score>60 else '市场早期，机会较大'}。
        """)
        
        if "clean_sales" in data.columns:
            st.markdown("#### Top 15 SKU 参考")
            top = data.sort_values("clean_sales", ascending=False).head(15)
            st.dataframe(top[["Title_Str", "clean_price", "Origin", "Pack_Count", "Tech_Main"]], use_container_width=True)

# =============================================================================
# 4. BRAND / SELLER 简易模块
# =============================================================================
# 关键修复：增加了 sheet_name 参数
def render_brand_dashboard(df, sheet_name):
    st.info(f"🏢 **品牌格局模式** (来源表: {sheet_name})")
    all_cols = df.columns.tolist()
    col_map = {
        "brand": find_col(all_cols, ["brand", "品牌"]),
        "share": find_col(all_cols, ["share", "份额"]),
        "rev": find_col(all_cols, ["revenue", "销售额", "gmv", "amount"]),
        "price": find_col(all_cols, ["price", "价格", "均价"])
    }
    
    # 关键修复：为每个 selectbox 增加了 key
    with st.expander("🛠️ 字段映射设置 (品牌表)", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        col_map["brand"] = c1.selectbox("品牌 Brand*", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0, key=f"{sheet_name}_brand_b")
        col_map["share"] = c2.selectbox("份额 Share", cols, index=cols.index(col_map["share"]) if col_map["share"] in cols else 0, key=f"{sheet_name}_share_b")
        col_map["rev"] = c3.selectbox("销售额 Revenue", cols, index=cols.index(col_map["rev"]) if col_map["rev"] in cols else 0, key=f"{sheet_name}_rev_b")
        col_map["price"] = c4.selectbox("均价 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0, key=f"{sheet_name}_price_b")
    
    if not col_map["brand"] or not col_map["share"]:
        st.error("缺少品牌或份额列")
        st.dataframe(df.head())
        return
        
    data = df.copy()
    data["clean_share"] = data[col_map["share"]].apply(clean_numeric)
    data = data.sort_values("clean_share", ascending=False)
    
    c1, c2 = st.columns(2)
    with c1:
        top5 = data.head(5)["clean_share"].sum()
        st.metric("CR5", f"{top5:.1%}")
        st.plotly_chart(px.pie(data.head(10), values="clean_share", names=col_map["brand"], title="Top 10 品牌份额"), use_container_width=True)
    with c2:
        if col_map["price"]:
            data["clean_price"] = data[col_map["price"]].apply(clean_numeric)
            st.plotly_chart(px.bar(data.head(15), x=col_map["brand"], y="clean_price", title="品牌均价"), use_container_width=True)

# 关键修复：增加了 sheet_name 参数
def render_seller_dashboard(df, sheet_name):
    st.info(f"🏪 **卖家渠道模式** (来源表: {sheet_name})")
    all_cols = df.columns.tolist()
    col_map = {
        "seller": find_col(all_cols, ["seller", "卖家"]),
        "sales": find_col(all_cols, ["sales", "销量"]),
        "country": find_col(all_cols, ["country", "region", "所属地", "国家"]),
    }
    
    # 关键修复：为每个 selectbox 增加了 key
    with st.expander("🛠️ 字段映射设置 (卖家表)", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3 = st.columns(3)
        col_map["seller"] = c1.selectbox("卖家 Seller*", cols, index=cols.index(col_map["seller"]) if col_map["seller"] in cols else 0, key=f"{sheet_name}_seller_s")
        col_map["sales"] = c2.selectbox("销量 Sales", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0, key=f"{sheet_name}_sales_s")
        col_map["country"] = c3.selectbox("所属地 Country/Region", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0, key=f"{sheet_name}_country_s")
    
    data = df.copy()
    if col_map["country"]:
        data["Origin"] = data[col_map["country"]].apply(clean_country)
        vc = data["Origin"].value_counts().reset_index()
        vc.columns = ["Origin", "Count"]
        st.plotly_chart(px.pie(vc, values="Count", names="Origin", title="卖家所属地"), use_container_width=True)
    
    if col_map["seller"] and col_map["sales"]:
        data["clean_sales"] = data[col_map["sales"]].apply(clean_numeric)
        top = data.sort_values("clean_sales", ascending=False).head(10)
        st.plotly_chart(px.bar(top, x="clean_sales", y=col_map["seller"], title="Top 卖家销量"), use_container_width=True)

# =============================================================================
# 5. 主程序
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
        
    st.success(f"读取成功: {len(dfs)} 个工作表")
    
    tabs = st.tabs([f"📑 {n}" for n in dfs.keys()])
    for i, (name, df) in enumerate(dfs.items()):
        with tabs[i]:
            mode = detect_sheet_mode(df)
            st.caption(f"模式: {mode}")
            # 关键修复：传递了 name 作为 sheet_name
            if mode == "PRODUCT": render_product_dashboard(df, name)
            elif mode == "BRAND": render_brand_dashboard(df, name)
            elif mode == "SELLER": render_seller_dashboard(df, name)
            else: st.dataframe(df.head())
else:
    st.info("👈 请上传文件")
