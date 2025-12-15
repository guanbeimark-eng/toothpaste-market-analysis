# -*- coding: utf-8 -*-
import re
import io
import time
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# =============================================================================
# 1) 页面配置
# =============================================================================
st.set_page_config(page_title="市场机会点分析系统(修复版)", layout="wide")
st.title("🧠 市场机会点分析系统 (Robust Ver.)")
st.markdown("""
**功能升级说明：**
1.  **修复了缩进错误**：解决了直接运行报错的问题。
2.  **增强容错性**：当数据量太少导致计算失败时（如价格分段），不会让整个程序崩溃。
3.  **智能状态重置**：切换文件时，会自动重置下拉框，防止“Index out of range”错误。
""")

# =============================================================================
# 2) 核心工具函数
# =============================================================================
def load_file(uploaded_file):
    if uploaded_file is None:
        return None, None, "没有文件"

    file_name = uploaded_file.name.lower()
    
    # 获取文件唯一标识，用于重置组件状态
    file_id = str(uploaded_file.file_id) if hasattr(uploaded_file, 'file_id') else str(time.time())

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
    """强健数值解析：处理 $12.99, 1,200.00, 12-15 等格式"""
    if pd.isna(val): return np.nan
    if isinstance(val, (int, float, np.number)): return float(val)

    s = str(val).strip()
    if s == "": return np.nan
    
    # 清理常见干扰字符
    s = s.replace("，", ",").replace("−", "-").replace("—", "-").replace("–", "-")
    s = s.replace("US$", "$").replace("USD", "$").replace("¥", "")
    
    # 提取所有数字
    nums = re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))
    if not nums: return np.nan

    # 处理区间 "10-20" -> 取平均 15
    if "-" in s or " to " in s.lower():
        if len(nums) >= 2:
            try:
                a, b = float(nums[0]), float(nums[1])
                return (a + b) / 2.0
            except: pass
            
    return float(nums[0])

# =============================================================================
# 3) 智能列识别
# =============================================================================
FIELD_KEYWORDS = {
    "brand":   {"include": ["brand", "品牌", "厂商", "manufacturer"], "exclude": ["story", "title"]},
    "title":   {"include": ["title", "name", "标题", "品名", "商品名"], "exclude": ["brand", "sku"]},
    "price":   {"include": ["price", "售价", "价格", "amount"], "exclude": ["list", "original"]},
    "sales":   {"include": ["sales", "sold", "销量", "成交"], "exclude": ["rank", "额", "revenue"]},
    "revenue": {"include": ["revenue", "sales_amt", "销售额", "金额"], "exclude": []},
    "rating":  {"include": ["rating", "score", "stars", "评分", "星级"], "exclude": ["count", "num", "人数"]},
    "reviews": {"include": ["review", "count", "评论", "评价", "number"], "exclude": ["rating", "star"]},
    "size":    {"include": ["size", "net", "weight", "ml", "oz", "g", "规格", "含量"], "exclude": ["package"]},
    "pack":    {"include": ["pack", "count", "装数", "pcs"], "exclude": []}
}

def get_best_col(columns, key):
    """自动寻找最匹配的列名"""
    columns_lower = [str(c).lower() for c in columns]
    rules = FIELD_KEYWORDS.get(key, {})
    
    best_col = None
    best_score = -100
    
    for idx, col_name in enumerate(columns_lower):
        score = 0
        # 包含关键词加分
        for kw in rules.get("include", []):
            if kw in col_name: score += 10
        # 排除关键词扣分
        for kw in rules.get("exclude", []):
            if kw in col_name: score -= 20
        # 优先匹配更短的列名（"Price" 优于 "Price Value"）
        if score > 0:
            score -= len(col_name) * 0.1
            
        if score > best_score and score > 0:
            best_score = score
            best_col = columns[idx]
            
    return best_col

# =============================================================================
# 4) 分析逻辑（增加 Try-Except 保护）
# =============================================================================
def analyze_data(df, col_map):
    """执行核心分析，返回清洗后的数据和图表对象"""
    data = df.copy()
    
    # 1. 基础清洗
    # -------------------------------------------------------
    data["_品牌"] = data[col_map["brand"]].astype(str).str.strip() if col_map["brand"] else "Unknown"
    data["_标题"] = data[col_map["title"]].astype(str) if col_map["title"] else ""
    
    # 数值清洗
    for key, new_col in [("price", "_价格"), ("sales", "_销量"), ("revenue", "_销售额"), 
                         ("rating", "_评分"), ("reviews", "_评论数")]:
        if col_map[key]:
            data[new_col] = data[col_map[key]].apply(clean_numeric)
        else:
            data[new_col] = np.nan

    # 2. 特征工程：单位价格
    # -------------------------------------------------------
    # 简单解析规格 (这里简化逻辑，防止正则报错)
    def parse_size(val):
        try:
            val = str(val).lower()
            if "oz" in val: return float(re.search(r"[\d\.]+", val).group()) * 28.35
            if "g" in val: return float(re.search(r"[\d\.]+", val).group())
            if "ml" in val: return float(re.search(r"[\d\.]+", val).group())
        except: return np.nan
        return np.nan

    if col_map["size"]:
        data["_净含量_g"] = data[col_map["size"]].apply(parse_size)
    else:
        data["_净含量_g"] = np.nan

    # 计算单位价格 ($/g)
    data["_单位价格"] = data["_价格"] / data["_净含量_g"]
    
    # 3. 需求指数构建 (如果有销售额用销售额，没有用销量，再没有用评论数)
    # -------------------------------------------------------
    if data["_销售额"].sum() > 0:
        data["_需求指数"] = data["_销售额"].fillna(0)
    elif data["_销量"].sum() > 0:
        data["_需求指数"] = data["_销量"].fillna(0)
    elif data["_评论数"].sum() > 0:
        data["_需求指数"] = data["_评论数"].fillna(0)
    else:
        data["_需求指数"] = 0

    # 4. 价格分段 (Robust)
    # -------------------------------------------------------
    try:
        # 如果数据太少，cut会报错，加保护
        valid_prices = data["_价格"].dropna()
        if len(valid_prices) > 5:
            data["价格区间"] = pd.cut(data["_价格"], bins=[0, 10, 20, 30, 50, 1000], labels=["<10", "10-20", "20-30", "30-50", "50+"])
        else:
            data["价格区间"] = "样本不足"
    except:
        data["价格区间"] = "计算错误"

    return data

# =============================================================================
# 5) 主程序
# =============================================================================
st.sidebar.header("📂 1. 上传文件")
uploaded_file = st.sidebar.file_uploader("支持 Excel (.xlsx) 或 CSV", type=["xlsx", "csv"])

if uploaded_file:
    # 加载文件
    ftype, fobj, err = load_file(uploaded_file)
    if err:
        st.error(err)
        st.stop()
        
    # 生成文件会话ID (用于刷新Widget)
    if 'file_id' not in st.session_state or st.session_state.file_id != uploaded_file.file_id:
        st.session_state.file_id = uploaded_file.file_id
        
    # 处理 Sheet
    sheets = {}
    if ftype == "xlsx":
        sheet_names = fobj.sheet_names
        selected_sheet = st.sidebar.selectbox("选择工作表", sheet_names)
        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
    else:
        df = fobj
        selected_sheet = "CSV数据"
        
    st.header(f"📊 分析报告: {selected_sheet}")
    
    # -------------------------------------------------------
    # 字段映射 (增加容错)
    # -------------------------------------------------------
    with st.expander("⚙️ 字段设置 (如果不准确请手动调整)", expanded=True):
        cols = df.columns.tolist()
        col_map = {}
        
        c1, c2, c3, c4 = st.columns(4)
        # 使用 key=session_state.file_id 确保换文件时重置
        uid = f"{st.session_state.file_id}_{selected_sheet}"
        
        def get_idx(options, val):
            return options.index(val) if val in options else 0

        # 智能预选
        auto_brand = get_best_col(cols, "brand")
        auto_title = get_best_col(cols, "title")
        auto_price = get_best_col(cols, "price")
        auto_sales = get_best_col(cols, "sales")
        
        col_map["brand"] = c1.selectbox("品牌列", [None] + cols, index=get_idx([None] + cols, auto_brand), key=f"b_{uid}")
        col_map["title"] = c2.selectbox("标题列", [None] + cols, index=get_idx([None] + cols, auto_title), key=f"t_{uid}")
        col_map["price"] = c3.selectbox("价格列", [None] + cols, index=get_idx([None] + cols, auto_price), key=f"p_{uid}")
        col_map["sales"] = c4.selectbox("销量列", [None] + cols, index=get_idx([None] + cols, auto_sales), key=f"s_{uid}")
        
        c5, c6, c7, c8 = st.columns(4)
        col_map["revenue"] = c5.selectbox("销售额列", [None] + cols, index=get_idx([None] + cols, get_best_col(cols, "revenue")), key=f"r_{uid}")
        col_map["rating"] = c6.selectbox("评分列", [None] + cols, index=get_idx([None] + cols, get_best_col(cols, "rating")), key=f"rt_{uid}")
        col_map["reviews"] = c7.selectbox("评论数列", [None] + cols, index=get_idx([None] + cols, get_best_col(cols, "reviews")), key=f"rv_{uid}")
        col_map["size"] = c8.selectbox("规格列(选填)", [None] + cols, index=get_idx([None] + cols, get_best_col(cols, "size")), key=f"sz_{uid}")

    # -------------------------------------------------------
    # 执行分析
    # -------------------------------------------------------
    if col_map["brand"] and col_map["price"]:
        try:
            data = analyze_data(df, col_map)
            
            # KPI
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("总SKU数", len(data))
            k2.metric("平均价格", f"${data['_价格'].mean():.2f}")
            k3.metric("市场总规模(估)", f"${data['_需求指数'].sum():,.0f}")
            if "_评分" in data:
                k4.metric("平均评分", f"{data['_评分'].mean():.2f}")

            # 图表 1: 价格分布
            g1, g2 = st.columns(2)
            with g1:
                st.subheader("💰 价格带分布")
                fig_p = px.histogram(data, x="_价格", title="产品价格分布直方图", nbins=20)
                st.plotly_chart(fig_p, use_container_width=True)
            
            with g2:
                st.subheader("🏆 品牌集中度 (CR Top 10)")
                top_brands = data.groupby("_品牌")["_需求指数"].sum().sort_values(ascending=False).head(10).reset_index()
                fig_b = px.bar(top_brands, x="_需求指数", y="_品牌", orientation='h', title="Top 10 品牌市场份额")
                st.plotly_chart(fig_b, use_container_width=True)

            # 图表 2: 机会点矩阵
            st.subheader("🎯 机会点矩阵 (高需求 vs 低竞争)")
            if "_评分" in data.columns and "_评论数" in data.columns:
                # 气泡图：X=评论数(竞争), Y=评分(满意度), Size=销量/销售额
                fig_opp = px.scatter(
                    data, 
                    x="_评论数", 
                    y="_评分", 
                    size="_价格", # 用价格或销量做大小
                    color="价格区间",
                    hover_data=["_品牌", "_标题"],
                    log_x=True, # 评论数通常差异巨大，用对数坐标更清晰
                    title="蓝海寻找：左上角区域 (评论少 + 评分高 = 潜力新品)"
                )
                st.plotly_chart(fig_opp, use_container_width=True)
            else:
                st.info("缺少评分或评论数据，无法生成机会矩阵图。")

            # 导出
            st.dataframe(data.head(100))
            
        except Exception as e:
            st.error(f"分析过程中发生错误: {str(e)}")
            st.warning("建议检查：价格列是否包含非数字字符？列名是否选择正确？")
    else:
        st.warning("⚠️ 请至少选择 [品牌] 和 [价格] 列以开始分析。")

else:
    st.info("👈 请在左侧上传数据文件")
