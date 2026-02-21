import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime

# --- 頁面配置 ---
st.set_page_config(page_title="專業日內交易員系統", layout="wide")

# --- 標題與說明 ---
st.title("🕯️ 5分鐘 K線趨勢跟隨系統 (Pro)")
st.caption("基於 EMA 系統、MACD 動能與成交量異動分析")

# --- 側邊欄參數 ---
with st.sidebar:
    st.header("⚙️ 交易參數")
    symbol = st.sidebar.text_input("股票代碼 (例如: AAPL, NVDA, TSLA, ^IXIC)", value="AAPL").upper()
    ma_type = st.sidebar.selectbox("均線類型", ["EMA", "SMA"], index=0)
    refresh_rate = st.sidebar.slider("自動刷新頻率 (秒)", 60, 600, 300)
    st.divider()
    st.info("💡 提示：本系統模擬專業交易員邏輯，建議在開盤期間使用。")

# --- 核心邏輯函數 ---
def fetch_and_analyze(symbol):
    # 1. 抓取數據 (5天內的 5分鐘線)
    df = yf.download(symbol, period="5d", interval="5m", progress=False)
    if df.empty: return None

    # 2. 計算均線系統 (EMA 5, 10, 20, 30, 60, 200)
    periods = [5, 10, 20, 30, 60, 200]
    for p in periods:
        df[f'EMA{p}'] = ta.ema(df['Close'], length=p)
    
    # 3. 計算 MA 5, 15
    df['MA5'] = ta.sma(df['Close'], length=5)
    df['MA15'] = ta.sma(df['Close'], length=15)

    # 4. 計算 MACD (12, 26, 9)
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    
    # 5. 成交量分析 (最近 20 根均量)
    df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
    
    return df

def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 判斷邏輯 ---
    # A. 價格位置
    price_above_200 = last['Close'] > last['EMA200']
    ema_bullish = last['EMA5'] > last['EMA10'] > last['EMA20']
    
    # B. 成交量異動 (Spike)
    vol_spike = last['Volume'] > (last['Vol_Avg'] * 1.5)
    
    # C. MACD 動能
    macd_cross_up = last['MACD_12_26_9'] > last['MACDs_12_26_9']
    macd_hist_increasing = last['MACDh_12_26_9'] > prev['MACDh_12_26_9']

    # --- 綜合建議 ---
    if price_above_200 and ema_bullish and macd_cross_up:
        status = "🚀 強勢上升趨勢"
        action = "【建議：做多】"
        strategy = "回踩 EMA10/20 買入，止損設於 EMA60 下方。"
        color = "#00ff00"
    elif not price_above_200 and last['EMA5'] < last['EMA10'] < last['EMA20'] and not macd_cross_up:
        status = "🔻 強勢下跌趨勢"
        action = "【建議：放空】"
        strategy = "反彈至 EMA20 附近放空，止損設於上根 K 線高點。"
        color = "#ff4b4b"
    elif vol_spike and macd_cross_up:
        status = "⚠️ 潛在放量築底"
        action = "【建議：觀察】"
        strategy = "成交量異常放大且 MACD 金叉，等待站穩 EMA60 後進場。"
        color = "#ffa500"
    else:
        status = "⚖️ 盤整 / 方向不明"
        action = "【建議：觀望】"
        strategy = "均線糾結中，建議等待突破 EMA200 方向明確後再動手。"
        color = "#aaaaaa"
        
    return status, action, strategy, color, vol_spike

# --- UI 渲染 ---
placeholder = st.empty()

while True:
    df = fetch_and_analyze(symbol)
    
    if df is not None:
        status, action, strategy, color, vol_spike = generate_signal(df)
        last_price = df['Close'].iloc[-1]
        
        with placeholder.container():
            # 1. 儀表板
            m1, m2, m3 = st.columns([1, 2, 2])
            m1.metric("當前市價", f"{last_price:.2f}")
            m2.markdown(f"### 狀態: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            m3.warning(f"分析: {action} \n\n {strategy}")

            if vol_spike:
                st.error("🚨 警告：偵測到成交量異常放大 (Volume Spike)！")

            # 2. 繪製圖表 (K線 + 均線 + 成交量 + MACD)
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                               vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

            # K 線與 EMA
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                        low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
            for p in [20, 60, 200]:
                fig.add_trace(go.Scatter(x=df.index, y=df[f'EMA{p}'], name=f'EMA{p}', line=dict(width=1)), row=1, col=1)

            # 成交量
            vol_colors = ['green' if df['Close'][i] >= df['Open'][i] else 'red' for i in range(len(df))]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=vol_colors), row=2, col=1)

            # MACD
            fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="MACD柱狀圖"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="DIF", line=dict(color='blue')), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="DEA", line=dict(color='orange')), row=3, col=1)

            fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            # 3. 數據表格
            with st.expander("查看技術指標細節"):
                st.dataframe(df.tail(10))

            st.caption(f"📅 最後同步時間: {datetime.now().strftime('%H:%M:%S')} | 標標：{symbol}")

    time.sleep(refresh_rate)
