# -*- coding: utf-8 -*-
import os, requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="財務比率分析儀表板", layout="wide")

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
API_URL = "https://api.finmindtrade.com/api/v4/data"
COLORS = ["#378ADD", "#1D9E75", "#D85A30", "#7F77DD", "#BA7517", "#993556"]


@st.cache_data(ttl=3600)
def fetch_finmind(dataset, stock_code, token, start_date="2018-01-01"):
    params = {"dataset": dataset, "data_id": stock_code,
              "start_date": start_date, "token": token}
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200:
            return None, data.get("msg", "查詢失敗")
        return pd.DataFrame(data["data"]), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600)
def fetch_valuation(stock_code, token):
    df, _ = fetch_finmind("TaiwanStockPER", stock_code, token, "2024-01-01")
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    dividend_yield = (
        latest.get("DividendYield") or
        latest.get("dividend_yield") or
        latest.get("yield") or
        latest.get("Yield")
    )
    return {
        "本益比 PE": latest.get("PER"),
        "股價淨值比 PB": latest.get("PBR"),
        "殖利率(%)": dividend_yield,
        "_per_columns": list(df.columns),
    }


def get_val(df, year, keys):
    sub = df[df["date"].str.startswith(str(year))]
    for key in keys:
        row = sub[sub["type"] == key]
        if not row.empty:
            try:
                return float(row.iloc[-1]["value"])
            except Exception:
                pass
    return None


def calc_ratios(bs_df, is_df):
    if bs_df is None or is_df is None:
        return pd.DataFrame()

    # FinMind 資產負債表所有可能的欄位名稱（覆蓋 IFRS 前後格式）
    BS = {
        "流動資產": ["CurrentAssets"],
        "流動負債": ["CurrentLiabilities"],
        "存貨":     ["Inventories"],
        "應收帳款": ["AccountsReceivableNet",
                     "AccountsReceivableDuefromRelatedPartiesNet"],
        "資產總計": ["TotalAssets"],
        "負債總計": ["Liabilities"],
        "股東權益": ["Equity", "EquityAttributableToOwnersOfParent"],
    }

    IS = {
        "營業收入": ["Revenue"],
        "營業成本": ["CostOfGoodsSold"],
        "毛利":     ["GrossProfit"],
        "淨利":     ["NetIncome", "IncomeAfterTaxes",
                     "TotalConsolidatedProfitForThePeriod"],
    }

    years = sorted(set(
        list(bs_df["date"].str[:4].unique()) +
        list(is_df["date"].str[:4].unique())
    ))

    rows = {}
    for year in years:
        ca  = get_val(bs_df, year, BS["流動資產"])
        cl  = get_val(bs_df, year, BS["流動負債"])
        inv = get_val(bs_df, year, BS["存貨"]) or 0
        ar  = get_val(bs_df, year, BS["應收帳款"])
        ta  = get_val(bs_df, year, BS["資產總計"])
        tl  = get_val(bs_df, year, BS["負債總計"])
        eq  = get_val(bs_df, year, BS["股東權益"])
        rev = get_val(is_df, year, IS["營業收入"])
        cos = get_val(is_df, year, IS["營業成本"])
        gp  = get_val(is_df, year, IS["毛利"])
        ni  = get_val(is_df, year, IS["淨利"])

        def sd(a, b):
            try:
                if a is None or b is None or b == 0: return None
                return round(a / b, 4)
            except Exception: return None

        def pp(v):
            return round(v * 100, 2) if v is not None else None

        rows[year] = {
            "流動比率":       sd(ca, cl),
            "速動比率":       sd((ca or 0) - inv, cl) if ca and cl else None,
            "負債比率(%)":    pp(sd(tl, ta)),
            "權益比率(%)":    pp(sd(eq, ta)),
            "應收款項周轉率": sd(rev, ar),
            "存貨周轉率":     sd(cos, inv) if inv and inv > 0 else None,
            "毛利率(%)":      pp(sd(gp, rev)),
            "ROE(%)":         pp(sd(ni, eq)),
            "ROA(%)":         pp(sd(ni, ta)),
            "淨利率(%)":      pp(sd(ni, rev)),
        }

    return pd.DataFrame(rows).T.sort_index().dropna(how="all")


def diagnose(latest, val_info):
    msgs = []
    def fval(d, k):
        try: return float(d.get(k)) if d.get(k) is not None else None
        except: return None

    cr = fval(latest, "流動比率")
    if cr:
        if cr >= 2:     msgs.append(f"流動比率 {cr:.2f} — 短期償債能力充足")
        elif cr >= 1.5: msgs.append(f"流動比率 {cr:.2f} — 短期償債能力尚可")
        elif cr >= 1:   msgs.append(f"流動比率 {cr:.2f} — 短期償債能力偏弱")
        else:           msgs.append(f"流動比率 {cr:.2f} — 低於1,短期償債能力不足")

    dr = fval(latest, "負債比率(%)")
    if dr:
        if dr <= 40:    msgs.append(f"負債比率 {dr:.1f}% — 財務結構穩健")
        elif dr <= 60:  msgs.append(f"負債比率 {dr:.1f}% — 財務槓桿中等")
        else:           msgs.append(f"負債比率 {dr:.1f}% — 財務槓桿偏高")

    roe = fval(latest, "ROE(%)")
    if roe:
        if roe >= 15:   msgs.append(f"ROE {roe:.1f}% — 股東權益報酬表現優異")
        elif roe >= 8:  msgs.append(f"ROE {roe:.1f}% — 股東權益報酬中等")
        else:           msgs.append(f"ROE {roe:.1f}% — 股東權益報酬偏低")

    gm = fval(latest, "毛利率(%)")
    if gm:
        if gm >= 40:    msgs.append(f"毛利率 {gm:.1f}% — 產品獲利能力強")
        elif gm >= 20:  msgs.append(f"毛利率 {gm:.1f}% — 產品獲利能力中等")
        else:           msgs.append(f"毛利率 {gm:.1f}% — 毛利偏低")

    if val_info:
        try:
            pe = float(val_info.get("本益比 PE"))
            if pe < 15:   msgs.append(f"本益比 {pe:.1f} — 股價相對便宜")
            elif pe < 25: msgs.append(f"本益比 {pe:.1f} — 股價合理")
            else:         msgs.append(f"本益比 {pe:.1f} — 股價相對偏高")
        except: pass

    return msgs


def fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return str(v)


def color_cell(val, metric):
    try: v = float(val)
    except: return val
    good, warn, bad = "#d4edda", "#fff3cd", "#f8d7da"
    gtxt, wtxt, btxt = "#155724", "#856404", "#721c24"
    if metric == "流動比率":
        c, t = (good, gtxt) if v >= 2 else (warn, wtxt) if v >= 1 else (bad, btxt)
    elif metric == "負債比率(%)":
        c, t = (good, gtxt) if v <= 40 else (warn, wtxt) if v <= 60 else (bad, btxt)
    elif metric in ["ROE(%)", "ROA(%)", "毛利率(%)", "淨利率(%)"]:
        c, t = (good, gtxt) if v >= 15 else (warn, wtxt) if v >= 5 else (bad, btxt)
    else:
        return str(val)
    return f'<span style="background:{c};color:{t};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:500">{val}</span>'


def main():
    st.title("財務比率分析與診斷儀表板")
    st.caption("輸入多家台股代號，自動計算五大類財務比率、多公司橫向比較、歷史趨勢圖")
    st.info("資料來源：FinMind 台股公開資料。台股代號直接輸入數字，例如 2330, 2317")

    token = FINMIND_TOKEN
    if not token:
        token = st.text_input("請輸入 FinMind API Token", type="password")
        if not token:
            st.warning("請輸入 FinMind API Token 才能使用本系統")
            return

    codes_input = st.text_input(
        "輸入台股代號，多檔請用逗號分隔（例如 2330, 2317, 2412）",
        value="2330, 2317, 2412",
    )

    show_debug = st.checkbox("顯示欄位診斷（若資料有缺失請勾選）", value=False)

    if not st.button("開始分析", type="primary"):
        return

    codes = [c.strip() for c in codes_input.split(",") if c.strip()]
    if not codes:
        st.warning("請至少輸入一檔股票代號")
        return

    all_ratios, all_val, all_bs, all_is = {}, {}, {}, {}

    with st.spinner("查詢中，請稍候..."):
        for code in codes:
            bs_df, _ = fetch_finmind("TaiwanStockBalanceSheet", code, token)
            is_df, _ = fetch_finmind("TaiwanStockFinancialStatements", code, token)
            val_info  = fetch_valuation(code, token)
            df = calc_ratios(bs_df, is_df)
            if not df.empty:
                all_ratios[code] = df
            all_val[code]  = val_info
            all_bs[code]   = bs_df
            all_is[code]   = is_df

    # Debug 欄位顯示
    if show_debug:
        st.divider()
        st.subheader("欄位診斷（Debug）")
        for code in codes:
            with st.expander(f"{code} — 資產負債表欄位"):
                if all_bs.get(code) is not None and not all_bs[code].empty:
                    types = sorted(all_bs[code]["type"].unique().tolist())
                    st.write(types)
                else:
                    st.write("查無資料")
            with st.expander(f"{code} — 損益表欄位"):
                if all_is.get(code) is not None and not all_is[code].empty:
                    types = sorted(all_is[code]["type"].unique().tolist())
                    st.write(types)
                else:
                    st.write("查無資料")
            with st.expander(f"{code} — 估值(PER)欄位名稱"):
                per_cols = all_val.get(code, {}).get("_per_columns", [])
                st.write(per_cols if per_cols else "查無資料")

    if not all_ratios:
        st.error("所有股票皆查無比率資料，請勾選「顯示欄位診斷」查看原因")
        return

    # ========== 區塊一：橫向比較表 ==========
    st.divider()
    st.subheader("最新一期比較")

    compare_metrics = [
        "流動比率", "速動比率", "負債比率(%)", "權益比率(%)",
        "毛利率(%)", "ROE(%)", "ROA(%)", "淨利率(%)",
        "應收款項周轉率", "存貨周轉率",
    ]
    val_metrics = ["本益比 PE", "股價淨值比 PB", "殖利率(%)"]

    latest_rows = {}
    for code, df in all_ratios.items():
        latest_rows[code] = df.iloc[-1].to_dict()
    for code in codes:
        for k, v in all_val.get(code, {}).items():
            if code in latest_rows:
                latest_rows[code][k] = v

    col_names = list(latest_rows.keys())
    header_cells = "<th style='padding:8px 12px;font-weight:500;font-size:13px;color:#888'>比率</th>"
    for i, code in enumerate(col_names):
        color = COLORS[i % len(COLORS)]
        header_cells += f"<th style='padding:8px 12px;font-weight:500;font-size:13px;color:{color};text-align:center'>{code}</th>"

    html_rows = ""
    for metric in compare_metrics + val_metrics:
        cells = f"<td style='color:#888;font-size:13px;padding:8px 12px'>{metric}</td>"
        for code in col_names:
            v = latest_rows.get(code, {}).get(metric)
            val = fmt(v)
            if metric in ["流動比率","負債比率(%)","ROE(%)","ROA(%)","毛利率(%)","淨利率(%)"]:
                cell_content = color_cell(val, metric)
            else:
                cell_content = val
            cells += f"<td style='padding:8px 12px;text-align:center;font-size:13px'>{cell_content}</td>"
        html_rows += f"<tr style='border-bottom:0.5px solid #eee'>{cells}</tr>"

    st.markdown(f"""
    <div style="overflow-x:auto;border:0.5px solid #e0e0e0;border-radius:12px;margin-bottom:1rem">
      <table style="width:100%;border-collapse:collapse">
        <thead><tr style="border-bottom:1px solid #e0e0e0;background:#fafafa">{header_cells}</tr></thead>
        <tbody>{html_rows}</tbody>
      </table>
    </div>
    """, unsafe_allow_html=True)
    st.caption("🟢 表現良好　🟡 中等　🔴 需留意")

    # ========== 區塊二：個股診斷 ==========
    st.divider()
    st.subheader("個股診斷")
    diag_cols = st.columns(len(all_ratios))
    for i, (code, df) in enumerate(all_ratios.items()):
        with diag_cols[i]:
            color = COLORS[i % len(COLORS)]
            st.markdown(f"<h4 style='color:{color}'>{code}</h4>", unsafe_allow_html=True)
            msgs = diagnose(df.iloc[-1].to_dict(), all_val.get(code, {}))
            for msg in msgs:
                st.markdown(f"- {msg}")
            if not msgs:
                st.write("資料不足")

    # ========== 區塊三：折線趨勢圖 ==========
    st.divider()
    st.subheader("歷史趨勢比較")

    trend_metrics = {
        "獲利能力": ["ROE(%)", "ROA(%)", "毛利率(%)", "淨利率(%)"],
        "償債能力": ["流動比率", "速動比率"],
        "財務結構": ["負債比率(%)", "權益比率(%)"],
    }

    for cat_name, metrics in trend_metrics.items():
        for metric in metrics:
            has_data = any(
                metric in df.columns and pd.to_numeric(df[metric], errors="coerce").notna().any()
                for df in all_ratios.values()
            )
            if not has_data:
                continue
            fig = go.Figure()
            for i, (code, df) in enumerate(all_ratios.items()):
                if metric not in df.columns:
                    continue
                vals = pd.to_numeric(df[metric], errors="coerce")
                if vals.notna().any():
                    fig.add_trace(go.Scatter(
                        x=df.index, y=vals, mode="lines+markers", name=code,
                        line=dict(color=COLORS[i % len(COLORS)], width=2),
                        marker=dict(size=7),
                    ))
            fig.update_layout(
                title=dict(text=f"{cat_name}｜{metric}", font=dict(size=14)),
                xaxis_title="年度",
                yaxis_title="%" if "%" in metric else "倍",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
                margin=dict(l=10, r=10, t=50, b=10),
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)

    # ========== 區塊四：長條圖 ==========
    st.divider()
    st.subheader("各年度並排比較")
    for metric in ["毛利率(%)", "ROE(%)", "負債比率(%)"]:
        has_data = any(
            metric in df.columns and pd.to_numeric(df[metric], errors="coerce").notna().any()
            for df in all_ratios.values()
        )
        if not has_data:
            continue
        fig = go.Figure()
        for i, (code, df) in enumerate(all_ratios.items()):
            if metric not in df.columns:
                continue
            vals = pd.to_numeric(df[metric], errors="coerce")
            fig.add_trace(go.Bar(
                name=code, x=df.index, y=vals,
                marker_color=COLORS[i % len(COLORS)],
            ))
        fig.update_layout(
            barmode="group",
            title=dict(text=metric, font=dict(size=14)),
            xaxis_title="年度", yaxis_title="%",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=50, b=10),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption("⚠️ 本工具為教學示範用途，不構成投資建議。")


if __name__ == "__main__":
    main()
