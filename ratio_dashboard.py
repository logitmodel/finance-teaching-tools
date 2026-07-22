# -*- coding: utf-8 -*-
"""
財務比率分析與診斷儀表板（加入延遲避免 Rate Limit）
資料來源: Yahoo Finance 公開財報資料
包含五大類財務比率

執行: streamlit run ratio_dashboard.py
套件: pip install streamlit yfinance pandas plotly
"""

import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="財務比率分析儀表板", layout="centered")


def safe_div(a, b):
    try:
        if b in (0, None) or pd.isna(b) or pd.isna(a):
            return None
        return round(a / b, 4)
    except Exception:
        return None


def pct(val):
    return round(val * 100, 2) if val is not None else None


def fetch_data(stock_code):
    """抓取財報資料，加入重試機制與延遲"""
    for attempt in range(3):  # 最多重試3次
        try:
            time.sleep(2)  # 每次請求前等2秒
            ticker = yf.Ticker(stock_code)
            bs = ticker.balance_sheet
            time.sleep(1)
            is_ = ticker.financials
            time.sleep(1)
            info = ticker.info
            return bs, is_, info
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 5  # 第1次等5秒，第2次等10秒
                time.sleep(wait)
            else:
                raise e


def calc_ratios(bs, is_, info):
    periods = [c for c in bs.columns if c in is_.columns]
    rows = {}

    for period in periods:
        b = bs[period]
        i = is_[period]
        year = str(period.year) if hasattr(period, "year") else str(period)

        current_assets = b.get("Current Assets")
        current_liab   = b.get("Current Liabilities")
        inventory      = b.get("Inventory", 0) or 0
        total_assets   = b.get("Total Assets")
        total_liab     = b.get("Total Liabilities Net Minority Interest")
        equity         = b.get("Stockholders Equity")
        receivables    = b.get("Accounts Receivable") or b.get("Net Receivables")
        revenue        = i.get("Total Revenue")
        cogs           = i.get("Cost Of Revenue")
        gross_profit   = i.get("Gross Profit")
        net_income     = i.get("Net Income")

        rows[year] = {
            # 1. 償債能力
            "流動比率":       safe_div(current_assets, current_liab),
            "速動比率":       safe_div((current_assets or 0) - inventory, current_liab),
            # 2. 財務結構
            "負債比率(%)":    pct(safe_div(total_liab, total_assets)),
            "權益比率(%)":    pct(safe_div(equity, total_assets)),
            # 3. 經營能力
            "應收款項周轉率": safe_div(revenue, receivables),
            "存貨周轉率":     safe_div(cogs, inventory) if inventory else None,
            # 4. 獲利能力
            "毛利率(%)":      pct(safe_div(gross_profit, revenue)),
            "ROE(%)":         pct(safe_div(net_income, equity)),
            "ROA(%)":         pct(safe_div(net_income, total_assets)),
            "淨利率(%)":      pct(safe_div(net_income, revenue)),
        }

    df = pd.DataFrame(rows).T.sort_index()

    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    val_info = {
        "本益比 PE":     round(pe, 2) if pe else None,
        "股價淨值比 PB": round(pb, 2) if pb else None,
    }

    return df, val_info


def diagnose(latest, val_info):
    msgs = []

    cr = latest.get("流動比率")
    if cr:
        if cr >= 2:     msgs.append(f"流動比率 {cr:.2f},短期償債能力充足")
        elif cr >= 1.5: msgs.append(f"流動比率 {cr:.2f},短期償債能力尚可,建議留意流動性")
        elif cr >= 1:   msgs.append(f"流動比率 {cr:.2f},短期償債能力偏弱,需留意流動性風險")
        else:           msgs.append(f"流動比率 {cr:.2f},低於1,短期償債能力不足")

    dr = latest.get("負債比率(%)")
    if dr:
        if dr <= 40:    msgs.append(f"負債比率 {dr:.1f}%,財務結構穩健")
        elif dr <= 60:  msgs.append(f"負債比率 {dr:.1f}%,財務槓桿中等")
        else:           msgs.append(f"負債比率 {dr:.1f}%,財務槓桿偏高,需留意償債壓力")

    roe = latest.get("ROE(%)")
    if roe:
        if roe >= 15:   msgs.append(f"ROE {roe:.1f}%,股東權益報酬表現優異")
        elif roe >= 8:  msgs.append(f"ROE {roe:.1f}%,股東權益報酬中等")
        else:           msgs.append(f"ROE {roe:.1f}%,股東權益報酬偏低")

    gm = latest.get("毛利率(%)")
    if gm:
        if gm >= 40:    msgs.append(f"毛利率 {gm:.1f}%,產品獲利能力強")
        elif gm >= 20:  msgs.append(f"毛利率 {gm:.1f}%,產品獲利能力中等")
        else:           msgs.append(f"毛利率 {gm:.1f}%,毛利偏低,需留意成本控管")

    pe = val_info.get("本益比 PE")
    if pe:
        if pe < 15:     msgs.append(f"本益比 {pe:.1f},股價相對便宜")
        elif pe < 25:   msgs.append(f"本益比 {pe:.1f},股價合理")
        else:           msgs.append(f"本益比 {pe:.1f},股價相對偏高")

    return msgs


def show_company(code, idx, total):
    st.subheader(f"查詢中... ({idx}/{total})")

    try:
        bs, is_, info = fetch_data(code)
        df, val_info = calc_ratios(bs, is_, info)
    except Exception as e:
        st.error(f"{code} 查詢失敗: {e}\n\n請稍後再試，或減少一次查詢的股票數量。")
        return

    if df.empty:
        st.warning(f"{code} 查無可用財報資料")
        return

    company_name = info.get("longName", code)
    st.subheader(f"{company_name}（{code}）")

    categories = {
        "1. 償債能力": ["流動比率", "速動比率"],
        "2. 財務結構": ["負債比率(%)", "權益比率(%)"],
        "3. 經營能力": ["應收款項周轉率", "存貨周轉率"],
        "4. 獲利能力": ["毛利率(%)", "ROE(%)", "ROA(%)", "淨利率(%)"],
    }

    st.markdown("**財務比率歷史數據**")
    for cat_name, cols in categories.items():
        available = [c for c in cols if c in df.columns]
        if not available:
            continue
        st.markdown(f"*{cat_name}*")
        sub = df[available].copy()
        sub = sub.applymap(lambda x: str(x) if x is not None else "—")
        st.dataframe(sub, use_container_width=True)

    st.markdown("*5. 估值指標（當前）*")
    val_row = {k: (str(v) if v is not None else "—") for k, v in val_info.items()}
    st.dataframe(pd.DataFrame([val_row]), use_container_width=True)

    # 診斷
    latest = df.iloc[-1].to_dict()
    st.markdown("**最新一期診斷**")
    msgs = diagnose(latest, val_info)
    for msg in msgs:
        st.markdown(f"- {msg}")

    # 獲利能力趨勢圖
    profit_cols = [c for c in ["ROE(%)", "ROA(%)", "毛利率(%)", "淨利率(%)"] if c in df.columns]
    if profit_cols:
        st.markdown("**獲利能力趨勢**")
        fig = go.Figure()
        for col in profit_cols:
            vals = pd.to_numeric(df[col], errors="coerce")
            fig.add_trace(go.Scatter(x=df.index, y=vals, mode="lines+markers", name=col))
        fig.update_layout(
            xaxis_title="年度", yaxis_title="百分比 (%)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 償債能力趨勢圖
    liq_cols = [c for c in ["流動比率", "速動比率"] if c in df.columns]
    if liq_cols:
        st.markdown("**償債能力趨勢**")
        fig2 = go.Figure()
        for col in liq_cols:
            vals = pd.to_numeric(df[col], errors="coerce")
            fig2.add_trace(go.Scatter(x=df.index, y=vals, mode="lines+markers", name=col))
        fig2.update_layout(
            xaxis_title="年度", yaxis_title="比率",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()


def main():
    st.title("財務比率分析與診斷儀表板")
    st.caption("輸入台股代號,自動計算流動比率、負債比率、ROE、ROA、淨利率等五大類財務比率")
    st.info("資料來源: Yahoo Finance 公開財報資料。台股代號需加 .TW(上市)或 .TWO(上櫃),例如 2330.TW")
    st.warning("⏱ 為避免查詢被封鎖，每檔股票間會自動等待幾秒，查詢多檔時請耐心等候。建議一次查詢 1-2 檔。")

    codes_input = st.text_input(
        "輸入台股代號,多檔請用逗號分隔(例如 2330.TW, 2317.TW)",
        value="2330.TW",
    )

    if st.button("開始分析", type="primary"):
        codes = [c.strip() for c in codes_input.split(",") if c.strip()]
        if not codes:
            st.warning("請至少輸入一檔股票代號")
            return
        if len(codes) > 3:
            st.warning("建議一次最多查詢 3 檔，避免等待時間過長")
            return
        for idx, code in enumerate(codes, 1):
            show_company(code, idx, len(codes))
        st.caption("⚠️ 本工具為教學示範用途，不構成投資建議。")


if __name__ == "__main__":
    main()
