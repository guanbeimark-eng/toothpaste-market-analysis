import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 基础配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="牙膏市场数据分析(诊断版)", layout="wide")
st.title("🛠️ 牙膏市场分析 - 诊断模式")
st.markdown("""
**使用说明：**
1. 上传 CSV 文件。
2. 如果系统没有自动识别出列，请在下方的“列名映射”区域手动选择对应的列。
3. 图表会自动生成。
""")

# -----------------------------------------------------------------------------
# 2. 核心函数
# -----------------------------------------------------------------------------
def load_data(file):
    """尝试多种编码读取文件"""
    encodings = ['utf-8', 'gbk', 'utf-8-sig', 'ISO-8859-1']
    for enc in encodings:
        try:
            # 尝试读取
            df = pd.read_csv(file, encoding=enc)
            # 清理列名空格
            df.columns = df.columns.str.strip()
            return df, None
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return None, str(e)
    return None, "无法识别文件编码，请尝试将文件另存为 UTF-8 格式的 CSV。"

def clean_numeric(val):
    """强制转换为数字"""
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return val
    try:
        # 去除货币符号、逗号、空格
        clean_str = str(val).replace('$', '').replace('¥', '').replace(',', '').replace(' ', '')
        return float(clean_str)
    except:
        return 0

# -----------------------------------------------------------------------------
# 3. 侧边栏：文件上传
# -----------------------------------------------------------------------------
st.sidebar.header("📂 文件上传")
uploaded_us = st.sidebar.file_uploader("上传 US.csv (产品明细)", type=['csv'])
uploaded_brand = st.sidebar.file_uploader("上传 Brands.csv (品牌汇总)", type=['csv'])

# -----------------------------------------------------------------------------
# 4. 模块一：产品分析 (US.csv)
# -----------------------------------------------------------------------------
st.header("1. 产品分析 (Product Analysis)")

if uploaded_us:
    df_us, error_msg = load_data(uploaded_us)
    
    if df_us is not None:
        st.success(f"成功读取文件！包含 {len(df_us)} 行数据。")
        
        # --- 关键：列名映射选择器 ---
        with st.expander("⚙️ 字段设置 (如果不显示图表，请点这里检查列名)", expanded=True):
            st.info("系统会自动尝试匹配列名，如果不对，请手动修正。")
            
            # 获取所有列名
            all_cols = df_us.columns.tolist()
            
            # 辅助函数：尝试找到默认值
            def get_index(options, key_words):
                for i, opt in enumerate(options):
                    for kw in key_words:
                        if kw in opt: return i
                return 0

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                c_price = st.selectbox("选择[价格]列", all_cols, index=get_index(all_cols, ['价格', 'Price']))
            with col2:
                c_sales = st.selectbox("选择[销量]列", all_cols, index=get_index(all_cols, ['销量', 'Sales']))
            with col3:
                c_rev = st.selectbox("选择[销售额]列", all_cols, index=get_index(all_cols, ['销售额', 'Revenue']))
            with col4:
                c_brand = st.selectbox("选择[品牌]列", all_cols, index=get_index(all_cols, ['品牌', 'Brand']))

        # --- 数据处理 ---
        try:
            # 转换数据类型
            df_us['clean_price'] = df_us[c_price].apply(clean_numeric)
            df_us['clean_sales'] = df_us[c_sales].apply(clean_numeric)
            df_us['clean_rev'] = df_us[c_rev].apply(clean_numeric)
            
            # 顶部指标
            k1, k2, k3 = st.columns(3)
            k1.metric("总销售额", f"${df_us['clean_rev'].sum():,.0f}")
            k2.metric("总销量", f"{df_us['clean_sales'].sum():,.0f}")
            k3.metric("平均价格", f"${df_us['clean_price'].mean():.2f}")

            # 图表
            c_chart1, c_chart2 = st.columns(2)
            
            with c_chart1:
                st.subheader("价格分布")
                fig1 = px.histogram(df_us, x='clean_price', nbins=20, title="产品价格区间")
                st.plotly_chart(fig1, use_container_width=True)
            
            with c_chart2:
                st.subheader("品牌销量 Top 10 (基于当前文件)")
                # 简单的按品牌聚合
                if c_brand:
                    brand_agg = df_us.groupby(c_brand)['clean_sales'].sum().reset_index()
                    brand_agg = brand_agg.sort_values('clean_sales', ascending=False).head(10)
                    fig2 = px.bar(brand_agg, x=c_brand, y='clean_sales', title="品牌销量排行")
                    st.plotly_chart(fig2, use_container_width=True)
            
            st.subheader("原始数据预览")
            st.dataframe(df_us.head(5))

        except Exception as e:
            st.error(f"数据处理时出错: {e}")
            st.warning("请检查上方下拉框选中的列是否包含数字内容。")

    else:
        st.error(f"读取文件失败: {error_msg}")
else:
    st.info("👈 请在左侧上传 US.csv")

st.divider()

# -----------------------------------------------------------------------------
# 5. 模块二：品牌分析 (Brands.csv)
# -----------------------------------------------------------------------------
st.header("2. 品牌分析 (Brand Analysis)")

if uploaded_brand:
    df_brand, error_msg_b = load_data(uploaded_brand)
    
    if df_brand is not None:
        st.success("成功读取品牌文件！")
        
        with st.expander("⚙️ 品牌表字段设置", expanded=True):
            b_cols = df_brand.columns.tolist()
            
            bc1, bc2 = st.columns(2)
            with bc1:
                b_name_col = st.selectbox("选择[品牌名称]列", b_cols, index=get_index(b_cols, ['品牌', 'Brand']))
            with bc2:
                b_rev_col = st.selectbox("选择[月销售额]列", b_cols, index=get_index(b_cols, ['销售额', 'Revenue']))

        try:
            df_brand['clean_rev'] = df_brand[b_rev_col].apply(clean_numeric)
            
            st.subheader("品牌市场份额")
            top_brands = df_brand.sort_values('clean_rev', ascending=False).head(15)
            fig_pie = px.pie(top_brands, values='clean_rev', names=b_name_col, hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
            st.subheader("数据明细")
            st.dataframe(df_brand)
            
        except Exception as e:
            st.error(f"生成图表出错: {e}")
    else:
        st.error(f"读取失败: {error_msg_b}")
else:
    st.info("👈 请在左侧上传 Brands.csv")
