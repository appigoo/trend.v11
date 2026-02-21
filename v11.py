import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 頁面配置 ---
st.set_page_config(page_title="專業日內交易員系統", layout="wide")

# --- 標題與說明 ---
st.title("🕯️ 5分鐘 K線趨勢跟隨系統 (Pro)")
st.caption("基於 EMA 系統、MACD 動能與成交量異動分析")

# --- 側邊欄參數 ---
with st.sidebar:
    st.header("⚙️ 交易參數")
    symbol = st.text_input("股票代碼 (例如: AAPL, NVDA, TSLA, ^IXIC)", value="AAPL").upper().strip()
    ma_type = st.selectbox("均線類型", ["EMA", "SMA"], index=0)
    refresh_rate = st.slider("自動刷新頻率 (秒)", 60, 600, 300)
    st.divider()
    st.info("💡 提示：本系統模擬專業交易員邏輯，建議在開盤期間使用。")

# 快取資料（避免頻繁重抓）
@st.cache_data(ttl=refresh_rate - 10, show_spinner=False)
def fetch_and_analyze(symbol):
    try:
        # 抓取數據 (5天內的 5分鐘線)
        df = yf.download(symbol, period="5d", interval="5m", progress=False, prepost=False)
        if df.empty or len(df) < 30:
            return None

        # 計算均線系統
        periods = [5, 10, 20, 30, 60, 200]
        for p in periods:
            if ma_type == "EMA":
                df[f'{ma_type}{p}'] = ta.ema(df['Close'], length=p)
            else:
                df[f'{ma_type}{p}'] = ta.sma(df['Close'], length=p)

        # 額外短均線 (原本寫死 MA5/MA15)
        df['MA5']  = ta.sma(df['Close'], length=5)
        df['MA15'] = ta.sma(df['Close'], length=15)

        # MACD
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is None or macd.empty:
            return None
        df = pd.concat([df, macd.add_prefix('MACD_')], axis=1)

        # 成交量分析
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()

        return df

    except Exception as e:
        st.error(f"資料抓取失敗：{e}")
        return None


def generate_signal(df):
    if df is None or len(df) < 2:
        return "資料不足", "【建議：無法分析】", "", "#aaaaaa", False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # 使用動態均線名稱
    ema5  = last[f'{ma_type}5']
    ema10 = last[f'{ma_type}10']
    ema20 = last[f'{ma_type}20']
    ema200 = last.get(f'{ma_type}200', pd.NA)   # 可能還沒算出來

    # 價格位置
    price_above_200 = last['Close'] > ema200 if pd.notna(ema200) else False
    ema_bullish = ema5 > ema10 > ema20

    # 成交量異動
    vol_spike = last['Volume'] > (last['Vol_Avg'] * 1.5) if pd.notna(last['Vol_Avg']) else False

    # MACD 動能（更穩健的欄位名稱處理）
    macd_line = last.get('MACD_MACD_12_26_9', pd.NA)
    macd_sig  = last.get('MACD_MACDs_12_26_9', pd.NA)
    macd_hist = last.get('MACD_MACDh_12_26_9', pd.NA)

    macd_cross_up = macd_line > macd_sig if pd.notna(macd_line) and pd.notna(macd_sig) else False
    macd_hist_increasing = macd_hist > prev.get('MACD_MACDh_12_26_9', pd.NA) if pd.notna(macd_hist) else False

    # 綜合判斷（邏輯保持原樣）
    if price_above_200 and ema_bullish and macd_cross_up:
        status = "🚀 強勢上升趨勢"
        action = "【建議：做多】"
        strategy = "回踩 EMA10/20 買入，止損設於 EMA60 下方。"
        color = "#00ff00"
    elif not price_above_200 and ema5 < ema10 < ema20 and not macd_cross_up:
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


# ── 主畫面 ────────────────────────────────────────────────

placeholder = st.empty()

# 改用按鈕觸發 + 自動刷新（避免 while True 卡住 Streamlit）
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

# 自動刷新邏輯
now = time.time()
should_refresh = now - st.session_state.last_refresh >= refresh_rate

if st.button("立即刷新", use_container_width=True) or should_refresh:
    st.session_state.last_refresh = now

    with placeholder.container():
        df = fetch_and_analyze(symbol)

        if df is not None:
            status, action, strategy, color, vol_spike = generate_signal(df)
            last_price = df['Close'].iloc[-1]

            # 儀表板
            m1, m2, m3 = st.columns([1, 2, 2])
            m1.metric("當前市價", f"{last_price:.2f}")
            m2.markdown(f"### 狀態: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            m3.warning(f"分析: {action}  \n\n {strategy}")

            if vol_spike:
                st.error("🚨 警告：偵測到成交量異常放大 (Volume Spike)！")

            # 圖表
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

            # K線 + 均線
            fig.add_trace(go.Candlestick(x=df.index,
                                         open=df['Open'], high=df['High'],
                                         low=df['Low'], close=df['Close'],
                                         name="K線"), row=1, col=1)

            for p in [20, 60, 200]:
                col_name = f'{ma_type}{p}'
                if col_name in df.columns and df[col_name].notna().any():
                    fig.add_trace(go.Scatter(x=df.index, y=df[col_name],
                                            name=col_name, line=dict(width=1.2)),
                                 row=1, col=1)

            # 成交量（改用更簡潔寫法）
            fig.add_trace(
                go.Bar(x=df.index, y=df['Volume'],
                       marker_color=['rgba(0,200,0,0.7)' if c >= o else 'rgba(220,50,50,0.7)'
                                     for o, c in zip(df['Open'], df['Close'])],
                       name="成交量"),
                row=2, col=1
            )

            # MACD
            if 'MACD_MACDh_12_26_9' in df.columns:
                fig.add_trace(go.Bar(x=df.index, y=df['MACD_MACDh_12_26_9'],
                                    name="MACD Histogram"), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD_MACD_12_26_9'],
                                        name="MACD", line=dict(color='cyan')), row=3, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD_MACDs_12_26_9'],
                                        name="Signal", line=dict(color='yellow')), row=3, col=1)

            fig.update_layout(height=800, template="plotly_dark",
                              xaxis_rangeslider_visible=False, showlegend=False,
                              margin=dict(l=40, r=40, t=20, b=40))
            st.plotly_chart(fig, use_container_width=True)

            # 最近數據
            with st.expander("查看最近 10 根技術指標"):
                st.dataframe(df.tail(10)[['Close', 'Volume', 'Vol_Avg'] +
                                        [c for c in df.columns if ma_type in c or 'MACD' in c]])

            st.caption(f"📅 最後同步：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 標的：{symbol}")

        else:
            st.warning("無法取得資料，請檢查股票代碼是否正確，或目前是否為非交易時段。")

# 顯示下次更新倒數（可選）
if should_refresh:
    st.rerun()
