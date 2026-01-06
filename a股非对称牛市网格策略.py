import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 基础配置与视觉样式 ---
st.set_page_config(page_title="RJ 量化回测系统", layout="wide")

# 居中对齐自定义 CSS (针对表格标题等)
st.markdown("""
    <style>
    .reportview-container .main .block-container{ text-align: center; }
    div.stButton > button:first-child { margin: 0 auto; display: block; }
    [data-testid="stMetricValue"] { text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 股票代码库 (简单映射，方便查询) ---
STOCK_DICT = {
    "沪深300ETF": "510300.SS",
    "贵州茅台": "600519.SS",
    "宁德时代": "300750.SZ",
    "招商银行": "600036.SS",
    "中国平安": "601318.SS",
    "五粮液": "000858.SZ",
    "中芯国际": "688981.SS",
    "比亚迪": "002594.SZ",
    "东方财富": "300059.SZ",
    "上证指数": "000001.SS"
}

# --- 3. 侧边栏交互设置 ---
st.sidebar.header("🛠 策略设置中心")
st.sidebar.write(f"作者: **RJ**")

# 公司名查询功能
search_query = st.sidebar.text_input("🔍 输入公司名查询 (如: 茅台)", "")
auto_code = ""
if search_query:
    matches = [v for k, v in STOCK_DICT.items() if search_query in k]
    if matches:
        auto_code = matches[0]
        st.sidebar.success(f"匹配到代码: {auto_code}")
    else:
        st.sidebar.warning("未在常用库找到，请手动输入代码")

# 标的代码输入
ticker_input = st.sidebar.text_input(
    "输入标的代码 (需带 .SS 或 .SZ)", 
    value=auto_code if auto_code else "510300.SS"
)

st.sidebar.divider()

# 呈现模式选择
view_mode = st.sidebar.radio(
    "选择呈现模式",
    ("结构化对比 (三段牛市)", "历史全景回测 (2015-至今)")
)

st.sidebar.divider()
buy_pct = st.sidebar.slider("跌多少买入 (%)", 0.1, 5.0, 1.0, 0.1)
sell_pct = st.sidebar.slider("涨多少卖出 (%)", 0.1, 5.0, 1.5, 0.1)
trade_amt = st.sidebar.number_input("单笔金额 (元)", value=1000)

# --- 4. 核心回测引擎 ---
@st.cache_data
def get_stock_data(ticker, start, end):
    try:
        data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except:
        return pd.DataFrame()

def run_strategy_logic(df, b_pct, s_pct, amt):
    prices = df['Close'].astype(float).values
    changes = np.insert(np.diff(prices) / prices[:-1], 0, 0)
    cash, shares = 0, 0.0
    b_cnt, s_cnt = 0, 0
    history = []
    
    for p, c in zip(prices, changes):
        if c <= -b_pct/100:
            shares += amt / p
            cash -= amt
            b_cnt += 1
        elif c >= s_pct/100 and shares > 0:
            val = min(amt, shares * p)
            shares -= val / p
            cash += val
            s_cnt += 1
        history.append(shares * p + cash)
    
    # 指标计算
    h_arr = np.array(history)
    win_rate = (np.diff(h_arr) > 0).mean() if len(h_arr) > 1 else 0
    total_inv = b_cnt * amt
    cum_ret = (h_arr[-1] / total_inv - 1) if total_inv > 0 else 0
    peak = np.maximum.accumulate(h_arr)
    mdd = np.nanmin((h_arr - peak) / peak) if peak.any() else 0
    
    return history, df.index, b_cnt, s_cnt, cum_ret, mdd, win_rate, shares * prices[-1]

# --- 5. 页面主视图 ---
st.title(f"🚀 {ticker_input} 非对称网格策略分析")

results_list = []

# 定义回测区间
if view_mode == "结构化对比 (三段牛市)":
    periods = [
        ("2016-01-01", "2017-12-31", "2016-2017 蓝筹牛"),
        ("2019-01-01", "2021-02-10", "2019-2021 赛道牛"),
        ("2024-09-24", datetime.now().strftime('%Y-%m-%d'), "2024-至今 政策牛")
    ]
    cols = st.columns(3)
else:
    periods = [("2015-01-01", datetime.now().strftime('%Y-%m-%d'), "2015-至今 历史全景")]
    cols = st.columns(1)

for idx, (s, e, label) in enumerate(periods):
    df = get_stock_data(ticker_input, s, e)
    if not df.empty:
        hist, dates, bc, sc, cret, mdd, wr, fmv = run_strategy_logic(df, buy_pct, sell_pct, trade_amt)
        
        # 记录汇总数据
        results_list.append([label, bc, sc, f"{cret:.2%}", f"{mdd:.2%}", f"{wr:.1%}", bc+sc, f"{fmv:,.0f}"])
        
        # 绘图逻辑
        with cols[idx]:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=hist, mode='lines', name='净资产'))
            
            # 修改点：图表文字全部居中
            fig.update_layout(
                title={'text': label, 'y':0.95, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'},
                xaxis_title={'text': "交易日期", 'standoff': 10},
                yaxis_title="账户净资产 (元)",
                template="plotly_white",
                margin=dict(l=40, r=40, t=60, b=40),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

# --- 6. 汇总表格展示 ---
st.divider()
st.subheader("📊 策略回测数据报表")

# 构建 DataFrame
summary_df = pd.DataFrame(results_list, columns=["区间名称", "买入次数", "卖出次数", "累计收益", "最大回撤", "日胜率", "总次数", "期末持仓市值"])

# 表格样式美化
st.dataframe(
    summary_df.style.set_properties(**{'text-align': 'center'})
                 .set_table_styles([dict(selector='th', props=[('text-align', 'center')])])
                 .highlight_max(subset=['累计收益', '日胜率'], color='#c8e6c9'),
    use_container_width=True,
    hide_index=True
)

st.caption(f"提示：RJ 开发。数据每 24 小时更新一次。")