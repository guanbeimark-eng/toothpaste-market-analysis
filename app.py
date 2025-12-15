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
st.set_page_config(page_title="亚马逊全维分析 (稳定增强版)", layout="wide", page_icon="🌍")

st.title("🌍 亚马逊全维分析系统（稳定增强版）")
st.markdown("""
**本版强化点：**
1. ✅ **静默错误修复**：数值解析失败不再默默变 0，而是变 NaN，并给出【解析率诊断】提醒你修正映射。
2. ✅ **评分强校验**：评分必须符合 0–5 星分布，否则自动判定“列选错”（常见：把评论数/评分数当评分）。
3. ✅ **国家/供应链分析**：自动识别卖家国家/所属地，并归一化统计。
4. ✅ **PRODUCT 模块升级为产品开发分析**：新增 SKU 结构、功效&技术路线、价格锚点、内容密度、成熟度评分、决策清单。
""")

# --- 通用清洗函数：数值（失败=NaN，不吞错）---
def clean_numeric(val):
    """
    更稳健的数值清洗：
    - 失败返回 NaN（关键：避免静默错误）
    - 支持 $/¥/千分位/区间 10-20 或 10 to 20
    """
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]:
        return np.nan

    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    # 百分号（如份额）
    if "%" in s:
        try:
            return float(s.replace("%", "")) / 100.0
        except Exception:
            return np.nan

    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return np.nan

    # 区间取均值
    if len(nums) >= 2 and ("-" in s or "to" in s.lower()):
        try:
            return (float(nums[0]) + float(nums[1])) / 2.0
        except Exception:
            return np.nan

    try:
        return float(nums[0])
    except Exception:
        return np.nan


def numeric_diagnose(series: pd.Series):
    """返回解析率、中位数、P90（用于判别字段是否选错）"""
    parsed = series.apply(clean_numeric)
    rate = float(parsed.notna().mean()) if len(parsed) else 0.0
    med = float(parsed.median()) if parsed.notna().any() else np.nan
    p90 = float(parsed.quantile(0.9)) if parsed.notna().any() else np.nan
    return rate, med, p90


def clean_country(val):
    """清洗国家/地区代码（可按你数据继续扩展）"""
    if pd.isna(val):
        return "Unknown"
    s = str(val).strip().upper()

    # 常见归并
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
    if "UK" in s or "UNITED KINGDOM" in s or "BRITAIN" in s:
        return "UK (英国)"
    if "FR" in s or "FRANCE" in s:
        return "FR (法国)"
    if "IT" in s or "ITALY" in s:
        return "IT (意大利)"
    if "CA" in s or "CANADA" in s:
        return "CA (加拿大)"

    return s


def find_col(columns, keywords):
    """模糊查找列名（只做列名匹配；准确性由后续诊断兜底）"""
    for col in columns:
        col_norm = str(col).lower().replace(" ", "")
        for kw in keywords:
            if kw.lower().replace(" ", "") in col_norm:
                return col
    return None


def safe_mode(series: pd.Series):
    """安全取众数，避免空序列报错"""
    s = series.dropna()
    if len(s) == 0:
        return np.nan
    try:
        return s.mode().iloc[0]
    except Exception:
        return s.iloc[0]


# =============================================================================
# 2. 模式识别引擎（更稳一点：避免误判）
# =============================================================================
def detect_sheet_mode(df):
    cols = [str(c).lower() for c in df.columns]
    col_str = " ".join(cols)

    has_asin = ("asin" in col_str) or ("sku" in col_str)
    has_title = ("title" in col_str) or ("标题" in col_str) or ("name" in col_str) or ("商品" in col_str)
    has_seller = ("seller" in col_str) or ("卖家" in col_str)
    has_brand = ("brand" in col_str) or ("品牌" in col_str)
    has_share = ("share" in col_str) or ("份额" in col_str)
    has_price_or_sales = ("price" in col_str) or ("价格" in col_str) or ("sales" in col_str) or ("销量" in col_str)

    # PRODUCT：必须有（ASIN 或 Title）且同时具备价格/销量/评分等任意一个“交易字段”
    if (has_asin or has_title) and has_price_or_sales:
        return "PRODUCT"

    # SELLER：有 seller 且没有 asin（否则通常是产品表包含 seller 信息）
    if has_seller and (not has_asin):
        return "SELLER"

    # BRAND：有 brand 且有 share/revenue 这类汇总字段
    if has_brand and has_share:
        return "BRAND"

    return "GENERIC"


# =============================================================================
# 3. PRODUCT 模块：产品开发模式（含 9 大维度核心）
# =============================================================================
def render_product_dashboard(df):
    st.info("📦 **产品开发模式**（含供应链 + 9 大维度）")

    all_cols = df.columns.tolist()

    # 1) 字段映射（含 country/brand/asin 等）
    col_map = {
        "asin": find_col(all_cols, ["asin", "sku", "itemid", "产品id", "商品id"]),
        "title": find_col(all_cols, ["title", "标题", "name", "商品名"]),
        "brand": find_col(all_cols, ["brand", "品牌", "manufacturer", "maker"]),
        "price": find_col(all_cols, ["price", "价格", "售价", "均价", "currentprice", "buybox"]),
        "sales": find_col(all_cols, ["sales", "销量", "sold", "units", "orders"]),
        "revenue": find_col(all_cols, ["revenue", "销售额", "amount", "gmv"]),
        "rating": find_col(all_cols, ["rating", "评分", "stars", "avg rating", "average rating"]),
        "reviews": find_col(all_cols, ["reviews", "评论数", "评价数", "ratings count", "review count", "评分数"]),
        "country": find_col(all_cols, ["country", "region", "卖家所属地", "所属地", "国家", "location", "origin"]),
        "size": find_col(all_cols, ["size", "净含量", "规格", "oz", "ml", "g", "gram", "ounce", "容量"]),
        "flavor": find_col(all_cols, ["flavor", "味", "香型", "香味", "口味", "variant"]),
        "rank": find_col(all_cols, ["rank", "bsr", "best sellers", "排名"]),
    }

    # 2) 映射手动修正（不改变你原结构：保留“自动为主，手动为辅”）
    with st.expander("🛠️ 字段映射设置（识别不准点这里修正）", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        col_map["asin"] = c1.selectbox("ASIN/SKU", cols, index=cols.index(col_map["asin"]) if col_map["asin"] in cols else 0)
        col_map["title"] = c2.selectbox("标题/名称 Title*", cols, index=cols.index(col_map["title"]) if col_map["title"] in cols else 0)
        col_map["brand"] = c3.selectbox("品牌 Brand", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0)
        col_map["country"] = c4.selectbox("卖家所属地 Country/Region", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0)

        c5, c6, c7, c8 = st.columns(4)
        col_map["price"] = c5.selectbox("价格 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0)
        col_map["sales"] = c6.selectbox("销量 Sales/Units", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0)
        col_map["rating"] = c7.selectbox("评分 Rating(0-5)", cols, index=cols.index(col_map["rating"]) if col_map["rating"] in cols else 0)
        col_map["reviews"] = c8.selectbox("评论/评分数 Reviews/Count", cols, index=cols.index(col_map["reviews"]) if col_map["reviews"] in cols else 0)

        c9, c10, c11, c12 = st.columns(4)
        col_map["revenue"] = c9.selectbox("销售额 Revenue", cols, index=cols.index(col_map["revenue"]) if col_map["revenue"] in cols else 0)
        col_map["size"] = c10.selectbox("规格/净含量 Size", cols, index=cols.index(col_map["size"]) if col_map["size"] in cols else 0)
        col_map["flavor"] = c11.selectbox("口味/变体 Flavor/Variant", cols, index=cols.index(col_map["flavor"]) if col_map["flavor"] in cols else 0)
        col_map["rank"] = c12.selectbox("排名/BSR Rank", cols, index=cols.index(col_map["rank"]) if col_map["rank"] in cols else 0)

    # 3) 必要字段检查
    if not col_map["title"]:
        st.error("无法分析：缺少【标题/名称】列（Title）。请在映射设置中选择正确列。")
        return

    data = df.copy()
    data["Title_Str"] = data[col_map["title"]].astype(str)

    # 4) 数值清洗（失败=NaN，后续不会污染统计）
    if col_map["price"]:
        data["clean_price"] = data[col_map["price"]].apply(clean_numeric)
    else:
        data["clean_price"] = np.nan

    if col_map["sales"]:
        data["clean_sales"] = data[col_map["sales"]].apply(clean_numeric)
    else:
        data["clean_sales"] = np.nan

    if col_map["revenue"]:
        data["clean_revenue"] = data[col_map["revenue"]].apply(clean_numeric)
    else:
        data["clean_revenue"] = np.nan

    if col_map["rating"]:
        data["clean_rating"] = data[col_map["rating"]].apply(clean_numeric)
    else:
        data["clean_rating"] = np.nan

    if col_map["reviews"]:
        data["clean_reviews"] = data[col_map["reviews"]].apply(clean_numeric)
    else:
        data["clean_reviews"] = np.nan

    # 5) 国家/所属地清洗
    if col_map["country"]:
        data["_raw_country"] = data[col_map["country"]]
        data["Origin"] = data[col_map["country"]].apply(clean_country)
    else:
        data["_raw_country"] = np.nan
        data["Origin"] = "Unknown"

    # 6) 诊断：解析率 / 合理性校验（把静默错误变成可诊断、可修复）
    with st.expander("🧪 数据诊断（解析率/合理性校验）", expanded=True):
        st.caption("如果这里出现解析率很低或评分不在 0–5，说明列映射可能选错。")

        # 价格诊断
        if col_map["price"]:
            r, med, p90 = numeric_diagnose(df[col_map["price"]])
            st.write(f"**价格列**：`{col_map['price']}` | 解析率={r:.1%} | 中位数={med:.2f} | P90={p90:.2f}")
            if r < 0.25 or (np.isfinite(med) and med > 300):
                st.warning("⚠️ 价格列疑似选错（解析率过低或中位数过大）。请回到字段映射设置手动修正。")
                # 展示部分失败样本
                parsed = df[col_map["price"]].apply(clean_numeric)
                bad = df.loc[parsed.isna(), col_map["price"]].dropna().astype(str).head(12)
                if len(bad):
                    st.write("价格解析失败样本（前 12 条，若出现品牌/标题，说明选错）：")
                    st.dataframe(bad.to_frame("bad_samples"), use_container_width=True)
        else:
            st.info("ℹ️ 未选择价格列：价格相关分析会缺失。")

        # 评分诊断（强校验 0–5）
        if col_map["rating"]:
            r, med, p90 = numeric_diagnose(df[col_map["rating"]])
            st.write(f"**评分列**：`{col_map['rating']}` | 解析率={r:.1%} | 中位数={med:.2f} | P90={p90:.2f}")
            # 强校验：如果评分分布明显不是 0-5，禁用评分列
            if (not np.isfinite(med)) or med > 5.5 or p90 > 6.0:
                st.warning("⚠️ 评分列疑似选错（常见：把评论数/评分数当评分）。本 Sheet 已自动禁用评分分析。")
                data["clean_rating"] = np.nan
                col_map["rating"] = None
        else:
            st.info("ℹ️ 未选择评分列：评分相关分析会缺失。")

        # 销量诊断（不做硬阈值，只提示解析率）
        if col_map["sales"]:
            r, med, p90 = numeric_diagnose(df[col_map["sales"]])
            st.write(f"**销量列**：`{col_map['sales']}` | 解析率={r:.1%} | 中位数={med:.2f} | P90={p90:.2f}")
            if r < 0.25:
                st.warning("⚠️ 销量列解析率较低，可能选错或数据为非结构化文本。")
        else:
            st.info("ℹ️ 未选择销量列：销量相关分析会缺失。")

        # 评论/评分数诊断
        if col_map["reviews"]:
            r, med, p90 = numeric_diagnose(df[col_map["reviews"]])
            st.write(f"**评论/评分数列**：`{col_map['reviews']}` | 解析率={r:.1%} | 中位数={med:.2f} | P90={p90:.2f}")
        else:
            st.info("ℹ️ 未选择评论/评分数列：可用于“需求代理”的口径会缺失。")

    # =============================================================================
    # 7) 9 大维度：字段抽取与派生
    # =============================================================================

    # --- 维度一：SKU结构（Pack / 规格 / Flavor / ASIN） ---
    def extract_pack(title: str) -> int:
        t = str(title).lower()
        m = re.search(r"(pack\s*of\s*\d+|\d+\s*pack\b|\d+\s*count\b|\bx\s*\d+)", t)
        if m:
            nums = re.findall(r"\d+", m.group(0))
            return int(nums[0]) if nums else 1
        return 1

    data["Pack_Count"] = data["Title_Str"].apply(extract_pack)
    data["Is_Multipack"] = data["Pack_Count"] > 1

    # flavor：优先列，否则从标题粗提取（可按你的品类换词库）
    FLAVOR_KW = ["mint", "spearmint", "peppermint", "cinnamon", "strawberry", "bubblegum", "lemon", "orange"]
    if col_map["flavor"]:
        data["Flavor"] = data[col_map["flavor"]].astype(str)
    else:
        def extract_flavor_from_title(t: str):
            tl = str(t).lower()
            hits = [k for k in FLAVOR_KW if k in tl]
            return hits[0] if hits else np.nan
        data["Flavor"] = data["Title_Str"].apply(extract_flavor_from_title)

    # size：如果没有 size 列，可从标题抓常见规格（oz/g/ml）
    def extract_size_str(t: str):
        tl = str(t).lower()
        m = re.search(r"(\d+(?:\.\d+)?)\s*(oz|ounce|ounces|g|gram|grams|ml|l)\b", tl)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        return np.nan

    if col_map["size"]:
        data["Size_Str"] = data[col_map["size"]].astype(str)
    else:
        data["Size_Str"] = data["Title_Str"].apply(extract_size_str)

    # --- 维度二：功效与技术路线 ---
    TECH_KW = ["nano", "hydroxyapatite", "hap", "fluoride-free", "fluoride free", "xylitol", "charcoal", "probiotic", "biomimetic"]
    EFF_KW = ["remineral", "remineralization", "sensitivity", "sensitive", "whitening", "stain", "enamel", "gum", "fresh breath", "cavity", "plaque", "tartar", "repair"]

    def extract_kw_list(text: str, kws):
        tl = str(text).lower()
        return [k for k in kws if k in tl]

    data["Tech_Tags"] = data["Title_Str"].apply(lambda x: extract_kw_list(x, TECH_KW))
    data["Eff_Tags"] = data["Title_Str"].apply(lambda x: extract_kw_list(x, EFF_KW))

    data["Tech_Main"] = data["Tech_Tags"].apply(lambda x: x[0] if isinstance(x, list) and len(x) else np.nan)
    data["Eff_Main"] = data["Eff_Tags"].apply(lambda x: x[0] if isinstance(x, list) and len(x) else np.nan)

    # --- 维度三：价格带 & 锚点 ---
    data["Price_Band"] = pd.cut(
        data["clean_price"],
        bins=[0, 10, 15, 20, 30, 1000],
        labels=["<10", "10-15", "15-20", "20-30", "30+"]
    )

    # 单支价（Pack 后）
    data["Unit_Price_per_item"] = np.where(
        data["clean_price"].notna() & (data["Pack_Count"] > 0),
        data["clean_price"] / data["Pack_Count"].replace(0, np.nan),
        np.nan
    )

    # --- 维度四：品牌定位与背书强度 ---
    MEDICAL_KW = ["doctor", "dr.", "clinical", "health", "professional", "dentist"]
    if col_map["brand"]:
        data["Brand_Str"] = data[col_map["brand"]].astype(str)
        data["Brand_Type"] = data["Brand_Str"].str.lower().apply(
            lambda x: "Medical/Functional" if any(k in x for k in MEDICAL_KW) else "Consumer"
        )
    else:
        data["Brand_Str"] = np.nan
        data["Brand_Type"] = "Unknown"

    # --- 维度五：包装体积 & FBA风险（简化 proxy：多支装可能触发） ---
    data["FBA_Risk_Flag"] = data["Pack_Count"] >= 3

    # --- 维度六：内容表达与卖点密度 ---
    data["Title_Length"] = data["Title_Str"].str.len()
    data["Selling_Point_Count"] = data["Title_Str"].apply(
        lambda x: int(sum([(k in str(x).lower()) for k in (TECH_KW + EFF_KW)]))
    )
    data["Is_Tech_Heavy"] = data["Tech_Tags"].apply(lambda x: len(x) >= 2)

    # --- 维度七：渠道策略（proxy：销量集中度 / 排名如有） ---
    if data["clean_sales"].notna().any():
        total_sales = data["clean_sales"].sum(skipna=True)
        top10_sales = data.sort_values("clean_sales", ascending=False).head(10)["clean_sales"].sum(skipna=True)
        sales_concentration_top10 = float(top10_sales / total_sales) if total_sales and total_sales > 0 else np.nan
    else:
        sales_concentration_top10 = np.nan

    # --- 维度八：市场成熟度（综合评分：规则可调） ---
    # 价格收敛：std 越小越成熟；技术集中：主技术占比越高越成熟；SKU标准化：pack 种类越少越成熟
    price_std = float(data["clean_price"].std(skipna=True)) if data["clean_price"].notna().any() else np.nan
    tech_mode_share = np.nan
    if data["Tech_Main"].notna().any():
        tech_mode_share = float(data["Tech_Main"].value_counts(normalize=True, dropna=True).iloc[0])
    pack_unique = int(data["Pack_Count"].nunique(dropna=True))

    # 构造一个 0-100 的“成熟度分”（越高越成熟）
    # 经验规则：可按类目微调
    score = 0
    if np.isfinite(price_std):
        # std <=5 记更成熟
        score += 35 if price_std <= 5 else (20 if price_std <= 10 else 10)
    else:
        score += 10

    if np.isfinite(tech_mode_share):
        score += 35 if tech_mode_share >= 0.5 else (20 if tech_mode_share >= 0.3 else 10)
    else:
        score += 10

    score += 30 if pack_unique <= 3 else (20 if pack_unique <= 6 else 10)
    market_maturity_score = int(min(max(score, 0), 100))

    # --- 维度九：可反推的开发决策清单（Tab 内输出） ---

    # =============================================================================
    # 8) KPI 指标卡（仅用有效值，避免 NaN 污染）
    # =============================================================================
    k1, k2, k3, k4 = st.columns(4)
    # 总销量（有效）
    total_sales_val = float(data["clean_sales"].sum(skipna=True)) if data["clean_sales"].notna().any() else 0.0
    avg_price_val = float(data["clean_price"].mean(skipna=True)) if data["clean_price"].notna().any() else np.nan
    # 销售额：优先用 clean_revenue，否则用 sales*price
    if data["clean_revenue"].notna().any():
        total_rev_val = float(data["clean_revenue"].sum(skipna=True))
        rev_label = "总销售额"
    elif data["clean_sales"].notna().any() and data["clean_price"].notna().any():
        total_rev_val = float((data["clean_sales"] * data["clean_price"]).sum(skipna=True))
        rev_label = "预估销售额"
    else:
        total_rev_val = np.nan
        rev_label = "销售额"

    avg_rating_val = float(data["clean_rating"].mean(skipna=True)) if data["clean_rating"].notna().any() else np.nan
    demand_proxy = float(data["clean_reviews"].sum(skipna=True)) if data["clean_reviews"].notna().any() else np.nan

    k1.metric("SKU数", f"{len(data):,}")
    k2.metric("总销量（有效）", f"{total_sales_val:,.0f}")
    k3.metric(rev_label, f"${total_rev_val:,.0f}" if np.isfinite(total_rev_val) else "N/A")
    k4.metric("平均评分（有效）", f"{avg_rating_val:.2f} ⭐" if np.isfinite(avg_rating_val) else "N/A")

    # =============================================================================
    # 9) 可视化 Tabs（保持你原 Tab 思路，但增强内容）
    # =============================================================================
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🌏 供应链与国家",
        "📦 SKU结构&形态",
        "🧪 功效&技术路线",
        "💰 价格体系&锚点",
        "🗣️ 表达密度&内容策略",
        "✅ 决策建议"
    ])

    # ---------------------------
    # Tab1: 供应链与国家
    # ---------------------------
    with tab1:
        st.subheader("供应链源头分析（Seller Location / Origin）")

        if col_map["country"]:
            c1, c2 = st.columns(2)

            with c1:
                origin_counts = data["Origin"].value_counts(dropna=False).reset_index()
                origin_counts.columns = ["Origin", "Count"]
                fig = px.pie(origin_counts, values="Count", names="Origin",
                             title="卖家所属地分布（SKU数量）", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                price_by_country = data.groupby("Origin", dropna=False)["clean_price"].mean(skipna=True).reset_index()
                fig2 = px.bar(price_by_country, x="Origin", y="clean_price",
                              title="不同所属地卖家的平均售价（有效价格）", color="Origin")
                st.plotly_chart(fig2, use_container_width=True)

            cn_ratio = float((data["Origin"].astype(str).str.contains("CN")).mean())
            if cn_ratio > 0.6:
                st.warning(f"🔴 供应链预警：中国卖家占比 {cn_ratio:.1%}。通常意味着供应链成熟、价格战更激烈。")
            elif cn_ratio < 0.2:
                st.success(f"🟢 机会信号：中国卖家占比 {cn_ratio:.1%}。本土品牌为主，可能存在供应链降本切入机会。")
            else:
                st.info(f"🟡 中性：CN 占比 {cn_ratio:.1%}。需要结合价格带/品牌类型进一步判断。")
        else:
            st.warning("⚠️ 未检测到 Country/Region/所属地列。请在字段映射设置里手动选择正确列。")

        st.markdown("#### 需求代理口径提示")
        if np.isfinite(demand_proxy):
            st.write(f"当前使用 `评论/评分数` 作为需求代理（总量={demand_proxy:,.0f}）。")
        else:
            st.write("未提供评论/评分数列：建议补充 Reviews/Rating Count，用于更稳健的需求代理判断。")

    # ---------------------------
    # Tab2: SKU结构 & 形态
    # ---------------------------
    with tab2:
        st.subheader("产品形态与 SKU 结构（Product Architecture）")

        c1, c2 = st.columns(2)
        with c1:
            # Pack 分布：用销量加权优先，否则用SKU计数
            if data["clean_sales"].notna().any():
                pack_dist = data.groupby("Pack_Count")["clean_sales"].sum(skipna=True).reset_index()
                fig = px.bar(pack_dist, x="Pack_Count", y="clean_sales",
                             title="Pack 数分布（按销量加权）")
            else:
                pack_cnt = data["Pack_Count"].value_counts().reset_index()
                pack_cnt.columns = ["Pack_Count", "Count"]
                fig = px.bar(pack_cnt, x="Pack_Count", y="Count",
                             title="Pack 数分布（按SKU数量）")
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            # Flavor 分布（若可用）
            flav = data["Flavor"].dropna()
            if len(flav):
                top_flavor = flav.value_counts().head(15).reset_index()
                top_flavor.columns = ["Flavor", "Count"]
                fig2 = px.bar(top_flavor, x="Count", y="Flavor", orientation="h",
                              title="口味/变体 Top15（计数）")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("未识别到 Flavor：如数据里有变体列请在映射中选择 Flavor/Variant。")

        st.markdown("#### 多支装是否承担客单价/摊薄成本？")
        tmp = data.dropna(subset=["clean_price"]).copy()
        if len(tmp):
            tmp["Unit_Price_per_item"] = tmp["clean_price"] / tmp["Pack_Count"].replace(0, np.nan)
            g = tmp.groupby("Is_Multipack").agg(
                SKU数=("Title_Str", "size"),
                均价=("clean_price", "mean"),
                单支均价=("Unit_Price_per_item", "mean")
            ).reset_index()
            g["Is_Multipack"] = g["Is_Multipack"].map({True: "Multipack", False: "Single"})
            st.dataframe(g, use_container_width=True)
        else:
            st.info("价格不可用：无法计算单支均价。")

        st.markdown("#### 规格（Size）可用性")
        non_empty_size = data["Size_Str"].astype(str).str.strip()
        st.write(f"可解析/可见规格字段占比（非空）：{(non_empty_size != 'nan').mean():.1%}")

    # ---------------------------
    # Tab3: 功效 & 技术路线
    # ---------------------------
    with tab3:
        st.subheader("功效与技术路线（Efficacy & Tech Route）")

        c1, c2 = st.columns(2)
        with c1:
            eff = data["Eff_Main"].dropna()
            if len(eff):
                eff_hot = eff.value_counts().head(15).reset_index()
                eff_hot.columns = ["Efficacy", "Count"]
                fig = px.bar(eff_hot, x="Count", y="Efficacy", orientation="h", title="功效主词 Top15（计数）")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("标题中未匹配到功效关键词（可扩展 EFF_KW 词库）。")

        with c2:
            tech = data["Tech_Main"].dropna()
            if len(tech):
                tech_hot = tech.value_counts().head(15).reset_index()
                tech_hot.columns = ["Tech", "Count"]
                fig = px.bar(tech_hot, x="Count", y="Tech", orientation="h", title="技术主词 Top15（计数）")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("标题中未匹配到技术关键词（可扩展 TECH_KW 词库）。")

        st.markdown("#### 技术/功效是否同质化？（集中度）")
        if data["Tech_Main"].notna().any():
            top_share = float(data["Tech_Main"].value_counts(normalize=True, dropna=True).iloc[0])
            st.write(f"技术主词 Top1 占比：**{top_share:.1%}**（越高=越同质化/越成熟）")
        else:
            st.write("技术主词不可用。")

        if data["Eff_Main"].notna().any():
            top_share2 = float(data["Eff_Main"].value_counts(normalize=True, dropna=True).iloc[0])
            st.write(f"功效主词 Top1 占比：**{top_share2:.1%}**（越高=越集中）")
        else:
            st.write("功效主词不可用。")

        st.markdown("#### 技术叙事是否支撑溢价？（Tech vs Price）")
        tmp = data.dropna(subset=["clean_price"]).copy()
        if len(tmp) and tmp["Tech_Main"].notna().any():
            g = tmp.groupby("Tech_Main")["clean_price"].mean().dropna().sort_values(ascending=False).head(15).reset_index()
            fig = px.bar(g, x="clean_price", y="Tech_Main", orientation="h", title="不同技术主词的平均售价（有效价格）")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("价格或技术标签不可用，无法做技术溢价对比。")

    # ---------------------------
    # Tab4: 价格体系 & 锚点
    # ---------------------------
    with tab4:
        st.subheader("价格带 & 价值锚点（Price Architecture）")

        if data["clean_price"].notna().any():
            fig = px.histogram(data.dropna(subset=["clean_price"]), x="clean_price", nbins=25,
                               title="售价区间分布（有效价格）", color="Origin")
            st.plotly_chart(fig, use_container_width=True)

            # 价格带（SKU计数）
            band = data.groupby("Price_Band", dropna=False)["Title_Str"].size().reset_index()
            band.columns = ["Price_Band", "SKU_Count"]
            fig2 = px.bar(band, x="Price_Band", y="SKU_Count", title="价格带分布（SKU数量）")
            st.plotly_chart(fig2, use_container_width=True)

            # 单支价分布（如果 pack 提取有效）
            tmp = data.dropna(subset=["Unit_Price_per_item"]).copy()
            if len(tmp):
                fig3 = px.histogram(tmp, x="Unit_Price_per_item", nbins=25, title="单支价格分布（价格/Pack）")
                st.plotly_chart(fig3, use_container_width=True)
        else:
            st.warning("⚠️ 价格不可用：请修正 Price 列映射或检查数据源。")

        st.markdown("#### 高价位是否绑定专业背书？（Brand Type vs Price）")
        tmp = data.dropna(subset=["clean_price"]).copy()
        if len(tmp) and "Brand_Type" in tmp.columns:
            g = tmp.groupby("Brand_Type")["clean_price"].mean().reset_index()
            fig = px.bar(g, x="Brand_Type", y="clean_price", title="不同品牌定位的平均售价（有效价格）")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("缺少品牌或价格数据，无法判断背书与价格绑定关系。")

    # ---------------------------
    # Tab5: 内容表达 & 卖点密度
    # ---------------------------
    with tab5:
        st.subheader("内容表达与卖点密度（Messaging Strategy）")

        c1, c2 = st.columns(2)
        with c1:
            fig = px.histogram(data, x="Title_Length", nbins=30, title="标题长度分布")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.histogram(data, x="Selling_Point_Count", nbins=15, title="标题卖点数量分布（技术+功效词命中数）")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 是否存在“说不清但卖得好”的产品？（短标题+高销量）")
        if data["clean_sales"].notna().any():
            tmp = data.dropna(subset=["clean_sales"]).copy()
            tmp = tmp[tmp["clean_sales"] > 0]
            if len(tmp):
                tmp["short_title_flag"] = tmp["Title_Length"] <= tmp["Title_Length"].median()
                # 候选：短标题 & 高销量（Top20%）
                q = tmp["clean_sales"].quantile(0.8)
                cand = tmp[(tmp["short_title_flag"]) & (tmp["clean_sales"] >= q)].copy()
                cand = cand.sort_values("clean_sales", ascending=False).head(15)

                if len(cand):
                    show_cols = ["Title_Str", "clean_sales", "clean_price", "Origin", "Selling_Point_Count", "Title_Length", "Tech_Main", "Eff_Main"]
                    st.dataframe(cand[show_cols], use_container_width=True, height=360)
                    st.info("这些 SKU 可能具备：表达更简洁，但依旧卖得好（可能依赖品牌/渠道/外部背书/强需求）。")
                else:
                    st.write("未发现明显的“短标题+高销量”候选。")
        else:
            st.info("未提供销量列：无法做“说不清但卖得好”识别。")

        st.markdown("#### 高频词（粗略）")
        text = " ".join(data["Title_Str"].tolist()).lower()
        stop = set(["toothpaste", "with", "pack", "count", "ounce", "oz", "ml", "gram", "grams", "and", "for", "the"])
        words = [w for w in re.split(r"\W+", text) if len(w) > 3 and w not in stop]
        top_words = pd.Series(words).value_counts().head(20)
        st.bar_chart(top_words)

    # ---------------------------
    # Tab6: 决策建议（输出“开发决策清单”）
    # ---------------------------
    with tab6:
        st.subheader("🤖 产品开发决策清单（可直接写进立项）")

        # 多规格判断：多支装销量占比 / SKU占比
        multi_sales_share = np.nan
        if data["clean_sales"].notna().any():
            s_total = data["clean_sales"].sum(skipna=True)
            s_multi = data.loc[data["Is_Multipack"], "clean_sales"].sum(skipna=True)
            multi_sales_share = float(s_multi / s_total) if s_total and s_total > 0 else np.nan
        multi_sku_share = float(data["Is_Multipack"].mean()) if len(data) else np.nan

        # 技术化判断：技术标签覆盖 & tech-heavy 占比
        tech_cover = float(data["Tech_Main"].notna().mean()) if len(data) else np.nan
        tech_heavy = float(data["Is_Tech_Heavy"].mean()) if len(data) else np.nan

        # 专业背书占比
        med_share = float((data["Brand_Type"] == "Medical/Functional").mean()) if "Brand_Type" in data.columns else np.nan

        # 价格锚点（中位数）
        price_median = float(data["clean_price"].median()) if data["clean_price"].notna().any() else np.nan

        # 成熟度结论
        if market_maturity_score >= 70:
            maturity_txt = "偏成熟（拼执行/渠道/成本）"
        elif market_maturity_score >= 45:
            maturity_txt = "中等成熟（仍可差异化切入）"
        else:
            maturity_txt = "相对早期（通过体验/技术/叙事都有机会）"

        # 渠道依赖 proxy
        if np.isfinite(sales_concentration_top10):
            if sales_concentration_top10 >= 0.6:
                channel_txt = "头部高度集中（更偏广告/资源驱动，进入门槛更高）"
            elif sales_concentration_top10 >= 0.4:
                channel_txt = "头部中度集中（既要投放，也要产品硬差异）"
            else:
                channel_txt = "头部分散（更可能自然流量也能跑，产品差异是关键）"
        else:
            channel_txt = "缺少销量，无法判断渠道集中度"

        st.markdown("### 1) 我们要不要做多规格？")
        if np.isfinite(multi_sales_share):
            if multi_sales_share >= 0.4:
                st.success(f"建议：**要做**（多支装销量占比 {multi_sales_share:.1%}，说明多规格是真需求/强运营工具）")
            else:
                st.info(f"建议：**首发可先单规格**（多支装销量占比 {multi_sales_share:.1%}，多支装更像后续拉客单工具）")
        else:
            # 没销量，用SKU占比
            if np.isfinite(multi_sku_share) and multi_sku_share >= 0.3:
                st.info(f"建议：倾向做（多支装 SKU 占比 {multi_sku_share:.1%}），但建议补充销量/评论作为校验。")
            else:
                st.info("建议：先单规格试水（缺销量/评论数据，谨慎一次上太多规格）。")

        st.markdown("### 2) 功效主轴要“技术”还是“体验”？")
        if np.isfinite(tech_cover):
            if tech_cover >= 0.6:
                st.warning(f"市场当前偏技术叙事（技术标签覆盖 {tech_cover:.1%}，tech-heavy {tech_heavy:.1%}）。你要么卷更硬技术/证据，要么反向做“更好懂的体验路线”。")
            else:
                st.success(f"市场技术叙事不算压倒性（技术覆盖 {tech_cover:.1%}）。更适合用“温和、长期、体验可感”切入。")
        else:
            st.info("缺少技术标签信号（可扩展 TECH_KW 词库或补充字段）。")

        st.markdown("### 3) 是否需要医疗/专家背书？")
        if np.isfinite(med_share):
            if med_share >= 0.5:
                st.warning(f"建议：**需要背书**（医疗/功能品牌占比 {med_share:.1%}）。高价位更可能绑定专业信任。")
            else:
                st.success(f"建议：**不一定需要强背书**（医疗/功能品牌占比 {med_share:.1%}）。消费品牌仍有机会靠体验/包装专业感进入。")
        else:
            st.info("缺少品牌字段，无法判断背书格局。")

        st.markdown("### 4) 合理目标定价 & 是否一步到位？")
        if np.isfinite(price_median):
            st.write(f"市场价格中位数（有效价格）：**${price_median:.2f}**")
            st.write("参考锚点：")
            if price_median >= 15:
                st.info("市场能接受中高价。若你要上高价，建议同步强化：技术证据/专业背书/包装专业感。")
            else:
                st.info("市场偏中低价。若你想拉高客单，需要“更强的理由”（临床/稀缺技术/更好体验）。")
        else:
            st.warning("价格不可用：请先修复价格列映射。")

        st.markdown("### 5) 包装/组合装是否有风险？（FBA proxy）")
        fba_risk_rate = float(data["FBA_Risk_Flag"].mean()) if len(data) else np.nan
        if np.isfinite(fba_risk_rate):
            st.write(f"Pack>=3 的 SKU 占比：**{fba_risk_rate:.1%}**（越高越需要注意 FBA 成本/体积临界点）")
        else:
            st.write("无法计算 FBA 风险 proxy。")

        st.markdown("### 6) 渠道/可见度模型（proxy）")
        st.write(channel_txt)

        st.markdown("### 7) 市场成熟度与进入难度")
        st.metric("市场成熟度评分（0-100）", f"{market_maturity_score}/100")
        st.write(f"结论：**{maturity_txt}**")
        st.caption("评分逻辑：价格收敛 + 技术集中 + SKU标准化（可按类目调整阈值）")

        st.markdown("### 8) Top SKU（用于你快速定位竞品策略）")
        sort_key = None
        if data["clean_sales"].notna().any():
            sort_key = "clean_sales"
        elif data["clean_reviews"].notna().any():
            sort_key = "clean_reviews"
        elif data["clean_revenue"].notna().any():
            sort_key = "clean_revenue"

        if sort_key:
            top = data.sort_values(sort_key, ascending=False).head(20).copy()
            top["_short_title"] = top["Title_Str"].astype(str).str[:80] + "..."
            show_cols = ["_short_title", "clean_price", "Unit_Price_per_item", "Pack_Count", "Origin", "Tech_Main", "Eff_Main", "Selling_Point_Count"]
            if sort_key in top.columns:
                show_cols.insert(1, sort_key)
            st.dataframe(top[show_cols], use_container_width=True, height=420)
        else:
            st.info("缺少销量/评论/销售额等排序字段，无法输出 Top SKU。")

    # 原始数据预览
    with st.expander("查看原始数据（前 50 行）", expanded=False):
        st.dataframe(df.head(50), use_container_width=True)


# =============================================================================
# 4. BRAND 模块：品牌格局模式
# =============================================================================
def render_brand_dashboard(df):
    st.info("🏢 **品牌格局模式**")
    all_cols = df.columns.tolist()
    col_map = {
        "brand": find_col(all_cols, ["brand", "品牌"]),
        "share": find_col(all_cols, ["share", "份额"]),
        "rev": find_col(all_cols, ["revenue", "销售额", "gmv", "amount"]),
        "price": find_col(all_cols, ["price", "价格", "均价"])
    }

    with st.expander("🛠️ 字段映射设置（品牌表）", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3, c4 = st.columns(4)
        col_map["brand"] = c1.selectbox("品牌 Brand*", cols, index=cols.index(col_map["brand"]) if col_map["brand"] in cols else 0)
        col_map["share"] = c2.selectbox("份额 Share", cols, index=cols.index(col_map["share"]) if col_map["share"] in cols else 0)
        col_map["rev"] = c3.selectbox("销售额 Revenue", cols, index=cols.index(col_map["rev"]) if col_map["rev"] in cols else 0)
        col_map["price"] = c4.selectbox("均价 Price", cols, index=cols.index(col_map["price"]) if col_map["price"] in cols else 0)

    if not col_map["brand"]:
        st.error("缺少品牌列，无法分析。")
        return

    data = df.copy()

    if col_map["share"]:
        data["clean_share"] = data[col_map["share"]].apply(clean_numeric)
    else:
        data["clean_share"] = np.nan

    if col_map["rev"]:
        data["clean_rev"] = data[col_map["rev"]].apply(clean_numeric)
    else:
        data["clean_rev"] = np.nan

    if col_map["price"]:
        data["clean_price"] = data[col_map["price"]].apply(clean_numeric)
    else:
        data["clean_price"] = np.nan

    # 选择价值列：优先销售额，其次份额
    val_col = None
    if data["clean_rev"].notna().any():
        val_col = "clean_rev"
    elif data["clean_share"].notna().any():
        val_col = "clean_share"

    if not val_col:
        st.error("缺少销售额或份额数据（且解析失败）。请检查映射或数据格式。")
        return

    data = data.sort_values(val_col, ascending=False)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("品牌垄断度")
        top5 = float(data.head(5)[val_col].sum(skipna=True))
        total = float(data[val_col].sum(skipna=True))
        cr5 = top5 / total if total > 0 else 0
        st.metric("CR5 (Top5 占比)", f"{cr5:.1%}")

        fig = px.pie(data.head(10), values=val_col, names=col_map["brand"], title="Top10 品牌占比", hole=0.35)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("品牌价格带")
        if data["clean_price"].notna().any():
            fig = px.bar(data.head(15), x=col_map["brand"], y="clean_price", title="头部品牌均价对比")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("未提供价格列或价格解析失败。")

    with st.expander("查看原始数据（前 50 行）", expanded=False):
        st.dataframe(df.head(50), use_container_width=True)


# =============================================================================
# 5. SELLER 模块：渠道卖家模式（含国家）——修复饼图 bug
# =============================================================================
def render_seller_dashboard(df):
    st.info("🏪 **渠道卖家模式**")
    all_cols = df.columns.tolist()
    col_map = {
        "seller": find_col(all_cols, ["seller", "卖家"]),
        "sales": find_col(all_cols, ["sales", "销量", "units", "orders"]),
        "country": find_col(all_cols, ["country", "region", "国家", "属地", "location", "origin"]),
    }

    with st.expander("🛠️ 字段映射设置（卖家表）", expanded=False):
        cols = [None] + all_cols
        c1, c2, c3 = st.columns(3)
        col_map["seller"] = c1.selectbox("卖家 Seller*", cols, index=cols.index(col_map["seller"]) if col_map["seller"] in cols else 0)
        col_map["sales"] = c2.selectbox("销量 Sales", cols, index=cols.index(col_map["sales"]) if col_map["sales"] in cols else 0)
        col_map["country"] = c3.selectbox("所属地 Country/Region", cols, index=cols.index(col_map["country"]) if col_map["country"] in cols else 0)

    data = df.copy()

    if col_map["sales"]:
        data["clean_sales"] = data[col_map["sales"]].apply(clean_numeric)
    else:
        data["clean_sales"] = np.nan

    if col_map["country"]:
        data["Origin"] = data[col_map["country"]].apply(clean_country)
    else:
        data["Origin"] = "Unknown"

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("卖家国籍分布")
        if col_map["country"]:
            cnt = data["Origin"].value_counts(dropna=False).reset_index()
            cnt.columns = ["Origin", "count"]  # ✅ 修复：保证列名稳定
            fig = px.pie(cnt, values="count", names="Origin", title="卖家所属地占比（按店铺数）", hole=0.35)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未找到[卖家所属地]列")

    with c2:
        st.subheader("Top 卖家排行")
        if col_map["seller"] and data["clean_sales"].notna().any():
            top = data.dropna(subset=["clean_sales"]).sort_values("clean_sales", ascending=False).head(10)
            fig = px.bar(top, x="clean_sales", y=col_map["seller"], orientation="h", title="Top10 卖家（按销量）")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("缺少卖家列或销量列/销量解析失败，无法输出 Top 卖家。")

    with st.expander("查看原始数据（前 50 行）", expanded=False):
        st.dataframe(df.head(50), use_container_width=True)


# =============================================================================
# 6. 主程序入口
# =============================================================================
st.sidebar.header("📂 上传文件")
uploaded_file = st.sidebar.file_uploader("上传 Excel/CSV", type=["xlsx", "csv"])

if uploaded_file:
    dfs = {}
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            try:
                df0 = pd.read_csv(uploaded_file, encoding="utf-8")
            except Exception:
                uploaded_file.seek(0)
                df0 = pd.read_csv(uploaded_file, encoding="gbk")
            dfs["Sheet1"] = df0
        else:
            xl = pd.ExcelFile(uploaded_file)
            for sheet in xl.sheet_names:
                dfs[sheet] = pd.read_excel(uploaded_file, sheet_name=sheet)
                dfs[sheet].columns = dfs[sheet].columns.astype(str).str.strip()
    except Exception as e:
        st.error(f"读取错误: {e}")
        st.stop()

    st.success(f"成功读取 {len(dfs)} 个工作表：{', '.join(list(dfs.keys()))}")

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
                st.info("GENERIC：未识别出明确模式，展示数据预览。")
                st.dataframe(df_active.head(50), use_container_width=True)
else:
    st.info("👈 请上传数据文件开始分析")
