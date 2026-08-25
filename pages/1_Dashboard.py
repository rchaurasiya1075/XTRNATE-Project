import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats
from utils.escalation import load_escalation_matrix, apply_escalation_to_open
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.data_processing import process_closed_tickets, process_open_tickets

st.set_page_config(page_title="Dashboard | XTRNATE", page_icon="📊", layout="wide")

st.title("📊 Command Dashboard")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

st.markdown(f"**Active Partner:** `{isp}`")

# ========== QUICK LOAD FROM GOOGLE SHEET ==========
with st.expander("☁️ Quick Load from Google Sheet (agar data nahi hai)"):
    st.caption("Aapka tickets sheet already set hai. Load dabao → Auto Split (Open + Closed)")
    default_url = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
    if st.button("🔄 Load Tickets from Google Sheet", type="primary"):
        try:
            sheet_id = extract_sheet_id(default_url)
            with st.spinner("Loading..."):
                df = load_sheet_as_csv(sheet_id, gid=0)
            processed = process_closed_tickets(df)
            if 'status' in processed.columns:
                status_str = processed['status'].astype(str).str.lower()
                open_mask = (
                    status_str.str.contains('assign to fe', na=False) |
                    status_str.str.contains('call on hold', na=False) |
                    status_str.str.contains('on hold', na=False)
                )
                open_part = processed[open_mask].copy()
                closed_part = processed[~open_mask].copy()
                if not open_part.empty:
                    open_part = process_open_tickets(open_part)
                st.session_state.closed_df = closed_part if not closed_part.empty else None
                st.session_state.open_df = open_part if not open_part.empty else None
                st.success(f"Loaded! Closed: {len(closed_part)} | Open: {len(open_part)}")
                st.rerun()
            else:
                st.session_state.closed_df = processed
                st.warning("Status column nahi mila")
                st.rerun()
        except Exception as e:
            st.error(str(e))
            st.info("Sheet Share → Anyone with the link → Viewer hona chahiye.")

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is not None and isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()
if open_df is not None and isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()

period = st.selectbox("Analysis Period (Closed)", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "All Time"], index=0)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "All Time": "ALL"}

if closed_df is not None and not closed_df.empty:
    closed_filtered = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df
else:
    closed_filtered = pd.DataFrame()

# ========== KPIs ==========
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

# ========== CLOSED SECTION (same as before) ==========
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
            st.info("State or Down Time column missing.")

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
    st.info("No closed tickets data. Google Sheet se Load karo ya Upload Data page use karo.")

# ========== CURRENT OPEN CALLS SECTION (NEW / EXPANDED) ==========
st.markdown("---")
st.subheader("📞 Current Open Calls (Assign to FE + Call on Hold)")
st.caption("Data Google Sheet se aata hai — Current Status = Assign to FE / Call on Hold")

if open_df is not None and not open_df.empty:
    # Ensure only open statuses if status column exists
    open_view = open_df.copy()
    if 'status' in open_view.columns:
        status_lower = open_view['status'].astype(str).str.lower()
        mask = (
            status_lower.str.contains('assign to fe', na=False) |
            status_lower.str.contains('call on hold', na=False) |
            status_lower.str.contains('on hold', na=False)
        )
        filtered_open = open_view[mask].copy()
        if filtered_open.empty:
            filtered_open = open_view  # fallback
    else:
        filtered_open = open_view

    matrix = load_escalation_matrix(isp if isp != "ALL" else "HCIN")
    open_with_esc = apply_escalation_to_open(filtered_open, matrix)

    # Summary cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Open", len(open_with_esc))
    with c2:
        l1 = len(open_with_esc[open_with_esc['escalation_level'] == 'L1']) if 'escalation_level' in open_with_esc.columns else 0
        st.metric("L1", l1)
    with c3:
        l2_l3 = 0
        if 'escalation_level' in open_with_esc.columns:
            l2_l3 = len(open_with_esc[open_with_esc['escalation_level'].isin(['L2', 'L3'])])
        st.metric("L2 + L3", l2_l3)
    with c4:
        l4 = len(open_with_esc[open_with_esc['escalation_level'] == 'L4']) if 'escalation_level' in open_with_esc.columns else 0
        st.metric("L4 Critical", l4)

    # Charts
    col_a, col_b = st.columns(2)
    with col_a:
        if 'state' in open_with_esc.columns:
            st.markdown("#### Open by State")
            state_o = open_with_esc['state'].value_counts().reset_index()
            state_o.columns = ['State', 'Count']
            fig = px.bar(state_o, x='State', y='Count', color='Count', text='Count',
                         color_continuous_scale='Oranges')
            fig.update_layout(template='plotly_dark', height=320)
            st.plotly_chart(fig, use_container_width=True)
    with col_b:
        if 'status' in open_with_esc.columns:
            st.markdown("#### Open by Status")
            status_o = open_with_esc['status'].value_counts().reset_index()
            status_o.columns = ['Status', 'Count']
            fig = px.pie(status_o, names='Status', values='Count', hole=0.4)
            fig.update_layout(template='plotly_dark', height=320)
            st.plotly_chart(fig, use_container_width=True)

    # Full table
    st.markdown("#### All Current Open Calls")
    display_cols = [
        'ticket_id', 'site_code', 'status', 'state', 'city',
        'submitted_time', 'open_hours', 'escalation_level', 'escalation_person',
        'reason', 'owner'
    ]
    display_cols = [c for c in display_cols if c in open_with_esc.columns]

    sort_col = 'open_hours' if 'open_hours' in open_with_esc.columns else display_cols[0]
    show = open_with_esc[display_cols].sort_values(sort_col, ascending=False)

    st.dataframe(show, use_container_width=True, height=450)

    st.download_button(
        "📥 Download Current Open Calls",
        data=show.to_csv(index=False).encode('utf-8'),
        file_name=f"Open_Calls_{isp}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
else:
    st.warning("No open tickets loaded.")
    st.info("Upar **Quick Load from Google Sheet** use karo, ya Upload Data page se load karo.")
