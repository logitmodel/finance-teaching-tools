# -*- coding: utf-8 -*-
"""
財務比率分析與診斷儀表板（TWSE 公開資料版）
資料來源: 台灣證券交易所 + 櫃買中心公開 API，不需要任何帳號或 API Key

執行: streamlit run ratio_dashboard.py
套件: pip install streamlit pandas plotly requests
"""

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="財務比率分析儀表板", layout="centered")


# ============== 抓取 TWSE 財務資料 ==============
@st.cache_data(ttl=3600)
def fetch_financial_ratios(stock_code):
    """
    從台灣證交所抓取財務比率資料
    使用 TWSE OpenAPI: https://openapi.twse.com.tw/
    """
    url = f"https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        # 篩選指定股票
        df = df[df["Code"] == stock_code].copy()
        return df
    except Exception as e:
        return None


@st.cache_data(ttl=3600)
def fetch_company_info(stock_code):
    """抓取公司基本資料"""
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        df = pd.DataFrame(data)
        row = df[df["公司代號"] == stock_code]
        if not row.empty:
            return row.iloc[0].to_dict()
        return {}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def fetch_twse_financials(stock_code, year, season):
    """
    從 TWSE 抓取特定年季的財務報表
    season: 1=Q1, 2=Q2, 3=Q3, 4=Q4
    """
    url = f"https://mops.twse.com.tw/server-java/t164sb01?step=1&CO_ID={stock_code}&SYEAR={year}&SSEASON={season}&REPORT_ID=C"
    try:
        tables = pd.read_html(url, encoding="utf-8")
        return tables
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_financial_statement(stock_code):
    """
    使用 TWSE OpenAPI 抓取財務摘要
    回傳近幾季的財務數據
    """
    results = {}
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # 決定目前是第幾季
    if current_month <= 3:
        seasons = [(current_year - 1, 3), (current_year - 1, 2),
                   (current_year - 1, 1), (current_year - 2, 4)]
    elif current_month <= 6:
        seasons = [(current_year, 1), (current_year - 1, 4),
                   (current_year - 1, 3), (current_year - 1, 2)]
    elif current_month <= 9:
        seasons = [(current_year, 2), (current_year, 1),
                   (current_year - 1, 4), (current_year - 1, 3)]
    else:
        seasons = [(current_year, 3), (current_year, 2),
                   (current_year, 1), (current_year - 1, 4)]

    for year, season in seasons:
        label = f"{year}Q{season}"
        url = (
            f"https://mops.twse.com.tw/mops/web/ajax_t164sb03"
            f"?encodeURIComponent=1&step=1&firstin=1&off=1"
            f"&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id"
            f"&inpuType=co_id&TYPEK=all&isnew=false"
            f"&co_id={stock_code}&year={year - 1911}&season={season:02d}"
        )
        try:
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            tables = pd.read_html(resp.text, encoding="utf-8")
            if tables:
                results[label] = tables
        except Exception:
            pass

    return results


@st.cache_data(ttl=3600)
def fetch_twse_pe_pb(stock_code):
    """從 TWSE 抓取本益比與股價淨值比"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        df = pd.DataFrame(data)
        row = df[df["Code"] == stock_code]
        if not row.empty:
            r = row.iloc[0]
            return {
                "本益比 PE": r.get("PEratio", "—"),
                "股價淨值比 PB": r.get("PBratio", "—"),
                "殖利率(%)": r.get("DividendYield", "—"),
            }
    except Exception:
        pass
    return {}


@st.cache_data(ttl=3600)
def fetch_twse_ratio_history(stock_code):
    """
    從 TWSE eMPF 抓取財務比率歷史資料
    使用公開財務分析資料
    """
    all_data = []
    current_year = datetime.now().year

    for year in range(current_year - 4, current_year + 1):
        roc_year = year - 1911
        url = (
            f"https://mops.twse.com.tw/mops/web/ajax_t51sb02"
            f"?encodeURIComponent=1&step=1&firstin=1&off=1"
            f"&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id"
            f"&inpuType=co_id&TYPEK=all&isnew=false"
            f"&co_id={stock_code}&year={roc_year}"
        )
        try:
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            tables = pd.read_html(resp.text, encoding="utf-8")
            if tables:
                df = tables[0]
                df["年度"] = year
                all_data.append(df)
        except Exception:
            pass

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_simple_ratios(stock_code):
    """
    用 TWSE OpenAPI 抓取簡化版財務數據
    這個 API 比較穩定，回傳當期財務比率
    """
    # 抓本益比、殖利率、淨值比
    pe_pb = fetch_twse_pe_pb(stock_code)

    # 嘗試從公開資訊觀測站抓財務比率
    ratio_history = {}
    current_year = datetime.now().year

    for year in range(current_year - 4, current_year + 1):
        roc_year = year - 1911
        url = f"https://mops.twse.com.tw/mops/web/ajax_t51sb02?encodeURIComponent=1&step=1&firstin=1&off=1&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id&inpuType=co_id&TYPEK=all&isnew=false&co_id={stock_code}&year={roc_year}"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            tables = pd.read_html(resp.text, encoding="utf-8")
            if tables and len(tables) > 0:
                df = tables[0]
                # 嘗試解析財務比率
                ratio_history[str(year)] = df
        except Exception:
            pass

    return pe_pb, ratio_history


# ============== 備用：用 TWSE OpenAPI 抓股票清單確認代號存在 ==============
@st.cache_data(ttl=86400)
def get_listed_stocks():
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        df = pd.DataFrame(data)
        return df
    except Exception:
        return pd.DataFrame()


# ============== 診斷文字 ==============
def diagnose(ratios_dict):
    msgs = []

    cr = ratios_dict.get("流動比率")
    if cr and cr != "—":
        try:
            cr = float(cr)
            if cr >= 2:      msgs.append(f"流動比率 {cr:.2f},短期償債能力充足")
            elif cr >= 1.5:  msgs.append(f"流動比率 {cr:.2f},短期償債能力尚可,建議留意流動性")
            elif cr >= 1:    msgs.append(f"流動比率 {cr:.2f},短期償債能力偏弱")
            else:            msgs.append(f"流動比率 {cr:.2f},低於1,短期償債能力不足")
        except Exception:
            pass

    dr = ratios_dict.get("負債比率(%)")
    if dr and dr != "—":
        try:
            dr = float(dr)
            if dr <= 40:    msgs.append(f"負債比率 {dr:.1f}%,財務結構穩健")
            elif dr <= 60:  msgs.append(f"負債比率 {dr:.1f}%,財務槓桿中等")
            else:           msgs.append(f"負債比率 {dr:.1f}%,財務槓桿偏高,需留意償債壓力")
        except Exception:
            pass

    roe = ratios_dict.get("ROE(%)")
    if roe and roe != "—":
        try:
            roe = float(roe)
            if roe >= 15:   msgs.append(f"ROE {roe:.1f}%,股東權益報酬表現優異")
            elif roe >= 8:  msgs.append(f"ROE {roe:.1f}%,股東權益報酬中等")
            else:           msgs.append(f"ROE {roe:.1f}%,股東權益報酬偏低")
        except Exception:
            pass

    pe = ratios_dict.get("本益比 PE")
    if pe and pe != "—":
        try:
            pe = float(pe)
            if pe < 15:     msgs.append(f"本益比 {pe:.1f},股價相對便宜")
            elif pe < 25:   msgs.append(f"本益比 {pe:.1f},股價合理")
            else:           msgs.append(f"本益比 {pe:.1f},股價相對偏高")
        except Exception:
            pass

    return msgs


# ============== 主介面 ==============
def show_company(stock_code):
    stock_code = stock_code.strip()

    with st.spinner(f"查詢 {stock_code} 中..."):
        # 確認股票存在
        listed = get_listed_stocks()
        company_name = stock_code
        if not listed.empty and "公司代號" in listed.columns:
            row = listed[listed["公司代號"] == stock_code]
            if not row.empty:
                company_name = row.iloc[0].get("公司簡稱", stock_code)
            else:
                st.warning(f"{stock_code} 在上市股票清單中查無此代號,請確認是否為上市股票")

        # 抓本益比、殖利率、淨值比（當期）
        pe_pb = fetch_twse_pe_pb(stock_code)

        # 抓財務比率歷史
        ratio_df = fetch_twse_ratio_history(stock_code)

    st.subheader(f"{company_name}（{stock_code}）")

    # ---- 估值指標（當期）----
    if pe_pb:
        st.markdown("**5. 估值與市場指標（當期）**")
        val_df = pd.DataFrame([pe_pb])
        st.dataframe(val_df, use_container_width=True)

        # 診斷
        st.markdown("**最新一期診斷**")
        msgs = diagnose(pe_pb)
        if msgs:
            for msg in msgs:
                st.markdown(f"- {msg}")
        else:
            st.write("目前無足夠資料進行診斷")
    else:
        st.warning("當期估值資料查無結果,可能不在交易時段或該股票代號有誤")

    # ---- 歷史財務比率表格 ----
    if not ratio_df.empty:
        st.markdown("**財務比率歷史數據**")
        st.dataframe(ratio_df, use_container_width=True)
    else:
        st.info(
            "歷史財務比率資料來自公開資訊觀測站，部分股票可能需要稍後再試。\n\n"
            "你也可以直接到以下網址查詢完整財務比率：\n"
            f"https://mops.twse.com.tw/mops/web/t51sb02?co_id={stock_code}"
        )
        st.markdown(
            f"[📊 點此查看 {stock_code} 完整財務分析資料（公開資訊觀測站）]"
            f"(https://mops.twse.com.tw/mops/web/t51sb02?co_id={stock_code})"
        )

    st.divider()


def main():
    st.title("財務比率分析與診斷儀表板")
    st.caption("輸入台股代號,自動計算流動比率、負債比率、ROE、ROA、淨利率等五大類財務比率,並進行多公司比較")
    st.info("資料來源：台灣證券交易所公開資料。台股代號格式直接輸入數字即可，例如 2330（不需加 .TW）")

    st.subheader("輸入分析標的")
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
            show_company(code)
        st.caption("⚠️ 本工具為教學示範用途，不構成投資建議。")


if __name__ == "__main__":
    main()
