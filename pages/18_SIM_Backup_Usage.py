import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
import re
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, show_last_update
from utils.google_sheets import load_sheet_as_csv
from utils.auto_load import auto_load_tickets

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
show_last_update()

st.title("📶 SIM Backup Usage vs BB Down")
st.caption("Backup SIM data • 10 GB plan • GB columns: `Aug Usage in GB`, `Sep Usage in GB` • High usage = BB down chance")

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
    """Prefer '* Usage in GB' / 'Aug Usage in GB'. Skip raw MB if GB exists."""
    best = {}
    for c in columns:
        mon = month_from_col(c)
        if not mon:
            continue
        cl = str(c).lower()
        is_gb = "gb" in cl
        score = 0
        if is_gb:
            score += 5
        if "usage" in cl:
            score += 2
        if "in gb" in cl:
            score += 3
        prev = best.get(mon)
        if prev is None or score > prev[1]:
            best[mon] = (c, score)
    return [(m, best[m][0]) for m in MONTHS if MONTH_ALIAS[m] in best for m in [MONTH_ALIAS[m]]]


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

site_col = next(
    (c for c in usage.columns if str(c).strip().lower() in ("site code", "sitecode", "hughessitecode")),
    usage.columns[0],
)
usage["site_code"] = usage[site_col].astype(str).str.strip().str.upper()

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
        own = tix["owner"].astype(str).str.upper()
        tix["isp"] = "OTHER"
        tix.loc[own.str.contains("HCIN|HICOM", na=False), "isp"] = "HCIN"
        tix.loc[own.str.contains("ONEOTT|OTT|CELERITY", na=False), "isp"] = "ONEOTT"
    elif "isp" not in tix.columns:
        tix["isp"] = "OTHER"

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
merged["isp"] = merged["isp"].fillna("UNKNOWN")
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
    partner = st.radio("ISP", ["ALL", "HCIN", "ONEOTT"], horizontal=True)
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
if partner != "ALL":
    view = view[view["isp"] == partner]
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
        hover_data=["bb_downs", "isp", "Telco"] if "Telco" in top.columns else ["bb_downs", "isp"],
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
show = view[[c for c in [
    "site_code", "month", "usage_gb", "plan_pct", "bb_downs", "isp",
    "Telco", "IP Address", "MDN Number", "Asset Number", "last_reason",
] if c in view.columns]].copy()
show = show.rename(columns={
    "site_code": "Site Code",
    "month": "Month",
    "usage_gb": "SIM Usage GB",
    "plan_pct": "% of 10GB",
    "bb_downs": "BB Downs (same month)",
    "isp": "ISP",
    "last_reason": "Last BB remark",
})
st.dataframe(show, use_container_width=True, height=480)

pick = st.selectbox("Site ka month-wise detail", ["—"] + sorted(view["site_code"].unique().tolist()))
if pick and pick != "—":
    one = merged[merged["site_code"] == pick][["month", "usage_gb", "plan_pct", "bb_downs", "isp"]].copy()
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

buf = BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
    show.to_excel(w, index=False, sheet_name="Site_Usage_Downs")
    mon.to_excel(w, index=False, sheet_name="Month_ISP")
    if not split.empty:
        split.to_excel(w, index=False, sheet_name="ISP_Split")

st.download_button(
    "📥 Excel — SIM usage + BB downs",
    data=buf.getvalue(),
    file_name="XTRNATE_SIM_Backup_Usage.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
