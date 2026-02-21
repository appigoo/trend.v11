import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import requests

# --- 1. 頁面配置與 CSS 動畫 (保留閃爍效果) ---
st.set_page_config(page_title="全功能實時監控系統", layout="wide")

st.markdown("""
<style>
@keyframes blink {
    0% { border-color: #444; box-shadow: none; }
    50% { border-color: inherit; box-shadow: 0 0 20px inherit; }
    100% { border-color: #444; box-shadow: none; }
}
.blink-bull { border: 3px solid #00ff00 !important; animation: blink 1s infinite; background-color: rgba(0, 255, 0, 0.05); }
.blink-bear { border: 3px solid #ff4b4b !important; animation: blink 1s infinite; background-color: rgba(255, 75, 75, 0.05); }
</style>
""", unsafe_allow_html=True)

# --- 2. 初始化 Session State (保留冷卻機制) ---
if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

# --- 3. Telegram 通知函式 (保留理由詳列功能) ---
def send_telegram_msg(sym, action, reason, price, p_change, v_ratio):
    try:
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        message = (
            f"🔔 【{action}】: {sym}\n"
            f"價格: {price:.2f} ({p_change:+.2f}%)\n"
            f"量比: {v_ratio:.1f}x\n"
            f"--------------------\n"
            f"📋 交易根據:\n{reason}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.get(url, params={"chat_id": chat_id, "text": message})
    except Exception as e:
        st.error(f"Telegram 失敗: {e}")

# --- 4. 數據獲取與指標計算 (保留所有技術指標) ---
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
        
        # 支撐阻力 (20週期)
        df['Resist'] = df['High'].rolling(window=20).max().shift(1)
        df['Support'] = df['Low'].rolling(window=20).min().shift(1)
        
        return df
    except: return None

# --- 5. 核心信號判定 (整合支撐阻力 + 價量異動 + 趨勢) ---
def get_signal(df, p_limit, v_limit, sym):
    if len(df) < 21: return "⏳ 加載中", "#aaa", "數據不足", ""
    
    last, prev = df.iloc[-1], df.iloc[-2]
    price = float(last['Close'])
    res_val, sup_val = float(last['Resist']), float(last['Support'])
    ema20, ema60, ema200 = float(last['EMA20']), float(last['EMA60']), float(last['EMA200'])
    
    p_change = ((price - float(prev['Close'])) / float(prev['Close'])) * 100
    v_ratio = float(last['Volume']) / float(last['Vol_Avg']) if last['Vol_Avg'] > 0 else 1
    
    # 策略判定
    is_bullish = price > ema200 and ema20 > ema60
    is_bearish = price < ema200 and ema20 < ema60
    
    trigger_alert, action_type, card_style = False, "", ""
    reasons = []

    # 做多：趨勢向上 + 突破阻力 + 爆量
    if is_bullish and price > res_val and v_ratio >= v_limit:
        trigger_alert, action_type, card_style = True, "🚀 阻力突破做多", "blink-bull"
        reasons = [f"✅ 突破 20K 高點 {res_val:.2f}", f"✅ 趨勢多頭 (Price > EMA200)", f"✅ 量能驗證 {v_ratio:.1f}x"]
    
    # 做空：趨勢向下 + 跌破支撐 + 爆量
    elif is_bearish and price < sup_val and v_ratio >= v_limit:
        trigger_alert, action_type, card_style = True, "🔻 支撐跌破做空", "blink-bear"
        reasons = [f"❌ 跌破 20K 低點 {sup_val:.2f}", f"❌ 趨勢空頭 (Price < EMA200)", f"❌ 下殺放量 {v_ratio:.1f}x"]

    # 冷卻機制 (15分鐘)
    if trigger_alert:
        now = time.time()
        if (now - st.session_state.last_alert_time.get(sym, 0)) > 900:
            send_telegram_msg(sym, action_type, "\n".join(reasons), price, p_change, v_ratio)
            st.session_state.last_alert_time[sym] = now

    status, color = ("做多趨勢", "#00ff00") if price > ema200 else ("做空趨勢", "#ff4b4b") if price < ema200 else ("觀望", "#aaa")
    if action_type: status = action_type

    alert_summary = []
    if abs(p_change) >= p_limit: alert_summary.append(f"⚠️ 價變: {p_change:+.2f}%")
    if v_ratio >= v_limit: alert_summary.append(f"🔥 量比: {v_ratio:.1f}x")
    
    return status, color, "<br>".join(alert_summary) if alert_summary else "波動穩定", card_style

# --- 6. 側邊欄 (保留動態控制功能) ---
with st.sidebar:
    st.header("⚙️ 系統參數")
    input_syms = st.text_input("股票代碼 (逗號分隔)", value="NVDA, TSLA, AAPL, BTC-USD").upper()
    symbols = [s.strip() for s in input_syms.split(",") if s.strip()]
    
    c1, c2 = st.columns(2)
    with c1: sel_p = st.selectbox("範圍 (Period)", ["1d", "5d", "1mo"], index=1)
    with c2: sel_i = st.selectbox("週期 (Interval)", ["1m", "5m", "15m", "1h"], index=1)
        
    refresh_rate = st.slider("自動刷新 (秒)", 60, 600, 300)
    st.divider()
    vol_threshold = st.number_input("成交量異常倍數", value=2.0, step=0.5)
    price_threshold = st.number_input("股價單根異動 (%)", value=1.0, step=0.1)

# --- 7. 主界面 (保留即時摘要與30根K線圖表) ---
st.title("🏹 全功能日內趨勢監控大屏")
placeholder = st.empty()

while True:
    all_data = {}
    with placeholder.container():
        st.subheader("🔍 實時異動掃描")
        cols = st.columns(len(symbols)) if symbols else [st.empty()]
        
        for i, sym in enumerate(symbols):
            df = fetch_data(sym, sel_p, sel_i)
            if df is not None:
                all_data[sym] = df
                status, color, alert, card_style = get_signal(df, price_threshold, vol_threshold, sym)
                cols[i].markdown(f"""
                    <div class='{card_style}' style='border:1px solid #444; padding:15px; border-radius:10px; text-align:center;'>
                        <h3 style='margin:0;'>{sym}</h3>
                        <h2 style='color:{color}; margin:10px 0;'>{status}</h2>
                        <p style='font-size:1.3em; margin:0;'><b>{df['Close'].iloc[-1]:.2f}</b></p>
                        <hr style='margin:10px 0; border:0.5px solid #333;'>
                        <p style='font-size:0.85em; color:#ffa500; font-weight:bold;'>{alert}</p>
                    </div>
                """, unsafe_allow_html=True)

        st.divider()

        if all_data:
            tabs = st.tabs(list(all_data.keys()))
            for i, (sym, df) in enumerate(all_data.items()):
                with tabs[i]:
                    plot_df = df.tail(30).copy() # 保留只顯示 30 根的功能
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                    
                    # 圖表內容：K線 + EMA200 + 支撐阻力虛線
                    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA200'], name='EMA200', line=dict(color='red', width=2)), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Resist'], name='阻力線', line=dict(color='rgba(0,255,0,0.3)', dash='dash')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Support'], name='支撐線', line=dict(color='rgba(255,0,0,0.3)', dash='dash')), row=1, col=1)
                    
                    # MACD Hist
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Hist'], name='MACD動能', marker_color='white', opacity=0.4), row=2, col=1)
                    
                    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10))
                    st.plotly_chart(fig, use_container_width=True, key=f"f_{sym}_{time.time()}")

        st.caption(f"📅 最後更新: {datetime.now().strftime('%H:%M:%S')} | 策略：EMA200 趨勢 + 20K 突破 + 價量異動")

    time.sleep(refresh_rate)
