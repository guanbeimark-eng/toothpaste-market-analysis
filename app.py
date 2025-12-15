import re
import io
import numpy as np
import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="市场&产品开发分析(Excel版)", layout="wide")
st.title("🧠 市场数据 → 产品开发机会点分析（Excel/CSV 通用版）")
st.markdown("""
**使用说明：**
1) 支持上传 **.xlsx** / **.csv**  
2) Excel 会让你选择 Sheet  
3) 选择/确认字段映射后，程序会自动：
- 计算 **净含量、Pack 数、单位价格**
- 从标题抽取 **功效/技术/人群/场景标签**
- 输出 **价格结构、品牌集中度、机会点、风险点**
""")

# -----------------------------------------------------------------------------
# 2. 文件加载
# -----------------------------------------------------------------------------
def load_file(uploaded_file):
    if uploaded_file is None:
        return None, None, "没有文件"

    file_name = uploaded_file.name

    if file_name.endswith('.xlsx'):
        try:
            xl = pd.ExcelFile(uploaded_file)
            return "xlsx", xl, None
        except Exception as e:
            return None, None, f"Excel 读取失败: {str(e)}"

    if file_name.endswith('.csv'):
        encodings = ['utf-8', 'gbk', 'utf-8-sig', 'ISO-8859-1']
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
    """强制转换为数字"""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        return float(val)
    try:
        s = str(val)
        s = s.replace('$', '').replace('¥', '').replace(',', '').replace(' ', '').replace('%', '')
        return float(s)
    except:
        return np.nan


def get_col_index(options, key_words):
    """自动猜测列名索引"""
    options_low = [str(o).lower() for o in options]
    for i, opt in enumerate(options_low):
        for kw in key_words:
            if kw.lower() in opt:
                return i
    return 0


# -----------------------------------------------------------------------------
# 3. 特征工程：净含量 / Pack / 标签
# -----------------------------------------------------------------------------
UNIT_TO_G = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "ml": 1.0,     # 这里简单视作 1ml≈1g（若要更准可按品类密度调）
    "l": 1000.0,
}

def parse_net_content_to_g(text):
    """
    从字符串抽取净含量，统一成 g（或近似 g）
    示例： "4 Ounce", "120g", "100 ml", "0.5 kg"
    """
    if pd.isna(text):
        return np.nan
    s = str(text).lower()

    # 常见写法：数字 + 单位
    m = re.search(r'(\d+(?:\.\d+)?)\s*(g|gram|grams|kg|oz|ounce|ounces|ml|l)\b', s)
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

    # pack of 3
    m = re.search(r'pack\s*of\s*(\d+)', s)
    if m:
        return int(m.group(1))

    # 3 pack
    m = re.search(r'(\d+)\s*pack\b', s)
    if m:
        return int(m.group(1))

    # x3 / ×3
    m = re.search(r'[x×]\s*(\d+)', s)
    if m:
        return int(m.group(1))

    return 1


DEFAULT_TAG_DICT = {
    "efficacy": [
        "whitening", "brighten", "sensitivity", "sensitive", "repair", "remineral", "enamel",
        "gum", "fresh", "breath", "cavity", "anti-caries", "plaque", "tartar", "stain"
    ],
    "tech": [
        "nano", "hydroxyapatite", "hap", "fluoride-free", "fluoride free", "xylitol",
        "activated charcoal", "charcoal", "probiotic", "biomimetic"
    ],
    "persona": [
        "kids", "children", "adult", "seniors", "pregnant", "braces", "orthodontic"
    ],
    "scenario": [
        "night", "daily", "travel", "morning", "after meals"
    ]
}

def extract_tags(title, tag_dict=DEFAULT_TAG_DICT):
    """返回 {group: [hits]}"""
    res = {}
    if pd.isna(title):
        for k in tag_dict:
            res[k] = []
        return res

    t = str(title).lower()
    for group, kws in tag_dict.items():
        hits = []
        for kw in kws:
            if kw in t:
                hits.append(kw)
        res[group] = hits
    return res


# -----------------------------------------------------------------------------
# 4. 市场结构与机会点
# -----------------------------------------------------------------------------
def add_price_bands(df, price_col, unit_price_col):
    # 价格带：可按你习惯调整
    df["price_band"] = pd.cut(
        df[price_col],
        bins=[-0.01, 10, 15, 20, 30, 99999],
        labels=["<10", "10-15", "15-20", "20-30", "30+"]
    )
    df["unit_price_band"] = pd.qcut(
        df[unit_price_col].replace([np.inf, -np.inf], np.nan),
        q=5,
        duplicates="drop"
    )
    return df

def brand_concentration(df, brand_col, demand_col):
    """
    用 demand_col（如 reviews / sales / rank倒数）作为需求代理，算 CR3/5/10
    """
    tmp = df[[brand_col, demand_col]].copy()
    tmp = tmp.dropna(subset=[brand_col])
    tmp[demand_col] = tmp[demand_col].fillna(0)

    brand_sum = tmp.groupby(brand_col)[demand_col].sum().sort_values(ascending=False)
    total = brand_sum.sum() if brand_sum.sum() > 0 else 1.0

    def cr(n):
        return float(brand_sum.head(n).sum() / total)

    out = {
        "CR3": cr(3),
        "CR5": cr(5),
        "CR10": cr(10),
        "TopBrands": brand_sum.head(10)
    }
    return out

def tag_performance(df, tag_col, price_col, rating_col, demand_col):
    """
    tag_col：某个标签列（比如 'tech_tag'）
    统计：覆盖率、均价、评分、需求代理均值
    """
    res = []
    for tag in sorted(df[tag_col].dropna().unique()):
        sub = df[df[tag_col] == tag]
        res.append({
            "tag": tag,
            "count": len(sub),
            "coverage": len(sub) / max(len(df), 1),
            "avg_price": sub[price_col].mean(),
            "avg_rating": sub[rating_col].mean() if rating_col in sub else np.nan,
            "avg_demand": sub[demand_col].mean() if demand_col in sub else np.nan,
        })
    return pd.DataFrame(res).sort_values(["avg_demand", "avg_rating"], ascending=False)

def find_opportunities(df, price_col, unit_price_col, rating_col, demand_col, tech_tag_col, eff_tag_col):
    """
    三类机会：
    1) 低供给高需求：标签组合少但 demand 高
    2) 价格空档：unit_price 的密度低区间 + 高评分
    3) 风险点：评分低 + 高覆盖标签
    """
    out = {}

    # 1) 标签组合机会（简单版：tech + efficacy）
    combo = df[[tech_tag_col, eff_tag_col, demand_col, rating_col, price_col, unit_price_col]].copy()
    combo = combo.dropna(subset=[tech_tag_col, eff_tag_col])
    combo["combo"] = combo[tech_tag_col].astype(str) + " + " + combo[eff_tag_col].astype(str)

    gp = combo.groupby("combo").agg(
        count=("combo", "size"),
        demand_mean=(demand_col, "mean"),
        rating_mean=(rating_col, "mean"),
        price_mean=(price_col, "mean"),
        unit_price_mean=(unit_price_col, "mean")
    ).reset_index()

    # 机会定义：count 小（供给少）且 demand_mean 高
    gp["opp_score"] = gp["demand_mean"].rank(pct=True) * (1 - gp["count"].rank(pct=True))
    out["low_supply_high_demand"] = gp.sort_values("opp_score", ascending=False).head(15)

    # 2) 价格空档（unit_price 分桶后找密度最低但评分较高的桶）
    valid = df[[unit_price_col, rating_col, demand_col]].dropna()
    if len(valid) > 10:
        valid["up_bin"] = pd.qcut(valid[unit_price_col], q=10, duplicates="drop")
        bins = valid.groupby("up_bin").agg(
            bin_count=(unit_price_col, "size"),
            rating_mean=(rating_col, "mean"),
            demand_mean=(demand_col, "mean"),
            unit_price_min=(unit_price_col, "min"),
            unit_price_max=(unit_price_col, "max"),
        ).reset_index()

        bins["gap_score"] = (1 - bins["bin_count"].rank(pct=True)) * bins["rating_mean"].rank(pct=True)
        out["price_gaps"] = bins.sort_values("gap_score", ascending=False).head(10)
    else:
        out["price_gaps"] = pd.DataFrame()

    # 3) 风险点：高覆盖但低评分标签
    risk = df[[eff_tag_col, rating_col, demand_col]].dropna(subset=[eff_tag_col])
    rg = risk.groupby(eff_tag_col).agg(
        count=(eff_tag_col, "size"),
        rating_mean=(rating_col, "mean"),
        demand_mean=(demand_col, "mean")
    ).reset_index()
    # 风险：count 高、rating 低
    rg["risk_score"] = rg["count"].rank(pct=True) * (1 - rg["rating_mean"].rank(pct=True))
    out["risk_tags"] = rg.sort_values("risk_score", ascending=False).head(15)

    return out


def to_excel_bytes(sheets: dict):
    """多sheet导出"""
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


# -----------------------------------------------------------------------------
# 5. 侧边栏：选择模式 + 上传
# -----------------------------------------------------------------------------
MODULES = {
    "dev": "🧩 产品开发分析（推荐）",
    "product_simple": "📦 基础产品图表（旧版）",
    "brand_simple": "🏢 基础品牌占比（旧版）"
}

st.sidebar.header("1) 选择分析模式")
analysis_mode = st.sidebar.radio("你想分析什么？", list(MODULES.values()), index=0)

st.sidebar.header("2) 上传文件")
uploaded_file = st.sidebar.file_uploader("上传数据文件 (.xlsx / .csv)", type=['xlsx', 'csv'])


# -----------------------------------------------------------------------------
# 6. 主流程
# -----------------------------------------------------------------------------
if uploaded_file:
    file_type, data_obj, error = load_file(uploaded_file)
    if error:
        st.error(error)
        st.stop()

    # Excel 选择 Sheet
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

    # -----------------------------------------------------------------------------
    # A) 产品开发分析（新）
    # -----------------------------------------------------------------------------
    if analysis_mode == MODULES["dev"]:
        st.divider()
        st.subheader("🧩 产品开发分析：字段映射（建议尽量补全）")

        with st.expander("⚙️ 设置数据列映射（标准字段）", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            col_asin = c1.selectbox("ASIN/SKU（可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["asin", "sku"]))
            col_brand = c2.selectbox("Brand（品牌）", all_cols, index=get_col_index(all_cols, ["brand", "品牌"]))
            col_title = c3.selectbox("Title（标题）", all_cols, index=get_col_index(all_cols, ["title", "name", "标题", "商品名"]))
            col_price = c4.selectbox("Price（价格）", all_cols, index=get_col_index(all_cols, ["price", "价格"]))

            c5, c6, c7, c8 = st.columns(4)
            col_rating = c5.selectbox("Rating（评分，可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["rating", "评分", "stars"]))
            col_reviews = c6.selectbox("Reviews（评论数/需求代理，强烈建议）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["reviews", "review", "评论", "ratings"]))
            col_size = c7.selectbox("Size/Net Content（净含量，可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["size", "ounce", "oz", "ml", "g", "净含量"]))
            col_pack = c8.selectbox("Pack/Variant（装数，可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["pack", "variant", "flavor", "装"]))

            c9, c10 = st.columns(2)
            col_weight = c9.selectbox("Weight（重量，可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["weight", "重量"]))
            col_dim = c10.selectbox("Dimensions（尺寸，可选）", ["(None)"] + all_cols, index=get_col_index(["(None)"] + all_cols, ["dimension", "尺寸", "length"]))

        # ---- 清洗&特征工程 ----
        data = df.copy()

        # 基础字段
        data["_brand"] = data[col_brand].astype(str).str.strip()
        data["_title"] = data[col_title].astype(str)

        data["_price"] = data[col_price].apply(clean_numeric)

        # rating & demand(=reviews)
        if col_rating != "(None)":
            data["_rating"] = data[col_rating].apply(clean_numeric)
        else:
            data["_rating"] = np.nan

        if col_reviews != "(None)":
            data["_demand"] = data[col_reviews].apply(clean_numeric).fillna(0)
        else:
            # 没有 reviews 时用 price 的倒数做一个很弱的代理（只是为了程序能跑）
            data["_demand"] = (1 / (data["_price"].replace(0, np.nan))).fillna(0)

        # size & pack
        if col_size != "(None)":
            data["_net_g"] = data[col_size].apply(parse_net_content_to_g)
        else:
            data["_net_g"] = np.nan

        if col_pack != "(None)":
            data["_pack"] = data[col_pack].apply(parse_pack_count)
        else:
            data["_pack"] = 1

        # 单位价格：优先用净含量，否则用单件价
        data["_unit_price"] = np.where(
            data["_net_g"].notna() & (data["_net_g"] > 0),
            data["_price"] / (data["_net_g"] * data["_pack"]),
            data["_price"] / data["_pack"].replace(0, np.nan)
        )

        # 标签抽取（标题为主）
        tags = data["_title"].apply(lambda x: extract_tags(x, DEFAULT_TAG_DICT))
        data["_eff_tag"] = tags.apply(lambda d: d["efficacy"][0] if len(d["efficacy"]) else np.nan)
        data["_tech_tag"] = tags.apply(lambda d: d["tech"][0] if len(d["tech"]) else np.nan)
        data["_persona_tag"] = tags.apply(lambda d: d["persona"][0] if len(d["persona"]) else np.nan)
        data["_scenario_tag"] = tags.apply(lambda d: d["scenario"][0] if len(d["scenario"]) else np.nan)

        # 价格带
        data = add_price_bands(data, "_price", "_unit_price")

        st.divider()
        st.subheader("📌 核心指标概览")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("SKU 数", f"{len(data):,}")
        m2.metric("均价", f"${np.nanmean(data['_price']):.2f}")
        m3.metric("均评分", f"{np.nanmean(data['_rating']):.2f}" if not np.isnan(np.nanmean(data["_rating"])) else "N/A")
        m4.metric("需求代理总量（Reviews/Sales等）", f"{data['_demand'].sum():,.0f}")

        # -----------------------------------------------------------------------------
        # 市场结构图表
        # -----------------------------------------------------------------------------
        cA, cB = st.columns(2)
        with cA:
            st.markdown("##### 价格带分布（SKU数）")
            fig = px.histogram(data, x="_price", nbins=25)
            st.plotly_chart(fig, use_container_width=True)

        with cB:
            st.markdown("##### 单位价格分布（用于规格差异大时）")
            fig = px.histogram(data.replace([np.inf, -np.inf], np.nan), x="_unit_price", nbins=25)
            st.plotly_chart(fig, use_container_width=True)

        # -----------------------------------------------------------------------------
        # 品牌集中度
        # -----------------------------------------------------------------------------
        st.subheader("🏢 品牌格局（集中度）")
        conc = brand_concentration(data, "_brand", "_demand")
        c1, c2, c3 = st.columns(3)
        c1.metric("CR3", f"{conc['CR3']*100:.1f}%")
        c2.metric("CR5", f"{conc['CR5']*100:.1f}%")
        c3.metric("CR10", f"{conc['CR10']*100:.1f}%")

        top_brands = conc["TopBrands"].reset_index()
        top_brands.columns = ["brand", "demand_sum"]
        fig = px.bar(top_brands.head(15), x="demand_sum", y="brand", orientation="h", title="Top 品牌（按需求代理）")
        st.plotly_chart(fig, use_container_width=True)

        # -----------------------------------------------------------------------------
        # 标签表现
        # -----------------------------------------------------------------------------
        st.subheader("🏷️ 卖点标签表现（用于定义技术路线/功效主轴）")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 技术标签表现（tech）")
            tech_perf = tag_performance(data, "_tech_tag", "_price", "_rating", "_demand")
            st.dataframe(tech_perf.head(30), use_container_width=True)

        with col2:
            st.markdown("##### 功效标签表现（efficacy）")
            eff_perf = tag_performance(data, "_eff_tag", "_price", "_rating", "_demand")
            st.dataframe(eff_perf.head(30), use_container_width=True)

        # -----------------------------------------------------------------------------
        # 机会点识别
        # -----------------------------------------------------------------------------
        st.subheader("🎯 机会点与风险点（直接给产品开发用）")
        opp = find_opportunities(
            data,
            price_col="_price",
            unit_price_col="_unit_price",
            rating_col="_rating",
            demand_col="_demand",
            tech_tag_col="_tech_tag",
            eff_tag_col="_eff_tag"
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 机会1：低供给高需求（标签组合）")
            st.dataframe(opp["low_supply_high_demand"], use_container_width=True)

        with c2:
            st.markdown("##### 机会2：单位价格空档（Gap）")
            st.dataframe(opp["price_gaps"], use_container_width=True)

        st.markdown("##### 风险点：高覆盖但低评分标签（避坑清单）")
        st.dataframe(opp["risk_tags"], use_container_width=True)

        # -----------------------------------------------------------------------------
        # 导出报告
        # -----------------------------------------------------------------------------
        st.subheader("⬇️ 导出报告（Excel 多 Sheet）")
        export_sheets = {
            "cleaned_data": data,
            "top_brands": top_brands,
            "tech_tag_perf": tech_perf,
            "eff_tag_perf": eff_perf,
            "opp_low_supply": opp["low_supply_high_demand"],
            "opp_price_gaps": opp["price_gaps"],
            "risk_tags": opp["risk_tags"],
        }
        excel_bytes = to_excel_bytes(export_sheets)

        st.download_button(
            label="下载分析结果 Excel",
            data=excel_bytes,
            file_name="market_product_dev_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


    # -----------------------------------------------------------------------------
    # B) 旧版基础产品图表（保留你原功能）
    # -----------------------------------------------------------------------------
    elif analysis_mode == MODULES["product_simple"]:
        st.divider()
        st.subheader("📦 基础产品图表（旧版）")

        with st.expander("⚙️ 设置数据列 (对应关系)", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            col_price = c1.selectbox("价格列", all_cols, index=get_col_index(all_cols, ['价格', 'price']))
            col_sales = c2.selectbox("销量列", all_cols, index=get_col_index(all_cols, ['销量', 'sales']))
            col_rev = c3.selectbox("销售额列", all_cols, index=get_col_index(all_cols, ['销售额', 'revenue']))
            col_title = c4.selectbox("商品标题/名称列", all_cols, index=get_col_index(all_cols, ['标题', 'name', 'title']))

        try:
            df2 = df.copy()
            df2['_price'] = df2[col_price].apply(clean_numeric)
            df2['_sales'] = df2[col_sales].apply(clean_numeric)
            df2['_rev'] = df2[col_rev].apply(clean_numeric)

            m1, m2, m3 = st.columns(3)
            m1.metric("总销售额", f"${df2['_rev'].sum():,.0f}")
            m2.metric("总销量", f"{df2['_sales'].sum():,.0f}")
            m3.metric("平均价格", f"${df2['_price'].mean():.2f}")

            g1, g2 = st.columns(2)
            with g1:
                st.markdown("##### 价格分布")
                fig = px.histogram(df2, x='_price', nbins=20, title="价格区间分布")
                st.plotly_chart(fig, use_container_width=True)

            with g2:
                st.markdown("##### 销量 Top 10 商品")
                top_items = df2.sort_values('_sales', ascending=False).head(10)
                top_items['_short_title'] = top_items[col_title].astype(str).str[:30] + "..."
                fig = px.bar(top_items, x='_sales', y='_short_title', orientation='h', title="热销商品")
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")


    # -----------------------------------------------------------------------------
    # C) 旧版品牌占比（保留你原功能）
    # -----------------------------------------------------------------------------
    elif analysis_mode == MODULES["brand_simple"]:
        st.divider()
        st.subheader("🏢 基础品牌占比（旧版）")

        with st.expander("⚙️ 设置数据列 (对应关系)", expanded=True):
            c1, c2 = st.columns(2)
            b_name = c1.selectbox("品牌名称列", all_cols, index=get_col_index(all_cols, ['品牌', 'brand']))
            b_rev = c2.selectbox("销售额/占比列", all_cols, index=get_col_index(all_cols, ['销售额', 'revenue', 'share']))

        try:
            df3 = df.copy()
            df3['_val'] = df3[b_rev].apply(clean_numeric)
            st.markdown("##### 品牌市场占比")
            df_sorted = df3.sort_values('_val', ascending=False).head(15)
            fig = px.pie(df_sorted, values='_val', names=b_name, title="Top 15 品牌占比", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("##### 品牌数据明细")
            st.dataframe(df3, use_container_width=True)

        except Exception as e:
            st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")

else:
    st.info("👈 请在左侧侧边栏上传文件")
