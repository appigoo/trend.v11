import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 頁面配置 ---
st.set_page_config(page_title="專業日內交易員系統 (Cloud版)", layout="wide")

# --- 側邊欄參數 ---
with st.sidebar:
    st.header("⚙️ 交易參數")
    symbol = st.text_input("股票代碼 (例如: AAPL, NVDA, TSLA, ^IXIC)", value="TSLA,TSLL,XPEV,NIO").upper()
    refresh_rate = st.slider("自動刷新頻率 (秒)", 60, 600, 300)
    st.divider()
    st.info("💡 提示：本版本已優化，支援 Streamlit Cloud 直接部署。")

# --- 核心邏輯函數 (移除 pandas-ta) ---
def fetch_and_analyze(symbol):
    try:
        # 1. 抓取數據 (5天內的 5分鐘線)
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty: return None
        
        # 處理 Multi-Index (新版 yfinance 常見問題)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 2. 計算 EMA 系統 (使用 pandas 內建 ewm)
        periods = [5, 10, 20, 30, 60, 200]
        for p in periods:
            df[f'EMA{p}'] = df['Close'].ewm(span=p, adjust=False).mean()
            
        # 3. 計算 MACD (12, 26, 9)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_12_26_9'] = ema12 - ema26
        df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
        df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
        
        # 4. 成交量分析 (最近 20 根均量)
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        
        return df
    except Exception as e:
        st.error(f"數據加載出錯: {e}")
        return None

def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 判斷邏輯 ---
    price_above_200 = last['Close'] > last['EMA200']
    ema_bullish = last['EMA5'] > last['EMA10'] > last['EMA20']
    vol_spike = last['Volume'] > (last['Vol_Avg'] * 1.5)
    macd_cross_up = last['MACD_12_26_9'] > last['MACDs_12_26_9']

    # --- 綜合建議邏輯 ---
    if price_above_200 and ema_bullish and macd_cross_up:
        status, action, color = "🚀 強勢上升趨勢", "【建議：做多】", "#00ff00"
        strategy = "回踩 EMA10/20 買入，止損設於 EMA60 下方。"
    elif not price_above_200 and last['EMA5'] < last['EMA10'] < last['EMA20'] and not macd_cross_up:
        status, action, color = "🔻 強勢下跌趨勢", "【建議：放空】", "#ff4b4b"
        strategy = "反彈至 EMA20 附近放空，止損設於前高。"
    elif vol_spike and macd_cross_up:
        status, action, color = "⚠️ 潛在放量築底", "【建議：觀察】", "#ffa500"
        strategy = "成交量異常放大且 MACD 金叉，等待站穩 EMA60 後進場。"
    else:
        status, action, color = "⚖️ 盤整 / 方向不明", "【建議：觀望】", "#aaaaaa"
        strategy = "均線糾結中，建議等待突破方向明確後再動手。"
        
    return status, action, strategy, color, vol_spike

# --- UI 渲染主體 ---
st.title("🚨 5分鐘 K線趨勢系統 (Lite)")

placeholder = st.empty()

# 為了在 Streamlit 中實現自動刷新而不導致死循環報錯，建議使用 st.rerun
while True:
    df = fetch_and_analyze(symbol)
    
    if df is not None:
        status, action, strategy, color, vol_spike = generate_signal(df)
        last_price = float(df['Close'].iloc[-1])
        
        with placeholder.container():
            # 1. 儀表板
            m1, m2, m3 = st.columns([1, 2, 2])
            m1.metric("當前市價", f"{last_price:.2f}")
            m2.markdown(f"### 狀態: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            m3.info(f"建議: {action} \n\n策略: {strategy}")

            if vol_spike:
                st.warning("🚨 偵測到成交量異常放大 (Volume Spike)！")

            # 2. 繪製圖表
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                               vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

            # 主圖：K線與核心均線
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                        low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
            
            # 只顯示關鍵均線避免畫面太亂
            for p, c in zip([20, 60, 200], ['yellow', 'cyan', 'red']):
                fig.add_trace(go.Scatter(x=df.index, y=df[f'EMA{p}'], name=f'EMA{p}', line=dict(color=c, width=1.5)), row=1, col=1)

            # 成交量
            vol_colors = ['#26a69a' if df['Close'][i] >= df['Open'][i] else '#ef5350' for i in range(len(df))]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=vol_colors), row=2, col=1)

            # MACD
            fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="DIF", line=dict(color='#2962FF')), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="DEA", line=dict(color='#FF6D00')), row=3, col=1)

            fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False,
                             margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.caption(f"📅 最後同步: {datetime.now().strftime('%H:%M:%S')} | 標的：{symbol} | 頻率：{refresh_rate}s")

    time.sleep(refresh_rate)
