# -*- coding: utf-8 -*-
"""
財務比率分析與診斷儀表板（FinMind 版）
資料來源: FinMind 台股公開資料 API
包含五大類財務比率

執行: streamlit run ratio_dashboard.py
套件: pip install streamlit pandas plotly requests
"""

import os
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="財務比率分析儀表板", layout="centered")

# Token 從環境變數讀取（部署到 Streamlit Cloud 時設定）
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
API_URL = "https://api.finmindtrade.com/api/v4/data"


# ============== 資料抓取 ==============
@st.cache_data(ttl=3600)
def fetch_financial_ratios(stock_code, token):
    """抓取財務比率資料"""
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": stock_code,
        "start_date": "2018-01-01",
        "token": token,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200:
            return None, data.get("msg", "查詢失敗")
        df = pd.DataFrame(data["data"])
        return df, None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600)
def fetch_balance_sheet(stock_code, token):
    """抓取資產負債表"""
    params = {
        "dataset": "TaiwanStockBalanceSheet",
        "data_id": stock_code,
        "start_date": "2018-01-01",
        "token": token,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200:
            return None
        return pd.DataFrame(data["data"])
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_income_statement(stock_code, token):
    """抓取損益表"""
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": stock_code,
        "start_date": "2018-01-01",
        "token": token,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200:
            return None
        return pd.DataFrame(data["data"])
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_valuation(stock_code, token):
    """抓取本益比、殖利率、股價淨值比"""
    params = {
        "dataset": "TaiwanStockPER",
        "data_id": stock_code,
        "start_date": "2024-01-01",
        "token": token,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200:
            return None
        df = pd.DataFrame(data["data"])
        if df.empty:
            return None
        latest = df.iloc[-1]
        return {
            "本益比 PE": latest.get("PER"),
            "股價淨值比 PB": latest.get("PBR"),
            "殖利率(%)": latest.get("DividendYield"),
        }
    except Exception:
        return None


# ============== 計算財務比率 ==============
def calc_ratios_from_finmind(bs_df, is_df):
    """從 FinMind 資料計算五大類財務比率"""
    if bs_df is None or is_df is None:
        return pd.DataFrame()

    # 資產負債表關鍵科目
    bs_items = {
        "流動資產": ["CurrentAssets", "流動資產合計"],
        "流動負債": ["CurrentLiabilities", "流動負債合計"],
        "存貨":     ["Inventories", "存貨"],
        "應收帳款": ["ReceivablesNet", "應收帳款淨額", "應收票據及帳款淨額"],
        "資產總計": ["TotalAssets", "資產總計"],
        "負債總計": ["TotalLiabilities", "負債總計"],
        "股東權益": ["TotalEquity", "權益總計", "股東權益合計"],
    }

    # 損益表關鍵科目
    is_items = {
        "營業收入": ["Revenue", "營業收入合計", "營收"],
        "營業成本": ["CostOfGoodsSold", "營業成本合計"],
        "營業毛利": ["GrossProfit", "營業毛利（毛損）淨額"],
        "稅後淨利": ["NetIncome", "本期淨利（淨損）", "稅後淨利"],
    }

    def get_value(df, year, quarter, keys):
        sub = df[(df["date"].str.startswith(str(year))) &
                 (df["date"].str.contains(f"Q{quarter}" if "Q" in df["date"].iloc[0] else str(year)))]
        if sub.empty:
            sub = df[df["date"].str.startswith(str(year))]
        for key in keys:
            row = sub[sub["type"] == key]
            if not row.empty:
                return row.iloc[-1]["value"]
        return None

    # 按年度整理
    rows = {}
    if "date" in bs_df.columns:
        years = sorted(bs_df["date"].str[:4].unique())
        for year in years:
            bs_y = bs_df[bs_df["date"].str.startswith(year)]
            is_y = is_df[is_df["date"].str.startswith(year)]

            def get_bs(keys):
                for k in keys:
                    r = bs_y[bs_y["type"] == k]
                    if not r.empty:
                        return r.iloc[-1]["value"]
                return None

            def get_is(keys):
                for k in keys:
                    r = is_y[is_y["type"] == k]
                    if not r.empty:
                        return r.iloc[-1]["value"]
                return None

            ca   = get_bs(bs_items["流動資產"])
            cl   = get_bs(bs_items["流動負債"])
            inv  = get_bs(bs_items["存貨"]) or 0
            ar   = get_bs(bs_items["應收帳款"])
            ta   = get_bs(bs_items["資產總計"])
            tl   = get_bs(bs_items["負債總計"])
            eq   = get_bs(bs_items["股東權益"])
            rev  = get_is(is_items["營業收入"])
            cogs = get_is(is_items["營業成本"])
            gp   = get_is(is_items["營業毛利"])
            ni   = get_is(is_items["稅後淨利"])

            def sd(a, b):
                try:
                    if not b or b == 0 or a is None:
                        return None
                    return round(a / b, 4)
                except Exception:
                    return None

            def pp(v):
                return round(v * 100, 2) if v is not None else None

            rows[year] = {
                "流動比率":       sd(ca, cl),
                "速動比率":       sd((ca or 0) - inv, cl),
                "負債比率(%)":    pp(sd(tl, ta)),
                "權益比率(%)":    pp(sd(eq, ta)),
                "應收款項周轉率": sd(rev, ar),
                "存貨周轉率":     sd(cogs, inv) if inv else None,
                "毛利率(%)":      pp(sd(gp, rev)),
                "ROE(%)":         pp(sd(ni, eq)),
                "ROA(%)":         pp(sd(ni, ta)),
                "淨利率(%)":      pp(sd(ni, rev)),
            }

    return pd.DataFrame(rows).T.sort_index()


# ============== 診斷 ==============
def diagnose(latest, val_info):
    msgs = []

    cr = latest.get("流動比率")
    if cr:
        try:
            cr = float(cr)
            if cr >= 2:     msgs.append(f"流動比率 {cr:.2f},短期償債能力充足")
            elif cr >= 1.5: msgs.append(f"流動比率 {cr:.2f},短期償債能力尚可,建議留意流動性")
            elif cr >= 1:   msgs.append(f"流動比率 {cr:.2f},短期償債能力偏弱")
            else:           msgs.append(f"流動比率 {cr:.2f},低於1,短期償債能力不足")
        except Exception:
            pass

    dr = latest.get("負債比率(%)")
    if dr:
        try:
            dr = float(dr)
            if dr <= 40:    msgs.append(f"負債比率 {dr:.1f}%,財務結構穩健")
            elif dr <= 60:  msgs.append(f"負債比率 {dr:.1f}%,財務槓桿中等")
            else:           msgs.append(f"負債比率 {dr:.1f}%,財務槓桿偏高,需留意償債壓力")
        except Exception:
            pass

    roe = latest.get("ROE(%)")
    if roe:
        try:
            roe = float(roe)
            if roe >= 15:   msgs.append(f"ROE {roe:.1f}%,股東權益報酬表現優異")
            elif roe >= 8:  msgs.append(f"ROE {roe:.1f}%,股東權益報酬中等")
            else:           msgs.append(f"ROE {roe:.1f}%,股東權益報酬偏低")
        except Exception:
            pass

    gm = latest.get("毛利率(%)")
    if gm:
        try:
            gm = float(gm)
            if gm >= 40:    msgs.append(f"毛利率 {gm:.1f}%,產品獲利能力強")
            elif gm >= 20:  msgs.append(f"毛利率 {gm:.1f}%,產品獲利能力中等")
            else:           msgs.append(f"毛利率 {gm:.1f}%,毛利偏低,需留意成本控管")
        except Exception:
            pass

    if val_info:
        pe = val_info.get("本益比 PE")
        if pe:
            try:
                pe = float(pe)
                if pe < 15:     msgs.append(f"本益比 {pe:.1f},股價相對便宜")
                elif pe < 25:   msgs.append(f"本益比 {pe:.1f},股價合理")
                else:           msgs.append(f"本益比 {pe:.1f},股價相對偏高")
            except Exception:
                pass

    return msgs


# ============== 主介面 ==============
def show_company(stock_code, token):
    with st.spinner(f"查詢 {stock_code} 中..."):
        bs_df = fetch_balance_sheet(stock_code, token)
        is_df = fetch_income_statement(stock_code, token)
        val_info = fetch_valuation(stock_code, token)

    df = calc_ratios_from_finmind(bs_df, is_df)

    st.subheader(f"{stock_code}")

    if not df.empty:
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
            sub = df[available].applymap(lambda x: str(x) if x is not None else "—")
            st.dataframe(sub, use_container_width=True)

    if val_info:
        st.markdown("*5. 估值指標（當前）*")
        val_row = {k: (str(v) if v is not None else "—") for k, v in val_info.items()}
        st.dataframe(pd.DataFrame([val_row]), use_container_width=True)

    # 診斷
    st.markdown("**最新一期診斷**")
    latest = df.iloc[-1].to_dict() if not df.empty else {}
    msgs = diagnose(latest, val_info)
    if msgs:
        for msg in msgs:
            st.markdown(f"- {msg}")
    else:
        st.write("資料不足，無法進行診斷")

    # 獲利能力趨勢圖
    if not df.empty:
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
    st.caption("輸入台股代號,自動計算五大類財務比率並進行診斷")
    st.info("資料來源: FinMind 台股公開資料。台股代號直接輸入數字,例如 2330")

    token = FINMIND_TOKEN
    if not token:
        token = st.text_input("請輸入 FinMind API Token", type="password")
        if not token:
            st.warning("請輸入 FinMind API Token 才能使用本系統")
            return

    codes_input = st.text_input(
        "輸入台股代號,多檔請用逗號分隔(例如 2330, 2317)",
        value="2330",
    )

    if st.button("開始分析", type="primary"):
        codes = [c.strip() for c in codes_input.split(",") if c.strip()]
        if not codes:
            st.warning("請至少輸入一檔股票代號")
            return
        for code in codes:
            show_company(code, token)
        st.caption("⚠️ 本工具為教學示範用途，不構成投資建議。")


if __name__ == "__main__":
    main()
