import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats, merge_with_site_master
from utils.escalation import load_escalation_matrix, apply_escalation_to_open

st.set_page_config(page_title="Dashboard | XTRNATE", page_icon="📊", layout="wide")

st.title("📊 Command Dashboard")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

st.markdown(f"**Active Partner:** `{isp}`")

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')
site_master = st.session_state.get('site_master')

if closed_df is not None and isp != "ALL":
    closed_df = closed_df[closed_df['isp'] == isp].copy() if 'isp' in closed_df.columns else closed_df

if open_df is not None and isp != "ALL":
    open_df = open_df[open_df['isp'] == isp].copy() if 'isp' in open_df.columns else open_df

period = st.selectbox("Analysis Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "All Time"], index=0)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "All Time": "ALL"}

if closed_df is not None and not closed_df.empty:
    closed_filtered = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df
else:
    closed_filtered = pd.DataFrame()

st.markdown("### Key Performance Indicators")
col1, col2, col3, col4, col5 = st.columns(5)
stats = get_summary_stats(closed_filtered)

with col1:
    st.metric("Closed Tickets", stats.get('total_tickets', 0))
with col2:
    st.metric("Total Downtime (Hrs)", stats.get('total_downtime_hrs', 0))
with col3:
    st.metric("Avg Resolution (Hrs)", stats.get('avg_downtime_hrs', 0))
with col4:
    open_count = len(open_df) if open_df is not None else 0
    st.metric("Currently Open", open_count)
with col5:
    if open_df is not None and not open_df.empty and 'open_hours' in open_df.columns:
        critical = len(open_df[open_df['open_hours'] >= 8])
        st.metric("Critical Open (≥8h)", critical, delta_color="inverse")
    else:
        st.metric("Critical Open (≥8h)", 0)

st.markdown("---")

if not closed_filtered.empty:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Downtime by State")
        if 'state' in closed_filtered.columns and 'down_time_min' in closed_filtered.columns:
            state_df = closed_filtered.groupby('state')['down_time_min'].sum().reset_index()
            state_df = state_df.sort_values('down_time_min', ascending=False).head(10)
            state_df['hours'] = (state_df['down_time_min'] / 60).round(1)
            fig = px.bar(state_df, x='state', y='hours', color='hours',
                         color_continuous_scale='Blues', text='hours')
            fig.update_layout(template='plotly_dark', height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("State or Down Time column missing in data.")

    with col_right:
        st.subheader("Tickets by Owner / ISP")
        if 'owner' in closed_filtered.columns:
            owner_df = closed_filtered['owner'].value_counts().reset_index()
            owner_df.columns = ['owner', 'count']
            fig = px.pie(owner_df, names='owner', values='count', hole=0.4)
            fig.update_layout(template='plotly_dark', height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Owner column not found.")

    st.subheader("Top Down Reasons")
    if 'reason_clean' in closed_filtered.columns:
        reason_df = closed_filtered['reason_clean'].value_counts().head(8).reset_index()
        reason_df.columns = ['Reason', 'Count']
        fig = px.bar(reason_df, x='Count', y='Reason', orientation='h', color='Count',
                     color_continuous_scale='Teal')
        fig.update_layout(template='plotly_dark', height=400, yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    elif 'reason' in closed_filtered.columns:
        reason_df = closed_filtered['reason'].astype(str).str[:60].value_counts().head(8).reset_index()
        reason_df.columns = ['Reason', 'Count']
        fig = px.bar(reason_df, x='Count', y='Reason', orientation='h', color='Count',
                     color_continuous_scale='Teal')
        fig.update_layout(template='plotly_dark', height=400, yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Reason column not found.")

    # Show available columns for debugging
    with st.expander("Available columns in Closed data (for debugging)"):
        st.write(list(closed_filtered.columns))

else:
    st.info("No closed tickets data loaded. Please go to **Upload Data** page and upload Closed Tickets Excel.")

st.markdown("---")
st.subheader("🚨 Open Tickets Snapshot")
if open_df is not None and not open_df.empty:
    matrix = load_escalation_matrix(isp if isp != "ALL" else "HCIN")
    open_with_esc = apply_escalation_to_open(open_df, matrix)
    display_cols = ['ticket_id', 'site_code', 'status', 'state', 'open_hours', 'escalation_level', 'escalation_person', 'reason']
    display_cols = [c for c in display_cols if c in open_with_esc.columns]
    st.dataframe(
        open_with_esc[display_cols].sort_values('open_hours', ascending=False).head(15) if 'open_hours' in open_with_esc.columns else open_with_esc[display_cols].head(15),
        use_container_width=True,
        height=400
    )
else:
    st.info("No open tickets loaded.")
