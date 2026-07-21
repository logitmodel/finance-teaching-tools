# -*- coding: utf-8 -*-
"""
系統三: 股利政策模擬與股價反應分析系統
對應課程: 第10-14週(公司理財、股利政策)
功能: 輸入股票代號與股利宣告日期 → 抓取前後股價 → 計算異常報酬(AR)
     → 視覺化股利信號效果(簡化版事件研究法)

執行: streamlit run dividend_event_study.py
套件: pip install streamlit yfinance pandas numpy plotly
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="股利政策與股價反應分析", layout="wide")


# ============== 資料抓取與計算 ==============
@st.cache_data(ttl=3600)
def fetch_event_data(stock_code, market_code, event_date_str, pre_days=30, post_days=30):
    """
    抓取事件窗口內的股票與市場指數資料
    stock_code: 個股代號(如 2330.TW)
    market_code: 市場指數代號(如 ^TWII 台灣加權指數)
    event_date_str: 股利宣告日期 YYYY-MM-DD
    pre_days / post_days: 事件前後各幾天
    """
    event_date = pd.Timestamp(event_date_str)
    start = event_date - timedelta(days=pre_days + 15)
    end = event_date + timedelta(days=post_days + 15)

    stock = yf.download(stock_code, start=start, end=end,
                        auto_adjust=True, progress=False)["Close"]
    market = yf.download(market_code, start=start, end=end,
                         auto_adjust=True, progress=False)["Close"]

    if isinstance(stock, pd.DataFrame):
        stock = stock.squeeze()
    if isinstance(market, pd.DataFrame):
        market = market.squeeze()

    df = pd.DataFrame({"stock": stock, "market": market}).dropna()
    return df, event_date


def calc_abnormal_return(df, event_date, pre_days=30, post_days=30):
    """
    簡化版事件研究法:
    1. 用估計期(事件前 30 天之前)以 OLS 估計市場模型 α, β
    2. 事件窗口的異常報酬 AR = 實際報酬 - (α + β × 市場報酬)
    3. 累積異常報酬 CAR = AR 累加
    """
    df = df.copy()
    df["ret_stock"] = df["stock"].pct_change()
    df["ret_market"] = df["market"].pct_change()
    df = df.dropna()

    # 找出事件日在 df 中最近的交易日
    trading_days = df.index
    event_idx = trading_days.searchsorted(event_date)
    if event_idx >= len(trading_days):
        return None, None, None

    event_day = trading_days[event_idx]

    # 估計期: 事件日前 pre_days 個交易日之前的 30 個交易日
    est_end = event_idx - pre_days
    est_start = max(0, est_end - 60)
    est_df = df.iloc[est_start:est_end]

    if len(est_df) < 10:
        return None, None, None

    # OLS 估計市場模型
    x = est_df["ret_market"].values
    y = est_df["ret_stock"].values
    X = np.column_stack([np.ones_like(x), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha, beta_coef = beta

    # 事件窗口
    win_start = max(0, event_idx - pre_days)
    win_end = min(len(df), event_idx + post_days + 1)
    win_df = df.iloc[win_start:win_end].copy()

    win_df["expected_ret"] = alpha + beta_coef * win_df["ret_market"]
    win_df["AR"] = win_df["ret_stock"] - win_df["expected_ret"]
    win_df["CAR"] = win_df["AR"].cumsum()

    # 相對事件日的 t 值
    win_df["t"] = range(-pre_days, len(win_df) - pre_days)
    win_df = win_df[win_df.index >= df.index[win_start]]

    return win_df, event_day, (alpha, beta_coef)


def plot_event_study(win_df, event_day, code):
    """畫 AR 與 CAR 的事件研究圖"""
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=win_df["t"], y=win_df["AR"] * 100,
        name="每日異常報酬 AR(%)",
        marker_color=win_df["AR"].apply(lambda x: "#EF553B" if x < 0 else "#00CC96"),
        opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        x=win_df["t"], y=win_df["CAR"] * 100,
        mode="lines+markers", name="累積異常報酬 CAR(%)",
        line=dict(color="#636EFA", width=2),
        yaxis="y2"
    ))
    fig.add_vline(x=0, line_dash="dash", line_color="gray",
                  annotation_text="股利宣告日", annotation_position="top right")
    fig.update_layout(
        title=f"{code} 股利宣告事件窗口 — 異常報酬分析",
        xaxis_title="相對事件日 (t=0 為宣告日)",
        yaxis_title="每日 AR (%)",
        yaxis2=dict(title="累積 CAR (%)", overlaying="y", side="right"),
        legend=dict(x=0.01, y=0.99),
        hovermode="x unified"
    )
    return fig


def plot_price_around_event(df, event_day, pre_days, post_days, code):
    """畫事件窗口內的原始股價走勢"""
    event_idx = df.index.searchsorted(event_day)
    win_start = max(0, event_idx - pre_days)
    win_end = min(len(df), event_idx + post_days + 1)
    win_df = df.iloc[win_start:win_end]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=win_df.index, y=win_df["stock"],
        mode="lines+markers", name="股價", line=dict(color="#636EFA")
    ))
    fig.add_vline(x=str(event_day.date()), line_dash="dash", line_color="red",
                  annotation_text="股利宣告日")
    fig.update_layout(
        title=f"{code} 事件窗口股價走勢",
        xaxis_title="日期", yaxis_title="收盤價(元)"
    )
    return fig


# ============== 介面 ==============
def main():
    st.title("📈 股利政策模擬與股價反應分析")
    st.caption("輸入股票代號與股利宣告日期 → 自動分析宣告前後的異常報酬(簡化版事件研究法)")
    st.info(
        "這個系統模擬「股利信號理論」:若公司宣告高股利，市場通常有正向反應。"
        "透過事件研究法，你可以『看見』股利宣告對股價的影響。"
    )

    st.subheader("輸入分析參數")
    col1, col2 = st.columns(2)

    with col1:
        stock_code = st.text_input("台股代號", value="2330.TW")
        market_code = st.selectbox(
            "市場基準指數",
            ["^TWII", "0050.TW"],
            format_func=lambda x: "台灣加權指數 (^TWII)" if x == "^TWII" else "元大台灣50 (0050.TW)"
        )

    with col2:
        event_date = st.date_input(
            "股利宣告日期",
            value=datetime(2024, 3, 15),
            min_value=datetime(2015, 1, 1),
            max_value=datetime.today()
        )
        pre_days = st.slider("事件前觀察天數", 5, 60, 20)
        post_days = st.slider("事件後觀察天數", 5, 60, 20)

    # 教學說明
    with st.expander("📚 什麼是事件研究法? (教學說明)"):
        st.markdown("""
**事件研究法 (Event Study)** 是財務研究中常用的方法,用來衡量某一特定事件(如股利宣告、併購消息)對股票價格的影響。

**核心概念:**
1. **市場模型估計**: 用事件前的歷史資料估計個股與市場的關係 → `股票報酬 = α + β × 市場報酬`
2. **異常報酬 AR**: 股利宣告後的實際報酬 vs. 市場模型預測報酬的差距
   - `AR = 實際報酬 - (α + β × 市場報酬)`
3. **累積異常報酬 CAR**: 事件窗口內所有 AR 的累加
   - CAR > 0 → 市場對此次股利宣告有正面反應
   - CAR < 0 → 市場有負面反應或訊息早已提前反映

**股利信號理論:** 公司宣告發放(高)股利，向市場傳遞「公司未來獲利看好」的信號，
通常會引發股價上漲，即正的異常報酬。
        """)

    if st.button("開始分析", type="primary"):
        with st.spinner("抓取股價資料並計算異常報酬中..."):
            try:
                df, event_day = fetch_event_data(
                    stock_code, market_code,
                    str(event_date), pre_days, post_days
                )
                if df.empty or len(df) < 20:
                    st.error("資料筆數不足,請確認代號或選擇不同日期")
                    return

                win_df, event_day_actual, params = calc_abnormal_return(
                    df, event_day, pre_days, post_days
                )
                if win_df is None:
                    st.error("計算失敗,可能是該日期附近的交易資料不足,請調整參數後重試")
                    return

            except Exception as e:
                st.error(f"資料抓取或計算失敗: {e}")
                return

        alpha, beta = params
        st.success(f"分析完成 | 市場模型: α={alpha:.4f}, β={beta:.3f} | 事件日: {event_day_actual.date()}")

        # 股價走勢
        st.subheader("事件窗口股價走勢")
        st.plotly_chart(plot_price_around_event(df, event_day_actual, pre_days, post_days, stock_code), use_container_width=True)

        # AR / CAR 圖
        st.subheader("異常報酬分析(AR & CAR)")
        st.plotly_chart(plot_event_study(win_df, event_day_actual, stock_code), use_container_width=True)

        # 數字摘要
        st.subheader("事件窗口統計摘要")
        car_total = win_df["CAR"].iloc[-1] * 100
        ar_event_day = win_df[win_df["t"] == 0]["AR"].values
        ar_day0 = ar_event_day[0] * 100 if len(ar_event_day) > 0 else None

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("宣告日 AR (t=0)", f"{ar_day0:.2f}%" if ar_day0 is not None else "N/A",
                     help="宣告當日的異常報酬")
        col_b.metric("整體窗口 CAR", f"{car_total:.2f}%",
                     delta="正向反應" if car_total > 0 else "負向反應")
        col_c.metric("市場 β 係數", f"{beta:.3f}",
                     help="個股與市場的系統性風險關係,>1 代表較市場波動大")

        # 解讀
        st.subheader("結果解讀")
        if ar_day0 is not None:
            if ar_day0 > 0:
                st.success(f"宣告日當天出現正的異常報酬 (+{ar_day0:.2f}%),符合股利信號理論的預期:市場對這次股利宣告有正面反應。")
            else:
                st.warning(f"宣告日當天出現負的異常報酬 ({ar_day0:.2f}%),可能原因:市場早已提前反映(資訊洩漏)、或市場認為股利低於預期。")
        if car_total > 1:
            st.info(f"事件窗口累積異常報酬 CAR = {car_total:.2f}%,整體呈正面反應。")
        elif car_total < -1:
            st.info(f"事件窗口累積異常報酬 CAR = {car_total:.2f}%,整體呈負面反應,值得進一步探討原因。")

        # 原始數據表
        with st.expander("查看完整數據表"):
            display_df = win_df[["t", "ret_stock", "ret_market", "AR", "CAR"]].copy()
            display_df.columns = ["相對事件日(t)", "個股日報酬", "市場日報酬", "異常報酬(AR)", "累積異常報酬(CAR)"]
            display_df = display_df.applymap(lambda x: f"{x*100:.3f}%" if isinstance(x, float) else x)
            st.dataframe(display_df, use_container_width=True)

        st.caption("⚠️ 本工具為教學示範用途,採簡化版市場模型,不構成投資建議。")


if __name__ == "__main__":
    main()
