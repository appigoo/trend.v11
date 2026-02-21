import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import requests

# --- 1. 頁面配置與 CSS 動畫 ---
st.set_page_config(page_title="專業交易員監控大屏", layout="wide")

st.markdown("""
<style>
@keyframes blink { 0% { border-color: #444; } 50% { border-color: inherit; box-shadow: 0 0 20px inherit; } 100% { border-color: #444; } }
.blink-bull { border: 3px solid #00ff00 !important; animation: blink 1s infinite; background-color: rgba(0, 255, 0, 0.05); }
.blink-bear { border: 3px solid #ff4b4b !important; animation: blink 1s infinite; background-color: rgba(255, 75, 75, 0.05); }
</style>
""", unsafe_allow_html=True)

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

# --- 2. Telegram 通知函式 (新增評分顯示) ---
def send_telegram_msg(sym, action, reason, score_info, price, p_change, v_ratio):
    try:
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        message = (
            f"🔔 【{action}】: {sym}\n"
            f"💰 價格: {price:.2f} ({p_change:+.2f}%)\n"
            f"📊 {score_info}\n"
            f"--------------------\n"
            f"📋 交易根據:\n{reason}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.get(url, params={"chat_id": chat_id, "text": message})
    except Exception as e:
        st.error(f"Telegram 失敗: {e}")

# --- 3. 數據獲取 ---
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
        df['Hist'] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        df['Resist'] = df['High'].rolling(window=20).max().shift(1)
        df['Support'] = df['Low'].rolling(window=20).min().shift(1)
        return df
    except: return None

# --- 4. 核心邏輯：加入量化評分系統 ---
def get_signal(df, p_limit, v_limit, sym):
    if len(df) < 21: return "⏳ 加載中", "#aaa", "數據不足", ""
    
    last, prev = df.iloc[-1], df.iloc[-2]
    price = float(last['Close'])
    res_val, sup_val = float(last['Resist']), float(last['Support'])
    ema20, ema60, ema200 = float(last['EMA20']), float(last['EMA60']), float(last['EMA200'])
    v_ratio = float(last['Volume']) / float(last['Vol_Avg']) if last['Vol_Avg'] > 0 else 1
    p_change = ((price - float(prev['Close'])) / float(prev['Close'])) * 100
    
    # --- 評分邏輯 (Score Calculation) ---
    trend_score = 0  # 趨勢分 (50分滿分)
    if price > ema200: trend_score += 20
    if ema20 > ema60: trend_score += 20
    if price > ema20: trend_score += 10
    if price < ema200: trend_score = (50 - trend_score) # 空頭反向計分
    
    momentum_score = min(50, int((v_ratio / v_limit) * 20) + int(abs(p_change) / p_limit * 10)) # 動能分 (50分滿分)
    total_score = trend_score + momentum_score
    
    score_info = f"📈 趨勢評級: {trend_score}/50 | 🔥 動能強度: {momentum_score}/50\n🎯 綜合信號得分: {total_score} 分"

    trigger_alert, action_type, card_style = False, "", ""
    reasons = []

    # 做多：趨勢與突破共振
    if price > ema200 and price > res_val and v_ratio >= v_limit:
        trigger_alert, action_type, card_style = True, "🚀 強力突破 (做多)", "blink-bull"
        reasons = [f"✅ 突破阻力位 {res_val:.2f}", f"✅ EMA多頭排列", f"✅ 放量倍數 {v_ratio:.1f}x"]
    # 做空
    elif price < ema200 and price < sup_val and v_ratio >= v_limit:
        trigger_alert, action_type, card_style = True, "🔻 強力破位 (做空)", "blink-bear"
        reasons = [f"❌ 跌破支撐位 {sup_val:.2f}", f"❌ EMA空頭排列", f"❌ 放量倍數 {v_ratio:.1f}x"]

    # 冷卻發送
    if trigger_alert:
        now = time.time()
        if (now - st.session_state.last_alert_time.get(sym, 0)) > 900:
            send_telegram_msg(sym, action_type, "\n".join(reasons), score_info, price, p_change, v_ratio)
            st.session_state.last_alert_time[sym] = now

    status = action_type if action_type else ("多頭" if price > ema200 else "空頭")
    color = "#00ff00" if price > ema200 else "#ff4b4b"
    alert_summary = f"得分:{total_score} | 量比:{v_ratio:.1f}x"
    
    return status, color, alert_summary, card_style

# --- 5. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 交易員參數")
    input_syms = st.text_input("監控代碼", value="NVDA, TSLA, AAPL").upper()
    symbols = [s.strip() for s in input_syms.split(",") if s.strip()]
    sel_p = st.selectbox("數據範圍", ["1d", "5d", "1mo"], index=1)
    sel_i = st.selectbox("K線週期", ["1m", "5m", "15m", "1h"], index=1)
    refresh_rate = st.slider("刷新(秒)", 60, 600, 300)
    vol_threshold = st.number_input("量比門檻", value=2.0)
    price_threshold = st.number_input("波幅門檻(%)", value=1.0)

# --- 6. 主介面 ---
st.title("🏹 專業動能突破監控系統")
placeholder = st.empty()

while True:
    all_data = {}
    with placeholder.container():
        cols = st.columns(len(symbols)) if symbols else [st.empty()]
        for i, sym in enumerate(symbols):
            df = fetch_data(sym, sel_p, sel_i)
            if df is not None:
                all_data[sym] = df
                status, color, alert, style = get_signal(df, price_threshold, vol_threshold, sym)
                cols[i].markdown(f"""
                    <div class='{style}' style='border:1px solid #444; padding:15px; border-radius:10px; text-align:center;'>
                        <h3 style='margin:0;'>{sym}</h3>
                        <h2 style='color:{color}; margin:10px 0;'>{status}</h2>
                        <p style='font-size:1.1em; color:#ffa500;'>{alert}</p>
                        <p style='font-size:1.4em; margin:0;'><b>{df['Close'].iloc[-1]:.2f}</b></p>
                    </div>
                """, unsafe_allow_html=True)

        if all_data:
            tabs = st.tabs(list(all_data.keys()))
            for i, (sym, df) in enumerate(all_data.items()):
                with tabs[i]:
                    plot_df = df.tail(30).copy()
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Resist'], name='阻力', line=dict(color='rgba(0,255,0,0.3)', dash='dash')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Support'], name='支撐', line=dict(color='rgba(255,0,0,0.3)', dash='dash')), row=1, col=1)
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量'), row=2, col=1)
                    fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"{sym}_{time.time()}")
    time.sleep(refresh_rate)
