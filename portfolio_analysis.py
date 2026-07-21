# -*- coding: utf-8 -*-
"""
系統二: 投資組合分析與績效評估工具
對應課程: 第7-9週(報酬與風險、投資組合管理)
功能: 輸入多檔台股 → 計算個股報酬率/標準差/Sharpe Ratio
     → Markowitz 效率前緣模擬 → 視覺化風險報酬曲線

執行: streamlit run portfolio_analysis.py
套件: pip install streamlit yfinance pandas numpy plotly scipy
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="投資組合分析工具", layout="wide")

RISK_FREE_RATE = 0.02  # 無風險利率(年化),可依台灣定存利率調整


# ============== 資料抓取 ==============
@st.cache_data(ttl=3600)
def fetch_prices(codes, period="2y"):
    """抓取多檔股票的每日收盤價"""
    raw = yf.download(codes, period=period, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]]
        prices.columns = codes
    prices = prices.dropna(how="all")
    return prices


# ============== 績效計算 ==============
def calc_stats(prices):
    """計算年化報酬率、標準差、Sharpe Ratio"""
    daily_ret = prices.pct_change().dropna()
    annual_ret = daily_ret.mean() * 252
    annual_std = daily_ret.std() * np.sqrt(252)
    sharpe = (annual_ret - RISK_FREE_RATE) / annual_std
    return annual_ret, annual_std, sharpe, daily_ret


def simulate_portfolios(daily_ret, n_sim=3000):
    """蒙地卡羅模擬隨機投資組合,計算效率前緣"""
    n_assets = daily_ret.shape[1]
    results = []

    for _ in range(n_sim):
        w = np.random.dirichlet(np.ones(n_assets))
        port_ret = (daily_ret.mean() @ w) * 252
        port_std = np.sqrt(w @ (daily_ret.cov() * 252) @ w)
        port_sharpe = (port_ret - RISK_FREE_RATE) / port_std
        results.append({
            "報酬率(%)": port_ret * 100,
            "風險(%)": port_std * 100,
            "Sharpe": port_sharpe,
            "weights": w,
        })

    return pd.DataFrame(results)


def best_portfolio(sim_df, daily_ret):
    """找出最大 Sharpe Ratio 組合"""
    idx = sim_df["Sharpe"].idxmax()
    best = sim_df.iloc[idx]
    return best


# ============== 介面 ==============
def main():
    st.title("📊 投資組合分析與績效評估工具")
    st.caption("輸入多檔台股 → 計算報酬/風險/Sharpe Ratio → 效率前緣視覺化")
    st.info("資料來源: Yahoo Finance 公開股價(有約 15 分鐘延遲)。台股代號需加 .TW(上市)或 .TWO(上櫃)")

    # 輸入區
    st.subheader("設定分析條件")
    col1, col2 = st.columns([2, 1])
    with col1:
        codes_input = st.text_input(
            "輸入台股代號(至少2檔,逗號分隔)",
            value="2330.TW, 2317.TW, 2412.TW, 0050.TW",
        )
    with col2:
        period = st.selectbox("歷史資料期間", ["1y", "2y", "3y", "5y"], index=1)

    n_sim = st.slider("效率前緣模擬次數(越多越精確,越慢)", 1000, 5000, 2000, 500)

    if st.button("開始分析", type="primary"):
        codes = [c.strip() for c in codes_input.split(",") if c.strip()]
        if len(codes) < 2:
            st.warning("請至少輸入 2 檔股票")
            return

        with st.spinner("抓取股價資料中..."):
            try:
                prices = fetch_prices(codes, period)
            except Exception as e:
                st.error(f"資料抓取失敗: {e}")
                return

        valid_codes = [c for c in codes if c in prices.columns and prices[c].notna().sum() > 10]
        if len(valid_codes) < 2:
            st.error("有效資料不足,請確認代號格式或改用其他標的")
            return

        prices = prices[valid_codes].fillna(method="ffill").dropna()
        annual_ret, annual_std, sharpe, daily_ret = calc_stats(prices)

        # ---- 個股統計 ----
        st.divider()
        st.subheader("個股績效統計")
        stats_df = pd.DataFrame({
            "年化報酬率(%)": (annual_ret * 100).round(2),
            "年化標準差/風險(%)": (annual_std * 100).round(2),
            "Sharpe Ratio": sharpe.round(3),
        })
        st.dataframe(stats_df, use_container_width=True)

        # ---- 個股報酬率走勢 ----
        st.subheader("累積報酬率走勢")
        cum_ret = (1 + prices.pct_change().dropna()).cumprod() - 1
        fig1 = go.Figure()
        for code in valid_codes:
            fig1.add_trace(go.Scatter(
                x=cum_ret.index, y=cum_ret[code] * 100,
                mode="lines", name=code
            ))
        fig1.update_layout(yaxis_title="累積報酬率 (%)", xaxis_title="日期",
                           legend_title="標的")
        st.plotly_chart(fig1, use_container_width=True)

        # ---- 效率前緣 ----
        st.subheader("Markowitz 效率前緣(蒙地卡羅模擬)")
        with st.spinner(f"模擬 {n_sim} 個隨機組合中..."):
            sim_df = simulate_portfolios(daily_ret[valid_codes], n_sim)
            best = best_portfolio(sim_df, daily_ret)

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=sim_df["風險(%)"], y=sim_df["報酬率(%)"],
            mode="markers",
            marker=dict(color=sim_df["Sharpe"], colorscale="Viridis",
                        size=4, colorbar=dict(title="Sharpe")),
            name="隨機組合",
            hovertemplate="風險: %{x:.2f}%<br>報酬: %{y:.2f}%<extra></extra>"
        ))
        fig2.add_trace(go.Scatter(
            x=[best["風險(%)"]],
            y=[best["報酬率(%)"]],
            mode="markers+text",
            marker=dict(color="red", size=14, symbol="star"),
            text=["最佳 Sharpe"],
            textposition="top center",
            name=f"最大 Sharpe({best['Sharpe']:.2f})"
        ))
        fig2.update_layout(
            xaxis_title="年化風險/標準差 (%)",
            yaxis_title="年化報酬率 (%)",
            title="效率前緣: 每個點代表一種資產配置比例"
        )
        st.plotly_chart(fig2, use_container_width=True)

        # ---- 最佳組合配置 ----
        st.subheader("最大 Sharpe Ratio 最佳配置建議")
        weights = best["weights"]
        alloc_df = pd.DataFrame({
            "股票": valid_codes,
            "建議比重(%)": (weights * 100).round(2)
        }).sort_values("建議比重(%)", ascending=False)
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.dataframe(alloc_df, use_container_width=True)
            st.metric("組合年化報酬率", f"{best['報酬率(%)']:.2f}%")
            st.metric("組合年化風險", f"{best['風險(%)']:.2f}%")
            st.metric("Sharpe Ratio", f"{best['Sharpe']:.3f}")
        with col_b:
            fig3 = go.Figure(go.Pie(
                labels=alloc_df["股票"],
                values=alloc_df["建議比重(%)"],
                hole=0.4
            ))
            fig3.update_layout(title="最佳配置比重")
            st.plotly_chart(fig3, use_container_width=True)

        st.caption(
            "⚠️ 本工具為教學示範用途，效率前緣結果基於歷史數據，不構成投資建議。"
            f"無風險利率設定: {RISK_FREE_RATE*100}%"
        )


if __name__ == "__main__":
    main()
