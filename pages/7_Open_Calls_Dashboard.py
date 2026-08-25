import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.escalation import load_escalation_matrix, apply_escalation_to_open, get_escalation_color

st.set_page_config(page_title="Open Calls Dashboard | XTRNATE", page_icon="📞", layout="wide")

st.title("📞 Open Calls Dashboard")
st.markdown("**Assign to FE** + **Call on Hold** tickets | Full details + Site History")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

open_df = st.session_state.get('open_df')
closed_df = st.session_state.get('closed_df')

if open_df is None or open_df.empty:
    st.warning("No open tickets data found. Please upload **Open Tickets Excel** from Upload Data page.")
    st.stop()

# Filter by ISP
if isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()
if closed_df is not None and not closed_df.empty and isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()

# Keep only Assign to FE and Call on Hold
if 'status' in open_df.columns:
    status_lower = open_df['status'].astype(str).str.lower()
    mask = status_lower.str.contains('assign to fe') | status_lower.str.contains('call on hold') | status_lower.str.contains('on hold')
    open_calls = open_df[mask].copy()
    if open_calls.empty:
        # if filter removes everything, show all open as fallback
        open_calls = open_df.copy()
        st.info("Status filter mein Assign to FE / Call on Hold nahi mila, isliye saare open tickets dikha raha hoon.")
else:
    open_calls = open_df.copy()

st.markdown(f"**Active ISP:** `{isp}` | **Open Calls (Assign to FE + On Hold):** **{len(open_calls)}**")

# Apply escalation
matrix = load_escalation_matrix(isp if isp != "ALL" else "HCIN")
open_esc = apply_escalation_to_open(open_calls, matrix)

# ========== SUMMARY CARDS ==========
st.subheader("Summary")
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Total Open Calls", len(open_esc))
with c2:
    l1 = len(open_esc[open_esc['escalation_level'] == 'L1']) if 'escalation_level' in open_esc.columns else 0
    st.metric("L1", l1)
with c3:
    l2 = len(open_esc[open_esc['escalation_level'] == 'L2']) if 'escalation_level' in open_esc.columns else 0
    st.metric("L2", l2)
with c4:
    l3 = len(open_esc[open_esc['escalation_level'] == 'L3']) if 'escalation_level' in open_esc.columns else 0
    st.metric("L3", l3)
with c5:
    l4 = len(open_esc[open_esc['escalation_level'] == 'L4']) if 'escalation_level' in open_esc.columns else 0
    st.metric("L4 (Critical)", l4)

st.markdown("---")

# ========== FILTERS ==========
f1, f2, f3, f4 = st.columns(4)
with f1:
    levels = ['All'] + sorted(open_esc['escalation_level'].dropna().unique().tolist()) if 'escalation_level' in open_esc.columns else ['All']
    sel_level = st.selectbox("Escalation Level", levels)
with f2:
    states = ['All'] + sorted(open_esc['state'].dropna().unique().tolist()) if 'state' in open_esc.columns else ['All']
    sel_state = st.selectbox("State", states)
with f3:
    statuses = ['All'] + sorted(open_esc['status'].dropna().unique().tolist()) if 'status' in open_esc.columns else ['All']
    sel_status = st.selectbox("Status", statuses)
with f4:
    min_hours = st.number_input("Min Open Hours", min_value=0.0, value=0.0, step=0.5)

filtered = open_esc.copy()
if sel_level != 'All' and 'escalation_level' in filtered.columns:
    filtered = filtered[filtered['escalation_level'] == sel_level]
if sel_state != 'All' and 'state' in filtered.columns:
    filtered = filtered[filtered['state'] == sel_state]
if sel_status != 'All' and 'status' in filtered.columns:
    filtered = filtered[filtered['status'] == sel_status]
if 'open_hours' in filtered.columns:
    filtered = filtered[filtered['open_hours'] >= min_hours]

st.write(f"Filtered Open Calls: **{len(filtered)}**")

# ========== MAIN TABLE ==========
st.subheader("Open Calls List")

def highlight_level(row):
    color = get_escalation_color(row.get('escalation_level', 'L1'))
    return [f'background-color: {color}33'] * len(row)

display_cols = [
    'ticket_id', 'site_code', 'status', 'state', 'city',
    'submitted_time', 'open_hours', 'escalation_level', 'escalation_person',
    'reason', 'owner'
]
display_cols = [c for c in display_cols if c in filtered.columns]

show_df = filtered[display_cols].sort_values('open_hours', ascending=False) if 'open_hours' in filtered.columns else filtered[display_cols]

st.dataframe(
    show_df.style.apply(highlight_level, axis=1),
    use_container_width=True,
    height=420
)

# ========== STATE / CITY BREAKDOWN ==========
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("Open Calls by State")
    if 'state' in filtered.columns:
        state_c = filtered['state'].value_counts().reset_index()
        state_c.columns = ['State', 'Count']
        fig = px.bar(state_c, x='State', y='Count', color='Count', text='Count',
                     color_continuous_scale='Oranges')
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("State column missing")

with col2:
    st.subheader("Open Calls by Status")
    if 'status' in filtered.columns:
        status_c = filtered['status'].value_counts().reset_index()
        status_c.columns = ['Status', 'Count']
        fig = px.pie(status_c, names='Status', values='Count', hole=0.4)
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Status column missing")

# ========== SITE HISTORY ==========
st.markdown("---")
st.subheader("📜 Site History (Past Downs of Selected Open Site)")
st.caption("Open call ka Site Code select karo → us site pe pehle kab-kab down hua, kitne din me resolve hua, Last Enclosure reason kya tha.")

if 'site_code' not in filtered.columns or filtered.empty:
    st.info("Koi open call nahi hai ya site_code missing hai.")
else:
    sites = sorted(filtered['site_code'].dropna().unique().tolist())
    selected_site = st.selectbox("Select Site Code", sites)

    # Current open on this site
    curr = filtered[filtered['site_code'] == selected_site]
    st.markdown(f"#### Currently Open on **{selected_site}**")
    curr_cols = ['ticket_id', 'status', 'submitted_time', 'open_hours', 'reason', 'state', 'city', 'escalation_level']
    curr_cols = [c for c in curr_cols if c in curr.columns]
    st.dataframe(curr[curr_cols], use_container_width=True)

    # History from closed
    st.markdown(f"#### Previous Downs History — **{selected_site}**")
    if closed_df is not None and not closed_df.empty and 'site_code' in closed_df.columns:
        hist = closed_df[closed_df['site_code'] == selected_site].copy()

        if hist.empty:
            st.info("Is site pe koi previous closed ticket nahi mila.")
        else:
            if 'submitted_time' in hist.columns:
                hist = hist.sort_values('submitted_time', ascending=False)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Past Occurrences", len(hist))
            if 'resolution_days' in hist.columns:
                m2.metric("Avg Resolution Days", round(hist['resolution_days'].mean(), 1))
                m3.metric("Max Resolution Days", round(hist['resolution_days'].max(), 1))
            if 'category' in hist.columns and not hist['category'].mode().empty:
                m4.metric("Top Category", hist['category'].mode().iloc[0])

            # Month-wise
            if 'submitted_time' in hist.columns:
                hist['month'] = hist['submitted_time'].dt.to_period('M').astype(str)
                month_df = hist['month'].value_counts().sort_index().reset_index()
                month_df.columns = ['Month', 'Count']
                fig = px.bar(month_df, x='Month', y='Count', text='Count', color='Count',
                             color_continuous_scale='Reds', title="Month-wise Previous Downs")
                fig.update_layout(template='plotly_dark', height=300)
                st.plotly_chart(fig, use_container_width=True)

            hist_cols = ['ticket_id', 'submitted_time', 'resolved_time', 'resolution_days',
                         'category', 'reason_clean', 'state', 'city']
            hist_cols = [c for c in hist_cols if c in hist.columns]
            st.dataframe(hist[hist_cols], use_container_width=True, height=380)

            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='History')
                return output.getvalue()

            st.download_button(
                f"📥 Download History of {selected_site}",
                data=to_excel(hist[hist_cols]),
                file_name=f"OpenSite_History_{selected_site}_{isp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.warning("Closed Tickets data upload nahi hai. History ke liye Closed Excel bhi upload karo.")

# ========== DOWNLOAD OPEN LIST ==========
st.markdown("---")
def to_excel_open(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Open_Calls')
    return output.getvalue()

st.download_button(
    "📥 Download All Filtered Open Calls",
    data=to_excel_open(show_df),
    file_name=f"XTRNATE_Open_Calls_{isp}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
