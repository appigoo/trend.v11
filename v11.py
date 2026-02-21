import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 頁面配置 ---
st.set_page_config(page_title="專業日內交易系統", layout="wide")

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 交易參數")
    symbol = st.text_input("股票代碼 (例如: AAPL, TSLA, ^IXIC)", value="AAPL").upper()
    refresh_rate = st.sidebar.slider("自動刷新頻率 (秒)", 60, 600, 300)
    st.divider()
    st.markdown("""
    **均線顏色說明：**
    - 🟡 EMA20 (短期)
    - 🔵 EMA60 (中期)
    - 🔴 EMA200 (長期)
    """)

# --- 核心數據處理 (修正 Multi-Index 報錯) ---
def fetch_and_analyze(symbol):
    try:
        # 1. 抓取數據
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty: return None
        
        # --- 核心修正：處理 yfinance 的多層索引 ---
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 強制轉換為 Series 並移除可能的重複欄位
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 確保 Close 是單一序列 (Series)
        close_price = df['Close'].squeeze()
        if isinstance(close_price, pd.DataFrame):
            close_price = close_price.iloc[:, 0]

        # 2. 計算 EMA 系統
        periods = [5, 10, 20, 30, 60, 200]
        for p in periods:
            df[f'EMA{p}'] = close_price.ewm(span=p, adjust=False).mean()

        # 3. 計算 MACD
        ema12 = close_price.ewm(span=12, adjust=False).mean()
        ema26 = close_price.ewm(span=26, adjust=False).mean()
        df['MACD_12_26_9'] = ema12 - ema26
        df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
        df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']

        # 4. 成交量均線
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        
        return df
    except Exception as e:
        st.error(f"數據加載出錯: {e}")
        return None

def generate_signal(df):
    # 確保取到的是單一數值而非 Series
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 判斷邏輯
    price_above_200 = float(last['Close']) > float(last['EMA200'])
    ema_bullish = float(last['EMA5']) > float(last['EMA10']) > float(last['EMA20'])
    vol_spike = float(last['Volume']) > (float(last['Vol_Avg']) * 1.5)
    macd_cross_up = float(last['MACD_12_26_9']) > float(last['MACDs_12_26_9'])

    if price_above_200 and ema_bullish and macd_cross_up:
        return "🚀 強勢上升趨勢", "【建議：做多】", "回踩 EMA10/20 買入，止損設於 EMA60 下方。", "#00ff00", vol_spike
    elif not price_above_200 and float(last['EMA5']) < float(last['EMA10']) < float(last['EMA20']):
        return "🔻 強勢下跌趨勢", "【建議：放空】", "反彈至 EMA20 附近放空，止損設於前高。", "#ff4b4b", vol_spike
    elif vol_spike and macd_cross_up:
        return "⚠️ 潛在放量築底", "【建議：觀察】", "成交量異常放大且 MACD 金叉，等待站穩 EMA60。", "#ffa500", vol_spike
    else:
        return "⚖️ 盤整 / 方向不明", "【建議：觀望】", "均線糾結中，等待突破 EMA200 方向明確。", "#aaaaaa", vol_spike

# --- UI 渲染 ---
st.title("🕯️ 5分鐘 K線趨勢監控")
placeholder = st.empty()

while True:
    df = fetch_and_analyze(symbol)
    
    if df is not None:
        status, action, strategy, color, vol_spike = generate_signal(df)
        last_price = float(df['Close'].iloc[-1])
        
        with placeholder.container():
            # 1. 指標卡片
            m1, m2, m3 = st.columns([1, 2, 2])
            m1.metric("當前市價", f"{last_price:.2f}")
            m2.markdown(f"### 狀態: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            m3.info(f"建議: {action}\n\n{strategy}")

            if vol_spike:
                st.error("🚨 警告：偵測到成交量異常放大 (Volume Spike)！")

            # 2. Plotly 圖表
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                               vertical_spacing=0.03, row_heights=[0.6, 0.15, 0.25])

            # K線圖
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                        low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA20', line=dict(color='yellow', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA60'], name='EMA60', line=dict(color='cyan', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA200'], name='EMA200', line=dict(color='red', width=2)), row=1, col=1)

            # 成交量
            vol_colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ef5350' for i in range(len(df))]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=vol_colors), row=2, col=1)

            # MACD
            fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="柱狀圖"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="DIF", line=dict(color='#2962FF')), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="DEA", line=dict(color='#FF6D00')), row=3, col=1)

            fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            st.caption(f"📅 數據同步時間: {datetime.now().strftime('%H:%M:%S')} | 代碼: {symbol}")

    time.sleep(refresh_rate)
