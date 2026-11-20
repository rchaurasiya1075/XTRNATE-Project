import os
import sys
import calendar

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, apply_isp_filter, isp_label
from utils.report_download import download_pack

st.set_page_config(page_title="Vendor Report | Opsora", page_icon="📑", layout="wide")
ensure_ready()

SLA_ORDER = [
    "<4 Hours", "4-8 Hours", "8-12 Hours", "12-24 Hours",
    "24-48 Hours", "48-72 Hours", "More than 72 Hours",
]
UPTIME_BANDS = [
    ("Below 80%", 0.0, 0.80),
    ("Between 80% to 85%", 0.80, 0.85),
    ("Between 85% to 90%", 0.85, 0.90),
    ("Between 90% to 93%", 0.90, 0.93),
    ("Between 93% to 96%", 0.93, 0.96),
    ("Between 96% to 98%", 0.96, 0.98),
    ("Greater than 98%", 0.98, 1.01),
]


def sla_band(hrs):
    if pd.isna(hrs) or hrs < 0:
        return None
    if hrs < 4:
        return "<4 Hours"
    if hrs < 8:
        return "4-8 Hours"
    if hrs < 12:
        return "8-12 Hours"
    if hrs < 24:
        return "12-24 Hours"
    if hrs < 48:
        return "24-48 Hours"
    if hrs < 72:
        return "48-72 Hours"
    return "More than 72 Hours"


def link_kind(row):
    bits = []
    for c in (
        "link_type", "LINK-TYPE", "products_item", "Products Item",
        "problem_reported", "reason", "category", "problem_class",
    ):
        if c in row.index:
            bits.append(str(row.get(c) or ""))
    blob = " ".join(bits).lower()
    if "leased" in blob or " ill" in f" {blob}" or "internet leased" in blob:
        return "ILL"
    if "broadband" in blob or " bb " in f" {blob} " or "primary bb" in blob:
        return "BB"
    return "Other"


def month_minutes(ts):
    days = calendar.monthrange(int(ts.year), int(ts.month))[1]
    return days * 24 * 60


def uptime_band(ratio):
    if pd.isna(ratio):
        return None
    for name, lo, hi in UPTIME_BANDS:
        if lo <= ratio < hi or (name.startswith("Greater") and ratio >= 0.98):
            return name
    return "Below 80%"


st.title("📑 Vendor Report")
st.caption("Same layout as the Shell vendor sheet — repeat, SLA, BB / ILL uptime, classification. Uses the month / date you select above.")

closed = st.session_state.get("closed_df")
if closed is None or getattr(closed, "empty", True):
    st.warning("No ticket data. Load the sheet from Home first.")
    st.stop()

work = apply_isp_filter(closed.copy())
if work is None or work.empty:
    st.warning("No tickets in the selected month / date / ISP. Change the period at the top.")
    st.stop()

if "submitted_time" not in work.columns:
    st.error("Submitted time is missing in this file.")
    st.stop()

work["submitted_time"] = pd.to_datetime(work["submitted_time"], errors="coerce")
if "resolved_time" in work.columns:
    work["resolved_time"] = pd.to_datetime(work["resolved_time"], errors="coerce")
else:
    work["resolved_time"] = pd.NaT
try:
    if getattr(work["submitted_time"].dt, "tz", None) is not None:
        work["submitted_time"] = work["submitted_time"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    if getattr(work["resolved_time"].dt, "tz", None) is not None:
        work["resolved_time"] = work["resolved_time"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
except Exception:
    pass

work = work[work["submitted_time"].notna()].copy()
if work.empty:
    st.warning("No tickets with a date in this selection.")
    st.stop()
if "resolution_hours" not in work.columns:
    work["resolution_hours"] = (work["resolved_time"] - work["submitted_time"]).dt.total_seconds() / 3600.0
work["resolution_hours"] = pd.to_numeric(work["resolution_hours"], errors="coerce")
work = work[work["resolution_hours"].isna() | (work["resolution_hours"] >= 0)].copy()
work["month"] = work["submitted_time"].dt.strftime("%b-%Y")
work["month_key"] = work["submitted_time"].dt.to_period("M")
months = [str(p) for p in sorted(work["month_key"].dropna().unique())]
month_label = {str(p): p.strftime("%b-%Y") for p in sorted(work["month_key"].dropna().unique())}
work["month"] = work["month_key"].map(lambda p: month_label.get(str(p), ""))
work["sla_band"] = work["resolution_hours"].apply(sla_band)
work["link_kind"] = work.apply(link_kind, axis=1)
site_col = "site_code" if "site_code" in work.columns else None

st.caption(f"**{isp_label()}** • **{len(work)}** tickets • months: {', '.join(month_label[m] for m in months)}")


def count_table(series_name, order, frame):
    rows = []
    for lab in order:
        row = {"": lab}
        for m in months:
            part = frame[(frame["month_key"].astype(str) == m)]
            row[month_label[m]] = int((part[series_name] == lab).sum()) if series_name in part.columns else 0
        rows.append(row)
    total = {"": "Grand Total"}
    for m in months:
        total[month_label[m]] = int((frame["month_key"].astype(str) == m).sum())
    rows.append(total)
    return pd.DataFrame(rows)


st.subheader("Repeat")
if site_col:
    rep_rows = []
    site_month = (
        work.groupby([site_col, "month_key"]).size().rename("n").reset_index()
    )
    max_n = int(site_month["n"].max()) if not site_month.empty else 1
    for n in range(1, max_n + 1):
        row = {"": f"{n}Time Repeat"}
        for m in months:
            row[month_label[m]] = int(((site_month["month_key"].astype(str) == m) & (site_month["n"] == n)).sum())
        if sum(v for k, v in row.items() if k) == 0:
            continue
        rep_rows.append(row)
    rep_df = pd.DataFrame(rep_rows) if rep_rows else pd.DataFrame()
else:
    rep_df = pd.DataFrame()
    st.caption("Site code column not found — repeat by site is skipped.")
if not rep_df.empty:
    st.dataframe(rep_df, use_container_width=True, hide_index=True)

st.subheader("SLA")
sla_df = count_table("sla_band", SLA_ORDER, work[work["sla_band"].notna()])
st.dataframe(sla_df, use_container_width=True, hide_index=True)

def uptime_table(kind):
    part = work[work["link_kind"] == kind].copy()
    if part.empty or not site_col:
        return pd.DataFrame()
    part["down_min"] = part["resolution_hours"].fillna(0) * 60.0
    g = part.groupby([site_col, "month_key"], as_index=False)["down_min"].sum()
    g["mins"] = g["month_key"].apply(lambda p: month_minutes(p.to_timestamp()))
    g["uptime"] = (1 - (g["down_min"] / g["mins"])).clip(lower=0, upper=1)
    g["band"] = g["uptime"].apply(uptime_band)
    rows = []
    for name, _, _ in UPTIME_BANDS:
        row = {"": name}
        for m in months:
            row[month_label[m]] = int(((g["month_key"].astype(str) == m) & (g["band"] == name)).sum())
        rows.append(row)
    total = {"": "Grand Total"}
    for m in months:
        total[month_label[m]] = int((g["month_key"].astype(str) == m).sum())
    rows.append(total)
    return pd.DataFrame(rows)

c1, c2 = st.columns(2)
with c1:
    st.subheader("BB uptime")
    bb_df = uptime_table("BB")
    if bb_df.empty:
        st.caption("No Broadband rows in this period.")
    else:
        st.dataframe(bb_df, use_container_width=True, hide_index=True)
with c2:
    st.subheader("ILL uptime")
    ill_df = uptime_table("ILL")
    if ill_df.empty:
        st.caption("No ILL rows in this period.")
    else:
        st.dataframe(ill_df, use_container_width=True, hide_index=True)

st.subheader("Problem classification")
cls_col = "problem_class" if "problem_class" in work.columns else ("category" if "category" in work.columns else None)
cls_count = pd.DataFrame()
cls_avg = pd.DataFrame()
if cls_col:
    names = [x for x in work[cls_col].fillna("Others").astype(str).unique() if x.strip() and x.lower() not in ("nan", "none")]
    names = sorted(names, key=lambda s: -int((work[cls_col].astype(str) == s).sum()))
    count_rows, avg_rows = [], []
    for name in names:
        cr, ar = {"": name}, {"": name}
        sub = work[work[cls_col].astype(str) == name]
        for m in months:
            bit = sub[sub["month_key"].astype(str) == m]
            cr[month_label[m]] = int(len(bit))
            ar[month_label[m]] = round(float(bit["resolution_hours"].mean()), 2) if len(bit) else None
        if sum(v for k, v in cr.items() if k) == 0:
            continue
        count_rows.append(cr)
        avg_rows.append(ar)
    tot = {"": "Grand Total"}
    for m in months:
        tot[month_label[m]] = int((work["month_key"].astype(str) == m).sum())
    count_rows.append(tot)
    cls_count = pd.DataFrame(count_rows)
    cls_avg = pd.DataFrame(avg_rows)
    a, b = st.columns(2)
    with a:
        st.markdown("**Tickets**")
        st.dataframe(cls_count, use_container_width=True, hide_index=True)
    with b:
        st.markdown("**Average resolution (hours)**")
        st.dataframe(cls_avg, use_container_width=True, hide_index=True)
else:
    st.caption("Problem classification column not in this file.")

st.subheader("Site-wise log")
site_df = pd.DataFrame()
if site_col:
    pivot = (
        work.groupby([site_col, "month"]).size().unstack(fill_value=0).reset_index()
    )
    ordered = [month_label[m] for m in months if month_label[m] in pivot.columns]
    site_df = pivot[[site_col] + ordered]
    site_df = site_df.rename(columns={site_col: "Site"})
    st.dataframe(site_df, use_container_width=True, hide_index=True, height=360)

sheets = {}
if not rep_df.empty:
    sheets["Repeat"] = rep_df
sheets["SLA"] = sla_df
if not bb_df.empty:
    sheets["BB_Uptime"] = bb_df
if not ill_df.empty:
    sheets["ILL_Uptime"] = ill_df
if not cls_count.empty:
    sheets["Classification"] = cls_count
if not cls_avg.empty:
    sheets["Avg_Hours"] = cls_avg
if not site_df.empty:
    sheets["Site_Wise"] = site_df

download_pack(
    "Vendor Report",
    sheets,
    file_stem="Vendor_Report",
    title="Vendor Report",
    subtitle=f"{isp_label()} • {len(work)} tickets",
    key="vendor_report_dl",
)
