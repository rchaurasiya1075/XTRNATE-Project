import streamlit as st
import pandas as pd
import numpy as np
import sys
import os
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.data_processing import process_closed_tickets
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.bootstrap import ensure_ready

st.set_page_config(page_title="Partner Report | XTRNATE", page_icon="📑", layout="wide")

DATA_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
DATA_GID = 1980854633

CLASS_ORDER = [
    "Backend /Upstream issue/Node isolation at ISP end",
    "Fibre Cut",
    "Interface down/ Cable disconnected from SDWAN",
    "Maintenance activity by ISP",
    "No changes done",
    "ONU/Media converter/ZTE modem is faulty",
    "ONU/Media converter/ZTE modem Rebooted",
    "Others",
    "Power outage at ISP Node",
    "Problem in LAN connectivity.",
]

SLA_ORDER = ["<2 Hours", "2-4 Hours", "4-8 Hours", "8-12 Hours", "More than 24 Hours"]

UPTIME_ORDER = [
    "Between 80% to 75%",
    "Between 85% to 80%",
    "Between 90% to 85%",
    "Between 93% to 90%",
    "Between 96% to 93%",
    "Between 98% to 96%",
    "Greater than 98%",
]

def classify_problem(row):
    parts = []
    for col in ['problem_class', 'root_cause', 'reason', 'problem_related', 'problem_reported']:
        v = str(row.get(col, '') or '')
        if v and v.lower() not in ('nan', '--', 'none', ''):
            parts.append(v)
    text = " ".join(parts).lower()

    raw = str(row.get('problem_class', '') or '').strip()
    if raw and raw.lower() not in ('nan', '--', 'none'):
        # keep source label if it already matches known classes
        for c in CLASS_ORDER:
            if c.lower() in raw.lower() or raw.lower() in c.lower():
                return c

    if 'no changes done' in text:
        return "No changes done"
    if 'maintenance' in text:
        return "Maintenance activity by ISP"
    if ('interface down' in text) or ('sdwan' in text) or ('cable disconnect' in text):
        return "Interface down/ Cable disconnected from SDWAN"
    if ('lan connectivity' in text) or ('lan-cable' in text) or ('loose lan' in text):
        return "Problem in LAN connectivity."
    if ('rebooted' in text) or ('reboot' in text and ('onu' in text or 'modem' in text)):
        return "ONU/Media converter/ZTE modem Rebooted"
    if ('onu' in text or 'modem' in text or 'media converter' in text or 'zte' in text) and (
        'fault' in text or 'hang' in text or 'replace' in text or 'faulty' in text
    ):
        return "ONU/Media converter/ZTE modem is faulty"
    if 'fibre cut' in text or 'fiber cut' in text:
        return "Fibre Cut"
    if 'backend' in text or 'upstream' in text or 'node isolation' in text:
        return "Backend /Upstream issue/Node isolation at ISP end"
    if 'power outage' in text or 'pop end power' in text or 'power issue' in text:
        return "Power outage at ISP Node"
    if 'nff' in text or 'no issue' in text:
        return "Others"
    return "Others"

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
    return "More than 24 Hours"

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
        if str(row.iloc[0]).strip().lower() == 'grand total':
            return ['background-color:#00AEEF;color:#fff;font-weight:800;text-align:center'] * len(row)
        return ['background-color:#F8FAFC;color:#0F172A;text-align:center'] * len(row)
    return df.style.apply(apply, axis=1).set_table_styles([
        {'selector': 'th', 'props': [('background-color', '#00AEEF'), ('color', '#fff'),
                                     ('font-weight', '800'), ('text-align', 'center'), ('padding', '8px')]},
        {'selector': 'td', 'props': [('border', '1px solid #CBD5E1'), ('padding', '6px')]},
    ])

def style_navy(df):
    def apply(row):
        if str(row.iloc[0]).strip().lower() == 'grand total':
            return ['background-color:#DBEAFE;color:#1E3A8A;font-weight:800;text-align:center'] * len(row)
        return ['text-align:center'] * len(row)
    return df.style.apply(apply, axis=1).set_table_styles([
        {'selector': 'th', 'props': [('background-color', '#2563EB'), ('color', '#fff'),
                                     ('font-weight', '800'), ('text-align', 'center'), ('padding', '8px')]},
        {'selector': 'td', 'props': [('border', '1px solid #CBD5E1'), ('padding', '6px')]},
    ])

st.title("📑 Partner Performance Report")
st.caption("Format: SLA hours + Problem Classification + Uptime bands + Repeat calls  •  Source: Xtranet overall data")

ensure_ready()

with st.expander("Reload from Xtranet overall data"):
    if st.button("Reload DATA tab", type="primary"):
        try:
            sid = extract_sheet_id(DATA_URL)
            raw = load_sheet_as_csv(sid, gid=DATA_GID)
            processed = process_closed_tickets(raw)
            # keep extra source columns
            for col in raw.columns:
                key = str(col).strip()
                if key not in processed.columns:
                    processed[key] = raw[col]
            if 'ticket_id' in processed.columns:
                processed = processed.drop_duplicates(subset=['ticket_id'], keep='first')
            st.session_state.raw_tickets_df = processed
            st.session_state.closed_df = processed
            st.success(f"Loaded {len(processed)} unique incidents")
            st.rerun()
        except Exception as e:
            st.error(str(e))

df = st.session_state.get('raw_tickets_df')
if df is None or df.empty:
    df = st.session_state.get('closed_df')
if df is None or df.empty:
    st.warning("Data nahi mila. Reload dabao.")
    st.stop()

work = df.copy()
if 'ticket_id' in work.columns:
    work = work.drop_duplicates(subset=['ticket_id'], keep='first')

# map extra names
rename_extra = {
    'Problem Classification': 'problem_class',
    'Problem Related To': 'problem_related',
    'Problem Reported': 'problem_reported',
    'Root Cause': 'root_cause',
}
for a, b in rename_extra.items():
    if a in work.columns and b not in work.columns:
        work[b] = work[a]

# resolved hours from Submitted -> Resolved Time-Active only
if 'submitted_time' in work.columns and 'resolved_time' in work.columns:
    work = work.dropna(subset=['submitted_time', 'resolved_time'])
    work['resolution_hours'] = (work['resolved_time'] - work['submitted_time']).dt.total_seconds() / 3600.0
    work = work[work['resolution_hours'] >= 0]
    work['month_key'] = work['resolved_time'].dt.to_period('M')
    work['month_label'] = work['resolved_time'].dt.strftime('%b-%y')
else:
    st.error("submitted_time / resolved_time missing")
    st.stop()

work['sla_band'] = work['resolution_hours'].apply(sla_bucket)
work['issue_type'] = work.apply(classify_problem, axis=1)

def isp_of(val):
    s = str(val or '').upper()
    if 'HCIN' in s:
        return 'HCIN'
    if any(x in s for x in ['ONEOTT', 'OTT', 'CELERITY']):
        return 'ONEOTT'
    return 'OTHER'

if 'isp' not in work.columns:
    work['isp'] = work.get('owner', '').apply(isp_of)
else:
    work['isp'] = work['isp'].fillna('').astype(str)
    work.loc[work['isp'].isin(['', 'OTHER', 'nan']), 'isp'] = work.loc[work['isp'].isin(['', 'OTHER', 'nan']), 'owner'].apply(isp_of)

# only closed/resolved for this performance report
if 'status' in work.columns:
    sl = work['status'].astype(str).str.lower()
    closed_mask = sl.str.contains('resolv|close', na=False)
    if closed_mask.any():
        work = work[closed_mask].copy()

partner = st.radio("Report for", ["HCIN", "ONEOTT", "ALL"], horizontal=True)
months_n = st.selectbox("Period (last N months + Overall option)",
                        ["Last 1 Month", "Last 2 Months", "Last 3 Months", "Last 4 Months",
                         "Last 5 Months", "Last 6 Months", "Last 7 Months", "Overall"],
                        index=2)

if partner != "ALL":
    work = work[work['isp'] == partner].copy()

# month window from latest resolved date
max_dt = work['resolved_time'].max()
if pd.isna(max_dt):
    st.info("No resolved tickets")
    st.stop()

if months_n == "Overall":
    selected = work.copy()
else:
    n = int(months_n.split()[1])
    start = (max_dt.to_period('M') - (n - 1)).to_timestamp()
    selected = work[work['resolved_time'] >= start].copy()

if selected.empty:
    st.warning("Is period / partner pe resolved data nahi hai.")
    st.stop()

# month columns in chronological order
month_periods = sorted(selected['month_key'].dropna().unique().tolist())
month_labels = [pd.Period(p, freq='M').strftime('%b-%y') for p in month_periods]

# ========== TABLE 1: SLA buckets x Month ==========
sla_rows = []
for band in SLA_ORDER:
    row = {"Row Labels": band}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        cnt = int(((selected['month_key'] == p) & (selected['sla_band'] == band)).sum())
        row[lab] = cnt
        total += cnt
    row["Grand Total"] = total
    sla_rows.append(row)

gt = {"Row Labels": "Grand Total"}
for lab in month_labels:
    gt[lab] = int(sum(r[lab] for r in sla_rows))
gt["Grand Total"] = int(sum(r["Grand Total"] for r in sla_rows))
sla_rows.append(gt)
sla_df = pd.DataFrame(sla_rows)

# ========== TABLE 2: Problem Classification + Avg Hrs ==========
cls_rows = []
for cls in CLASS_ORDER:
    row = {"Problem Classification Terrestrial Calls": cls}
    for p, lab in zip(month_periods, month_labels):
        part = selected[(selected['month_key'] == p) & (selected['issue_type'] == cls)]
        row[lab] = int(len(part))
        avg = part['resolution_hours'].mean() if len(part) else np.nan
        row[f"Average Resolution (in Hrs) -{lab}"] = round(avg, 2) if pd.notna(avg) else ""
    cls_rows.append(row)

# grand total classification
gt2 = {"Problem Classification Terrestrial Calls": "Grand Total"}
for lab in month_labels:
    gt2[lab] = int(sum(r[lab] for r in cls_rows))
    gt2[f"Average Resolution (in Hrs) -{lab}"] = ""
cls_rows.append(gt2)
cls_df = pd.DataFrame(cls_rows)

# ========== TABLE 3: Uptime bands ==========
# period hours = days in selected window * 24
min_t = selected['resolved_time'].min()
max_t = selected['resolved_time'].max()
period_hours = max((max_t - min_t).total_seconds() / 3600.0, 24.0)
# better: calendar span of selected months
span_start = pd.Period(month_periods[0], freq='M').to_timestamp()
span_end = (pd.Period(month_periods[-1], freq='M') + 1).to_timestamp()
period_hours = max((span_end - span_start).total_seconds() / 3600.0, 24.0)

if 'down_time_min' in selected.columns:
    selected['down_hrs'] = pd.to_numeric(selected['down_time_min'], errors='coerce').fillna(0) / 60.0
else:
    selected['down_hrs'] = selected['resolution_hours']

site_up = selected.groupby('site_code', dropna=True).agg(down_hrs=('down_hrs', 'sum'), tickets=('ticket_id', 'count')).reset_index()
site_up['uptime_pct'] = (1 - (site_up['down_hrs'] / period_hours)).clip(0, 1) * 100
site_up['band'] = site_up['uptime_pct'].apply(uptime_band if False else uptime_bucket)

up_rows = []
for b in UPTIME_ORDER:
    up_rows.append({
        "UPTIME IN PERIOD": b,
        "Count of Sites": int((site_up['band'] == b).sum()),
        "Count of Tickets": int(site_up.loc[site_up['band'] == b, 'tickets'].sum()),
    })
up_rows.append({
    "UPTIME IN PERIOD": "Grand Total",
    "Count of Sites": int(len(site_up)),
    "Count of Tickets": int(site_up['tickets'].sum()),
})
up_df = pd.DataFrame(up_rows)

# ========== TABLE 4: Repeat per month ==========
repeat_idx = ["SINGLE TIME CALL LOG", "2 TIMES CALL LOG", "3 TIME CALL LOG", "4 Time Repeat", "5+ Time Repeat"]
rep_row_map = {1: "SINGLE TIME CALL LOG", 2: "2 TIMES CALL LOG", 3: "3 TIME CALL LOG", 4: "4 Time Repeat"}

rep = {"REPEAT TIME": repeat_idx}
for p, lab in zip(month_periods, month_labels):
    mdf = selected[selected['month_key'] == p]
    vc = mdf.groupby('site_code').size() if 'site_code' in mdf.columns else pd.Series(dtype=int)
    tt_vals, sc_vals = [], []
    for nrep, label in [(1, "SINGLE TIME CALL LOG"), (2, "2 TIMES CALL LOG"), (3, "3 TIME CALL LOG"), (4, "4 Time Repeat")]:
        sites = vc[vc == nrep]
        sc_vals.append(int(len(sites)))
        tt_vals.append(int(sites.sum()) if len(sites) else 0)
    sites5 = vc[vc >= 5]
    sc_vals.append(int(len(sites5)))
    tt_vals.append(int(sites5.sum()) if len(sites5) else 0)
    rep[f"{lab}-TT"] = tt_vals
    rep[f"{lab}-SITE CODE"] = sc_vals
rep_df = pd.DataFrame(rep)

# ========== RENDER ==========
st.markdown(f"### {partner}  •  {months_n}  •  Unique tickets: **{len(selected)}**")

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Resolution Time Buckets")
    st.dataframe(style_blue(sla_df), use_container_width=True, hide_index=True)
    st.markdown("#### Uptime bands (site-wise in selected months)")
    st.dataframe(style_blue(up_df), use_container_width=True, hide_index=True)

with c2:
    st.markdown("#### Problem Classification + Avg Resolution Hrs")
    st.dataframe(style_navy(cls_df), use_container_width=True, hide_index=True)
    st.markdown("#### Repeat Time (TT count vs unique Site Codes)")
    st.dataframe(style_blue(rep_df), use_container_width=True, hide_index=True)

def to_xlsx():
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        sla_df.to_excel(writer, index=False, sheet_name='SLA_Buckets')
        cls_df.to_excel(writer, index=False, sheet_name='Classification')
        up_df.to_excel(writer, index=False, sheet_name='Uptime')
        rep_df.to_excel(writer, index=False, sheet_name='Repeat')
        cols = [c for c in ['ticket_id', 'site_code', 'submitted_time', 'resolved_time',
                            'resolution_hours', 'issue_type', 'owner', 'isp', 'state', 'city',
                            'down_time_min', 'reason', 'root_cause'] if c in selected.columns]
        selected[cols].to_excel(writer, index=False, sheet_name='Ticket_Detail')
    return out.getvalue()

st.download_button(
    f"📥 Download {partner} Report Excel",
    data=to_xlsx(),
    file_name=f"XTRNATE_{partner}_{months_n.replace(' ', '_')}_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
