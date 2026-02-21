import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- 核心邏輯優化 ---
@st.cache_data(ttl=60) # 增加緩存，避免短時間內重複請求導致被 Yahoo 封鎖
def fetch_and_analyze(symbol):
    try:
        # 下載數據，並處理可能的 Multi-index 問題
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty: return None
        
        # 如果是多個股票或新版 yfinance，處理 Column
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 清洗數據：確保沒有 NaN 影響計算
        df = df.ffill().dropna()

        # 計算指標
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA60'] = ta.ema(df['Close'], length=60)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        
        # MACD
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        
        # ATR (用於設定動態止損)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        return df
    except Exception as e:
        st.error(f"數據獲取失敗: {e}")
        return None

# --- UI 改進：自動刷新機制 ---
# 使用 Streamlit 內建 fragment 或簡單的 experimental_rerun 邏輯
if st.sidebar.button("立即刷新數據"):
    st.rerun()

# 建議增加一個「止損/止盈計算法」在 generate_signal 中
# 例如：止損 = last['Close'] - (last['ATR'] * 2)
