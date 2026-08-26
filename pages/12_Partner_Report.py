import os
import sys
from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.data_processing import process_closed_tickets
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv

st.set_page_config(
    page_title="Partner Report | XTRNATE", page_icon="📑", layout="wide"
)

DATA_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
DATA_GID = 1980854633

CLASS_ORDER = [
    "Fibre Cut",
    "Backend /Upstream issue/Node isolation at ISP end",
    "ONU/Media converter/ZTE modem Rebooted",
    "ONU/Media converter/ZTE modem is faulty",
    "Power outage at ISP Node",
    "Power failure at site",
    "Problem in LAN connectivity.",
    "Interface down/ Cable disconnected from SDWAN",
    "No changes done",
    "Maintenance activity by ISP",
    "Natural Calamity",
    "Coordinated & found no problem",
    "Loose connection/ Power socket issue",
    "Latency Issue",
    "WAN IP Issue",
    "Address mismatch issue",
    "TELCO Sytem Failure",
    "Signal issue",
    "Power cord damaged/unplugged",
    "Ticket logged with wrong inputs",
    "LAN IP changed",
    "Test Call",
    "Others",
]

RELATED_ORDER = [
    "Third Party",
    "House keeping",
    "Force Majeure",
    "Cannot Duplicate",
]

# Updated SLA order to include detailed >24h breakdown
SLA_ORDER = [
    "<2 Hours",
    "2-4 Hours",
    "4-8 Hours",
    "8-12 Hours",
    "12-24 Hours",
    "24-48 Hours",
    "48-72 Hours",
    "More than 72 Hours",
]

UPTIME_ORDER = [
    "Between 80% to 75%",
    "Between 85% to 80%",
    "Between 90% to 85%",
    "Between 93% to 90%",
    "Between 96% to 93%",
    "Between 98% to 96%",
    "Greater than 98%",
]


def sheet_class(row):
    raw = str(
        row.get("problem_class", "") or row.get("category", "") or ""
    ).strip()
    if raw and raw.lower() not in ("nan", "--", "none", ""):
        return raw
    return "Others"


def sheet_related(row):
    raw = str(row.get("problem_related", "") or "").strip()
    if raw and raw.lower() not in ("nan", "--", "none", ""):
        return raw
    return None


# Extended SLA Bucket Logic (Includes >24h, >48h, >72h)
def sla_bucket(hrs):
    if pd.isna(hrs) or hrs < 0:
        return None
    if hrs < 2:
        return "<2 Hours"
    if hrs < 4:
        return "2-4 Hours"
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


def uptime_bucket(pct):
    if pd.isna(pct):
        return None
    if pct > 98:
        return "Greater than 98%"
    if pct > 96:
        return "Between 98% to 96%"
    if pct > 93:
        return "Between 96% to 93%"
    if pct > 90:
        return "Between 93% to 90%"
    if pct > 85:
        return "Between 90% to 85%"
    if pct > 80:
        return "Between 85% to 80%"
    return "Between 80% to 75%"


def style_blue(df):
    def apply(row):
        if str(row.iloc[0]).strip().lower() == "grand total":
            return [
                "background-color:#0284C7;color:#fff;font-weight:800;text-align:center"
            ] * len(row)
        return [
            "background-color:#F8FAFC;color:#0F172A;text-align:center"
        ] * len(row)

    return df.style.apply(apply, axis=1).set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#0F172A"),
                ("color", "#fff"),
                ("font-weight", "800"),
                ("text-align", "center"),
                ("padding", "10px"),
            ],
        },
        {
            "selector": "td",
            "props": [("border", "1px solid #CBD5E1"), ("padding", "8px")],
        },
    ])


def style_navy(df):
    def apply(row):
        if str(row.iloc[0]).strip().lower() == "grand total":
            return [
                "background-color:#1E293B;color:#38BDF8;font-weight:800;text-align:center"
            ] * len(row)
        return [
            "background-color:#FFFFFF;color:#0F172A;text-align:center"
        ] * len(row)

    return df.style.apply(apply, axis=1).set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#0F172A"),
                ("color", "#fff"),
                ("font-weight", "800"),
                ("text-align", "center"),
                ("padding", "10px"),
            ],
        },
        {
            "selector": "td",
            "props": [("border", "1px solid #E2E8F0"), ("padding", "8px")],
        },
    ])


st.title("📑 Partner Performance Report")
st.caption(
    "Detailed Partner Analysis • SLA Breakdown (Up to >72 hrs) • Problem"
    " Classification"
)

ensure_ready()

with st.expander("🔄 Reload Data from Google Sheet"):
    if st.button("Reload DATA tab", type="primary"):
        try:
            sid = extract_sheet_id(DATA_URL)
            raw = load_sheet_as_csv(sid, gid=DATA_GID)
            processed = process_closed_tickets(raw)
            if "ticket_id" in processed.columns:
                processed = processed.drop_duplicates(
                    subset=["ticket_id"], keep="first"
                )
            st.session_state.raw_tickets_df = processed
            st.session_state.closed_df = processed
            st.success(f"Loaded {len(processed)} unique incidents")
            st.rerun()
        except Exception as e:
            st.error(str(e))

df = st.session_state.get("raw_tickets_df")
if df is None or df.empty:
    df = st.session_state.get("closed_df")
if df is None or df.empty:
    st.warning("Data nahi mila. Refresh button dabao.")
    st.stop()

work = df.copy()
if "ticket_id" in work.columns:
    work = work.drop_duplicates(subset=["ticket_id"], keep="first")

for a, b in {
    "Problem Classification": "problem_class",
    "Problem Related To": "problem_related",
    "Problem Reported": "problem_reported",
    "Root Cause": "root_cause",
}.items():
    if a in work.columns and b not in work.columns:
        work[b] = work[a]

if "submitted_time" in work.columns and "resolved_time" in work.columns:
    work = work.dropna(subset=["submitted_time", "resolved_time"])
    work["resolution_hours"] = (
        work["resolved_time"] - work["submitted_time"]
    ).dt.total_seconds() / 3600.0
    work = work[work["resolution_hours"] >= 0]
    work["month_key"] = work["resolved_time"].dt.to_period("M")
    work["month_label"] = work["resolved_time"].dt.strftime("%b-%y")
else:
    st.error("submitted_time / resolved_time missing")
    st.stop()

work["sla_band"] = work["resolution_hours"].apply(sla_bucket)
work["issue_type"] = work.apply(sheet_class, axis=1)
work["related_to"] = work.apply(sheet_related, axis=1)


def isp_of(val):
    s = str(val or "").upper()
    if "HCIN" in s:
        return "HCIN"
    if any(x in s for x in ["ONEOTT", "OTT", "CELERITY"]):
        return "ONEOTT"
    return "OTHER"


if "isp" not in work.columns:
    work["isp"] = work.get("owner", "").apply(isp_of)
else:
    work["isp"] = work["isp"].fillna("").astype(str)
    mask = work["isp"].isin(["", "OTHER", "nan"])
    if mask.any() and "owner" in work.columns:
        work.loc[mask, "isp"] = work.loc[mask, "owner"].apply(isp_of)

if "status" in work.columns:
    sl = work["status"].astype(str).str.lower()
    closed_mask = sl.str.contains("resolv|close", na=False)
    if closed_mask.any():
        work = work[closed_mask].copy()

st.markdown("---")
f_col1, f_col2 = st.columns([1, 2])
with f_col1:
    partner = st.radio("Select Partner", ["HCIN", "ONEOTT", "ALL"], horizontal=True)
with f_col2:
    months_n = st.selectbox(
        "Period Filter",
        [
            "Last 1 Month",
            "Last 2 Months",
            "Last 3 Months",
            "Last 4 Months",
            "Last 5 Months",
            "Last 6 Months",
            "Last 7 Months",
            "Overall",
        ],
        index=2,
    )

if partner != "ALL":
    work = work[work["isp"] == partner].copy()

max_dt = work["resolved_time"].max()
if pd.isna(max_dt):
    st.info("No resolved tickets for this selection.")
    st.stop()

if months_n == "Overall":
    selected = work.copy()
else:
    n = int(months_n.split()[1])
    start = (max_dt.to_period("M") - (n - 1)).to_timestamp()
    selected = work[work["resolved_time"] >= start].copy()

if selected.empty:
    st.warning("Is period / partner pe resolved data nahi hai.")
    st.stop()

# Key KPI summary cards
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
total_tkts = len(selected)
gt24 = len(selected[selected["resolution_hours"] > 24])
gt48 = len(selected[selected["resolution_hours"] > 48])
gt72 = len(selected[selected["resolution_hours"] > 72])

with kpi1:
    st.metric("Total Tickets", total_tkts)
with kpi2:
    st.metric("> 24 Hrs Outages", gt24)
with kpi3:
    st.metric("> 48 Hrs Outages", gt48)
with kpi4:
    st.metric("> 72 Hrs Outages", gt72)

st.markdown("---")

month_periods = sorted(selected["month_key"].dropna().unique().tolist())
month_labels = [
    pd.Period(p, freq="M").strftime("%b-%y") for p in month_periods
]

extra_cls = [
    c for c in selected["issue_type"].dropna().unique() if c not in CLASS_ORDER
]
all_cls = CLASS_ORDER + extra_cls

# ----------------- TABLE 1: SLA Resolution Time -----------------
sla_rows = []
for band in SLA_ORDER:
    row = {"SLA Bucket": band}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        cnt = int(
            (
                (selected["month_key"] == p) & (selected["sla_band"] == band)
            ).sum()
        )
        row[lab] = cnt
        total += cnt
    row["Grand Total"] = total
    sla_rows.append(row)

gt = {"SLA Bucket": "Grand Total"}
for lab in month_labels:
    gt[lab] = int(sum(r[lab] for r in sla_rows))
gt["Grand Total"] = int(sum(r["Grand Total"] for r in sla_rows))
sla_rows.append(gt)
sla_df = pd.DataFrame(sla_rows)

# ----------------- TABLE 2: Classification Details -----------------
cls_rows = []
for cls in all_cls:
    row = {"Problem Classification": cls}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        part = selected[
            (selected["month_key"] == p) & (selected["issue_type"] == cls)
        ]
        cnt = int(len(part))
        row[lab] = cnt if cnt else 0
        avg = part["resolution_hours"].mean() if len(part) else np.nan
        row[f"Avg Hrs ({lab})"] = (
            round(avg, 2) if pd.notna(avg) else "-"
        )
        total += cnt
    if total == 0:
        continue
    row["Grand Total"] = total
    cls_rows.append(row)

if cls_rows:
    gt2 = {"Problem Classification": "Grand Total"}
    for lab in month_labels:
        gt2[lab] = int(sum(int(r[lab] or 0) for r in cls_rows))
        gt2[f"Avg Hrs ({lab})"] = "-"
    gt2["Grand Total"] = int(sum(r["Grand Total"] for r in cls_rows))
    cls_rows.append(gt2)
cls_df = pd.DataFrame(cls_rows)

# ----------------- TABLE 3: Problem Related To -----------------
rel_rows = []
for rel in RELATED_ORDER + [
    x
    for x in selected["related_to"].dropna().unique()
    if x not in RELATED_ORDER
]:
    row = {"Problem Related To": rel}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        cnt = int(
            (
                (selected["month_key"] == p) & (selected["related_to"] == rel)
            ).sum()
        )
        row[lab] = cnt if cnt else 0
        total += cnt
    if total == 0:
        continue
    row["Grand Total"] = total
    rel_rows.append(row)

if rel_rows:
    gtr = {"Problem Related To": "Grand Total"}
    for lab in month_labels:
        gtr[lab] = int(sum(int(r[lab] or 0) for r in rel_rows))
    gtr["Grand Total"] = int(sum(r["Grand Total"] for r in rel_rows))
    rel_rows.append(gtr)
rel_df = pd.DataFrame(rel_rows) if rel_rows else pd.DataFrame()

# ----------------- TABLE 4: Repeat Incidents -----------------
repeat_idx = [
    "SINGLE TIME CALL LOG",
    "2 TIMES CALL LOG",
    "3 TIME CALL LOG",
    "4 Time Repeat",
    "5+ Time Repeat",
]
rep = {"REPEAT TIME": repeat_idx}
for p, lab in zip(month_periods, month_labels):
    mdf = selected[selected["month_key"] == p]
    vc = (
        mdf.groupby("site_code").size()
        if "site_code" in mdf.columns
        else pd.Series(dtype=int)
    )
    tt_vals, sc_vals = [], []
    for nrep in [1, 2, 3, 4]:
        sites = vc[vc == nrep]
        sc_vals.append(int(len(sites)))
        tt_vals.append(int(sites.sum()) if len(sites) else 0)
    sites5 = vc[vc >= 5]
    sc_vals.append(int(len(sites5)))
    tt_vals.append(int(sites5.sum()) if len(sites5) else 0)
    rep[f"{lab}-TT"] = tt_vals
    rep[f"{lab}-SITES"] = sc_vals
rep_df = pd.DataFrame(rep)

# ----------------- RENDER FULL WIDTH TABLES -----------------
st.subheader("1. Resolution Time Buckets (SLA)")
st.dataframe(style_blue(sla_df), use_container_width=True, hide_index=True)

st.subheader("2. Problem Classification & Avg Resolution Time")
st.dataframe(style_navy(cls_df), use_container_width=True, hide_index=True)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("3. Problem Related To")
    if not rel_df.empty:
        st.dataframe(style_blue(rel_df), use_container_width=True, hide_index=True)
    else:
        st.info("No Problem Related data available.")

with col_b:
    st.subheader("4. Repeat Call Analysis")
    st.dataframe(style_blue(rep_df), use_container_width=True, hide_index=True)


def to_xlsx():
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        sla_df.to_excel(writer, index=False, sheet_name="SLA_Buckets")
        cls_df.to_excel(writer, index=False, sheet_name="Classification")
        if not rel_df.empty:
            rel_df.to_excel(writer, index=False, sheet_name="Related_To")
        rep_df.to_excel(writer, index=False, sheet_name="Repeat")
        cols = [
            c
            for c in [
                "ticket_id",
                "site_code",
                "submitted_time",
                "resolved_time",
                "resolution_hours",
                "issue_type",
                "related_to",
                "owner",
                "isp",
                "state",
                "city",
                "down_time_min",
                "reason",
                "root_cause",
                "problem_reported",
            ]
            if c in selected.columns
        ]
        selected[cols].to_excel(
            writer, index=False, sheet_name="Ticket_Detail"
        )
    return out.getvalue()


st.markdown("---")
st.download_button(
    f"📥 Download {partner} Full Performance Report (Excel)",
    data=to_xlsx(),
    file_name=f"XTRNATE_{partner}_{months_n.replace(' ', '_')}_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
