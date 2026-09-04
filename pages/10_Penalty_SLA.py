import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, isp_options, classify_isp
from utils.auto_load import auto_load_tickets
from utils.bootstrap import ensure_ready, apply_isp_filter, get_selected_isps, isp_label
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

st.set_page_config(page_title="Penalty & SLA | XTRNATE", page_icon="📜", layout="wide")
ensure_ready()

# Exact CKT Page Custom CSS Theme
st.markdown("""
<style>
@media (max-width: 768px) {
  .block-container { padding: 0.6rem !important; }
}

.ckt-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 70%);
  border: 1px solid #38bdf8;
  border-radius: 18px;
  padding: 1.4rem 1.6rem 1.1rem 1.6rem;
  margin-bottom: 1.2rem;
  box-shadow: 0 10px 30px rgba(15,23,42,0.35);
}
.ckt-hero h1 { color: #fff; margin: 0 0 0.25rem 0; font-size: 1.7rem; }
.ckt-hero p { color: #cbd5e1; margin: 0; }

.ckt-card {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 1.2rem 1.4rem;
  margin-top: 0.8rem;
  margin-bottom: 1rem;
}
.ckt-label { color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.2rem; }
</style>
""", unsafe_allow_html=True)

# Hero Banner Integration
st.markdown("""
<div class="ckt-hero">
  <h1>📜 Automated Penalty — All ISPs (Owner)</h1>
  <p>Period-wise SLA breach &nbsp;•&nbsp; Site-wise down count & total downtime tracking</p>
</div>
""", unsafe_allow_html=True)

if st.session_state.get('closed_df') is None:
    with st.spinner("Auto-loading data..."):
        auto_load_tickets()

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi mila. Sheet share check karo.")
    st.stop()

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df_all = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()
df_all = apply_isp_filter(df_all)

if 'resolution_days' not in df_all.columns:
    st.error("resolution_days nahi hai. Submitted + Resolved Time-Active chahiye.")
    st.stop()

if 'penalty_rules' not in st.session_state:
    st.session_state.penalty_rules = {
        'l1_hours': 24, 'l1_penalty': 500,
        'l2_hours': 72, 'l2_penalty': 2000,
        'l3_hours': 120, 'l3_penalty': 5000,
    }

with st.expander("⚙️ Penalty Rules Configuration"):
    r = st.session_state.penalty_rules
    c1, c2, c3 = st.columns(3)
    with c1:
        r['l1_hours'] = st.number_input("L1 SLA (hrs)", value=int(r['l1_hours']), min_value=1)
        r['l1_penalty'] = st.number_input("L1 Penalty ₹", value=int(r['l1_penalty']), min_value=0, step=100)
    with c2:
        r['l2_hours'] = st.number_input("L2 SLA (hrs)", value=int(r['l2_hours']), min_value=1)
        r['l2_penalty'] = st.number_input("L2 Penalty ₹", value=int(r['l2_penalty']), min_value=0, step=100)
    with c3:
        r['l3_hours'] = st.number_input("L3 SLA (hrs)", value=int(r['l3_hours']), min_value=1)
        r['l3_penalty'] = st.number_input("L3 Penalty ₹", value=int(r['l3_penalty']), min_value=0, step=500)
    st.session_state.penalty_rules = r

rules = st.session_state.penalty_rules

def apply_penalty(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    d['resolution_hours'] = pd.to_numeric(d['resolution_days'], errors='coerce') * 24

    def calc(hours):
        if pd.isna(hours):
            return 'Unknown', 0
        if hours > rules['l3_hours']:
            return 'L3 Critical', rules['l3_penalty']
        if hours > rules['l2_hours']:
            return 'L2 Breach', rules['l2_penalty']
        if hours > rules['l1_hours']:
            return 'L1 Breach', rules['l1_penalty']
        return 'Within SLA', 0

    res = d['resolution_hours'].apply(calc)
    d['sla_status'] = res.apply(lambda x: x[0])
    d['penalty_est'] = res.apply(lambda x: x[1])
    return d

def get_isp_slice(df, name):
    if df is None or df.empty or 'isp' not in df.columns:
        return pd.DataFrame()
    return df[df['isp'] == name].copy()

def site_summary(d):
    """Per site: count, avg hours, total downtime, penalty."""
    if d is None or d.empty or 'site_code' not in d.columns:
        return pd.DataFrame()
    x = d.copy()
    if 'down_time_min' not in x.columns:
        x['down_time_min'] = x.get('resolution_hours', 0) * 60
    x['down_time_min'] = pd.to_numeric(x['down_time_min'], errors='coerce').fillna(0)
    x['resolution_hours'] = pd.to_numeric(x.get('resolution_hours', 0), errors='coerce').fillna(0)
    x['penalty_est'] = pd.to_numeric(x.get('penalty_est', 0), errors='coerce').fillna(0)

    g = x.groupby('site_code').agg(
        down_count=('ticket_id', 'count'),
        total_downtime_min=('down_time_min', 'sum'),
        avg_resolution_hrs=('resolution_hours', 'mean'),
        max_resolution_hrs=('resolution_hours', 'max'),
        total_penalty_inr=('penalty_est', 'sum'),
    ).reset_index()
    g['total_downtime_hrs'] = (g['total_downtime_min'] / 60).round(1)
    g['avg_resolution_hrs'] = g['avg_resolution_hrs'].round(1)
    g['max_resolution_hrs'] = g['max_resolution_hrs'].round(1)
    g['total_penalty_inr'] = g['total_penalty_inr'].astype(int)
    g = g.sort_values(['down_count', 'total_downtime_hrs'], ascending=False)

    if 'state' in x.columns:
        g['state'] = g['site_code'].map(x.groupby('site_code')['state'].first())
    return g



def summary_block(d):
    if d.empty:
        return {'total': 0, 'within': 0, 'l1': 0, 'l2': 0, 'l3': 0, 'penalty': 0, 'breaches': 0}
    return {
        'total': len(d),
        'within': int((d['sla_status'] == 'Within SLA').sum()),
        'l1': int((d['sla_status'] == 'L1 Breach').sum()),
        'l2': int((d['sla_status'] == 'L2 Breach').sum()),
        'l3': int((d['sla_status'] == 'L3 Critical').sum()),
        'penalty': int(d['penalty_est'].sum()),
        'breaches': int((d['penalty_est'] > 0).sum()),
    }

if "isp" not in df_all.columns and "owner" in df_all.columns:
    df_all["isp"] = df_all["owner"].map(classify_isp)

isp_names = isp_options(df_all, add_all=False)
picked = get_selected_isps()
if picked and isp_label(picked) not in ("ALL", "NONE"):
    isp_names = [n for n in isp_names if n in picked] or isp_names
if not isp_names and "isp" in df_all.columns:
    isp_names = [
        x for x in df_all["isp"].dropna().astype(str).unique()
        if x and x.upper() not in ("UNKNOWN", "OTHER", "NAN", "NONE")
    ]
if not isp_names:
    isp_names = ["HCIN", "ONEOTT"]

penalized = {name: apply_penalty(get_isp_slice(df_all, name)) for name in isp_names}
summaries = {name: summary_block(penalized[name]) for name in isp_names}
site_map = {name: site_summary(penalized[name]) for name in isp_names}
PALETTE = ["#38bdf8", "#f97316", "#a78bfa", "#22c55e", "#eab308", "#f43f5e", "#14b8a6"]
color_map = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(isp_names)}

st.subheader("⚡ ISP Penalty Summary (Owner ke saare ISP)")
for i in range(0, len(isp_names), 2):
    cols = st.columns(2)
    chunk = isp_names[i:i + 2]
    for j, name in enumerate(chunk):
        s = summaries[name]
        with cols[j]:
            st.markdown(
                f"""
        <div class="ckt-card">
          <div class="ckt-label">Vendor Overview</div>
          <h3 style="color:{color_map[name]}; margin:0;">🏢 {name}</h3>
        </div>
        """,
                unsafe_allow_html=True,
            )
            st.metric("Total Tickets", s["total"])
            a, b, c, d_ = st.columns(4)
            a.metric("Within", s["within"]); b.metric("L1", s["l1"]); c.metric("L2", s["l2"]); d_.metric("L3", s["l3"])
            st.metric("Penalty ₹", f"{s['penalty']:,}")

fig = px.bar(
    pd.DataFrame({"ISP": isp_names, "Penalty_INR": [summaries[n]["penalty"] for n in isp_names]}),
    x="ISP", y="Penalty_INR", color="ISP",
    color_discrete_map=color_map, text="Penalty_INR",
)
fig.update_layout(template="plotly_dark", height=320)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader(f"📍 Site-wise Down Count & Downtime — {period}")
st.caption("Har site: kitni baar down | avg/max hours | total downtime | estimated penalty")

tab_labels = [f"{n} Sites" for n in isp_names] + ["📋 Combined Data"]
tabs = st.tabs(tab_labels)

for i, name in enumerate(isp_names):
    with tabs[i]:
        sdf = site_map[name]
        if sdf.empty:
            st.info(f"{name} site data nahi")
        else:
            st.metric(f"Unique sites ({name})", len(sdf))
            st.dataframe(sdf, use_container_width=True, height=420)
            download_pack(
                f"{name} Site Summary",
                sdf,
                file_stem=f"Penalty_Sites_{name}_{period.replace(' ', '_')}",
                title=f"Penalty Site Summary  ·  {name}",
                subtitle=period,
                sheet_name="Sites",
                key=f"sites_dl_{i}_{name}",
            )

with tabs[-1]:
    parts = []
    for name in isp_names:
        sdf = site_map[name]
        if sdf is not None and not sdf.empty:
            copy = sdf.copy()
            copy.insert(0, "ISP", name)
            parts.append(copy)
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if combined.empty:
        st.info("No data available to display")
    else:
        st.dataframe(combined, use_container_width=True, height=420)
        penalty_sheets = {}
        for name in isp_names:
            sdf = site_map[name]
            if sdf is not None and not sdf.empty:
                penalty_sheets[f"{str(name)[:22]}_Sites"] = sdf
        penalty_sheets["Combined_Sites"] = combined
        download_pack(
            "Penalty & SLA Report",
            penalty_sheets,
            file_stem=f"XTRNATE_Formatted_Penalty_Report_{period.replace(' ', '_')}",
            title="Penalty & SLA Report",
            subtitle=period,
            key="penalty_combined_dl",
        )

st.markdown("---")
breach_tabs = st.tabs([f"{n} Breach Tickets" for n in isp_names])
show_cols = [
    "ticket_id", "site_code", "submitted_time", "resolved_time", "resolution_hours",
    "sla_status", "penalty_est", "state", "reason_clean", "owner",
]
for i, name in enumerate(isp_names):
    with breach_tabs[i]:
        d = penalized[name]
        if d is None or d.empty:
            st.info(f"{name} tickets nahi")
            continue
        hb = d[d["penalty_est"] > 0].sort_values("resolution_hours", ascending=False)
        if hb.empty:
            st.success(f"No {name} breaches")
        else:
            cols = [c for c in show_cols if c in hb.columns]
            st.dataframe(hb[cols], use_container_width=True, height=350)
