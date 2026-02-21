import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import requests

# --- 頁面配置 ---
st.set_page_config(page_title="多股實時監控系統", layout="wide")

# --- CSS 閃爍動畫效果 ---
st.markdown("""
<style>
@keyframes blink {
    0% { border-color: #444; box-shadow: none; }
    50% { border-color: #00ff00; box-shadow: 0 0 15px #00ff00; }
    100% { border-color: #444; box-shadow: none; }
}
.blink-border {
    border: 3px solid #00ff00 !important;
    animation: blink 1s infinite;
}
</style>
""", unsafe_allow_html=True)

# --- Telegram 通知函式 ---
def send_telegram_msg(message):
    try:
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={message}"
        requests.get(url)
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")

# --- 側邊欄 --- (保持原有邏輯並包含之前的 Period/Interval)
with st.sidebar:
    st.header("⚙️ 全局參數")
    input_symbols = st.text_input("輸入多個代碼 (逗號分隔)", value="AAPL, NVDA, TSLA, MSFT").upper()
    symbols = [s.strip() for s in input_symbols.split(",") if s.strip()]
    
    col1, col2 = st.columns(2)
    with col1:
        selected_period = st.selectbox("數據範圍", options=["1d", "5d", "1mo", "1y"], index=1)
    with col2:
        selected_interval = st.selectbox("K線週期", options=["1m", "5m", "15m", "1d"], index=1)
    
    refresh_rate = st.sidebar.slider("自動刷新頻率 (秒)", 60, 600, 300)
    
    st.divider()
    vol_threshold = st.number_input("成交量異常倍數", value=2.0, step=0.5)
    price_threshold = st.number_input("股價單根異動幅度 (%)", value=1.0, step=0.1)
    
    st.info(f"監測：{len(symbols)} 隻股票 | {selected_interval}")

# --- 數據處理 ---
def fetch_data(symbol, p, i):
    try:
        df = yf.download(symbol, period=p, interval=i, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        close = df['Close'].squeeze()
        df['EMA20'] = close.ewm(span=20, adjust=False).mean()
        df['EMA60'] = close.ewm(span=60, adjust=False).mean()
        df['EMA200'] = close.ewm(span=200, adjust=False).mean()
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['Hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
        
        return df
    except: return None

def get_signal(df, p_limit, v_limit, sym):
    if len(df) < 2: return "⏳", "#aaa", "數據不足", False
    last, prev = df.iloc[-1], df.iloc[-2]
    price = float(last['Close'])
    
    # 趨勢與異動計算
    is_bullish = price > last['EMA200'] and last['EMA20'] > last['EMA60']
    p_change = ((price - float(prev['Close'])) / float(prev['Close'])) * 100
    v_ratio = float(last['Volume']) / float(last['Vol_Avg']) if last['Vol_Avg'] > 0 else 1
    
    # 判斷是否觸發「強烈訊號」: 趨勢做多 + 價漲 + 量爆
    trigger_alert = is_bullish and p_change >= p_limit and v_ratio >= v_limit
    
    status, color = ("🚀 做多", "#00ff00") if is_bullish else ("🔻 做空", "#ff4b4b") if price < last['EMA200'] else ("⚖️ 觀望", "#aaa")
    
    alerts = []
    if abs(p_change) >= p_limit: alerts.append(f"⚠️ 價異: {p_change:+.2f}%")
    if v_ratio >= v_limit: alerts.append(f"🔥 量爆: {v_ratio:.1f}x")
    
    if trigger_alert:
        send_telegram_msg(f"🌟 強烈訊號: {sym}\n價格: {price:.2f}\n變幅: {p_change:+.2f}%\n量比: {v_ratio:.1f}x")
        
    return status, color, "<br>".join(alerts) if alerts else "無異常", trigger_alert

# --- 主界面 ---
st.title("📈 多股日內監控 (含 Telegram 預警)")
dashboard_placeholder = st.empty()

while True:
    all_data = {}
    with dashboard_placeholder.container():
        st.subheader("🔍 實時信號")
        cols = st.columns(len(symbols)) if symbols else [st.empty()]
        
        for i, sym in enumerate(symbols):
            df = fetch_data(sym, selected_period, selected_interval)
            if df is not None:
                all_data[sym] = df
                status, color, alert_msg, is_critical = get_signal(df, price_threshold, vol_threshold, sym)
                # 動態加入 CSS 類名
                card_class = "blink-border" if is_critical else ""
                
                cols[i].markdown(f"""
                    <div class='{card_class}' style='border:1px solid #444; padding:10px; border-radius:5px; text-align:center;'>
                        <h4 style='margin:0;'>{sym}</h4>
                        <h2 style='color:{color}; margin:10px 0;'>{status}</h2>
                        <p style='font-size:1.2em; margin:0;'>{df['Close'].iloc[-1]:.2f}</p>
                        <hr style='margin:10px 0; border:0.5px solid #333;'>
                        <p style='font-size:0.85em; color:#ffa500; font-weight:bold;'>{alert_msg}</p>
                    </div>
                """, unsafe_allow_html=True)
        
        st.divider()

        if all_data:
            tabs = st.tabs(list(all_data.keys()))
            for i, (sym, df) in enumerate(all_data.items()):
                with tabs[i]:
                    plot_df = df.tail(30).copy() # 僅顯示 30 根
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name=sym), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA20'], name='EMA20', line=dict(color='yellow')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA200'], name='EMA200', line=dict(color='red')), row=1, col=1)
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Hist'], name="MACD Hist"), row=2, col=1)
                    fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10))
                    st.plotly_chart(fig, use_container_width=True, key=f"c_{sym}")

    time.sleep(refresh_rate)
