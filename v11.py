import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import numpy as np

# ==================== 快取與參數 ====================
@st.cache_data(ttl=60)   # 至少快取 60 秒
def get_data(symbol):
    try:
        df = yf.download(
            symbol, period="5d", interval="5m",
            progress=False, auto_adjust=True, repair=True
        )
        if df.empty:
            return None

        # 計算指標（只算需要的）
        df['EMA5']   = ta.ema(df['Close'],  5)
        df['EMA10']  = ta.ema(df['Close'], 10)
        df['EMA20']  = ta.ema(df['Close'], 20)
        df['EMA60']  = ta.ema(df['Close'], 60)
        df['EMA200'] = ta.ema(df['Close'], 200)

        df['MA5']  = ta.sma(df['Close'], 5)
        df['MA15'] = ta.sma(df['Close'], 15)

        macd = ta.macd(df['Close'], 12, 26, 9)
        df = df.join(macd)

        df['Vol_MA20'] = df['Volume'].rolling(20).mean()

        return df
    except:
        return None


# ==================== 主程式 ====================
st.set_page_config(page_title="5分鐘趨勢跟隨系統", layout="wide")

symbol = st.sidebar.text_input("股票代碼", "AAPL").strip().upper()
refresh_sec = st.sidebar.slider("刷新間隔", 30, 600, 180, step=30)

if not symbol:
    st.stop()

df = get_data(symbol)

if df is None or len(df) < 60:
    st.error(f"無法取得 {symbol} 的資料，或資料量不足")
    st.stop()

# ── 產生訊號 ──
last = df.iloc[-1]
prev = df.iloc[-2]

# 這裡可以把你的判斷邏輯重新整理優先順序
# 例如：先判斷是否有爆量，再判斷趨勢排列，再判斷 MACD...

# ── 畫圖 ──
# ... 圖表產生邏輯保持類似，但建議把 vol_colors 改成 np.where

# ── 自動更新控制 ──
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()

delta = (datetime.now() - st.session_state.last_refresh).total_seconds()

if delta >= refresh_sec:
    st.session_state.last_refresh = datetime.now()
    st.rerun()

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
