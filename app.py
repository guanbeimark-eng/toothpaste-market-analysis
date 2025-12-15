import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="牙膏市场数据分析", layout="wide")
st.title("🦷 纳米羟基磷灰石牙膏 - 亚马逊市场分析 (修复版)")

# -----------------------------------------------------------------------------
# 2. 辅助函数：更稳健的数据清洗
# -----------------------------------------------------------------------------
def clean_currency(x):
    """
    尝试将包含 $ , 空格 的字符串转换为浮点数。
    如果转换失败，返回 0。
    """
    if pd.isna(x) or x == '':
        return 0
    if isinstance(x, (int, float)):
        return x
    try:
        # 移除货币符号、逗号、空格
        clean_str = str(x).replace('$', '').replace('¥', '').replace(',', '').replace(' ', '')
        return float(clean_str)
    except:
        return 0

def load_csv_safe(file):
    """
    尝试多种编码格式读取 CSV，防止乱码报错
    """
    try:
        return pd.read_csv(file, encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return pd.read_csv(file, encoding='gbk')
        except UnicodeDecodeError:
            return pd.read_csv(file, encoding='ISO-8859-1')

# -----------------------------------------------------------------------------
# 3. 侧边栏上传
# -----------------------------------------------------------------------------
st.sidebar.header("📂 数据上传区")
uploaded_us_file = st.sidebar.file_uploader("1. 上传 US.csv (产品明细)", type=["csv"])
uploaded_brand_file = st.sidebar.file_uploader("2. 上传 Brands.csv (品牌汇总)", type=["csv"])

# -----------------------------------------------------------------------------
# 4. Tab 1: 产品分析 (US.csv)
# -----------------------------------------------------------------------------
st.header("📊 分析报告")
tab1, tab2 = st.tabs(["1. 产品明细分析 (Product)", "2. 品牌市场分析 (Brand)"])

with tab1:
    if uploaded_us_file is not None:
        try:
            # 读取数据
            df_us = load_csv_safe(uploaded_us_file)
            
            # --- 关键修复：去除列名两端的空格 ---
            df_us.columns = df_us.columns.str.strip()

            # 定义需要的列名 (根据你提供的文件)
            # 注意：这里列名必须和 CSV 里的一模一样
            col_sales = '月销量'
            col_revenue = '月销售额($)'
            col_price = '价格($)'
            col_rating = '评分'
            
            # 检查列是否存在
            missing_cols = [c for c in [col_sales, col_revenue, col_price] if c not in df_us.columns]
            
            if missing_cols:
                st.error(f"❌ 错误：在文件中找不到以下列名：{missing_cols}")
                st.info(f"系统检测到的所有列名如下：{list(df_us.columns)}")
                st.warning("请检查 CSV 文件的表头是否正确。")
            else:
                # 数据清洗
                df_us[col_sales] = df_us[col_sales].apply(clean_currency)
                df_us[col_revenue] = df_us[col_revenue].apply(clean_currency)
                df_us[col_price] = df_us[col_price].apply(clean_currency)
                if col_rating in df_us.columns:
                    df_us[col_rating] = pd.to_numeric(df_us[col_rating], errors='coerce')

                # 顶部指标
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总销售额", f"${df_us[col_revenue].sum():,.0f}")
                c2.metric("总销量", f"{df_us[col_sales].sum():,.0f}")
                c3.metric("平均价格", f"${df_us[col_price].mean():.2f}")
                if col_rating in df_us.columns:
                    c4.metric("平均评分", f"{df_us[col_rating].mean():.2f} ⭐")

                st.divider()

                # 图表区域
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    st.subheader("💰 价格分布")
                    fig_price = px.histogram(df_us, x=col_price, nbins=20, title="产品价格区间分布")
                    st.plotly_chart(fig_price, use_container_width=True)
                
                with col_chart2:
                    st.subheader("📈 销量 vs 评分")
                    if col_rating in df_us.columns:
                        # 过滤掉异常值以便图表更好看
                        plot_df = df_us[df_us[col_sales] > 0]
                        fig_scatter = px.scatter(
                            plot_df, 
                            x=col_rating, 
                            y=col_sales, 
                            size=col_price, 
                            color=col_price,
                            hover_data=[col_price],
                            title="评分与销量的关系 (气泡大小=价格)"
                        )
                        st.plotly_chart(fig_scatter, use_container_width=True)
                    else:
                        st.warning("数据中缺少'评分'列，无法生成散点图")

                st.subheader("🏆 Top 10 畅销单品")
                # 尝试寻找标题列
                title_col = '商品标题' if '商品标题' in df_us.columns else df_us.columns[0]
                brand_col = '品牌' if '品牌' in df_us.columns else None
                
                display_cols = [title_col, col_price, col_sales, col_revenue]
                if brand_col: display_cols.insert(1, brand_col)
                
                st.dataframe(
                    df_us[display_cols].sort_values(by=col_sales, ascending=False).head(10),
                    use_container_width=True
                )

        except Exception as e:
            st.error("处理 US.csv 时发生未知错误")
            st.exception(e)
    else:
        st.info("👈 请在左侧上传 US.csv 文件")

# -----------------------------------------------------------------------------
# 5. Tab 2: 品牌分析 (Brands.csv)
# -----------------------------------------------------------------------------
with tab2:
    if uploaded_brand_file is not None:
        try:
            df_brand = load_csv_safe(uploaded_brand_file)
            df_brand.columns = df_brand.columns.str.strip()

            # 列名映射
            b_brand = '品牌'
            b_revenue = '月销售额($)'
            b_sales = '月销量'
            b_price = '平均价格($)'

            # 检查关键列
            if b_revenue not in df_brand.columns:
                 # 尝试模糊匹配，有时候列名可能是 '月销售额' 没有 ($)
                found = False
                for c in df_brand.columns:
                    if '销售额' in c:
                        b_revenue = c
                        found = True
                        break
                if not found:
                    st.error(f"无法在 Brands.csv 中找到销售额列。现有列名: {list(df_brand.columns)}")
                    st.stop()

            # 清洗
            df_brand[b_revenue] = df_brand[b_revenue].apply(clean_currency)
            if b_sales in df_brand.columns:
                df_brand[b_sales] = df_brand[b_sales].apply(clean_currency)
            if b_price in df_brand.columns:
                df_brand[b_price] = df_brand[b_price].apply(clean_currency)

            # 布局
            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.subheader("🏢 品牌市场份额 (Revenue)")
                top_brands = df_brand.sort_values(by=b_revenue, ascending=False).head(15)
                fig_pie = px.pie(top_brands, values=b_revenue, names=b_brand, hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

            with c2:
                st.subheader("🏷️ 品牌均价 (Top 10)")
                if b_price in df_brand.columns:
                    top_vol = df_brand.sort_values(by=b_revenue, ascending=False).head(10)
                    fig_bar = px.bar(top_vol, x=b_brand, y=b_price, color=b_price)
                    st.plotly_chart(fig_bar, use_container_width=True)

            st.dataframe(df_brand)

        except Exception as e:
            st.error("处理 Brands.csv 时发生错误")
            st.exception(e)
    else:
        st.info("👈 请在左侧上传 Brands.csv 文件")
