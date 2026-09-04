import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats
from utils.escalation import load_escalation_matrix, apply_escalation_to_open
from utils.bootstrap import ensure_ready, apply_isp_filter, get_selected_isps
from utils.site_search import render_site_history_panel
from utils.report_download import download_pack
from utils.site_pack import render_multi_site_pack

st.set_page_config(page_title="Dashboard | XTRNATE", page_icon="📊", layout="wide")

st.markdown("""
<style>
@media (max-width: 768px) {
  .block-container { padding: 0.6rem !important; }
  div[data-testid="stMetricValue"] { font-size: 1.05rem !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Command Dashboard")
isp = ensure_ready()
st.caption(f"Active: **{isp}** • Data auto-loaded")

# Site search on dashboard too
with st.expander("🔍 Site Code Search (single site)", expanded=False):
    sq = st.text_input("Site Code", placeholder="XTNNTL358", key="dash_site_q")
    if sq:
        render_site_history_panel(sq.strip().upper())

with st.expander("📋 Multi-site pack — paste many site codes", expanded=True):
    render_multi_site_pack()
closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')
closed_df = apply_isp_filter(closed_df)
open_df = apply_isp_filter(open_df)

period = st.selectbox("Analysis Period (Closed)", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "All Time"], index=0)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "All Time": "ALL"}

if closed_df is not None and not closed_df.empty:
    closed_filtered = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df
else:
    closed_filtered = pd.DataFrame()

st.markdown("### Key Performance Indicators")
col1, col2, col3, col4, col5 = st.columns(5)
stats = get_summary_stats(closed_filtered)

col1.metric("Closed Tickets", stats.get('total_tickets', 0))
col2.metric("Total Downtime (Hrs)", stats.get('total_downtime_hrs', 0))
col3.metric("Avg Resolution (Hrs)", stats.get('avg_downtime_hrs', 0))
open_count = len(open_df) if open_df is not None else 0
col4.metric("Currently Open", open_count)
if open_df is not None and not open_df.empty and 'open_hours' in open_df.columns:
    col5.metric("Critical Open (≥8h)", len(open_df[open_df['open_hours'] >= 8]))
else:
    col5.metric("Critical Open (≥8h)", 0)

st.markdown("---")

if not closed_filtered.empty:
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Downtime by State")
        if 'state' in closed_filtered.columns and 'down_time_min' in closed_filtered.columns:
            state_df = closed_filtered.groupby('state')['down_time_min'].sum().reset_index()
            state_df = state_df.sort_values('down_time_min', ascending=False).head(10)
            state_df['hours'] = (state_df['down_time_min'] / 60).round(1)
            fig = px.bar(state_df, x='state', y='hours', color='hours', color_continuous_scale='Blues', text='hours')
            fig.update_layout(template='plotly_dark', height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("State / Down Time missing")
    with col_right:
        st.subheader("Tickets by Owner")
        if 'owner' in closed_filtered.columns:
            owner_df = closed_filtered['owner'].value_counts().reset_index()
            owner_df.columns = ['owner', 'count']
            fig = px.pie(owner_df, names='owner', values='count', hole=0.4)
            fig.update_layout(template='plotly_dark', height=350)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top Down Reasons")
    if 'reason_clean' in closed_filtered.columns:
        reason_df = closed_filtered['reason_clean'].value_counts().head(8).reset_index()
        reason_df.columns = ['Reason', 'Count']
        fig = px.bar(reason_df, x='Count', y='Reason', orientation='h', color='Count', color_continuous_scale='Teal')
        fig.update_layout(template='plotly_dark', height=400, yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Closed data loading... agar empty hai to sheet share check karo.")

st.markdown("---")
st.subheader("📞 Current Open Calls")
if open_df is not None and not open_df.empty:
    open_view = open_df.copy()
    if 'status' in open_view.columns:
        status_lower = open_view['status'].astype(str).str.lower()
        mask = status_lower.str.contains('assign to fe', na=False) | status_lower.str.contains('call on hold', na=False) | status_lower.str.contains('on hold', na=False)
        filtered_open = open_view[mask].copy() if mask.any() else open_view
    else:
        filtered_open = open_view

    matrix = load_escalation_matrix((get_selected_isps() or ["HCIN"])[0])
    open_with_esc = apply_escalation_to_open(filtered_open, matrix)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Open", len(open_with_esc))
    if 'escalation_level' in open_with_esc.columns:
        c2.metric("L1", len(open_with_esc[open_with_esc['escalation_level'] == 'L1']))
        c3.metric("L2+L3", len(open_with_esc[open_with_esc['escalation_level'].isin(['L2', 'L3'])]))
        c4.metric("L4", len(open_with_esc[open_with_esc['escalation_level'] == 'L4']))

    display_cols = [c for c in ['ticket_id', 'site_code', 'status', 'state', 'city', 'submitted_time', 'open_hours', 'escalation_level', 'reason', 'owner'] if c in open_with_esc.columns]
    sort_col = 'open_hours' if 'open_hours' in open_with_esc.columns else display_cols[0]
    show = open_with_esc[display_cols].sort_values(sort_col, ascending=False)
    st.dataframe(show, use_container_width=True, height=420)
    download_pack(
        "Open Calls",
        show,
        file_stem=f"Open_Calls_{isp}_{datetime.now().strftime('%Y%m%d')}",
        title=f"Dashboard Open Calls  ·  {isp}",
        sheet_name="Open_Calls",
        key="dash_open_dl",
    )
else:
    st.info("No open tickets right now.")
