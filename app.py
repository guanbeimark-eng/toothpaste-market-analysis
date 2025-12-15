import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="牙膏市场数据分析(Excel版)", layout="wide")
st.title("🦷 牙膏市场分析 - Excel/CSV 通用版")
st.markdown("""
**使用说明：**
1. 支持上传 **.xlsx** (Excel) 或 **.csv** 文件。
2. 如果是 Excel 文件，系统会让你选择要读取的 **工作表 (Sheet)**。
3. 随后请确认下方的列名映射是否正确。
""")

# -----------------------------------------------------------------------------
# 2. 核心数据加载函数
# -----------------------------------------------------------------------------
def load_file(uploaded_file):
    """
    智能读取文件：
    - 如果是 CSV：尝试不同编码
    - 如果是 XLSX：读取所有 Sheet 名称供用户选择
    """
    if uploaded_file is None:
        return None, None, "没有文件"

    file_name = uploaded_file.name
    
    # --- 处理 Excel 文件 ---
    if file_name.endswith('.xlsx'):
        try:
            xl = pd.ExcelFile(uploaded_file)
            return "xlsx", xl, None
        except Exception as e:
            return None, None, f"Excel 读取失败: {str(e)}"

    # --- 处理 CSV 文件 ---
    elif file_name.endswith('.csv'):
        encodings = ['utf-8', 'gbk', 'utf-8-sig', 'ISO-8859-1']
        for enc in encodings:
            try:
                uploaded_file.seek(0) # 重置指针
                df = pd.read_csv(uploaded_file, encoding=enc)
                df.columns = df.columns.str.strip() # 清理列名空格
                return "csv", df, None
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return None, None, str(e)
        return None, None, "CSV 编码识别失败，请转存为 UTF-8 格式。"
    
    else:
        return None, None, "不支持的文件格式，请上传 .csv 或 .xlsx"

def clean_numeric(val):
    """强制转换为数字"""
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return val
    try:
        clean_str = str(val).replace('$', '').replace('¥', '').replace(',', '').replace(' ', '').replace('%', '')
        return float(clean_str)
    except:
        return 0

def get_col_index(options, key_words):
    """辅助函数：自动猜测列名的索引"""
    for i, opt in enumerate(options):
        for kw in key_words:
            if kw in str(opt): return i
    return 0

# -----------------------------------------------------------------------------
# 3. 侧边栏与主逻辑
# -----------------------------------------------------------------------------

# 定义两个分析模块
MODULES = {
    "product": "📦 产品明细分析 (对应 US 表)",
    "brand": "🏢 品牌汇总分析 (对应 Brands 表)"
}

st.sidebar.header("1. 选择分析模式")
analysis_mode = st.sidebar.radio("你想分析什么？", list(MODULES.values()))

st.sidebar.header("2. 上传文件")
uploaded_file = st.sidebar.file_uploader("上传数据文件 (.xlsx / .csv)", type=['xlsx', 'csv'])

# -----------------------------------------------------------------------------
# 4. 分析逻辑
# -----------------------------------------------------------------------------

if uploaded_file:
    file_type, data_obj, error = load_file(uploaded_file)

    if error:
        st.error(error)
    else:
        # === 获取 DataFrame ===
        df = None
        
        if file_type == 'xlsx':
            # Excel 需要选择 Sheet
            sheet_names = data_obj.sheet_names
            st.info(f"检测到 Excel 文件，包含以下工作表: {sheet_names}")
            
            # 智能预选 Sheet
            default_idx = 0
            if "产品" in analysis_mode and "US" in sheet_names:
                default_idx = sheet_names.index("US")
            elif "品牌" in analysis_mode and "Brands" in sheet_names:
                try: default_idx = sheet_names.index("Brands")
                except: pass
            
            selected_sheet = st.selectbox("请选择要分析的数据表 (Sheet):", sheet_names, index=default_idx)
            df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
            df.columns = df.columns.astype(str).str.strip() # 清理列名
            
        else:
            # CSV 直接就是 DataFrame
            df = data_obj

        # === 进入分析界面 ===
        if df is not None:
            st.divider()
            st.subheader(f"正在分析: {analysis_mode}")
            st.write(f"数据预览 (前3行):")
            st.dataframe(df.head(3))

            all_cols = df.columns.tolist()

            # ==========================================
            # 模式 A: 产品分析 (Product / US)
            # ==========================================
            if analysis_mode == MODULES["product"]:
                with st.expander("⚙️ 设置数据列 (对应关系)", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    col_price = c1.selectbox("价格列", all_cols, index=get_col_index(all_cols, ['价格', 'Price']))
                    col_sales = c2.selectbox("销量列", all_cols, index=get_col_index(all_cols, ['销量', 'Sales']))
                    col_rev = c3.selectbox("销售额列", all_cols, index=get_col_index(all_cols, ['销售额', 'Revenue']))
                    col_title = c4.selectbox("商品标题/名称列", all_cols, index=get_col_index(all_cols, ['标题', 'Name', 'Title']))

                try:
                    # 清洗数据
                    df['_price'] = df[col_price].apply(clean_numeric)
                    df['_sales'] = df[col_sales].apply(clean_numeric)
                    df['_rev'] = df[col_rev].apply(clean_numeric)

                    # 指标卡
                    m1, m2, m3 = st.columns(3)
                    m1.metric("总销售额", f"${df['_rev'].sum():,.0f}")
                    m2.metric("总销量", f"{df['_sales'].sum():,.0f}")
                    m3.metric("平均价格", f"${df['_price'].mean():.2f}")

                    # 图表
                    g1, g2 = st.columns(2)
                    with g1:
                        st.markdown("##### 价格分布")
                        fig = px.histogram(df, x='_price', nbins=20, title="价格区间分布")
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with g2:
                        st.markdown("##### 销量 Top 10 商品")
                        top_items = df.sort_values('_sales', ascending=False).head(10)
                        # 截断太长的标题
                        top_items['_short_title'] = top_items[col_title].astype(str).str[:30] + "..."
                        fig = px.bar(top_items, x='_sales', y='_short_title', orientation='h', title="热销商品")
                        st.plotly_chart(fig, use_container_width=True)

                except Exception as e:
                    st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")

            # ==========================================
            # 模式 B: 品牌分析 (Brand)
            # ==========================================
            elif analysis_mode == MODULES["brand"]:
                with st.expander("⚙️ 设置数据列 (对应关系)", expanded=True):
                    c1, c2 = st.columns(2)
                    b_name = c1.selectbox("品牌名称列", all_cols, index=get_col_index(all_cols, ['品牌', 'Brand']))
                    b_rev = c2.selectbox("销售额/占比列", all_cols, index=get_col_index(all_cols, ['销售额', 'Revenue', 'Share']))

                try:
                    df['_val'] = df[b_rev].apply(clean_numeric)
                    
                    st.markdown("##### 品牌市场占比")
                    # 排序并取前15
                    df_sorted = df.sort_values('_val', ascending=False).head(15)
                    
                    fig = px.pie(df_sorted, values='_val', names=b_name, title="Top 15 品牌占比", hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("##### 品牌数据明细")
                    st.dataframe(df)

                except Exception as e:
                    st.error(f"分析出错，请检查上方列名是否选择正确。\n错误信息: {e}")

else:
    st.info("👈 请在左侧侧边栏上传文件")
