# -*- coding: utf-8 -*-
"""
Streamlit App: 多工作表（Excel）自动读取 + 市场/产品开发分析（中文）
- 自动遍历 Excel 所有 Sheet
- 每个 Sheet 自动识别字段（价格/标题/品牌/评分/评论数/规格/装数等）
- 强健价格解析 + 诊断
- 充足可视化（价格/单位价/需求结构/品牌集中度/标签热度/机会点/相关性等）
- 支持导出：每个Sheet一套分析结果（多Sheet Excel 报告）
"""

import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# =============================================================================
# 1) 页面配置
# =============================================================================
st.set_page_config(page_title="多Sheet市场&产品开发分析（Excel/CSV）", layout="wide")
st.title("🧠 多工作表（Excel）→ 市场数据 & 产品开发机会点分析（中文）")
st.markdown("""
**你现在上传的 Excel 有多个工作表**：本程序会 **自动读取并逐个 Sheet 分析**，并在每个 Sheet 下输出：
- **价格/单位价格/装数/规格**的标准化
- **标题标签（功效/技术/人群/场景）**抽取
- **品牌集中度（CR3/CR5/CR10）**
- **机会点（低供给高需求 / 单位价格空档 / 风险标签）**
- **更丰富的可视化图表**
- **一键导出 Excel 多Sheet报告**
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


# =============================================================================
# 3) 强健数值/价格解析
# =============================================================================
def clean_numeric(val):
    """
    更强健的数字提取：
    - '$12.99', 'US$ 12.99', '12.99-18.99', '$12.99 ($2 coupon)', '12.99/Count'
    - 对 '12.99-18.99' 取区间中位数（也可改成取最小值）
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        return float(val)

    s = str(val).strip()
    if s == "":
        return np.nan

    s = s.replace("，", ",").replace("−", "-").replace("—", "-").replace("–", "-")
    s = s.replace("US$", "$").replace("USD", "$")

    nums = re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))
    if not nums:
        return np.nan

    if "-" in s or " to " in s.lower():
        if len(nums) >= 2:
            a, b = float(nums[0]), float(nums[1])
            return (a + b) / 2.0

    return float(nums[0])


# =============================================================================
# 4) 列名自动识别：关键词词库 + 加权打分
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
        "include": ["price", "售价", "当前价", "现价", "sale price", "our price", "buy box", "buybox", "价格", "current price", "amazon price"],
        "exclude": ["list price", "msrp", "coupon", "discount", "save", "off", "promo", "rebate"]
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

def best_column(options, field_key):
    """
    返回：最佳列名（str 或 None）与得分（用于调试）
    """
    rules = FIELD_KEYWORDS.get(field_key)
    if rules is None or not options:
        return None, -1e9

    best_col, best_score = None, -1e9
    for col in options:
        c = _norm(col)
        score = 0

        for j, kw in enumerate(rules["include"]):
            kw_n = _norm(kw)
            if kw_n in c:
                score += 10 - min(j, 8)

        for kw in rules.get("exclude", []):
            if _norm(kw) in c:
                score -= 12

        for kw in rules["include"][:6]:
            kw_n = _norm(kw)
            if kw_n in c and len(c) <= max(len(kw_n) + 8, 18):
                score += 2

        if score > best_score:
            best_score = score
            best_col = col

    # 分数过低时视为没找到
    if best_score <= 0:
        return None, best_score
    return best_col, best_score


# =============================================================================
# 5) 特征工程：净含量 / Pack / 标签
# =============================================================================
UNIT_TO_G = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "ml": 1.0,    # 近似：1ml≈1g（如需更精确可按品类密度调整）
    "l": 1000.0,
}

def parse_net_content_to_g(text):
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
# 6) 市场结构/机会点
# =============================================================================
def add_price_bands(df, price_col, unit_price_col):
    df["价格带"] = pd.cut(
        df[price_col],
        bins=[-0.01, 10, 15, 20, 30, 999999],
        labels=["<10", "10-15", "15-20", "20-30", "30+"]
    )
    df["单位价格分位带"] = pd.qcut(
        df[unit_price_col].replace([np.inf, -np.inf], np.nan),
        q=5,
        duplicates="drop"
    )
    return df

def brand_concentration(df, brand_col, demand_col):
    tmp = df[[brand_col, demand_col]].copy().dropna(subset=[brand_col])
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
    out = {}

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
        gp["机会分"] = gp["需求代理均值"].rank(pct=True) * (1 - gp["SKU数"].rank(pct=True))
        out["低供给高需求"] = gp.sort_values("机会分", ascending=False).head(15)
    else:
        out["低供给高需求"] = pd.DataFrame()

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
            # sheet name max 31
            sdf.to_excel(writer, sheet_name=name[:31], index=False)
    output.seek(0)
    return output


# =============================================================================
# 7) 单个Sheet的完整分析函数（返回清洗数据+导出sheet字典）
# =============================================================================
def analyze_one_sheet(df: pd.DataFrame, sheet_name: str, allow_override: bool = True):
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    cols = df.columns.tolist()

    # --- 自动识别列 ---
    auto = {}
    scores = {}
    for k in ["asin", "brand", "title", "price", "rating", "reviews", "size", "pack", "weight", "dimensions", "sales", "revenue", "rank"]:
        c, sc = best_column(cols, k)
        auto[k] = c
        scores[k] = sc

    # --- 可选：给用户手动覆盖（每个sheet都能调整） ---
    chosen = auto.copy()

    if allow_override:
        with st.expander(f"⚙️ 字段映射（{sheet_name}）- 可手动调整", expanded=False):
            st.caption("系统已自动识别字段；如果识别不准（尤其是价格列），请在这里改正确。")
            c1, c2, c3, c4 = st.columns(4)
            chosen["brand"] = c1.selectbox("品牌（Brand）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["brand"]) if auto["brand"] in cols else 0, key=f"{sheet_name}_brand")
            chosen["title"] = c2.selectbox("标题（Title）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["title"]) if auto["title"] in cols else 0, key=f"{sheet_name}_title")
            chosen["price"] = c3.selectbox("价格（Price）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["price"]) if auto["price"] in cols else 0, key=f"{sheet_name}_price")
            chosen["reviews"] = c4.selectbox("评论数/评价数（Reviews）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["reviews"]) if auto["reviews"] in cols else 0, key=f"{sheet_name}_reviews")

            c5, c6, c7, c8 = st.columns(4)
            chosen["rating"] = c5.selectbox("评分（Rating）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["rating"]) if auto["rating"] in cols else 0, key=f"{sheet_name}_rating")
            chosen["size"] = c6.selectbox("净含量/规格（Size）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["size"]) if auto["size"] in cols else 0, key=f"{sheet_name}_size")
            chosen["pack"] = c7.selectbox("装数/变体（Pack）", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["pack"]) if auto["pack"] in cols else 0, key=f"{sheet_name}_pack")
            chosen["asin"] = c8.selectbox("ASIN/SKU", ["(None)"] + cols, index=(["(None)"] + cols).index(auto["asin"]) if auto["asin"] in cols else 0, key=f"{sheet_name}_asin")

    # --- 必要列校验 ---
    if chosen["brand"] in [None, "(None)"] or chosen["title"] in [None, "(None)"]:
        st.warning(f"Sheet【{sheet_name}】缺少品牌或标题列，无法做标签/品牌分析；请在字段映射里补全。")
        return None, {}

    # 价格列允许空（但会影响很多图）
    # --- 清洗与特征工程 ---
    data = df.copy()
    data["_sheet"] = sheet_name
    data["_品牌"] = data[chosen["brand"]].astype(str).str.strip()
    data["_标题"] = data[chosen["title"]].astype(str)

    if chosen["price"] not in [None, "(None)"]:
        data["_价格"] = data[chosen["price"]].apply(clean_numeric)
    else:
        data["_价格"] = np.nan

    if chosen["rating"] not in [None, "(None)"]:
        data["_评分"] = data[chosen["rating"]].apply(clean_numeric)
    else:
        data["_评分"] = np.nan

    # 需求代理：优先 reviews，否则用 sales/revenue/rank 等兜底，最后用 1/price（很弱）
    demand_source = "Reviews"
    if chosen["reviews"] not in [None, "(None)"]:
        data["_需求代理"] = data[chosen["reviews"]].apply(clean_numeric).fillna(0)
        demand_source = chosen["reviews"]
    else:
        # 尝试 sales
        if chosen.get("sales") not in [None, "(None)"] and chosen.get("sales") in cols:
            data["_需求代理"] = data[chosen["sales"]].apply(clean_numeric).fillna(0)
            demand_source = chosen["sales"]
        elif chosen.get("revenue") not in [None, "(None)"] and chosen.get("revenue") in cols:
            data["_需求代理"] = data[chosen["revenue"]].apply(clean_numeric).fillna(0)
            demand_source = chosen["revenue"]
        elif chosen.get("rank") not in [None, "(None)"] and chosen.get("rank") in cols:
            # rank 越小越好：用 1/rank
            r = data[chosen["rank"]].apply(clean_numeric)
            data["_需求代理"] = (1 / r.replace(0, np.nan)).fillna(0)
            demand_source = chosen["rank"]
        else:
            data["_需求代理"] = (1 / data["_价格"].replace(0, np.nan)).fillna(0)
            demand_source = "1/Price(弱替代)"

    if chosen["size"] not in [None, "(None)"]:
        data["_净含量_g"] = data[chosen["size"]].apply(parse_net_content_to_g)
    else:
        data["_净含量_g"] = np.nan

    if chosen["pack"] not in [None, "(None)"]:
        data["_装数"] = data[chosen["pack"]].apply(parse_pack_count)
    else:
        data["_装数"] = 1

    data["_单位价格"] = np.where(
        data["_净含量_g"].notna() & (data["_净含量_g"] > 0) & data["_装数"].notna() & (data["_装数"] > 0),
        data["_价格"] / (data["_净含量_g"] * data["_装数"]),
        data["_价格"] / data["_装数"].replace(0, np.nan)
    )

    # 标签
    tags = data["_标题"].apply(lambda x: extract_tags(x, DEFAULT_TAG_DICT))
    data["_功效标签"] = tags.apply(lambda d: d["功效"][0] if len(d["功效"]) else np.nan)
    data["_技术标签"] = tags.apply(lambda d: d["技术"][0] if len(d["技术"]) else np.nan)
    data["_人群标签"] = tags.apply(lambda d: d["人群"][0] if len(d["人群"]) else np.nan)
    data["_场景标签"] = tags.apply(lambda d: d["场景"][0] if len(d["场景"]) else np.nan)

    # 价格带
    data = add_price_bands(data, "_价格", "_单位价格")

    # 机会点
    opp = find_opportunities(
        data.replace([np.inf, -np.inf], np.nan),
        price_col="_价格",
        unit_price_col="_单位价格",
        rating_col="_评分",
        demand_col="_需求代理",
        tech_tag_col="_技术标签",
        eff_tag_col="_功效标签"
    )

    # 标签表现
    tech_perf = tag_performance(data, "_技术标签", "_价格", "_评分", "_需求代理")
    eff_perf = tag_performance(data, "_功效标签", "_价格", "_评分", "_需求代理")

    # 品牌集中度
    conc = brand_concentration(data, "_品牌", "_需求代理")
    top_brands = conc["TopBrands"].reset_index()
    top_brands.columns = ["品牌", "需求代理总量"]

    # 价格带需求
    band = data.groupby("价格带", dropna=False)["_需求代理"].sum().reset_index()
    band.columns = ["价格带", "需求代理总量"]

    # 装数需求
    pack_demand = data.groupby("_装数")["_需求代理"].sum().reset_index()
    pack_demand.columns = ["装数", "需求代理总量"]

    # Top SKU
    top_sku = data.sort_values("_需求代理", ascending=False).head(20).copy()
    top_sku["_短标题"] = top_sku["_标题"].astype(str).str[:60] + "..."

    # --- 导出 sheets ---
    export = {
        f"{sheet_name}_cleaned": data.replace([np.inf, -np.inf], np.nan),
        f"{sheet_name}_top_brands": top_brands,
        f"{sheet_name}_tech_perf": tech_perf,
        f"{sheet_name}_eff_perf": eff_perf,
        f"{sheet_name}_opp_low_supply": opp["低供给高需求"],
        f"{sheet_name}_opp_price_gaps": opp["价格空档"],
        f"{sheet_name}_risk": opp["风险点"],
        f"{sheet_name}_band": band,
        f"{sheet_name}_pack_demand": pack_demand,
        f"{sheet_name}_top_sku": top_sku[["_品牌","_短标题","_价格","_单位价格","_装数","_评分","_需求代理","_功效标签","_技术标签"]]
    }

    # sheet 内展示：诊断 + 图表 + 表格
    st.markdown("#### 🧪 关键字段识别结果（系统自动识别）")
    auto_show = pd.DataFrame(
        [{"字段": k, "自动识别列": (auto[k] if auto[k] else ""), "得分": scores[k]} for k in ["brand","title","price","reviews","rating","size","pack","asin"]],
    )
    st.dataframe(auto_show, use_container_width=True, height=220)

    # 价格诊断
    st.markdown("#### 🧪 价格读取诊断")
    if chosen["price"] not in [None, "(None)"]:
        price_raw = df[chosen["price"]]
        price_clean = price_raw.apply(clean_numeric)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("价格列非空占比", f"{price_raw.notna().mean()*100:.1f}%")
        c2.metric("价格成功解析占比", f"{price_clean.notna().mean()*100:.1f}%")
        c3.metric("解析后均价", f"${price_clean.dropna().mean():.2f}" if price_clean.notna().any() else "N/A")
        c4.metric("需求代理来源", f"{demand_source}")

        bad = df.loc[price_clean.isna(), chosen["price"]].dropna().astype(str).head(20)
        if len(bad) > 0:
            st.warning("以下为价格解析失败样本（前20条），通常说明该列并非纯价格或格式较特殊：")
            st.dataframe(bad.to_frame("解析失败样本"), use_container_width=True)
        else:
            st.success("价格解析看起来正常 ✅")
    else:
        st.warning("该 Sheet 未选择价格列，价格相关图表将无法展示。")
        st.info(f"当前需求代理来源：{demand_source}")

    # 指标卡片
    st.markdown("#### 📌 核心指标概览（产品开发视角）")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("SKU 数", f"{len(data):,}")
    m2.metric("均价", f"${np.nanmean(data['_价格']):.2f}" if np.isfinite(np.nanmean(data["_价格"])) else "N/A")
    m3.metric("均评分", f"{np.nanmean(data['_评分']):.2f}" if np.isfinite(np.nanmean(data["_评分"])) else "N/A")
    m4.metric("需求代理总量", f"{data['_需求代理'].sum():,.0f}")

    # 图表区
    st.markdown("#### 📊 可视化（产品开发足够用的一套）")
    cA, cB = st.columns(2)
    with cA:
        fig = px.histogram(data.dropna(subset=["_价格"]), x="_价格", nbins=25, title="价格分布（SKU数）")
        st.plotly_chart(fig, use_container_width=True)
    with cB:
        tmp = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_单位价格"])
        fig = px.histogram(tmp, x="_单位价格", nbins=25, title="单位价格分布（近似：$/g 或 $/ml）")
        st.plotly_chart(fig, use_container_width=True)

    # 价格带需求
    fig = px.bar(band, x="价格带", y="需求代理总量", title="价格带需求分布（需求代理加权）")
    st.plotly_chart(fig, use_container_width=True)

    # 价格 vs 评分（如有）
    if data["_评分"].notna().sum() > 0 and data["_价格"].notna().sum() > 0:
        fig = px.scatter(
            data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_价格", "_评分"]),
            x="_价格", y="_评分", size="_需求代理",
            hover_data=["_品牌","_标题","_单位价格","_装数","_功效标签","_技术标签"],
            title="价格 vs 评分（点越大=需求代理越大）"
        )
        st.plotly_chart(fig, use_container_width=True)

    # 单位价格 vs 需求
    if data["_单位价格"].notna().sum() > 0:
        fig = px.scatter(
            data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_单位价格"]),
            x="_单位价格", y="_需求代理",
            hover_data=["_品牌","_标题","_价格","_装数","_功效标签","_技术标签"],
            title="单位价格 vs 需求代理（判断市场偏好：性价比 or 高端溢价）"
        )
        st.plotly_chart(fig, use_container_width=True)

    # 装数与单位价/需求
    if data["_装数"].notna().sum() > 0 and data["_单位价格"].notna().sum() > 0:
        fig = px.box(
            data.replace([np.inf, -np.inf], np.nan).dropna(subset=["_装数","_单位价格"]),
            x="_装数", y="_单位价格", points="all", title="不同装数（Pack）的单位价格分布（箱线图）"
        )
        st.plotly_chart(fig, use_container_width=True)

        fig = px.bar(pack_demand, x="装数", y="需求代理总量", title="不同装数（Pack）的需求代理总量")
        st.plotly_chart(fig, use_container_width=True)

    # 品牌集中度 + Top品牌条形图
    st.markdown("#### 🏢 品牌集中度（CR）")
    c1, c2, c3 = st.columns(3)
    c1.metric("CR3（前3品牌份额）", f"{conc['CR3']*100:.1f}%")
    c2.metric("CR5（前5品牌份额）", f"{conc['CR5']*100:.1f}%")
    c3.metric("CR10（前10品牌份额）", f"{conc['CR10']*100:.1f}%")
    fig = px.bar(top_brands.head(15), x="需求代理总量", y="品牌", orientation="h", title="Top品牌（按需求代理总量）")
    st.plotly_chart(fig, use_container_width=True)

    # 标签热度：技术/功效 Top15
    st.markdown("#### 🏷️ 标签热度（用于决定产品主轴）")
    col1, col2 = st.columns(2)
    with col1:
        tech_hot = data.groupby("_技术标签")["_需求代理"].sum().reset_index().dropna().sort_values("_需求代理", ascending=False).head(15)
        tech_hot.columns = ["技术标签", "需求代理总量"]
        fig = px.bar(tech_hot, x="需求代理总量", y="技术标签", orientation="h", title="技术标签热度 Top15")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        eff_hot = data.groupby("_功效标签")["_需求代理"].sum().reset_index().dropna().sort_values("_需求代理", ascending=False).head(15)
        eff_hot.columns = ["功效标签", "需求代理总量"]
        fig = px.bar(eff_hot, x="需求代理总量", y="功效标签", orientation="h", title="功效标签热度 Top15")
        st.plotly_chart(fig, use_container_width=True)

    # Top SKU表
    st.markdown("#### 🏆 Top SKU（按需求代理）")
    st.dataframe(top_sku[["_品牌","_短标题","_价格","_单位价格","_装数","_评分","_需求代理","_功效标签","_技术标签"]],
                 use_container_width=True, height=360)

    # 品牌×价格带 热力图（Top20品牌）
    st.markdown("#### 🧊 品牌 × 价格带（需求代理热力图 Top20品牌）")
    pv = data.pivot_table(index="_品牌", columns="价格带", values="_需求代理", aggfunc="sum", fill_value=0)
    if pv.shape[0] > 0:
        pv = pv.sort_values(pv.columns.tolist(), ascending=False).head(20)
        heat = pv.reset_index().melt(id_vars="_品牌", var_name="价格带", value_name="需求代理")
        fig = px.density_heatmap(heat, x="价格带", y="_品牌", z="需求代理", title="Top品牌在不同价格带的需求分布（热力图）")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("品牌×价格带数据不足，热力图未生成。")

    # 相关性热力图
    st.markdown("#### 🔗 核心指标相关性（价格/单位价/评分/需求）")
    corr_cols = ["_价格","_单位价格","_评分","_需求代理"]
    corr_df = data[corr_cols].replace([np.inf, -np.inf], np.nan).dropna()
    if len(corr_df) >= 10:
        corr = corr_df.corr(numeric_only=True)
        fig = px.imshow(corr, text_auto=True, title="相关性热力图（Correlation Heatmap）")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("可用于相关性计算的数据不足（价格/单位价/评分缺失较多）。")

    # 标签表现表
    st.markdown("#### 🧾 标签表现（用于验证溢价/口碑/需求）")
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**技术标签表现**")
        st.dataframe(tech_perf, use_container_width=True, height=360)
    with t2:
        st.markdown("**功效标签表现**")
        st.dataframe(eff_perf, use_container_width=True, height=360)

    # 机会点/风险点
    st.markdown("#### 🎯 机会点 & 风险点")
    o1, o2 = st.columns(2)
    with o1:
        st.markdown("**机会1：低供给高需求（技术+功效组合）**")
        st.dataframe(opp["低供给高需求"], use_container_width=True, height=360)
    with o2:
        st.markdown("**机会2：单位价格空档（Gap）**")
        st.dataframe(opp["价格空档"], use_container_width=True, height=360)

    st.markdown("**风险点：覆盖高但评分偏低的功效标签（避坑清单）**")
    st.dataframe(opp["风险点"], use_container_width=True)

    # 清洗数据预览
    with st.expander("🔎 清洗数据预览（前200行）", expanded=False):
        show_cols = ["_品牌","_标题","_价格","_单位价格","_装数","_净含量_g","_评分","_需求代理",
                     "_功效标签","_技术标签","_人群标签","_场景标签","价格带","单位价格分位带"]
        if chosen["asin"] not in [None, "(None)"]:
            data["_ASIN/SKU"] = data[chosen["asin"]].astype(str)
            show_cols = ["_ASIN/SKU"] + show_cols
        st.dataframe(data[show_cols].head(200), use_container_width=True)

    return data.replace([np.inf, -np.inf], np.nan), export


# =============================================================================
# 8) 主入口：上传 + 多Sheet读取与分析
# =============================================================================
st.sidebar.header("上传文件")
uploaded_file = st.sidebar.file_uploader("上传 Excel(.xlsx) 或 CSV(.csv)", type=["xlsx", "csv"])

st.sidebar.header("分析设置")
allow_override = st.sidebar.checkbox("允许每个Sheet手动调整字段映射（推荐勾选）", value=True)
show_all_sheet_preview = st.sidebar.checkbox("先展示所有Sheet的前3行预览", value=True)

if not uploaded_file:
    st.info("👈 请在左侧上传文件")
    st.stop()

file_type, data_obj, error = load_file(uploaded_file)
if error:
    st.error(error)
    st.stop()

all_sheet_exports = {}
all_cleaned = []

# CSV：当作单sheet
if file_type == "csv":
    st.subheader("📄 当前为 CSV（单表）")
    df = data_obj
    df.columns = df.columns.astype(str).str.strip()

    tab = st.tabs(["CSV_分析"])[0]
    with tab:
        cleaned, export = analyze_one_sheet(df, "CSV", allow_override=allow_override)
        if cleaned is not None:
            all_cleaned.append(cleaned)
            all_sheet_exports.update(export)

else:
    # Excel 多Sheet
    sheet_names = data_obj.sheet_names
    st.subheader("📚 检测到 Excel 多工作表")
    st.write(f"工作表数量：**{len(sheet_names)}**")
    st.write(sheet_names)

    if show_all_sheet_preview:
        st.markdown("### 👀 所有Sheet快速预览（前3行）")
        for sn in sheet_names:
            tmp_df = pd.read_excel(uploaded_file, sheet_name=sn)
            tmp_df.columns = tmp_df.columns.astype(str).str.strip()
            with st.expander(f"预览：{sn}", expanded=False):
                st.dataframe(tmp_df.head(3), use_container_width=True)

    st.markdown("### ✅ 逐个Sheet分析（每个Sheet一个Tab）")
    tabs = st.tabs([f"{i+1}. {sn}" for i, sn in enumerate(sheet_names)])

    for i, sn in enumerate(sheet_names):
        with tabs[i]:
            df_sheet = pd.read_excel(uploaded_file, sheet_name=sn)
            df_sheet.columns = df_sheet.columns.astype(str).str.strip()

            cleaned, export = analyze_one_sheet(df_sheet, sn, allow_override=allow_override)
            if cleaned is not None:
                all_cleaned.append(cleaned)
                all_sheet_exports.update(export)

# =============================================================================
# 9) 跨Sheet汇总（如果有多个sheet可用）
# =============================================================================
st.divider()
st.subheader("📌 跨Sheet汇总（用于老板一眼看懂）")

if len(all_cleaned) == 0:
    st.warning("没有可用的清洗结果（可能所有Sheet都缺少品牌/标题字段映射）。")
    st.stop()

all_data = pd.concat(all_cleaned, ignore_index=True)
# 汇总指标
c1, c2, c3, c4 = st.columns(4)
c1.metric("总Sheet数", f"{all_data['_sheet'].nunique():,}")
c2.metric("总SKU数", f"{len(all_data):,}")
c3.metric("全表均价", f"${np.nanmean(all_data['_价格']):.2f}" if np.isfinite(np.nanmean(all_data["_价格"])) else "N/A")
c4.metric("全表需求代理总量", f"{all_data['_需求代理'].sum():,.0f}")

# 每个Sheet：价格解析率/均价/需求代理
sheet_summary = []
for sn, g in all_data.groupby("_sheet"):
    price_ok = g["_价格"].notna().mean() if len(g) else 0
    sheet_summary.append({
        "Sheet": sn,
        "SKU数": len(g),
        "价格可用率": price_ok,
        "均价": np.nanmean(g["_价格"]),
        "均评分": np.nanmean(g["_评分"]),
        "需求代理总量": g["_需求代理"].sum()
    })
sheet_summary_df = pd.DataFrame(sheet_summary).sort_values("需求代理总量", ascending=False)
st.dataframe(sheet_summary_df, use_container_width=True)

# 汇总图：各Sheet需求代理总量
fig = px.bar(sheet_summary_df, x="需求代理总量", y="Sheet", orientation="h", title="各Sheet需求代理总量（横向对比）")
st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# 10) 导出总报告（多sheet Excel）
# =============================================================================
st.divider()
st.subheader("⬇️ 导出：全量多Sheet分析报告（Excel）")

# 额外加一个“总汇总”sheet
all_sheet_exports["0_总汇总_sheet_summary"] = sheet_summary_df
all_sheet_exports["0_总汇总_all_cleaned"] = all_data.replace([np.inf, -np.inf], np.nan)

excel_bytes = to_excel_bytes(all_sheet_exports)
st.download_button(
    label="📥 下载全量分析报告（Excel 多Sheet）",
    data=excel_bytes,
    file_name="market_product_dev_multi_sheet_report_cn.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
