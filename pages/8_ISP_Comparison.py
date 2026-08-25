import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats

st.set_page_config(page_title="ISP Comparison | XTRNATE", page_icon="⚖️", layout="wide")

st.title("⚖️ HCIN vs ONEOTT Comparison")
st.markdown("Side-by-side comparison of both ISPs — Closed + Open metrics")

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if (closed_df is None or closed_df.empty) and (open_df is None or open_df.empty):
    st.warning("Data nahi hai. Pehle **Upload Data** ya Dashboard se Google Sheet load karo.")
    st.stop()

# Period filter for closed
period = st.radio(
    "Period (Closed tickets)",
    ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"],
    horizontal=True
)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}

def get_isp_data(df, isp_name):
    if df is None or df.empty:
        return pd.DataFrame()
    if 'isp' not in df.columns:
        return df.copy()
    return df[df['isp'] == isp_name].copy()

# Closed split
if closed_df is not None and not closed_df.empty:
    closed_all = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()
else:
    closed_all = pd.DataFrame()

hcin_closed = get_isp_data(closed_all, 'HCIN')
ott_closed = get_isp_data(closed_all, 'ONEOTT')

# Open split
hcin_open = get_isp_data(open_df, 'HCIN') if open_df is not None else pd.DataFrame()
ott_open = get_isp_data(open_df, 'ONEOTT') if open_df is not None else pd.DataFrame()

# ========== KPI COMPARISON ==========
st.subheader("📊 Key Metrics Comparison")

hcin_stats = get_summary_stats(hcin_closed)
ott_stats = get_summary_stats(ott_closed)

metrics = [
    ("Closed Tickets", hcin_stats.get('total_tickets', 0), ott_stats.get('total_tickets', 0)),
    ("Total Downtime (Hrs)", hcin_stats.get('total_downtime_hrs', 0), ott_stats.get('total_downtime_hrs', 0)),
    ("Avg Resolution (Hrs)", hcin_stats.get('avg_downtime_hrs', 0), ott_stats.get('avg_downtime_hrs', 0)),
    ("Currently Open", len(hcin_open), len(ott_open)),
]

cols = st.columns(4)
for i, (label, h_val, o_val) in enumerate(metrics):
    with cols[i]:
        st.markdown(f"**{label}**")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("HCIN", h_val)
        with c2:
            st.metric("ONEOTT", o_val)

# Bar comparison chart
st.markdown("#### Closed Tickets & Open Calls")
comp_df = pd.DataFrame({
    'Metric': ['Closed Tickets', 'Closed Tickets', 'Open Calls', 'Open Calls'],
    'ISP': ['HCIN', 'ONEOTT', 'HCIN', 'ONEOTT'],
    'Count': [
        hcin_stats.get('total_tickets', 0),
        ott_stats.get('total_tickets', 0),
        len(hcin_open),
        len(ott_open)
    ]
})
fig = px.bar(comp_df, x='Metric', y='Count', color='ISP', barmode='group',
             color_discrete_map={'HCIN': '#38bdf8', 'ONEOTT': '#f97316'}, text='Count')
fig.update_layout(template='plotly_dark', height=380)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========== STATE COMPARISON ==========
st.subheader("🗺️ State-wise Comparison (Closed)")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**HCIN — Top States**")
    if not hcin_closed.empty and 'state' in hcin_closed.columns:
        s = hcin_closed['state'].value_counts().head(10).reset_index()
        s.columns = ['State', 'Count']
        fig = px.bar(s, x='State', y='Count', color='Count', color_continuous_scale='Blues', text='Count')
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("HCIN closed data nahi / state missing")

with col2:
    st.markdown("**ONEOTT — Top States**")
    if not ott_closed.empty and 'state' in ott_closed.columns:
        s = ott_closed['state'].value_counts().head(10).reset_index()
        s.columns = ['State', 'Count']
        fig = px.bar(s, x='State', y='Count', color='Count', color_continuous_scale='Oranges', text='Count')
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ONEOTT closed data nahi / state missing")

st.markdown("---")

# ========== CATEGORY COMPARISON ==========
st.subheader("📁 Category Comparison (Closed)")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**HCIN Categories**")
    if not hcin_closed.empty and 'category' in hcin_closed.columns:
        c = hcin_closed['category'].value_counts().reset_index()
        c.columns = ['Category', 'Count']
        fig = px.pie(c, names='Category', values='Count', hole=0.4)
        fig.update_layout(template='plotly_dark', height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Category nahi mila")

with col2:
    st.markdown("**ONEOTT Categories**")
    if not ott_closed.empty and 'category' in ott_closed.columns:
        c = ott_closed['category'].value_counts().reset_index()
        c.columns = ['Category', 'Count']
        fig = px.pie(c, names='Category', values='Count', hole=0.4)
        fig.update_layout(template='plotly_dark', height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Category nahi mila")

st.markdown("---")

# ========== OPEN CALLS COMPARISON ==========
st.subheader("📞 Current Open Calls Comparison")

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"**HCIN Open: {len(hcin_open)}**")
    if not hcin_open.empty:
        cols_show = [c for c in ['ticket_id', 'site_code', 'status', 'state', 'open_hours', 'reason'] if c in hcin_open.columns]
        st.dataframe(hcin_open[cols_show].head(15), use_container_width=True, height=300)
    else:
        st.info("No HCIN open tickets")

with col2:
    st.markdown(f"**ONEOTT Open: {len(ott_open)}**")
    if not ott_open.empty:
        cols_show = [c for c in ['ticket_id', 'site_code', 'status', 'state', 'open_hours', 'reason'] if c in ott_open.columns]
        st.dataframe(ott_open[cols_show].head(15), use_container_width=True, height=300)
    else:
        st.info("No ONEOTT open tickets")

st.markdown("---")

# ========== SUMMARY TABLE ==========
st.subheader("📋 Summary Table")

summary = pd.DataFrame({
    'Metric': [
        'Closed Tickets',
        'Total Downtime (Hrs)',
        'Avg Resolution (Hrs)',
        'Open Calls',
        'Critical Open (≥8h)' if True else 'Critical Open'
    ],
    'HCIN': [
        hcin_stats.get('total_tickets', 0),
        hcin_stats.get('total_downtime_hrs', 0),
        hcin_stats.get('avg_downtime_hrs', 0),
        len(hcin_open),
        len(hcin_open[hcin_open['open_hours'] >= 8]) if not hcin_open.empty and 'open_hours' in hcin_open.columns else 0
    ],
    'ONEOTT': [
        ott_stats.get('total_tickets', 0),
        ott_stats.get('total_downtime_hrs', 0),
        ott_stats.get('avg_downtime_hrs', 0),
        len(ott_open),
        len(ott_open[ott_open['open_hours'] >= 8]) if not ott_open.empty and 'open_hours' in ott_open.columns else 0
    ]
})

st.dataframe(summary, use_container_width=True)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Comparison')
    return output.getvalue()

st.download_button(
    "📥 Download Comparison Summary",
    data=to_excel(summary),
    file_name="XTRNATE_HCIN_vs_ONEOTT_Comparison.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
