import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
import re
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, apply_isp_filter, isp_label
from utils.google_sheets import load_sheet_as_csv
from utils.auto_load import auto_load_tickets
from utils.data_processing import isp_options, classify_isp
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

SHEET_ID = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
USAGE_GID = "710549453"
PLAN_GB = 10.0
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
MONTH_ALIAS = {
    "jan": "January", "january": "January",
    "feb": "February", "february": "February",
    "mar": "March", "march": "March",
    "apr": "April", "april": "April",
    "may": "May",
    "jun": "June", "june": "June",
    "jul": "July", "july": "July",
    "aug": "August", "august": "August",
    "sep": "September", "sept": "September", "september": "September",
    "oct": "October", "october": "October",
    "nov": "November", "november": "November",
    "dec": "December", "december": "December",
}

st.set_page_config(page_title="SIM Backup Usage | XTRNATE", page_icon="📶", layout="wide")
st.title("📶 SIM Backup Usage vs BB Down")
st.caption("Backup SIM data • 10 GB plan • Site list: Branch + State + ISP (Owner ke saare names) sheet se")

ensure_ready()
if st.session_state.get("closed_df") is None:
    auto_load_tickets()


def parse_gb(v):
    if pd.isna(v):
        return 0.0
    s = str(v).lower().replace(",", " ")
    s = s.replace("gb", "").strip()
    try:
        return round(float(s), 2)
    except Exception:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
        return round(float(m.group(1)), 2) if m else 0.0


def month_from_col(col):
    tokens = re.findall(r"[a-z]+", str(col).lower())
    hit = None
    for tok in tokens:
        if tok in MONTH_ALIAS:
            name = MONTH_ALIAS[tok]
            if hit is None or len(tok) > 3:
                hit = name
    return hit


def detect_gb_columns(columns):
    best = {}
    for c in columns:
        mon = month_from_col(c)
        if not mon:
            continue
        cl = str(c).lower()
        score = 0
        if "gb" in cl:
            score += 5
        if "usage" in cl:
            score += 2
        if "in gb" in cl:
            score += 3
        prev = best.get(mon)
        if prev is None or score > prev[1]:
            best[mon] = (c, score)
    return [(m, best[m][0]) for m in MONTHS if MONTH_ALIAS[m] in best for m in [MONTH_ALIAS[m]]]


def find_col(df, *names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    for key, col in lower.items():
        for n in names:
            if n.lower() in key:
                return col
    return None


def clean_cell(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "-", "—") else s


def norm_isp(v):
    name = classify_isp(v)
    if name == "UNKNOWN":
        return clean_cell(v)
    return name


@st.cache_data(ttl=180)
def load_usage():
    df = load_sheet_as_csv(SHEET_ID, gid=USAGE_GID)
    df.columns = [str(c).strip() for c in df.columns]
    return df


c1, c2 = st.columns([2, 1])
with c1:
    st.markdown("### Sheet")
with c2:
    if st.button("🔄 Reload Excel / sheet", use_container_width=True):
        load_usage.clear()
        st.rerun()

try:
    usage = load_usage()
except Exception as e:
    st.error(f"Usage sheet load fail: {e}")
    st.stop()

if usage is None or usage.empty:
    st.warning("SIM usage sheet empty.")
    st.stop()

site_col = find_col(usage, "site code", "sitecode", "hughessitecode") or usage.columns[0]
usage["site_code"] = usage[site_col].astype(str).str.strip().str.upper()

isp_c = find_col(usage, "isp name", "isp")
br_c = find_col(usage, "branch name", "branch")
st_c = find_col(usage, "state")
ckt_c = find_col(usage, "ckt id")
addr_c = find_col(usage, "branch address")
usage["isp_name"] = usage[isp_c].map(norm_isp) if isp_c else ""
usage["branch_name"] = usage[br_c].map(clean_cell) if br_c else ""
usage["state_name"] = usage[st_c].map(clean_cell) if st_c else ""
usage["ckt_id"] = usage[ckt_c].map(clean_cell) if ckt_c else ""
usage["branch_address"] = usage[addr_c].map(clean_cell) if addr_c else ""

gb_cols = detect_gb_columns(usage.columns)
if not gb_cols:
    st.error("Month GB columns nahi mili. Header example: `Aug Usage in GB`")
    st.write("Sheet columns:", list(usage.columns))
    st.stop()

st.success("GB columns: " + " • ".join(f"**{m}** ← `{c}`" for m, c in gb_cols))

long_rows = []
for mon, col in gb_cols:
    tmp = usage.copy()
    tmp["month"] = mon
    tmp["usage_gb"] = tmp[col].apply(parse_gb)
    long_rows.append(tmp)
long_df = pd.concat(long_rows, ignore_index=True)

closed = st.session_state.get("closed_df")
raw = st.session_state.get("raw_tickets_df")
open_df = st.session_state.get("open_df")
parts = [p for p in (closed, raw, open_df) if p is not None and not getattr(p, "empty", True)]
tix = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
if not tix.empty:
    tix = tix.copy()
    tix = tix.loc[:, ~tix.columns.duplicated()]
    if "site_code" in tix.columns:
        tix["site_code"] = tix["site_code"].astype(str).str.strip().str.upper()
    if "submitted_time" in tix.columns:
        tix["submitted_time"] = pd.to_datetime(tix["submitted_time"], errors="coerce")
        tix["tix_month"] = tix["submitted_time"].dt.strftime("%B")
    else:
        tix["tix_month"] = ""
    if "isp" not in tix.columns and "owner" in tix.columns:
        tix["isp"] = tix["owner"].map(classify_isp)
    elif "isp" not in tix.columns:
        tix["isp"] = "UNKNOWN"

    if "ticket_id" in tix.columns:
        tix = tix.drop_duplicates(subset=["ticket_id"], keep="first")

    downs = (
        tix.dropna(subset=["site_code"])
        .groupby(["site_code", "tix_month"], dropna=False)
        .agg(
            bb_downs=("ticket_id", "count") if "ticket_id" in tix.columns else ("site_code", "count"),
            isp=("isp", lambda s: s.mode().iloc[0] if len(s.dropna()) else "UNKNOWN"),
            last_reason=("reason", "last") if "reason" in tix.columns else ("site_code", "last"),
        )
        .reset_index()
        .rename(columns={"tix_month": "month"})
    )
else:
    downs = pd.DataFrame(columns=["site_code", "month", "bb_downs", "isp", "last_reason"])

merged = long_df.merge(downs, on=["site_code", "month"], how="left")
merged["bb_downs"] = merged["bb_downs"].fillna(0).astype(int)
if "isp" not in merged.columns:
    merged["isp"] = ""
merged["isp"] = merged["isp"].fillna("")
if "isp_name" in merged.columns:
    sheet_ok = merged["isp_name"].astype(str).str.strip().ne("") & ~merged["isp_name"].isin(["UNKNOWN", "OTHER", ""])
    merged.loc[sheet_ok, "isp"] = merged.loc[sheet_ok, "isp_name"]
    miss = merged["isp"].isin(["", "UNKNOWN", "OTHER", "nan"])
    merged.loc[miss, "isp"] = merged.loc[miss, "isp_name"].replace("", pd.NA).fillna(merged.loc[miss, "isp"])
merged["isp"] = merged["isp"].replace({"": "UNKNOWN", "OTHER": "UNKNOWN"}).fillna("UNKNOWN")
merged["plan_pct"] = (merged["usage_gb"] / PLAN_GB * 100).round(1)
merged["near_cap"] = merged["usage_gb"] >= PLAN_GB * 0.8

if not tix.empty and "site_code" in tix.columns:
    site_isp = tix.groupby("site_code")["isp"].agg(
        lambda s: s.mode().iloc[0] if len(s.dropna()) else "UNKNOWN"
    )
    miss = merged["isp"].isin(["UNKNOWN", "OTHER", ""])
    merged.loc[miss, "isp"] = merged.loc[miss, "site_code"].map(site_isp).fillna(merged.loc[miss, "isp"])

st.markdown("### Filters")
f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.4, 1.4])
with f1:
    partner = isp_label()
    st.markdown(f"**ISP:** {partner}")
    st.caption("Top / sidebar se multi-select")
with f2:
    months_avail = sorted(
        merged["month"].dropna().unique().tolist(),
        key=lambda x: MONTHS.index(x.lower()) if x.lower() in MONTHS else 99,
    )
    month_sel = st.multiselect("Month", months_avail, default=months_avail)
with f3:
    min_gb = st.slider("Min SIM usage (GB)", 0.0, 15.0, 5.0, 0.5)
with f4:
    only_cap = st.checkbox(f"Sirf ≥ {PLAN_GB:.0f} GB plan (BB likely down)", value=False)

view = merged.copy()
if month_sel:
    view = view[view["month"].isin(month_sel)]
view = apply_isp_filter(view)
view = view[view["usage_gb"] >= min_gb]
if only_cap:
    view = view[view["usage_gb"] >= PLAN_GB]

view = view.sort_values(["usage_gb", "bb_downs"], ascending=False)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Sites (filter)", view["site_code"].nunique())
k2.metric("Rows", len(view))
k3.metric("Avg usage GB", round(view["usage_gb"].mean(), 2) if not view.empty else 0)
k4.metric(f"≥ {PLAN_GB:.0f} GB (plan cap)", int((view["usage_gb"] >= PLAN_GB).sum()) if not view.empty else 0)
k5.metric("BB downs (un sites pe)", int(view["bb_downs"].sum()) if not view.empty else 0)

if view.empty:
    st.info("Is filter pe site nahi mili. Usage limit kam karo ya month badlo.")
    st.stop()

st.subheader("📊 High SIM usage + us month ke BB downs")
st.caption("Zyada SIM GB = us month BB unstable. Plan 10 GB. Filter se limit set karo.")

g1, g2 = st.columns(2)
with g1:
    top = view.nlargest(20, "usage_gb")
    fig = px.bar(
        top, x="site_code", y="usage_gb", color="month",
        hover_data=[c for c in ["bb_downs", "isp", "branch_name", "state_name", "Telco"] if c in top.columns],
        title="Top 20 SIM usage (GB)",
    )
    fig.update_layout(template="plotly_dark", height=380, xaxis_tickangle=-40)
    fig.add_hline(y=PLAN_GB, line_dash="dash", line_color="#f87171", annotation_text="10 GB plan")
    st.plotly_chart(fig, use_container_width=True)
with g2:
    fig = px.scatter(
        view, x="bb_downs", y="usage_gb", color="isp",
        hover_name="site_code", size="usage_gb",
        title="BB down count vs SIM GB",
    )
    fig.update_layout(template="plotly_dark", height=380)
    fig.add_hline(y=PLAN_GB, line_dash="dash", line_color="#f87171")
    st.plotly_chart(fig, use_container_width=True)

split = pd.DataFrame()
if "isp" in view.columns:
    st.subheader("ISP split")
    split = view.groupby("isp").agg(
        sites=("site_code", "nunique"),
        avg_gb=("usage_gb", "mean"),
        cap_sites=("usage_gb", lambda s: int((s >= PLAN_GB).sum())),
        bb_downs=("bb_downs", "sum"),
    ).reset_index()
    split["avg_gb"] = split["avg_gb"].round(2)
    st.dataframe(split, use_container_width=True, hide_index=True)

st.subheader("Month-wise")
mon = view.groupby(["month", "isp"]).agg(
    sites=("site_code", "nunique"),
    avg_gb=("usage_gb", "mean"),
    over_plan=("usage_gb", lambda s: int((s >= PLAN_GB).sum())),
    bb_downs=("bb_downs", "sum"),
).reset_index()
mon["avg_gb"] = mon["avg_gb"].round(2)
st.dataframe(mon, use_container_width=True, hide_index=True)

st.subheader("Site list")
st.caption("Branch / State / ISP (Celerity → ONEOTT, HCIN) isi sheet se: gid 710549453")
show_src = view[[c for c in [
    "site_code", "branch_name", "state_name", "isp", "ckt_id", "month",
    "usage_gb", "plan_pct", "bb_downs", "Telco", "IP Address", "MDN Number",
    "Asset Number", "branch_address", "last_reason",
] if c in view.columns]].copy()
show = show_src.rename(columns={
    "site_code": "Site Code",
    "branch_name": "Branch",
    "state_name": "State",
    "isp": "ISP",
    "ckt_id": "CKT ID",
    "month": "Month",
    "usage_gb": "SIM Usage GB",
    "plan_pct": "% of 10GB",
    "bb_downs": "BB Downs (same month)",
    "branch_address": "Branch Address",
    "last_reason": "Last BB remark",
})
st.dataframe(show, use_container_width=True, height=480)

pick = st.selectbox("Site ka month-wise detail", ["—"] + sorted(view["site_code"].unique().tolist()))
if pick and pick != "—":
    meta = view[view["site_code"] == pick].iloc[0]
    st.markdown(
        f"**{pick}** • {meta.get('isp', '')} • {meta.get('branch_name', '')} • {meta.get('state_name', '')}"
    )
    cols_one = [c for c in ["month", "usage_gb", "plan_pct", "bb_downs", "isp", "branch_name", "state_name"] if c in merged.columns]
    one = merged[merged["site_code"] == pick][cols_one].copy()
    one["_ord"] = one["month"].str.lower().map({m: i for i, m in enumerate(MONTHS)})
    one = one.sort_values("_ord").drop(columns="_ord")
    st.dataframe(one, use_container_width=True, hide_index=True)
    if not tix.empty:
        hist = tix[(tix["site_code"] == pick)]
        if not hist.empty:
            hc = [c for c in ["ticket_id", "submitted_time", "resolved_time", "isp", "status", "reason", "down_time_min"] if c in hist.columns]
            st.markdown(f"**{pick}** BB tickets")
            sortc = hc[1] if len(hc) > 1 else hc[0]
            st.dataframe(hist[hc].sort_values(sortc, ascending=False), use_container_width=True, height=280)

sim_sheets = {"Site_Usage_Downs": show, "Month_ISP": mon}
if not split.empty:
    sim_sheets["ISP_Split"] = split
download_pack(
    "SIM usage + BB downs",
    sim_sheets,
    file_stem="XTRNATE_SIM_Backup_Usage",
    title="SIM Backup Usage",
    subtitle="Site usage + BB downs",
    key="sim_usage_dl",
)
