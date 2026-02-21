import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 頁面配置 ---
st.set_page_config(page_title="多股實時監控系統", layout="wide")

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 全局參數")
    # 支援逗號分隔輸入
    input_symbols = st.text_input("輸入多個代碼 (逗號分隔)", value="AAPL, NVDA, TSLA, MSFT").upper()
    symbols = [s.strip() for s in input_symbols.split(",") if s.strip()]
    
    refresh_rate = st.sidebar.slider("自動刷新頻率 (秒)", 60, 600, 300)
    
    st.divider()
    st.info(f"當前監測數：{len(symbols)} 隻股票")

# --- 數據處理函數 (修正 Multi-Index) ---
def fetch_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        # 計算指標
        close = df['Close'].squeeze()
        df['EMA20'] = close.ewm(span=20, adjust=False).mean()
        df['EMA60'] = close.ewm(span=60, adjust=False).mean()
        df['EMA200'] = close.ewm(span=200, adjust=False).mean()
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']
        
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        return df
    except:
        return None

def get_signal(df):
    last = df.iloc[-1]
    price = float(last['Close'])
    ema20, ema60, ema200 = float(last['EMA20']), float(last['EMA60']), float(last['EMA200'])
    
    if price > ema200 and ema20 > ema60:
        return "🚀 做多", "#00ff00"
    elif price < ema200 and ema20 < ema60:
        return "🔻 做空", "#ff4b4b"
    else:
        return "⚖️ 觀望", "#aaaaaa"

# --- 主界面 ---
st.title("📈 多股日內趨勢監控儀表板")

# 建立一個持續更新的區塊
dashboard_placeholder = st.empty()

while True:
    all_data = {}
    
    with dashboard_placeholder.container():
        # 1. 頂部狀態卡片 (快速掃描區)
        st.subheader("🔍 實時信號概覽")
        cols = st.columns(len(symbols))
        
        for i, sym in enumerate(symbols):
            df = fetch_data(sym)
            if df is not None:
                all_data[sym] = df
                status, color = get_signal(df)
                last_price = df['Close'].iloc[-1]
                cols[i].markdown(
                    f"""<div style='border:1px solid #444; padding:10px; border-radius:5px; text-align:center;'>
                        <h4>{sym}</h4>
                        <h2 style='color:{color}; margin:0;'>{status}</h2>
                        <p style='font-size:1.2em;'>{last_price:.2f}</p>
                    </div>""", unsafe_allow_html=True
                )
        
        st.divider()

        # 2. 詳細圖表區 (使用 Tabs 切換)
        if all_data:
            st.subheader("📊 詳細技術分析")
            tabs = st.tabs(list(all_data.keys()))
            for i, (sym, df) in enumerate(all_data.items()):
                with tabs[i]:
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                       vertical_spacing=0.05, row_heights=[0.7, 0.3])
                    
                    # K線
                    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                                low=df['Low'], close=df['Close'], name=sym), row=1, col=1)
                    # 均線
                    fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA20', line=dict(color='yellow')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['EMA200'], name='EMA200', line=dict(color='red')), row=1, col=1)
                    
                    # MACD 柱狀圖
                    fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD Hist"), row=2, col=1)
                    
                    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{sym}")

        st.caption(f"📅 最後更新: {datetime.now().strftime('%H:%M:%S')}")

    time.sleep(refresh_rate)
