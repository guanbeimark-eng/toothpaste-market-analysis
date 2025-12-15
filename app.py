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
st.set_page_config(page_title="全维度亚马逊市场分析系统", layout="wide", page_icon="🧩")

st.title("🧩 全维度亚马逊市场分析系统 (智能路由版)")
st.markdown("""
**系统已启用智能路由 (Smart Router)：**
系统会自动根据表头特征，将工作表识别为以下三种模式之一，并匹配专属分析维度：
1.  📦 **产品开发模式** (针对 Product/US 表)：分析规格、成分、卖点、SKU结构。
2.  🏢 **品牌格局模式** (针对 Brands 表)：分析垄断度、价格带占位、品牌分层。
3.  🏪 **渠道卖家模式** (针对 Sellers 表)：分析头部卖家掌控力、FBA/FBM分布。
""")

# --- 通用清洗函数 ---
def clean_numeric(val):
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return 0.0
    # 清理百分比、货币符号
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "").replace("￥", "")
    if "%" in s:
        try: return float(s.replace("%", "")) / 100.0
        except: pass
    # 提取数字
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return 0.0
    # 处理区间
    if len(nums) >= 2 and ("-" in str(val) or "to" in str(val).lower()):
        return (float(nums[0]) + float(nums[1])) / 2.0
    return float(nums[0])

def find_col(columns, keywords):
    """模糊查找列名"""
    for col in columns:
        for kw in keywords:
            if kw.lower() in str(col).lower().replace(" ", ""): return col
    return None

# =============================================================================
# 2. 模式识别引擎 (Router)
# =============================================================================
def detect_sheet_mode(df):
    cols = [str(c).lower() for c in df.columns]
    col_str = " ".join(cols)
    
    # 判定逻辑
    if "asin" in col_str or "sku" in col_str or "标题" in col_str or "title" in col_str:
        return "PRODUCT"
    elif "seller" in col_str or "卖家" in col_str:
        return "SELLER"
    elif ("brand" in col_str or "品牌" in col_str) and ("share" in col_str or "份额" in col_str):
        return "BRAND"
    else:
        return "GENERIC"

# =============================================================================
# 3. 专属分析模块 A: 产品开发模式 (Product Mode)
#    - 维度：SKU架构、成分技术、产品形态
# =============================================================================
def render_product_dashboard(df):
    st.info("检测到 [产品明细数据]，已加载 **产品开发决策面板 (9大维度)**")
    
    # --- 1. 字段映射 ---
    all_cols = df.columns.tolist()
    col_map = {
        'title': find_col(all_cols, ['title', '标题', 'name']),
        'price': find_col(all_cols, ['price', '价格', '售价']),
        'sales': find_col(all_cols, ['sales', '销量', 'sold']),
        'rating': find_col(all_cols, ['rating', '评分', 'stars']),
        'brand': find_col(all_cols, ['brand', '品牌']),
    }
    
    # 数据清洗
    data = df.copy()
    if not col_map['title']: 
        st.error("无法分析：缺少[标题]列"); return

    data['clean_price'] = data[col_map['price']].apply(clean_numeric) if col_map['price'] else 0
    data['clean_sales'] = data[col_map['sales']].apply(clean_numeric) if col_map['sales'] else 0
    data['clean_rating'] = data[col_map['rating']].apply(clean_numeric) if col_map['rating'] else 0
    data['Title_Str'] = data[col_map['title']].astype(str)

    # --- 2. 特征提取 (Pack/Flavor/Tech) ---
    def extract_pack(t):
        m = re.search(r"(pack of \d+|\d+\s?count|\d+\s?pack)", t.lower())
        if m: 
            nums = re.findall(r"\d+", m.group(0))
            return int(nums[0]) if nums else 1
        return 1

    data['Pack_Count'] = data['Title_Str'].apply(extract_pack)
    data['Unit_Price'] = data.apply(lambda x: x['clean_price']/x['Pack_Count'] if x['Pack_Count']>0 else x['clean_price'], axis=1)

    # --- 3. 可视化分析 ---
    tab1, tab2, tab3, tab4 = st.tabs(["📦 规格与形态", "💰 价格体系", "🧪 卖点分析", "✅ 开发建议"])
    
    with tab1:
        st.subheader("SKU 结构分析")
        c1, c2 = st.columns(2)
        with c1:
            # Pack 数分布
            pack_dist = data.groupby('Pack_Count')['clean_sales'].sum().reset_index()
            fig = px.pie(pack_dist, values='clean_sales', names='Pack_Count', title='销量按 Pack 数分布', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("👉 决策：如果 Pack 1 占比 <50%，说明多支装是主流，需考虑组合销售。")
        with c2:
            # 词云替代方案 (Top Keywords)
            st.markdown("**标题高频词 (热度分析)**")
            text = " ".join(data['Title_Str'].tolist()).lower()
            words = [w for w in re.split(r'\W+', text) if len(w)>3 and w not in ['toothpaste', 'with', 'pack', 'count']]
            top_words = pd.Series(words).value_counts().head(15)
            st.bar_chart(top_words)

    with tab2:
        st.subheader("价格锚点分析")
        c1, c2 = st.columns(2)
        with c1:
            # 价格区间
            fig = px.histogram(data[data['clean_price']>0], x='clean_price', nbins=20, title="售价区间分布 (Price Range)")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            # 价格 vs 评分
            fig = px.scatter(data, x='clean_price', y='clean_rating', size='clean_sales', title="价格 vs 评分 (寻找溢价空间)")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("👉 决策：右上角稀疏区域即为【高价高满意度】蓝海机会。")

    with tab3:
        st.subheader("卖点渗透率")
        # 简单正则检测
        tech_kws = ['hydroxyapatite', 'nano', 'fluoride free', 'whitening', 'sensitive', 'charcoal']
        res = []
        for k in tech_kws:
            cnt = data[data['Title_Str'].str.contains(k, case=False)].shape[0]
            sales = data[data['Title_Str'].str.contains(k, case=False)]['clean_sales'].sum()
            res.append({'Keyword': k, 'Count': cnt, 'Sales': sales})
        
        df_kw = pd.DataFrame(res).sort_values('Sales', ascending=False)
        fig = px.bar(df_kw, x='Sales', y='Keyword', orientation='h', title="核心成分/功效 销量贡献")
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.success(f"""
        **🤖 智能生成开发决策：**
        1. **规格建议**：市场主流 Pack 数为 {data.groupby('Pack_Count')['clean_sales'].sum().idxmax()}。
        2. **定价建议**：平均售价 ${data['clean_price'].mean():.2f}，建议起步价设定在 ${data['clean_price'].quantile(0.4):.2f} 以获取流量。
        3. **核心成分**："{df_kw.iloc[0]['Keyword']}" 是当前销量最大的技术路线。
        """)

# =============================================================================
# 4. 专属分析模块 B: 品牌格局模式 (Brand Mode)
#    - 维度：垄断度、红海判断、品牌分层
# =============================================================================
def render_brand_dashboard(df):
    st.success("检测到 [品牌汇总数据]，已加载 **品牌竞争格局面板**")
    
    all_cols = df.columns.tolist()
    col_map = {
        'brand': find_col(all_cols, ['brand', '品牌']),
        'share': find_col(all_cols, ['share', '份额']),
        'sales': find_col(all_cols, ['sales', '销量']),
        'price': find_col(all_cols, ['price', '价格', '均价']),
        'rev': find_col(all_cols, ['revenue', '销售额'])
    }
    
    data = df.copy()
    if col_map['share']: data['clean_share'] = data[col_map['share']].apply(clean_numeric)
    if col_map['rev']: data['clean_rev'] = data[col_map['rev']].apply(clean_numeric)
    if col_map['price']: data['clean_price'] = data[col_map['price']].apply(clean_numeric)
    
    # 排序
    val_col = 'clean_rev' if col_map['rev'] else ('clean_share' if col_map['share'] else None)
    if not val_col: st.error("无法分析：缺少份额或销售额列"); return
    
    data = data.sort_values(val_col, ascending=False)
    
    c1, c2, c3 = st.columns(3)
    
    # 1. 垄断度分析
    top5_share = data.head(5)[val_col].sum()
    total_share = data[val_col].sum()
    cr5 = top5_share / total_share if total_share > 0 else 0
    
    with c1:
        st.metric("CR5 (Top 5 集中度)", f"{cr5:.1%}")
        if cr5 > 0.6: st.error("🔴 高度垄断 (红海)")
        elif cr5 < 0.3: st.success("🟢 市场分散 (蓝海)")
        else: st.warning("🟡 竞争适中")
        
    with c2:
        st.metric("活跃品牌数", len(data))
    
    with c3:
        if col_map['price']:
            avg_p = data.head(20)['clean_price'].mean()
            st.metric("头部品牌均价", f"${avg_p:.2f}")

    st.divider()
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("品牌市场份额 Top 15")
        fig = px.bar(data.head(15), x=val_col, y=col_map['brand'], orientation='h', title="头部玩家榜单")
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.subheader("品牌价格定位")
        if col_map['price'] and col_map['rev']:
            # 气泡图：价格 vs 规模
            fig = px.scatter(data.head(30), x='clean_price', y='clean_rev', size='clean_rev', 
                           hover_name=col_map['brand'], title="品牌定位: 价格 vs 规模")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("👉 决策：避开大球（巨头），寻找价格空档。")

# =============================================================================
# 5. 专属分析模块 C: 渠道卖家模式 (Seller Mode)
#    - 维度：卖家国籍、FBA占比、渠道掌控
# =============================================================================
def render_seller_dashboard(df):
    st.warning("检测到 [卖家/渠道数据]，已加载 **渠道卖家分析面板**")
    
    all_cols = df.columns.tolist()
    col_map = {
        'seller': find_col(all_cols, ['seller', '卖家']),
        'sales': find_col(all_cols, ['sales', '销量']),
        'country': find_col(all_cols, ['country', 'region', '国家', '属地']),
        'type': find_col(all_cols, ['type', '类型', 'fba']) # 比如 Buybox 类型
    }
    
    data = df.copy()
    if col_map['sales']: data['clean_sales'] = data[col_map['sales']].apply(clean_numeric)
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("卖家销量分布 (Head vs Tail)")
        if col_map['seller'] and 'clean_sales' in data:
            top_sellers = data.sort_values('clean_sales', ascending=False).head(10)
            fig = px.bar(top_sellers, x='clean_sales', y=col_map['seller'], orientation='h', title="Top 10 卖家销量")
            st.plotly_chart(fig, use_container_width=True)
            
    with c2:
        st.subheader("卖家属性分布")
        if col_map['country']:
            country_dist = data[col_map['country']].value_counts().reset_index()
            fig = px.pie(country_dist, values='count', names=col_map['country'], title="卖家所属地分布")
            st.plotly_chart(fig, use_container_width=True)
        elif col_map['type']:
             type_dist = data[col_map['type']].value_counts().reset_index()
             fig = px.pie(type_dist, values='count', names=col_map['type'], title="配送方式 (FBA/FBM) 分布")
             st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("数据中缺少 [国家] 或 [配送方式] 列，无法展示属性分布。")

    st.info("""
    **📢 渠道洞察：**
    如果 'Amazon' 出现在 Top 卖家，说明自营占比高，需避开正面硬刚。
    如果 CN (China) 卖家占比高，说明该品类供应链在国内，成本竞争会很激烈。
    """)

# =============================================================================
# 6. 主程序入口
# =============================================================================
st.sidebar.header("📂 1. 上传文件")
uploaded_file = st.sidebar.file_uploader("上传 Excel (.xlsx) 或 CSV", type=['xlsx', 'csv'])

if uploaded_file:
    # 读取文件
    dfs = {}
    try:
        if uploaded_file.name.endswith('.csv'):
            try: df = pd.read_csv(uploaded_file, encoding='utf-8')
            except: 
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='gbk')
            dfs["Sheet1"] = df
        else:
            xl = pd.ExcelFile(uploaded_file)
            for sheet in xl.sheet_names:
                dfs[sheet] = pd.read_excel(uploaded_file, sheet_name=sheet)
    except Exception as e:
        st.error(f"读取失败: {e}")
        st.stop()

    # 渲染 Tabs
    sheet_names = list(dfs.keys())
    st.sidebar.success(f"成功读取 {len(sheet_names)} 个工作表")
    
    # 创建 Streamlit Tabs
    tabs = st.tabs([f"📑 {name}" for name in sheet_names])
    
    for i, name in enumerate(sheet_names):
        with tabs[i]:
            df_active = dfs[name]
            # 智能路由：判断模式
            mode = detect_sheet_mode(df_active)
            
            st.markdown(f"#### 当前工作表: `{name}` | 识别模式: `{mode}`")
            
            if mode == "PRODUCT":
                render_product_dashboard(df_active)
            elif mode == "BRAND":
                render_brand_dashboard(df_active)
            elif mode == "SELLER":
                render_seller_dashboard(df_active)
            else:
                st.warning("无法识别该表类型 (既不是产品，也不是品牌或卖家)。显示通用数据预览：")
                st.dataframe(df_active.head(50))
                
else:
    st.info("👈 请在左侧上传文件，系统将自动拆解分析。")# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# -----------------------------------------------------------------------------
# 1. 页面配置与业务逻辑字典
# -----------------------------------------------------------------------------
st.set_page_config(page_title="亚马逊产品开发决策系统", layout="wide")
st.title("🚀 亚马逊产品开发决策系统 (Deep Dive Ver.)")
st.markdown("""
**系统设计逻辑：**
本系统专为 **产品经理/开发人员** 设计，将原始数据转化为 9 大维度的决策依据：
1. **产品形态** (Size/Pack) -> 决定开模规格
2. **功效技术** (Ingredients) -> 决定配方路线
3. **价格体系** (Price Tier) -> 决定定价策略
4. **品牌定位** (Positioning) -> 决定竞对策略
5. **包装物流** (FBA) -> 决定成本结构
6. **卖点传达** (Messaging) -> 决定Listing文案
7. **渠道策略** (Traffic) -> 决定推广预算
8. **市场成熟度** (Readiness) -> 决定进入时机
9. **最终决策清单** (Checklist) -> 输出行动项
""")

# 预定义关键词库 (可根据类目扩展)
KEYWORDS_DB = {
    "flavor": ["mint", "spearmint", "peppermint", "watermelon", "strawberry", "coconut", "charcoal", "bubblegum", "unflavored", "berry", "citrus"],
    "tech": ["nano", "hydroxyapatite", "hap", "fluoride", "fluoride-free", "xylitol", "nhap", "remineralization"],
    "efficacy": ["whitening", "sensitive", "sensitivity", "gum", "enamel", "repair", "fresh", "plaque", "cavity", "stain"]
}

# -----------------------------------------------------------------------------
# 2. 强健的数据清洗与提取引擎
# -----------------------------------------------------------------------------
def clean_numeric(val):
    """通用数值清洗"""
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "null"]: return 0.0
    s = s.replace("$", "").replace("¥", "").replace(",", "").replace(" ", "")
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums: return 0.0
    if len(nums) >= 2 and ("-" in str(val) or "to" in str(val).lower()):
        return (float(nums[0]) + float(nums[1])) / 2.0
    return float(nums[0])

def extract_pack_count(title):
    """从标题提取 Pack 数 (如 Pack of 2, 3 Count)"""
    title = str(title).lower()
    # 模式1: pack of X
    m1 = re.search(r"pack of (\d+)", title)
    if m1: return int(m1.group(1))
    # 模式2: X count / X tubes
    m2 = re.search(r"(\d+)\s?(count|tubes|pack)", title)
    if m2: return int(m2.group(1))
    return 1 # 默认为单支

def extract_size_oz(text):
    """提取容量 (oz)"""
    text = str(text).lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s?(oz|ounce)", text)
    if m: return float(m.group(1))
    return None

def extract_tags(text, keyword_list):
    """提取标签"""
    text = str(text).lower()
    found = []
    for kw in keyword_list:
        if kw in text:
            found.append(kw)
    return found[0] if found else "Other"

# -----------------------------------------------------------------------------
# 3. 核心分析模块 (9大维度)
# -----------------------------------------------------------------------------
def analyze_product_sheet(df, col_map):
    data = df.copy()
    
    # --- 基础清洗 ---
    data['clean_price'] = data[col_map['price']].apply(clean_numeric) if col_map['price'] else 0
    data['clean_sales'] = data[col_map['sales']].apply(clean_numeric) if col_map['sales'] else 0
    data['clean_rating'] = data[col_map['rating']].apply(clean_numeric) if col_map['rating'] else 0
    data['clean_reviews'] = data[col_map['reviews']].apply(clean_numeric) if col_map['reviews'] else 0
    
    # 必须有标题才能做NLP提取
    if not col_map['title']:
        st.error("❌ 缺少[标题]列，无法进行深度产品形态分析。")
        return

    data['Title_Str'] = data[col_map['title']].astype(str)
    
    # --- 特征提取 (Feature Engineering) ---
    with st.spinner("正在解析产品特征 (Pack/Size/Flavor/Tech)..."):
        data['Pack_Count'] = data['Title_Str'].apply(extract_pack_count)
        data['Size_oz'] = data['Title_Str'].apply(extract_size_oz)
        data['Flavor'] = data['Title_Str'].apply(lambda x: extract_tags(x, KEYWORDS_DB['flavor']))
        data['Tech_Tag'] = data['Title_Str'].apply(lambda x: extract_tags(x, KEYWORDS_DB['tech']))
        data['Efficacy_Tag'] = data['Title_Str'].apply(lambda x: extract_tags(x, KEYWORDS_DB['efficacy']))
        
        # 计算单价
        data['Unit_Price'] = np.where(data['Pack_Count']>0, data['clean_price']/data['Pack_Count'], data['clean_price'])

    # --- 诊断信息 ---
    with st.expander("🛠️ 数据解析诊断 (点击查看)", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("成功提取 Pack数 比例", f"{len(data[data['Pack_Count']>1])/len(data):.1%}")
        c2.metric("成功提取 规格(oz) 比例", f"{data['Size_oz'].notna().mean():.1%}")
        c3.metric("包含核心成分 比例", f"{len(data[data['Tech_Tag']!='Other'])/len(data):.1%}")
        st.dataframe(data[['Title_Str', 'Pack_Count', 'Flavor', 'Tech_Tag']].head(10))

    # ========================== 9大维度 Tabs ==========================
    tabs = st.tabs([
        "1.产品形态", "2.功效技术", "3.价格体系", "4.品牌定位", 
        "5.包装物流", "6.卖点传达", "7.渠道策略", "8.市场成熟度", "✅决策清单"
    ])

    # 1. 产品形态与SKU结构 (Product Architecture)
    with tabs[0]:
        st.subheader("📦 产品形态与SKU结构")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Pack数 vs 销量份额** (判断是否需要做多支装)")
            pack_sales = data.groupby('Pack_Count')['clean_sales'].sum().reset_index()
            fig_pack = px.pie(pack_sales, values='clean_sales', names='Pack_Count', hole=0.4)
            st.plotly_chart(fig_pack, use_container_width=True)
            
        with c2:
            st.markdown("**口味分布** (Flavor Name)")
            flavor_sales = data[data['Flavor']!='Other'].groupby('Flavor')['clean_sales'].sum().sort_values(ascending=False).head(10)
            fig_flavor = px.bar(flavor_sales, orientation='h', title="热销口味 Top 10")
            st.plotly_chart(fig_flavor, use_container_width=True)
            
        st.info(f"👉 **决策建议**：市场主流 Pack 数为 {pack_sales.sort_values('clean_sales', ascending=False).iloc[0]['Pack_Count']}。如果多支装占比超过 30%，建议首发即包含 Pack-2 或 Pack-3 以拉升客单价。")

    # 2. 功效与技术路线 (Efficacy & Tech)
    with tabs[1]:
        st.subheader("🧪 功效与技术路线")
        c1, c2 = st.columns(2)
        with c1:
            tech_counts = data[data['Tech_Tag']!='Other'].groupby('Tech_Tag')['clean_sales'].sum().reset_index()
            fig_tech = px.treemap(tech_counts, path=['Tech_Tag'], values='clean_sales', title="核心成分/技术路线 销量分布")
            st.plotly_chart(fig_tech, use_container_width=True)
        with c2:
            eff_counts = data[data['Efficacy_Tag']!='Other'].groupby('Efficacy_Tag')['clean_sales'].sum().sort_values(ascending=False).head(10)
            fig_eff = px.bar(eff_counts, title="功效关键词热度 (按销量)")
            st.plotly_chart(fig_eff, use_container_width=True)
            
        st.info("👉 **决策建议**：观察左图，判断是‘卷浓度’（如 nHAp）还是‘卷概念’。如果‘Sensitive’销量巨大，说明温和体验是刚需。")

    # 3. 价格带 & 价值锚点 (Price Architecture)
    with tabs[2]:
        st.subheader("💰 价格带 & 价值锚点")
        # 价格分桶
        data['Price_Range'] = pd.cut(data['clean_price'], bins=[0,10,15,20,30,50,100], labels=['<$10','$10-15','$15-20','$20-30','$30-50','>$50'])
        
        c1, c2 = st.columns(2)
        with c1:
            price_dist = data.groupby('Price_Range')['clean_sales'].sum().reset_index()
            fig_price = px.bar(price_dist, x='Price_Range', y='clean_sales', title="各价格带销量分布")
            st.plotly_chart(fig_price, use_container_width=True)
        with c2:
            # 散点图：价格 vs 销量
            fig_scat = px.scatter(data, x='clean_price', y='clean_sales', color='Tech_Tag', size='clean_reviews', hover_name='Title_Str', title="价格 vs 销量 (颜色=技术路线)")
            st.plotly_chart(fig_scat, use_container_width=True)
            
        avg_p = data['clean_price'].mean()
        st.info(f"👉 **决策建议**：市场平均售价 ${avg_p:.2f}。如果你的目标定价高于此，必须有强‘技术叙事’（如右图彩色点所示的特殊成分）来支撑溢价。")

    # 4. 品牌定位 (Brand Positioning)
    with tabs[3]:
        st.subheader("🏢 品牌定位与背书")
        if col_map['brand']:
            brand_stats = data.groupby(col_map['brand']).agg({
                'clean_price': 'mean',
                'clean_sales': 'sum',
                'clean_rating': 'mean'
            }).reset_index()
            # 过滤掉小品牌
            brand_stats = brand_stats[brand_stats['clean_sales'] > data['clean_sales'].median()]
            
            fig_pos = px.scatter(brand_stats, x='clean_price', y='clean_rating', size='clean_sales', text=col_map['brand'],
                                 title="品牌定位地图 (X=均价, Y=评分, Size=销量)", labels={'clean_price':'品牌均价', 'clean_rating':'平均评分'})
            st.plotly_chart(fig_pos, use_container_width=True)
            st.info("👉 **决策建议**：寻找‘高价且高分’的区域（右上方），分析他们的卖点是医疗背书还是包装质感。避开‘低价低分’的红海区。")
        else:
            st.warning("缺少品牌列，无法分析。")

    # 5. 包装物流 (Packaging & Logistics)
    with tabs[4]:
        st.subheader("📦 包装体积 & FBA")
        # 尝试清洗重量/尺寸
        if col_map['weight']:
            # 简单清洗逻辑：提取数字
            data['clean_weight'] = data[col_map['weight']].astype(str).apply(lambda x: clean_numeric(x))
            
            fig_weight = px.box(data, y='clean_weight', title="产品重量分布 (lb/g 混合单位，需人工校验)")
            st.plotly_chart(fig_weight, use_container_width=True)
            st.info("👉 **决策建议**：检查中位数重量。如果大部分竞品很轻，但你设计了沉重的玻璃瓶，FBA 物流成本将吃掉你的利润。")
        else:
            st.warning("⚠️ 数据中未找到[重量/尺寸]列，无法评估 FBA 风险。建议在 Excel 中补充 'Item Weight' 列。")

    # 6. 内容表达 (Messaging)
    with tabs[5]:
        st.subheader("📝 内容表达与卖点密度")
        data['Title_Len'] = data['Title_Str'].apply(len)
        
        c1, c2 = st.columns(2)
        with c1:
            fig_len = px.scatter(data, x='Title_Len', y='clean_sales', title="标题长度 vs 销量")
            st.plotly_chart(fig_len, use_container_width=True)
        with c2:
            st.markdown("**高频卖点词云 (Top Keywords)**")
            # 简单词频
            all_text = " ".join(data['Title_Str'].tolist()).lower()
            words = [w for w in re.split(r'\W+', all_text) if len(w)>3 and w not in ['pack', 'toothpaste', 'with', 'for']]
            word_series = pd.Series(words).value_counts().head(20)
            st.bar_chart(word_series)
            
        st.info("👉 **决策建议**：如果长标题销量更好，说明消费者需要详细的技术解释；如果短标题更好，说明品牌认知度高或类目无需教育。")

    # 7. 渠道策略 (Channel)
    with tabs[6]:
        st.subheader("📢 渠道与搜索策略")
        # 假设有搜索排名列
        rank_col = None
        for c in data.columns:
            if '排名' in c or 'Rank' in c:
                rank_col = c
                break
        
        if rank_col:
            data['clean_rank'] = data[rank_col].apply(clean_numeric)
            fig_rank = px.scatter(data[data['clean_rank']>0], x='clean_rank', y='clean_sales', log_x=True, title="搜索排名 vs 销量 (对数坐标)")
            st.plotly_chart(fig_rank, use_container_width=True)
            st.info("👉 **决策建议**：观察曲线陡峭程度。如果排名掉出 Top 20 后销量断崖式下跌，说明该赛道是‘赢家通吃’，需要强广告预算冲排名。")
        else:
            st.warning("未找到[搜索排名]相关列，无法分析流量结构。")

    # 8. 市场成熟度 (Readiness)
    with tabs[7]:
        st.subheader("📊 市场成熟度判断")
        # CR5
        top5_share = 0
        if col_map['brand']:
            top5_share = data.groupby(col_map['brand'])['clean_sales'].sum().sort_values(ascending=False).head(5).sum() / data['clean_sales'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("CR5 (头部集中度)", f"{top5_share:.1%}")
        c2.metric("价格标准差 (价格混乱度)", f"${data['clean_price'].std():.2f}")
        c3.metric("平均评论数 (入场门槛)", f"{data['clean_reviews'].mean():.0f}")
        
        if top5_share > 0.6:
            st.error("🔴 红海预警：头部高度集中，拼执行和资金。")
        elif top5_share < 0.3:
            st.success("🟢 蓝海机会：市场分散，存在品类创新机会。")
        else:
            st.warning("🟡 震荡市场：机会存在，需差异化切入。")

    # 9. 决策清单 (Checklist)
    with tabs[8]:
        st.header("📝 产品开发决策清单 (Auto-Generated)")
        st.markdown("基于上述数据分析，生成的推荐策略：")
        
        # 动态生成策略
        rec_pack = "建议做 Pack-2/3 组合装" if (data[data['Pack_Count']>1]['clean_sales'].sum() / data['clean_sales'].sum()) > 0.3 else "建议以单支装切入"
        rec_price = f"建议定价区间: ${data['clean_price'].quantile(0.4):.2f} - ${data['clean_price'].quantile(0.7):.2f}"
        rec_tech = f"核心成分关注: {tech_counts.iloc[0]['Tech_Tag']}" if not tech_counts.empty else "需挖掘差异化成分"
        
        checklist = f"""
        - **规格策略**: {rec_pack}
        - **定价策略**: {rec_price} (避开 ${data['clean_price'].mean():.2f} 的红海均价)
        - **配方主轴**: {rec_tech}
        - **入场难度**: CR5={top5_share:.1%} ({"高难度" if top5_share>0.5 else "中等难度"})
        - **Review门槛**: 竞品平均评论数 {data['clean_reviews'].mean():.0f} (这是你需要追赶的基准)
        """
        st.markdown(checklist)
        st.button("📄 导出此决策报告 (PDF/Excel)")

# -----------------------------------------------------------------------------
# 4. 主程序入口
# -----------------------------------------------------------------------------
st.sidebar.header("📂 1. 上传文件")
uploaded_file = st.sidebar.file_uploader("支持 Excel (.xlsx) / CSV", type=['xlsx', 'csv'])

if uploaded_file:
    # 智能读取
    try:
        if uploaded_file.name.endswith('.csv'):
            try:
                df_raw = pd.read_csv(uploaded_file, encoding='utf-8')
            except:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, encoding='gbk')
            dfs = {"Sheet1": df_raw}
        else:
            xl = pd.ExcelFile(uploaded_file)
            dfs = {sheet: pd.read_excel(uploaded_file, sheet_name=sheet) for sheet in xl.sheet_names}
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    # Sheet 选择器
    st.sidebar.header("📊 2. 选择数据表")
    sheet_options = list(dfs.keys())
    # 智能预选 US 表 (通常包含产品明细)
    default_idx = 0
    for i, name in enumerate(sheet_options):
        if "US" in name or "Sheet1" in name: default_idx = i
        
    selected_sheet = st.sidebar.selectbox("选择包含【产品明细】的工作表进行深度分析:", sheet_options, index=default_idx)
    df_active = dfs[selected_sheet]
    
    # 字段映射 (Robust Mapping)
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 3. 关键字段确认")
    all_cols = df_active.columns.tolist()
    
    def find_col(kws):
        for c in all_cols:
            for k in kws:
                if k.lower() in str(c).lower().replace(" ", ""): return c
        return None

    col_map = {
        'title': st.sidebar.selectbox("标题列", [None]+all_cols, index=all_cols.index(find_col(['title','标题','name']))+1 if find_col(['title','标题','name']) else 0),
        'brand': st.sidebar.selectbox("品牌列", [None]+all_cols, index=all_cols.index(find_col(['brand','品牌']))+1 if find_col(['brand','品牌']) else 0),
        'price': st.sidebar.selectbox("价格列", [None]+all_cols, index=all_cols.index(find_col(['price','价格','售价']))+1 if find_col(['price','价格','售价']) else 0),
        'sales': st.sidebar.selectbox("销量列", [None]+all_cols, index=all_cols.index(find_col(['sales','销量']))+1 if find_col(['sales','销量']) else 0),
        'rating': st.sidebar.selectbox("评分列", [None]+all_cols, index=all_cols.index(find_col(['rating','评分','stars']))+1 if find_col(['rating','评分','stars']) else 0),
        'reviews': st.sidebar.selectbox("评论数列", [None]+all_cols, index=all_cols.index(find_col(['review','评论','评价']))+1 if find_col(['review','评论','评价']) else 0),
        'weight': st.sidebar.selectbox("重量列(选填)", [None]+all_cols, index=all_cols.index(find_col(['weight','重量']))+1 if find_col(['weight','重量']) else 0),
    }

    if st.sidebar.button("🚀 开始深度分析"):
        analyze_product_sheet(df_active, col_map)
    else:
        st.info("👈 请确认左侧字段映射无误，点击【开始深度分析】按钮。")
        st.dataframe(df_active.head(3))

else:
    st.info("👋 请先上传数据文件。本系统将帮助你从 0 到 1 完成产品定义。")

