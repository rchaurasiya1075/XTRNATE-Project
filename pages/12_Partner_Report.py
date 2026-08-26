import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.data_processing import filter_by_period, process_closed_tickets
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.bootstrap import ensure_ready

st.set_page_config(page_title="Partner Report | XTRNATE", page_icon="📑", layout="wide")

st.title("📑 Partner Report — HCIN / ONEOTT")
st.caption("Data sheet se • Unique Incident ID • Resolve = Resolved Time-Active only • Close Time ignore")

ensure_ready()

DATA_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
DATA_GID = 1980854633

# Extra column mapping if present on source
EXTRA_RENAME = {
    'Problem Reported': 'problem_reported',
    'Problem Related To': 'problem_related',
    'Problem Classification': 'problem_class',
    'Root Cause': 'root_cause',
    'Last Enclosure Comment(Active)': 'reason',
    'Incident ID': 'ticket_id',
    'Request Title': 'site_code',
    'Submitted Time': 'submitted_time',
    'CurrentStatus': 'status',
    'Current Status': 'status',
    'Owner': 'owner',
    'State': 'state',
    'City': 'city',
    'Resolved Time-Active': 'resolved_time',
    'Down Time': 'down_time_min',
}

def classify_issue(row):
    for col in ['problem_class', 'root_cause', 'reason', 'problem_related', 'problem_reported']:
        val = str(row.get(col, '') or '').lower()
        if val in ('', 'nan', '--', 'none'):
            continue
        if 'fibre cut' in val or 'fiber cut' in val:
            return 'Fibre Cut'
        if 'backend' in val or 'upstream' in val or 'node isolation' in val:
            return 'Backend / Upstream / Node Isolation'
        if 'force maj' in val or 'natural calamity' in val or 'landslide' in val or 'rain' in val:
            return 'Force Majeure / Natural Calamity'
        if 'onu' in val or 'modem' in val or 'media converter' in val or 'zte' in val:
            return 'ONU / Modem / Media Converter'
        if 'housekeep' in val:
            return 'Housekeeping'
        if 'third party' in val or 'vendor' in val:
            return 'Third Party'
        if 'nff' in val or 'no issue' in val or 'no changes' in val:
            return 'NFF / No Issue'
        if 'power' in val:
            return 'Power Issue'
        if 'sdwan' in val or 'interface down' in val or 'cable disconnect' in val:
            return 'Interface / Cable / SDWAN'
        if 'customer' in val or 'lan' in val:
            return 'Customer End'
    return 'Others'

with st.expander("☁️ Reload from DATA sheet (gid 1980854633)"):
    if st.button("Reload DATA tab now", type="primary"):
        try:
            sid = extract_sheet_id(DATA_URL)
            raw = load_sheet_as_csv(sid, gid=DATA_GID)
            processed = process_closed_tickets(raw)
            if 'ticket_id' in processed.columns:
                processed = processed.drop_duplicates(subset=['ticket_id'], keep='first')
            # attach extra cols if process dropped them
            for src, dst in EXTRA_RENAME.items():
                if src in raw.columns and dst not in processed.columns:
                    processed[dst] = raw[src]
            st.session_state.raw_tickets_df = processed
            st.session_state.closed_df = processed
            st.success(f"Loaded {len(processed)} unique incidents")
            st.rerun()
        except Exception as e:
            st.error(str(e))

df = st.session_state.get('raw_tickets_df')
if df is None or (hasattr(df, 'empty') and df.empty):
    df = st.session_state.get('closed_df')

if df is None or df.empty:
    st.warning("Data nahi mila. Home pe auto-load wait karo ya upar Reload dabao.")
    st.stop()

work = df.copy()
if 'ticket_id' in work.columns:
    work = work.drop_duplicates(subset=['ticket_id'], keep='first')

# Extra fields from original names if still present
for src, dst in EXTRA_RENAME.items():
    if src in work.columns and dst not in work.columns:
        work[dst] = work[src]

work['issue_type'] = work.apply(classify_issue, axis=1)

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
pmap = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
if pmap[period] != "ALL" and 'submitted_time' in work.columns:
    work = filter_by_period(work, pmap[period])

def isp_of(val):
    s = str(val or '').upper()
    if 'HCIN' in s:
        return 'HCIN'
    if 'ONEOTT' in s or 'OTT' in s or 'CELERITY' in s:
        return 'ONEOTT'
    return 'OTHER'

if 'isp' not in work.columns:
    work['isp'] = work.get('owner', pd.Series([''] * len(work))).apply(isp_of)

# Only resolved/closed for closed-report; keep all with status filter
status_opt = st.multiselect(
    "Status filter",
    options=sorted(work['status'].dropna().astype(str).unique().tolist()) if 'status' in work.columns else [],
    default=None,
)
if status_opt and 'status' in work.columns:
    work = work[work['status'].astype(str).isin(status_opt)]

hcin = work[work['isp'] == 'HCIN'].copy() if 'isp' in work.columns else pd.DataFrame()
ott = work[work['isp'] == 'ONEOTT'].copy() if 'isp' in work.columns else pd.DataFrame()

report_cols = [
    'ticket_id', 'site_code', 'submitted_time', 'resolved_time', 'status',
    'owner', 'isp', 'state', 'city', 'down_time_min', 'resolution_days',
    'issue_type', 'root_cause', 'problem_class', 'problem_related', 'problem_reported',
    'reason'
]

def kpi_block(d, title):
    st.markdown(f"### {title}")
    t = len(d)
    resolved = 0
    if 'status' in d.columns:
        sl = d['status'].astype(str).str.lower()
        resolved = int(sl.str.contains('resolv|close', na=False).sum())
    dt_hrs = 0
    if 'down_time_min' in d.columns:
        dt_hrs = round(pd.to_numeric(d['down_time_min'], errors='coerce').fillna(0).sum() / 60, 1)
    avg_d = 0
    if 'resolution_days' in d.columns and d['resolution_days'].notna().any():
        avg_d = round(pd.to_numeric(d['resolution_days'], errors='coerce').mean(), 1)
    a, b, c, dlt = st.columns(4)
    a.metric("Unique Tickets", t)
    b.metric("Resolved / Closed", resolved)
    c.metric("Total Downtime Hrs", dt_hrs)
    dlt.metric("Avg Resolution Days", avg_d)

def charts(d, color):
    c1, c2 = st.columns(2)
    with c1:
        if 'issue_type' in d.columns and not d.empty:
            g = d['issue_type'].value_counts().reset_index()
            g.columns = ['Issue Type', 'Count']
            fig = px.bar(g, x='Issue Type', y='Count', color='Count', color_continuous_scale=color, text='Count')
            fig.update_layout(template='plotly_dark', height=340, xaxis_tickangle=-25)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if 'state' in d.columns and not d.empty:
            g = d['state'].value_counts().head(10).reset_index()
            g.columns = ['State', 'Count']
            fig = px.bar(g, x='State', y='Count', color='Count', color_continuous_scale=color, text='Count')
            fig.update_layout(template='plotly_dark', height=340, xaxis_tickangle=-25)
            st.plotly_chart(fig, use_container_width=True)

def table(d):
    cols = [c for c in report_cols if c in d.columns]
    show = d[cols].copy()
    if 'submitted_time' in show.columns:
        show = show.sort_values('submitted_time', ascending=False)
    st.dataframe(show, use_container_width=True, height=420)
    return show

def to_xlsx(frames: dict):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        for name, frame in frames.items():
            if frame is not None and not frame.empty:
                frame.to_excel(writer, index=False, sheet_name=name[:31])
    return out.getvalue()

tab_h, tab_o, tab_b = st.tabs(["🏢 HCIN Report", "🌐 ONEOTT Report", "📊 Combined"])

with tab_h:
    kpi_block(hcin, "HCIN")
    charts(hcin, 'Blues')
    st.markdown("#### HCIN ticket list (unique Incident ID)")
    h_show = table(hcin) if not hcin.empty else pd.DataFrame()
    if not hcin.empty:
        st.download_button("📥 Download HCIN Report", data=to_xlsx({'HCIN': h_show}),
                           file_name=f"HCIN_Partner_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_hcin_rep")

with tab_o:
    kpi_block(ott, "ONEOTT / CELERITY")
    charts(ott, 'Oranges')
    st.markdown("#### ONEOTT ticket list (unique Incident ID)")
    o_show = table(ott) if not ott.empty else pd.DataFrame()
    if not ott.empty:
        st.download_button("📥 Download OTT Report", data=to_xlsx({'ONEOTT': o_show}),
                           file_name=f"ONEOTT_Partner_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_ott_rep")

with tab_b:
    kpi_block(work, "ALL Partners")
    both = pd.concat([
        hcin.assign(_p='HCIN') if not hcin.empty else pd.DataFrame(),
        ott.assign(_p='ONEOTT') if not ott.empty else pd.DataFrame()
    ], ignore_index=True) if not hcin.empty or not ott.empty else pd.DataFrame()
    if not both.empty:
        cols = [c for c in ['_p'] + report_cols if c in both.columns]
        st.dataframe(both[cols], use_container_width=True, height=400)
        st.download_button("📥 Download Combined",
                           data=to_xlsx({'HCIN': hcin, 'ONEOTT': ott, 'ALL': both}),
                           file_name=f"Partner_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_both_rep")

st.info("Existing Dashboard / Monthly SLA / Penalty pages same hain. Yeh **naya alag section** hai.")
