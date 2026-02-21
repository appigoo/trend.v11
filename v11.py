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
    input_symbols = st.text_input("輸入多個代碼 (逗號分隔)", value="AAPL, NVDA, TSLA, MSFT").upper()
    symbols = [s.strip() for s in input_symbols.split(",") if s.strip()]
    
    # --- 新增：動態時間範圍與頻率 ---
    col1, col2 = st.columns(2)
    with col1:
        selected_period = st.selectbox("數據範圍 (Period)", 
                                    options=["1d", "5d", "1mo", "3mo", "6mo", "1y"], index=1)
    with col2:
        selected_interval = st.selectbox("K線週期 (Interval)", 
                                      options=["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"], index=2)
    
    refresh_rate = st.sidebar.slider("自動刷新頻率 (秒)", 60, 600, 300)
    
    st.divider()
    vol_threshold = st.number_input("成交量異常倍數", value=2.0, step=0.5)
    price_threshold = st.number_input("股價單根異動幅度 (%)", value=1.0, step=0.1)
    
    st.divider()
    st.info(f"當前監測：{len(symbols)} 隻股票 | {selected_interval} 週期")

# --- 數據處理函數 ---
def fetch_data(symbol, p, i): # 增加參數接收
    try:
        # 使用側邊欄傳入的 p(period) 和 i(interval)
        df = yf.download(symbol, period=p, interval=i, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        close = df['Close'].squeeze()
        df['EMA20'] = close.ewm(span=20, adjust=False).mean()
        df['EMA60'] = close.ewm(span=60, adjust=False).mean()
        df['EMA200'] = close.ewm(span=200, adjust=False).mean()
        
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']
        
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        return df
    except:
        return None

def get_signal(df, p_limit, v_limit):
    if len(df) < 2: return "⏳ 載入中", "#aaaaaa", "數據不足"
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    price = float(last['Close'])
    ema20, ema60, ema200 = float(last['EMA20']), float(last['EMA60']), float(last['EMA200'])
    
    if price > ema200 and ema20 > ema60:
        status, color = "🚀 做多", "#00ff00"
    elif price < ema200 and ema20 < ema60:
        status, color = "🔻 做空", "#ff4b4b"
    else:
        status, color = "⚖️ 觀望", "#aaaaaa"
        
    alerts = []
    p_change = ((price - float(prev['Close'])) / float(prev['Close'])) * 100
    v_ratio = float(last['Volume']) / float(last['Vol_Avg']) if last['Vol_Avg'] > 0 else 1
    
    if abs(p_change) >= p_limit:
        alerts.append(f"⚠️ 價異: {p_change:+.2f}%")
    if v_ratio >= v_limit:
        alerts.append(f"🔥 量爆: {v_ratio:.1f}x")
    
    alert_text = "<br>".join(alerts) if alerts else "無異常"
    return status, color, alert_text

# --- 主界面 ---
st.title("📈 多股日內趨勢監控儀表板")
dashboard_placeholder = st.empty()

while True:
    all_data = {}
    with dashboard_placeholder.container():
        st.subheader("🔍 實時信號與異常提醒")
        cols = st.columns(len(symbols)) if symbols else [st.empty()]
        
        for i, sym in enumerate(symbols):
            # 傳遞側邊欄選擇的參數
            df = fetch_data(sym, selected_period, selected_interval)
            if df is not None:
                all_data[sym] = df
                status, color, alert_msg = get_signal(df, price_threshold, vol_threshold)
                last_price = df['Close'].iloc[-1]
                
                cols[i].markdown(
                    f"""<div style='border:1px solid #444; padding:10px; border-radius:5px; text-align:center;'>
                        <h4 style='margin:0;'>{sym}</h4>
                        <h2 style='color:{color}; margin:10px 0;'>{status}</h2>
                        <p style='font-size:1.2em; margin:0;'>{last_price:.2f}</p>
                        <hr style='margin:10px 0; border:0.5px solid #333;'>
                        <p style='font-size:0.85em; color:#ffa500; font-weight:bold;'>{alert_msg}</p>
                    </div>""", unsafe_allow_html=True
                )
        
        st.divider()

        # --- 在詳細圖表區 (Tabs) 的部分進行修改 ---
        if all_data:
            st.subheader("📊 詳細技術分析 (近 30 根 K 線)")
            tabs = st.tabs(list(all_data.keys()))
            for i, (sym, df) in enumerate(all_data.items()):
                with tabs[i]:
                    # --- 核心改動：建立一個僅包含最後 30 根數據的副本用於繪圖 ---
                    plot_df = df.tail(30).copy() 
                    
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                       vertical_spacing=0.05, row_heights=[0.7, 0.3])
                    
                    # K線 (使用 plot_df)
                    fig.add_trace(go.Candlestick(
                        x=plot_df.index, 
                        open=plot_df['Open'], high=plot_df['High'], 
                        low=plot_df['Low'], close=plot_df['Close'], 
                        name=sym), row=1, col=1)
                    
                    # 均線 (使用 plot_df)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA20'], name='EMA20', line=dict(color='yellow')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA200'], name='EMA200', line=dict(color='red')), row=1, col=1)
                    
                    # MACD 柱狀圖 (使用 plot_df)
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Hist'], name="MACD Hist"), row=2, col=1)
                    
                    # 移除範圍滑動條並美化佈局
                    fig.update_layout(
                        height=600, 
                        template="plotly_dark", 
                        xaxis_rangeslider_visible=False,
                        margin=dict(l=10, r=10, t=30, b=10)
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{sym}")

        st.caption(f"📅 最後更新: {datetime.now().strftime('%H:%M:%S')} | 週期: {selected_interval}")

    time.sleep(refresh_rate)
