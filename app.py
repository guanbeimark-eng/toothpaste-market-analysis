# -*- coding: utf-8 -*-
import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# =============================================================================
# 1) 页面配置
# =============================================================================
st.set_page_config(page_title="市场&产品开发分析（Excel/CSV）", layout="wide")
st.title("🧠 市场数据 → 产品开发机会点分析（Excel/CSV 通用版）")
st.markdown("""
**使用说明：**
1) 支持上传 **.xlsx / .csv**  
2) Excel 会让你选择 Sheet  
3) 选择/确认字段映射后，程序会自动输出：  
- **规格净含量、装数（Pack）、单位价格**  
- **标题关键词标签（功效/技术/人群/场景）**  
- **价格结构、品牌集中度、机会点、风险点**  
- **中文可视化图表 + 可导出 Excel 多 Sheet 报告**
""")

# =============================================================================
# 2) 文件加载
# =============================================================================
def load_file(uploaded_file):
    if uploaded_file is None:
        return None, None, "没有文件"

    file_name = uploaded_file.name.lower()

    if file_name.endswith(".xlsx"):
        try:
            xl = pd.ExcelFile(uploaded_file)
            return "xlsx", xl, None
        except Exception as e:
            return None, None, f"Excel 读取失败: {str(e)}"

    if file_name.endswith(".csv"):
        encodings = ["utf-8", "gbk", "utf-8-sig", "ISO-8859-1"]
        for enc in encodings:
            try:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding=enc)
                df.columns = df.columns.astype(str).str.strip()
                return "csv", df, None
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return None, None, str(e)
        return None, None, "CSV 编码识别失败，请转存为 UTF-8 格式。"

    return None, None, "不支持的文件格式，请上传 .csv 或 .xlsx"


def clean_numeric(val):
    """尽可能把值变成 float；失败返回 NaN"""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        return float(val)
    try:
        s = str(val)
        s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("%", "")
        return float(s)
    except:
        return np.nan


# =============================================================================
# 3) 更强列名识别：关键词词库 + 加权打分
# =============================================================================
FIELD_KEYWORDS = {
    "asin": {
        "include": ["asin", "sku", "parent asin", "child asin", "asin码", "父asin", "子asin", "商品id", "产品id", "listing id", "item id"],
        "exclude": ["brand", "title", "name"]
    },
    "brand": {
        "include": ["brand", "品牌", "品牌名", "manufacturer", "maker", "厂牌", "company"],
        "exclude": ["brand registry", "brand story", "title"]
    },
    "title": {
        "include": ["title", "name", "product name", "商品名", "商品标题", "标题", "品名", "listing title", "product title"],
        "exclude": ["brand", "asin", "sku"]
    },
    "price": {
        "include": ["price", "售价", "当前价", "现价", "sale price", "our price", "buy box", "buybox", "价格", "current price"],
        "exclude": ["list price", "msrp", "coupon", "discount", "save", "off", "promo"]
    },
    "rating": {
        "include": ["rating", "stars", "star", "评分", "星级", "average rating", "avg rating", "rating score"],
        "exclude": ["ratings count", "review", "reviews", "total ratings", "review count"]
    },
    "reviews": {
        "include": ["reviews", "review", "review count", "ratings count", "total ratings", "评论数", "评价数", "评分数", "review#", "ratings#", "number of reviews"],
        "exclude": ["rating", "stars", "star", "avg rating"]
    },
    "sales": {
        "include": ["sales", "units", "销量", "销售量", "unit sold", "sold", "orders", "订单量", "units sold"],
        "exclude": ["sales rank", "rank", "bsr"]
    },
    "revenue": {
        "include": ["revenue", "sales revenue", "销售额", "成交额", "gmv", "金额", "sales $", "gross sales"],
        "exclude": ["profit", "margin", "net"]
    },
    "size": {
        "include": ["size", "net", "net content", "net wt", "net weight", "净含量", "净重", "含量", "oz", "ounce", "ml", "g", "gram", "volume"],
        "exclude": ["dimension", "dimensions", "length", "width", "height", "package", "shipping"]
    },
    "pack": {
        "include": ["pack", "pack of", "count", "qty", "quantity", "数量", "装", "套装", "组合", "variant", "variations", "variation", "flavor", "口味", "规格"],
        "exclude": ["package weight", "package dimensions", "shipping"]
    },
    "weight": {
        "include": ["weight", "重量", "package weight", "item weight", "shipping weight", "lbs", "lb", "pounds", "kg"],
        "exclude": ["net wt", "net weight", "净重", "净含量"]
    },
    "dimensions": {
        "include": ["dimensions", "dimension", "尺寸", "package dimensions", "item dimensions", "length", "width", "height", "cm", "inch", "inches"],
        "exclude": ["size", "net", "oz", "ml", "g", "gram"]
    },
    "rank": {
        "include": ["rank", "bsr", "best sellers rank", "排名", "搜索排名", "organic rank", "ads rank", "position", "ranking"],
        "exclude": ["rating", "reviews"]
    }
}

def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def get_col_index(options, field_key, default=0):
    """
    options: df.columns 的 list
    field_key: FIELD_KEYWORDS 中的 key，比如 'price'/'reviews'
    返回最匹配列的 index
    """
    rules = FIELD_KEYWORDS.get(field_key)
    if rules is None:
        return default

    best_i, best_score = default, -10**9
    for i, col in enumerate(options):
        c = _norm(col)
        score = 0

        # include 命中加分：越靠前关键词权重越高
        for j, kw in enumerate(rules["include"]):
            kw_n = _norm(kw)
            if kw_n in c:
                score += 10 - min(j, 8)

        # exclude 命中扣分
        for kw in rules.get("exclude", []):
            if _norm(kw) in c:
                score -= 12

        # 更稳：如果列名非常短且完全包含关键字，额外加分
        for kw in rules["include"][:6]:
            kw_n = _norm(kw)
            if kw_n in c and len(c) <= max(len(kw_n) + 8, 18):
                score += 2

        if score > best_score:
            best_score = score
            best_i = i

    return best_i

# =============================================================================
# 4) 特征工程：净含量 / Pack / 标签
# =============================================================================
UNIT_TO_G = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "ml": 1.0,      # 近似：1ml≈1g（如需更精确可按品类密度调整）
    "l": 1000.0,
}

def parse_net_content_to_g(text):
    """
    从字符串抽取净含量，统一成 g
    示例： "4 Ounce", "120g", "100 ml", "0.5 kg"
    """
    if pd.isna(text):
        return np.nan
    s = str(text).lower()

    m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gram|grams|kg|oz|ounce|ounces|ml|l)\b", s)
    if not m:
        return np.nan
    val = float(m.group(1))
    unit = m.group(2)
    return val * UNIT_TO_G.get(unit, np.nan)

def parse_pack_count(text):
    """
    抽取 pack 数（Pack of 3 / 3 Pack / x3）
    如果没有就返回 1
    """
    if pd.isna(text):
        return 1
    s = str(text).lower()

    m = re.search(r"pack\s*of\s*(\d+)", s)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*pack\b", s)
    if m:
        return int(m.group(1))

    m = re.search(r"[x×]\s*(\d+)", s)
    if m:
        return int(m.group(1))

    return 1

# 你可以在侧边栏改成可编辑词库，这里给默认词库
DEFAULT_TAG_DICT = {
    "功效": [
        "whitening", "brighten", "sensitivity", "sensitive", "repair", "remineral", "remineralization", "enamel",
        "gum", "fresh", "breath", "cavity", "anti-caries", "plaque", "tartar", "stain"
    ],
    "技术": [
        "nano", "hydroxyapatite", "hap", "fluoride-free", "fluoride free", "xylitol",
        "activated charcoal", "charcoal", "probiotic", "biomimetic"
    ],
    "人群": [
        "kids", "children", "adult", "seniors", "pregnant", "braces", "orthodontic"
    ],
    "场景": [
        "night", "daily", "travel", "morning", "after meals"
    ]
}

def extract_tags(title, tag_dict=DEFAULT_TAG_DICT):
    """返回 {group: [hits]}"""
    if pd.isna(title):
        return {k: [] for k in tag_dict.keys()}

    t = str(title).lower()
    res = {}
    for group, kws in tag_dict.items():
        hits = []
        for kw in kws:
            if kw.lower() in t:
                hits.append(kw.lower())
        res[group] = hits
    return res

# =============================================================================
# 5) 市场结构与机会点
# =============================================================================
def add_price_bands(df, price_col, unit_price_col):
    # 价格带（可按你品类调整）
    df["价格带"] = pd.cut(
        df[price_col],
        bins=[-0.01, 10, 15, 20, 30, 999999],
        labels=["<10", "10-15", "15-20", "20-30", "30+"]
    )
    # 单位价格带（分位数分箱，便于规格差异大时对比）
    df["单位价格分位带"] = pd.qcut(
        df[unit_price_col].replace([np.inf, -np.inf], np.nan),
        q=5,
        duplicates="drop"
    )
    return df

def brand_concentration(df, brand_col, demand_col):
    """
    用 demand_col（如 reviews 或 sales）作为需求代理，算 CR3/5/10
    """
    tmp = df[[brand_col, demand_col]].copy()
    tmp = tmp.dropna(subset=[brand_col])
    tmp[demand_col] = tmp[demand_col].fillna(0)

    brand_sum = tmp.groupby(brand_col)[demand_col].sum().sort_values(ascending=False)
    total = brand_sum.sum() if brand_sum.sum() > 0 else 1.0

    def cr(n):
        return float(brand_sum.head(n).sum() / total)

    return {
        "CR3": cr(3),
        "CR5": cr(5),
        "CR10": cr(10),
        "TopBrands": brand_sum.head(20)
    }

def tag_performance(df, tag_col, price_col, rating_col, demand_col):
    """
    统计：覆盖率、均价、评分、需求代理均值
    """
    res = []
    tags = df[tag_col].dropna().unique()
    for tag in sorted(tags):
        sub = df[df[tag_col] == tag]
        res.append({
            "标签": tag,
            "SKU数": len(sub),
            "覆盖率": len(sub) / max(len(df), 1),
            "均价": sub[price_col].mean(),
            "均评分": sub[rating_col].mean(),
            "需求代理均值": sub[demand_col].mean(),
            "需求代理总量": sub[demand_col].sum(),
        })
    out = pd.DataFrame(res)
    if len(out) == 0:
        return out
    return out.sort_values(["需求代理总量", "均评分"], ascending=False)

def find_opportunities(df, price_col, unit_price_col, rating_col, demand_col, tech_tag_col, eff_tag_col):
    """
    三类机会：
    1) 低供给高需求：标签组合少但 demand 高
    2) 价格空档：unit_price 密度低区间 + 高评分
    3) 风险点：覆盖高但评分低的标签（避坑）
    """
    out = {}

    # 1) 标签组合（技术+功效）
    combo = df[[tech_tag_col, eff_tag_col, demand_col, rating_col, price_col, unit_price_col]].copy()
    combo = combo.dropna(subset=[tech_tag_col, eff_tag_col])
    combo["组合"] = combo[tech_tag_col].astype(str) + " + " + combo[eff_tag_col].astype(str)

    gp = combo.groupby("组合").agg(
        SKU数=("组合", "size"),
        需求代理均值=(demand_col, "mean"),
        需求代理总量=(demand_col, "sum"),
        均评分=(rating_col, "mean"),
        均价=(price_col, "mean"),
        单位价格均值=(unit_price_col, "mean")
    ).reset_index()

    if len(gp) > 0:
        # 机会分：需求高（rank_pct高）且供给少（count_pct低）
        gp["机会分"] = gp["需求代理均值"].rank(pct=True) * (1 - gp["SKU数"].rank(pct=True))
        out["低供给高需求"] = gp.sort_values("机会分", ascending=False).head(15)
    else:
        out["低供给高需求"] = pd.DataFrame()

    # 2) 单位价格空档
    valid = df[[unit_price_col, rating_col, demand_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) > 30:
        valid = valid.copy()
        valid["单位价格桶"] = pd.qcut(valid[unit_price_col], q=10, duplicates="drop")
        bins = valid.groupby("单位价格桶").agg(
            桶内SKU数=(unit_price_col, "size"),
            桶内均评分=(rating_col, "mean"),
            桶内需求代理均值=(demand_col, "mean"),
            单位价格最小=(unit_price_col, "min"),
            单位价格最大=(unit_price_col, "max")
        ).reset_index()

        bins["空档分"] = (1 - bins["桶内SKU数"].rank(pct=True)) * bins["桶内均评分"].rank(pct=True)
        out["价格空档"] = bins.sort_values("空档分", ascending=False).head(10)
    else:
        out["价格空档"] = pd.DataFrame()

    # 3) 风险标签：覆盖高但评分低（用功效标签举例）
    risk = df[[eff_tag_col, rating_col, demand_col]].dropna(subset=[eff_tag_col])
    rg = risk.groupby(eff_tag_col).agg(
        SKU数=(eff_tag_col, "size"),
        均评分=(rating_col, "mean"),
        需求代理总量=(demand_col, "sum")
    ).reset_index()

    if len(rg) > 0:
        rg["风险分"] = rg["SKU数"].rank(pct=True) * (1 - rg["均评分"].rank(pct=True))
        out["风险点"] = rg.sort_values("风险分", ascending=False).head(15)
    else:
        out["风险点"] = pd.DataFrame()

    return out

def to_excel_bytes(sheets: dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, sdf in sheets.items():
            if sdf is None:
                continue
            if isinstance(sdf, pd.Series):
                sdf = sdf.reset_index()
            sdf.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output

# =============================================================================
# 6) 侧边栏：模式选择 + 上传
# =============================================================================
MODULES = {
    "dev": "🧩 产品开发分析（推荐）",
    "product_simple": "📦 基础产品图表（旧版）",
    "brand_simple": "🏢 基础品牌占比（旧版）",
}

st.sidebar.header("1) 选择分析模式")
analysis_mode = st.sidebar.radio("你想分析什么？", list(MODULES.values()), index=0)

st.sidebar.header("2) 上传文件")
uploaded_file = st.sidebar.file_uploader("上传数据文件 (.xlsx / .csv)", type=["xlsx", "csv"])

# =============================================================================
# 7) 主流程
# =============================================================================
if not uploaded_file:
    st.info("👈 请在左侧侧边栏上传文件")
    st.stop()

file_type, data_obj, error = load_file(uploaded_file)
if error:
    st.error(error)
    st.stop()

# Excel 选 Sheet
if file_type == "xlsx":
    sheet_names = data_obj.sheet_names
    st.info(f"检测到 Excel 文件，包含工作表: {sheet_names}")
    selected_sheet = st.selectbox("请选择要分析的 Sheet:", sheet_names, index=0)
    df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
    df.columns = df.columns.astype(str).str.strip()
else:
    df = data_obj

st.subheader("数据预览")
st.dataframe(df.head(5), use_container_width=True)

all_cols = df.columns.tolist()

# =============================================================================
# A) 产品开发分析（新）
# =============================================================================
if analysis_mode == MODULES["dev"]:
    st.divider()
    st.subheader("🧩 产品开发分析：字段映射（请确认识别是否正确）")

    with st.expander("⚙️ 设置数据列映射（标准字段）", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        col_asin = c1.selectbox(
            "ASIN / SKU（可选）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "asin")
        )
        col_brand = c2.selectbox(
            "品牌（Brand）",
            all_cols,
            index=get_col_index(all_cols, "brand")
        )
        col_title = c3.selectbox(
            "商品标题（Title）",
            all_cols,
            index=get_col_index(all_cols, "title")
        )
        col_price = c4.selectbox(
            "价格（Price）",
            all_cols,
            index=get_col_index(all_cols, "price")
        )

        c5, c6, c7, c8 = st.columns(4)
        col_rating = c5.selectbox(
            "评分（Rating，可选）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "rating")
        )
        col_reviews = c6.selectbox(
            "评论数/评价数（Reviews，强烈建议作为需求代理）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "reviews")
        )
        col_size = c7.selectbox(
            "净含量/规格（Size，可选）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "size")
        )
        col_pack = c8.selectbox(
            "装数/变体（Pack/Variant，可选）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "pack")
        )

        c9, c10 = st.columns(2)
        col_weight = c9.selectbox(
            "重量（Weight，可选，用于物流/FBA判断）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "weight")
        )
        col_dim = c10.selectbox(
            "尺寸（Dimensions，可选，用于物流/FBA判断）",
            ["(None)"] + all_cols,
            index=get_col_index(["(None)"] + all_cols, "dimensions")
        )

    # ------------------------
    # 数据清洗 & 特征工程
    # ------------------------
    data = df.copy()
    data["_品牌"] = data[col_brand].astype(str).str.strip()
    data["_标题"] = data[col_title].astype(str)

    data["_价格"] = data[col_price].apply(clean_numeric)

    # 评分
    if col_rating != "(None)":
        data["_评分"] = data[col_rating].apply(clean_numeric)
    else:
        data["_评分"] = np.nan

    # 需求代理：优先 reviews
    if col_reviews != "(None)":
        data["_需求代理"] = data[col_reviews].apply(clean_numeric).fillna(0)
    else:
        # 没有 reviews 时，为保证程序可运行，给一个弱替代（不建议依赖）
        data["_需求代理"] = (1 / (data["_价格"].replace(0, np.nan))).fillna(0)

    # 净含量 & 装数
    if col_size != "(None)":
        data["_净含量_g"] = data[col_size].apply(parse_net_content_to_g)
    else:
        data["_净含量_g"] = np.nan

    if col_pack != "(None)":
        data["_装数"] = data[col_pack].apply(parse_pack_count)
    else:
        data["_装数"] = 1

    # 单位价格：有净含量优先，否则用单件价
    data["_单位价格"] = np.where(
        data["_净含量_g"].notna() & (data["_净含量_g"] > 0) & data["_装数"].notna() & (data["_装数"] > 0),
        data["_价格"] / (data["_净含量_g"] * data["_装数"]),
        data["_价格"] / data["_装数"].replace(0, np.nan)
    )

    # 标签抽取：每组取“第一个命中标签”（你也可以改成多标签）
    tags = data["_标题"].apply(lambda x: extract_tags(x, DEFAULT_TAG_DICT))
    data["_功效标签"] = tags.apply(lambda d: d["功效"][0] if len(d["功效"]) else np.nan)
    data["_技术标签"] = tags.apply(lambda d: d["技术"][0] if len(d["技术"]) else np.nan)
    data["_人群标签"] = tags.apply(lambda d: d["人群"][0] if len(d["人群"]) else np.nan)
    data["_场景标签"] = tags.apply(lambda d: d["场景"][0] if len(d["场景"]) else np.nan)

    # 价格带
    data = add_price_bands(data, "_价格", "_单位价格")

    # ------------------------
    # 核心指标卡片
    # ------------------------
    st.divider()
    st.subheader("📌 核心指标概览（产品开发视角）")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("SKU 数", f"{len(data):,}")
    m2.metric("均价", f"${np.nanmean(data['_价格']):.2f}" if np.isfinite(np.nanmean(data["_价格"])) else "N/A")
    m3.metric("均评分", f"{np.nanmean(data['_评分']):.2f}" if np.isfinite(np.nanmean(data["_评分"])) else "N/A")
    m4.metric("需求代理总量（Reviews/Sales等）", f"{data['_需求代理'].sum():,.0f}")

    # =============================================================================
    # 可视化图表（中文）
    # =============================================================================
    st.divider()
    st.subheader("📊 市场结构图表（更贴近产品开发决策）")

    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### 价格分布（SKU 数）")
        fig = px.histogram(data.dropna(subset=["_价格"]), x="_价格", nbins=25, title="价格分布（SKU 数）")
        st.plotly_chart(fig, use_container_width=True)

    with cB:
        st.markdown("##### 单位价格分布（用于规格差异大时）")
        tmp = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_单位价格"])
        fig = px.histogram(tmp, x="_单位价格", nbins=25, title="单位价格分布（近似：$/g 或 $/ml）")
        st.plotly_chart(fig, use_container_width=True)

    # 价格带按“需求代理”加权
    st.markdown("##### 价格带结构（按需求代理加权，更接近真实市场）")
    band = data.groupby("价格带", dropna=False)["_需求代理"].sum().reset_index()
    band.columns = ["价格带", "需求代理总量"]
    fig = px.bar(band, x="价格带", y="需求代理总量", title="价格带需求分布（需求代理加权）")
    st.plotly_chart(fig, use_container_width=True)

    # 价格 vs 评分（点大小=需求代理）
    st.markdown("##### 价格 vs 评分（判断溢价是否成立；点越大=需求代理越大）")
    scatter_df = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_价格"])
    if scatter_df["_评分"].notna().sum() > 0:
        fig = px.scatter(
            scatter_df,
            x="_价格",
            y="_评分",
            size="_需求代理",
            hover_data=["_品牌", "_标题", "_单位价格", "_装数", "_功效标签", "_技术标签"],
            title="价格 vs 评分（气泡图）"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("当前未提供评分列（Rating），因此无法绘制“价格 vs 评分”图。")

    # Pack 装数影响：单位价格箱线图 + 需求柱状图
    st.markdown("##### 装数（Pack）对单位价格与需求的影响（决定要不要做多支装）")
    pack_tmp = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_装数", "_单位价格"])
    fig = px.box(pack_tmp, x="_装数", y="_单位价格", points="all", title="不同装数的单位价格分布（箱线图）")
    st.plotly_chart(fig, use_container_width=True)

    pack_demand = data.groupby("_装数")["_需求代理"].sum().reset_index()
    fig = px.bar(pack_demand, x="_装数", y="_需求代理", title="不同装数的需求代理总量")
    st.plotly_chart(fig, use_container_width=True)

    # 标签热度（技术/功效）Top15：需求代理总量
    st.markdown("##### 标签热度（用于决定产品主轴）")
    col1, col2 = st.columns(2)

    with col1:
        tech_hot = data.groupby("_技术标签")["_需求代理"].sum().reset_index()
        tech_hot = tech_hot.dropna().sort_values("_需求代理", ascending=False).head(15)
        tech_hot.columns = ["技术标签", "需求代理总量"]
        fig = px.bar(tech_hot, x="需求代理总量", y="技术标签", orientation="h", title="技术标签热度 Top15")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        eff_hot = data.groupby("_功效标签")["_需求代理"].sum().reset_index()
        eff_hot = eff_hot.dropna().sort_values("_需求代理", ascending=False).head(15)
        eff_hot.columns = ["功效标签", "需求代理总量"]
        fig = px.bar(eff_hot, x="需求代理总量", y="功效标签", orientation="h", title="功效标签热度 Top15")
        st.plotly_chart(fig, use_container_width=True)

    # =============================================================================
    # 品牌集中度
    # =============================================================================
    st.divider()
    st.subheader("🏢 品牌格局（集中度）")
    conc = brand_concentration(data, "_品牌", "_需求代理")
    c1, c2, c3 = st.columns(3)
    c1.metric("CR3（前3品牌份额）", f"{conc['CR3']*100:.1f}%")
    c2.metric("CR5（前5品牌份额）", f"{conc['CR5']*100:.1f}%")
    c3.metric("CR10（前10品牌份额）", f"{conc['CR10']*100:.1f}%")

    top_brands = conc["TopBrands"].reset_index()
    top_brands.columns = ["品牌", "需求代理总量"]
    fig = px.bar(top_brands.head(15), x="需求代理总量", y="品牌", orientation="h", title="Top 品牌（按需求代理总量）")
    st.plotly_chart(fig, use_container_width=True)

    # =============================================================================
    # 标签表现（表格）
    # =============================================================================
    st.divider()
    st.subheader("🏷️ 卖点标签表现（用于定义技术路线/功效主轴）")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 技术标签表现")
        tech_perf = tag_performance(data, "_技术标签", "_价格", "_评分", "_需求代理")
        st.dataframe(tech_perf, use_container_width=True, height=360)

    with col2:
        st.markdown("##### 功效标签表现")
        eff_perf = tag_performance(data, "_功效标签", "_价格", "_评分", "_需求代理")
        st.dataframe(eff_perf, use_container_width=True, height=360)

    # =============================================================================
    # 机会点与风险点
    # =============================================================================
    st.divider()
    st.subheader("🎯 机会点与风险点（直接给产品开发用）")

    opp = find_opportunities(
        data,
        price_col="_价格",
        unit_price_col="_单位价格",
        rating_col="_评分",
        demand_col="_需求代理",
        tech_tag_col="_技术标签",
        eff_tag_col="_功效标签"
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 机会1：低供给高需求（技术 + 功效 标签组合）")
        st.dataframe(opp["低供给高需求"], use_container_width=True, height=360)
    with c2:
        st.markdown("##### 机会2：单位价格空档（Gap）")
        st.dataframe(opp["价格空档"], use_container_width=True, height=360)

    st.markdown("##### 风险点：覆盖高但评分偏低的功效标签（避坑清单）")
    st.dataframe(opp["风险点"], use_container_width=True)

    # =============================================================================
    # 清洗后的明细（可选展示）
    # =============================================================================
    with st.expander("🔎 查看清洗后的数据明细（可用于二次分析）", expanded=False):
        show_cols = ["_品牌", "_标题", "_价格", "_评分", "_需求代理", "_净含量_g", "_装数", "_单位价格",
                    "_功效标签", "_技术标签", "_人群标签", "_场景标签", "价格带", "单位价格分位带"]
        if col_asin != "(None)":
            data["_ASIN/SKU"] = data[col_asin].astype(str)
            show_cols = ["_ASIN/SKU"] + show_cols
        st.dataframe(data[show_cols].head(200), use_container_width=True)

    # =============================================================================
    # 导出 Excel（多 Sheet）
    # =============================================================================
    st.divider()
    st.subheader("⬇️ 导出报告（Excel 多 Sheet）")

    export_sheets = {
        "清洗数据_cleaned": data.replace([np.inf, -np.inf], np.nan),
        "品牌Top_top_brands": top_brands,
        "技术标签表现_tech_perf": tech_perf,
        "功效标签表现_eff_perf": eff_perf,
        "机会_低供给高需求": opp["低供给高需求"],
        "机会_价格空档": opp["价格空档"],
        "风险点_risk": opp["风险点"],
        "价格带需求_band": band,
        "装数需求_pack_demand": pack_demand,
    }
    excel_bytes = to_excel_bytes(export_sheets)

    st.download_button(
        label="📥 下载分析结果 Excel（含多Sheet）",
        data=excel_bytes,
        file_name="market_product_dev_report_cn.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =============================================================================
# B) 旧版：基础产品图表
# =============================================================================
elif analysis_mode == MODULES["product_simple"]:
    st.divider()
    st.subheader("📦 基础产品图表（旧版）")

    with st.expander("⚙️ 设置数据列（对应关系）", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        col_price = c1.selectbox("价格列", all_cols, index=get_col_index(all_cols, "price"))
        col_sales = c2.selectbox("销量列（可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, "sales"))
        col_rev = c3.selectbox("销售额列（可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, "revenue"))
        col_title = c4.selectbox("商品标题/名称列", all_cols, index=get_col_index(all_cols, "title"))

    try:
        df2 = df.copy()
        df2["_价格"] = df2[col_price].apply(clean_numeric)

        if col_sales != "(None)":
            df2["_销量"] = df2[col_sales].apply(clean_numeric).fillna(0)
        else:
            df2["_销量"] = 0

        if col_rev != "(None)":
            df2["_销售额"] = df2[col_rev].apply(clean_numeric).fillna(0)
        else:
            df2["_销售额"] = np.nan

        m1, m2, m3 = st.columns(3)
        m1.metric("总销售额", f"${np.nansum(df2['_销售额']):,.0f}" if col_rev != "(None)" else "N/A")
        m2.metric("总销量", f"{np.nansum(df2['_销量']):,.0f}" if col_sales != "(None)" else "N/A")
        m3.metric("平均价格", f"${np.nanmean(df2['_价格']):.2f}")

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("##### 价格分布")
            fig = px.histogram(df2.dropna(subset=["_价格"]), x="_价格", nbins=20, title="价格区间分布")
            st.plotly_chart(fig, use_container_width=True)

        with g2:
            if col_sales == "(None)":
                st.info("未选择“销量列”，无法输出销量Top10。")
            else:
                st.markdown("##### 销量 Top 10 商品")
                top_items = df2.sort_values("_销量", ascending=False).head(10).copy()
                top_items["_短标题"] = top_items[col_title].astype(str).str[:30] + "..."
                fig = px.bar(top_items, x="_销量", y="_短标题", orientation="h", title="热销商品（Top10）")
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")

# =============================================================================
# C) 旧版：基础品牌占比
# =============================================================================
elif analysis_mode == MODULES["brand_simple"]:
    st.divider()
    st.subheader("🏢 基础品牌占比（旧版）")

    with st.expander("⚙️ 设置数据列（对应关系）", expanded=True):
        c1, c2 = st.columns(2)
        b_name = c1.selectbox("品牌名称列", all_cols, index=get_col_index(all_cols, "brand"))
        b_val = c2.selectbox("销售额/占比列", all_cols, index=get_col_index(all_cols, "revenue"))

    try:
        df3 = df.copy()
        df3["_值"] = df3[b_val].apply(clean_numeric).fillna(0)

        st.markdown("##### 品牌市场占比（Top15）")
        df_sorted = df3.sort_values("_值", ascending=False).head(15)
        fig = px.pie(df_sorted, values="_值", names=b_name, title="Top 15 品牌占比", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### 品牌数据明细")
        st.dataframe(df3, use_container_width=True)

    except Exception as e:
        st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")
