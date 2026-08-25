import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period

st.set_page_config(page_title="Penalty & SLA | XTRNATE", page_icon="📜", layout="wide")

st.title("📜 Automated Penalty Calculation")
st.markdown("Data load hote hi SLA breach detect + penalty auto-calculate. Thresholds change kar sakte ho.")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Home se ISP select karo.")
    st.stop()

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("Closed data load karo (Google Sheet / Excel).")
    st.stop()

if isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()
if open_df is not None and not open_df.empty and isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

if 'resolution_days' not in df.columns:
    st.error("resolution_days nahi hai. Submitted Time + Resolved Time-Active chahiye.")
    st.stop()

# ========== DEFAULT AUTO RULES (session persistent) ==========
if 'penalty_rules' not in st.session_state:
    st.session_state.penalty_rules = {
        'l1_hours': 24,
        'l1_penalty': 500,
        'l2_hours': 72,
        'l2_penalty': 2000,
        'l3_hours': 120,
        'l3_penalty': 5000,
    }

with st.expander("⚙️ Penalty Rules (optional change — warna auto default chalega)"):
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
    st.caption("Rules save ho jati hain is session ke liye. Refresh pe default wapas.")

rules = st.session_state.penalty_rules

# ========== AUTO CALCULATE ==========
df = df.copy()
df['resolution_hours'] = pd.to_numeric(df['resolution_days'], errors='coerce') * 24

def calc_sla(hours):
    if pd.isna(hours):
        return 'Unknown', 0
    if hours > rules['l3_hours']:
        return 'L3 Critical', rules['l3_penalty']
    if hours > rules['l2_hours']:
        return 'L2 Breach', rules['l2_penalty']
    if hours > rules['l1_hours']:
        return 'L1 Breach', rules['l1_penalty']
    return 'Within SLA', 0

results = df['resolution_hours'].apply(lambda h: calc_sla(h))
df['sla_status'] = results.apply(lambda x: x[0])
df['penalty_est'] = results.apply(lambda x: x[1])

# ========== AUTO SUMMARY ==========
st.subheader("⚡ Auto-Calculated Summary")
st.caption(f"Rules: L1 >{rules['l1_hours']}h = ₹{rules['l1_penalty']} | L2 >{rules['l2_hours']}h = ₹{rules['l2_penalty']} | L3 >{rules['l3_hours']}h = ₹{rules['l3_penalty']}")

within = (df['sla_status'] == 'Within SLA').sum()
l1 = (df['sla_status'] == 'L1 Breach').sum()
l2 = (df['sla_status'] == 'L2 Breach').sum()
l3 = (df['sla_status'] == 'L3 Critical').sum()
total_pen = int(df['penalty_est'].sum())
breach_count = l1 + l2 + l3

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Tickets", len(df))
m2.metric("Within SLA", int(within))
m3.metric("L1 Breach", int(l1))
m4.metric("L2 Breach", int(l2))
m5.metric("L3 Critical", int(l3))
m6.metric("Auto Penalty ₹", f"{total_pen:,}")

st.success(f"**{breach_count}** tickets SLA breach | **Estimated Penalty: ₹{total_pen:,}**")

# Charts
col1, col2 = st.columns(2)
with col1:
    status_df = df['sla_status'].value_counts().reindex(
        ['Within SLA', 'L1 Breach', 'L2 Breach', 'L3 Critical', 'Unknown'], fill_value=0
    ).reset_index()
    status_df.columns = ['Status', 'Count']
    fig = px.pie(status_df, names='Status', values='Count', hole=0.4,
                 color='Status',
                 color_discrete_map={
                     'Within SLA': '#22c55e', 'L1 Breach': '#eab308',
                     'L2 Breach': '#f97316', 'L3 Critical': '#ef4444', 'Unknown': '#64748b'
                 })
    fig.update_layout(template='plotly_dark', height=360, title="SLA Status Distribution")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    if 'owner' in df.columns:
        pen_owner = df.groupby('owner').agg(
            tickets=('ticket_id', 'count'),
            penalty=('penalty_est', 'sum'),
            breaches=('penalty_est', lambda x: (x > 0).sum())
        ).reset_index().sort_values('penalty', ascending=False)
        fig = px.bar(pen_owner, x='owner', y='penalty', color='penalty',
                     color_continuous_scale='Reds', text='penalty',
                     title="Auto Penalty by Vendor/Owner (₹)")
        fig.update_layout(template='plotly_dark', height=360, xaxis_tickangle=-20)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Owner column nahi")

st.markdown("---")

# ========== VENDOR AUTO PENALTY TABLE ==========
st.subheader("🏭 Vendor-wise Auto Penalty")
if 'owner' in df.columns:
    vendor_pen = df.groupby('owner').agg(
        total_tickets=('ticket_id', 'count'),
        within_sla=('sla_status', lambda x: (x == 'Within SLA').sum()),
        breaches=('penalty_est', lambda x: (x > 0).sum()),
        total_penalty_inr=('penalty_est', 'sum'),
        avg_resolution_hrs=('resolution_hours', 'mean')
    ).reset_index()
    vendor_pen['avg_resolution_hrs'] = vendor_pen['avg_resolution_hrs'].round(1)
    vendor_pen['total_penalty_inr'] = vendor_pen['total_penalty_inr'].astype(int)
    vendor_pen = vendor_pen.sort_values('total_penalty_inr', ascending=False)
    st.dataframe(vendor_pen, use_container_width=True)
else:
    st.info("Owner missing")

st.markdown("---")

# ========== BREACH DETAIL ==========
st.subheader("🚨 Auto-Detected Breach Tickets")
breaches = df[df['penalty_est'] > 0].sort_values('resolution_hours', ascending=False)
if breaches.empty:
    st.success("Koi penalty applicable ticket nahi (current rules).")
else:
    cols = ['ticket_id', 'site_code', 'submitted_time', 'resolved_time', 'resolution_hours',
            'sla_status', 'penalty_est', 'owner', 'state', 'city', 'reason_clean']
    cols = [c for c in cols if c in breaches.columns]
    st.dataframe(breaches[cols], use_container_width=True, height=400)

st.markdown("---")

# ========== OPEN TICKETS PROJECTED PENALTY ==========
st.subheader("📞 Open Tickets — Projected Penalty (if closed now)")
st.caption("Jo tickets abhi open hain, unka current open hours ke hisaab se projected SLA / penalty")

if open_df is not None and not open_df.empty and 'open_hours' in open_df.columns:
    op = open_df.copy()
    op_results = op['open_hours'].apply(lambda h: calc_sla(h))
    op['projected_sla'] = op_results.apply(lambda x: x[0])
    op['projected_penalty'] = op_results.apply(lambda x: x[1])

    proj_total = int(op['projected_penalty'].sum())
    proj_breach = int((op['projected_penalty'] > 0).sum())

    st.metric("Open tickets already past SLA", proj_breach)
    st.metric("Projected penalty if resolved now (₹)", f"{proj_total:,}")

    op_show = op[op['projected_penalty'] > 0].sort_values('open_hours', ascending=False)
    if not op_show.empty:
        ocols = ['ticket_id', 'site_code', 'status', 'open_hours', 'projected_sla', 'projected_penalty', 'state', 'owner']
        ocols = [c for c in ocols if c in op_show.columns]
        st.dataframe(op_show[ocols], use_container_width=True, height=300)
    else:
        st.success("Saare open tickets abhi Within SLA hain.")
else:
    st.info("Open data nahi / open_hours missing")

# ========== DOWNLOAD ==========
st.markdown("---")

def to_excel(frames: dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, index=False, sheet_name=name[:31])
    return output.getvalue()

export = {
    'Breach_List': breaches[cols] if not breaches.empty else pd.DataFrame(),
}
if 'owner' in df.columns:
    export['Vendor_Penalty'] = vendor_pen

st.download_button(
    "📥 Download Auto Penalty Report (Excel)",
    data=to_excel(export),
    file_name=f"XTRNATE_Auto_Penalty_{isp}_{datetime.now().strftime('%Y%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.info("Penalty **auto** calculate hoti hai har load pe. Exact contract clause alag ho to rules expander mein values badal do.")
