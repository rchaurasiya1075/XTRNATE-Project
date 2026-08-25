import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period

st.set_page_config(page_title="Penalty & SLA | XTRNATE", page_icon="📜", layout="wide")

st.title("📜 Contractual Penalty & SLA Tracker")
st.markdown("SLA breach detection + configurable penalty estimate (Closed tickets based on Submitted → Resolved Time)")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Home se ISP select karo.")
    st.stop()

closed_df = st.session_state.get('closed_df')
if closed_df is None or closed_df.empty:
    st.warning("Closed data load karo (Google Sheet / Excel).")
    st.stop()

if isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

if 'resolution_days' not in df.columns:
    st.error("resolution_days nahi bana. Submitted Time + Resolved Time-Active chahiye.")
    st.stop()

st.markdown(f"**ISP:** `{isp}` | Tickets: **{len(df)}**")

# ========== CONFIGURABLE THRESHOLDS ==========
st.subheader("⚙️ SLA / Penalty Settings (aap change kar sakte ho)")
st.caption("Apne contract ke hisaab se values set karo. Default common telecom-style thresholds hain.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    sla_hours_1 = st.number_input("SLA Level 1 (hours)", min_value=1, value=24, step=1)
with c2:
    penalty_1 = st.number_input("Penalty per ticket (₹) if > L1", min_value=0, value=500, step=100)
with c3:
    sla_hours_2 = st.number_input("SLA Level 2 (hours)", min_value=1, value=72, step=1)
with c4:
    penalty_2 = st.number_input("Penalty per ticket (₹) if > L2", min_value=0, value=2000, step=100)

c5, c6 = st.columns(2)
with c5:
    sla_hours_3 = st.number_input("SLA Level 3 (hours) — Critical", min_value=1, value=120, step=1)
with c6:
    penalty_3 = st.number_input("Penalty per ticket (₹) if > L3", min_value=0, value=5000, step=500)

# Convert days to hours for comparison
df = df.copy()
df['resolution_hours'] = df['resolution_days'] * 24

def assign_breach(hours):
    if pd.isna(hours):
        return 'Unknown'
    if hours > sla_hours_3:
        return 'L3 Critical'
    if hours > sla_hours_2:
        return 'L2 Breach'
    if hours > sla_hours_1:
        return 'L1 Breach'
    return 'Within SLA'

def assign_penalty(level):
    if level == 'L3 Critical':
        return penalty_3
    if level == 'L2 Breach':
        return penalty_2
    if level == 'L1 Breach':
        return penalty_1
    return 0

df['sla_status'] = df['resolution_hours'].apply(assign_breach)
df['penalty_est'] = df['sla_status'].apply(assign_penalty)

# ========== SUMMARY ==========
st.subheader("📊 SLA Breach Summary")

within = len(df[df['sla_status'] == 'Within SLA'])
l1 = len(df[df['sla_status'] == 'L1 Breach'])
l2 = len(df[df['sla_status'] == 'L2 Breach'])
l3 = len(df[df['sla_status'] == 'L3 Critical'])
total_penalty = df['penalty_est'].sum()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Within SLA", within)
m2.metric("L1 Breach", l1)
m3.metric("L2 Breach", l2)
m4.metric("L3 Critical", l3)
m5.metric("Est. Total Penalty (₹)", f"{total_penalty:,.0f}")

# Charts
col1, col2 = st.columns(2)
with col1:
    status_counts = df['sla_status'].value_counts().reindex(
        ['Within SLA', 'L1 Breach', 'L2 Breach', 'L3 Critical', 'Unknown'], fill_value=0
    ).reset_index()
    status_counts.columns = ['SLA Status', 'Count']
    fig = px.pie(status_counts, names='SLA Status', values='Count', hole=0.4,
                 color='SLA Status',
                 color_discrete_map={
                     'Within SLA': '#22c55e',
                     'L1 Breach': '#eab308',
                     'L2 Breach': '#f97316',
                     'L3 Critical': '#ef4444',
                     'Unknown': '#94a3b8'
                 })
    fig.update_layout(template='plotly_dark', height=380)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    if 'owner' in df.columns:
        pen_by_owner = df.groupby('owner')['penalty_est'].sum().reset_index()
        pen_by_owner = pen_by_owner.sort_values('penalty_est', ascending=False)
        fig = px.bar(pen_by_owner, x='owner', y='penalty_est', color='penalty_est',
                     color_continuous_scale='Reds', text='penalty_est',
                     title="Estimated Penalty by Owner/Vendor (₹)")
        fig.update_layout(template='plotly_dark', height=380, xaxis_tickangle=-25)
        st.plotly_chart(fig, use_container_width=True)
    elif 'state' in df.columns:
        pen_by_state = df.groupby('state')['penalty_est'].sum().reset_index()
        pen_by_state = pen_by_state.sort_values('penalty_est', ascending=False).head(10)
        fig = px.bar(pen_by_state, x='state', y='penalty_est', color='penalty_est',
                     color_continuous_scale='Reds', text='penalty_est',
                     title="Estimated Penalty by State (₹)")
        fig.update_layout(template='plotly_dark', height=380)
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========== BREACH LIST ==========
st.subheader("🚨 SLA Breach Tickets (Penalty applicable)")

breaches = df[df['sla_status'].isin(['L1 Breach', 'L2 Breach', 'L3 Critical'])].copy()
if breaches.empty:
    st.success("Is period mein koi SLA breach nahi (selected thresholds ke hisaab se).")
else:
    breaches = breaches.sort_values('resolution_hours', ascending=False)
    show_cols = ['ticket_id', 'site_code', 'submitted_time', 'resolved_time',
                 'resolution_days', 'resolution_hours', 'sla_status', 'penalty_est',
                 'owner', 'state', 'city', 'reason_clean', 'category']
    show_cols = [c for c in show_cols if c in breaches.columns]
    st.dataframe(breaches[show_cols], use_container_width=True, height=420)

    st.download_button(
        "📥 Download Breach List + Penalty",
        data=breaches[show_cols].to_csv(index=False).encode('utf-8'),
        file_name=f"XTRNATE_SLA_Breaches_{isp}.csv",
        mime="text/csv"
    )

st.markdown("---")
st.info("""
**Note:** Yeh **estimate** hai. Actual contractual penalty clauses aapke agreement mein define hote hain  
(fixed per hour, % of monthly fee, cap, exclusions jaise force majeure / customer end).

Agar aap exact clause bhejoge (e.g. "after 24 hrs ₹500/hr" ya "% of link charge"),  
to formula uske hisaab se update kar dunga.
""")
