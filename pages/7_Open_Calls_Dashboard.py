import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.escalation import load_escalation_matrix, apply_escalation_to_open, get_escalation_color
from utils.bootstrap import ensure_ready, apply_isp_filter, get_selected_isps

st.set_page_config(page_title="Open Calls Dashboard | XTRNATE", page_icon="📞", layout="wide")

st.title("📞 Open Calls Dashboard")
st.markdown("**Assign to FE** + **Call on Hold** tickets | Full details + Site History")

isp = ensure_ready()

open_df = st.session_state.get('open_df')
closed_df = st.session_state.get('closed_df')

if open_df is None or open_df.empty:
    st.warning("No open tickets data found. Please upload Tickets Excel from **Upload Data** page (Auto Split tab).")
    st.stop()

open_df = apply_isp_filter(open_df)
closed_df = apply_isp_filter(closed_df)
# Keep only Assign to FE and Call on Hold
if 'status' in open_df.columns:
    status_lower = open_df['status'].astype(str).str.lower()
    mask = status_lower.str.contains('assign to fe') | status_lower.str.contains('call on hold') | status_lower.str.contains('on hold')
    open_calls = open_df[mask].copy()
    if open_calls.empty:
        open_calls = open_df.copy()
        st.info("Status filter mein Assign to FE / Call on Hold nahi mila, isliye saare open tickets dikha raha hoon.")
else:
    open_calls = open_df.copy()

st.markdown(f"**Active ISP:** `{isp}` | **Open Calls (Assign to FE + On Hold):** **{len(open_calls)}**")

matrix = load_escalation_matrix(isp if isp not in ("ALL", "NONE") else (get_selected_isps() or ["HCIN"])[0])
open_esc = apply_escalation_to_open(open_calls, matrix)

# ========== SUMMARY ==========
st.subheader("Summary")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("Total Open Calls", len(open_esc))
with c2:
    st.metric("L1", len(open_esc[open_esc.get('escalation_level') == 'L1']) if 'escalation_level' in open_esc.columns else 0)
with c3:
    st.metric("L2", len(open_esc[open_esc.get('escalation_level') == 'L2']) if 'escalation_level' in open_esc.columns else 0)
with c4:
    st.metric("L3", len(open_esc[open_esc.get('escalation_level') == 'L3']) if 'escalation_level' in open_esc.columns else 0)
with c5:
    st.metric("L4 (Critical)", len(open_esc[open_esc.get('escalation_level') == 'L4']) if 'escalation_level' in open_esc.columns else 0)

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

display_cols = ['ticket_id', 'site_code', 'status', 'state', 'city', 'submitted_time', 'open_hours',
                'escalation_level', 'escalation_person', 'reason', 'owner']
display_cols = [c for c in display_cols if c in filtered.columns]

show_df = filtered[display_cols].sort_values('open_hours', ascending=False) if 'open_hours' in filtered.columns else filtered[display_cols]
st.dataframe(show_df.style.apply(highlight_level, axis=1), use_container_width=True, height=420)

# ========== STATE / STATUS ==========
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Open Calls by State")
    if 'state' in filtered.columns:
        state_c = filtered['state'].value_counts().reset_index()
        state_c.columns = ['State', 'Count']
        fig = px.bar(state_c, x='State', y='Count', color='Count', text='Count', color_continuous_scale='Oranges')
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)
with col2:
    st.subheader("Open Calls by Status")
    if 'status' in filtered.columns:
        status_c = filtered['status'].value_counts().reset_index()
        status_c.columns = ['Status', 'Count']
        fig = px.pie(status_c, names='Status', values='Count', hole=0.4)
        fig.update_layout(template='plotly_dark', height=320)
        st.plotly_chart(fig, use_container_width=True)

# ========== SITE HISTORY (ONLY SELECTED SITE) ==========
st.markdown("---")
st.subheader("📜 Site History — Selected Site Only")
st.caption("⚠️ Sirf **selected Site Code** ka history dikhega. Overall nahi.")

if 'site_code' not in filtered.columns or filtered.empty:
    st.info("Koi open call nahi hai ya site_code missing hai.")
else:
    sites = sorted(filtered['site_code'].dropna().unique().tolist())
    selected_site = st.selectbox("Select ONE Site Code", sites, key="open_site_history")

    st.success(f"Showing data **only for Site: {selected_site}**")

    # Current open
    curr = filtered[filtered['site_code'] == selected_site]
    st.markdown(f"#### Currently Open — **{selected_site}**")
    curr_cols = ['ticket_id', 'status', 'submitted_time', 'open_hours', 'reason', 'state', 'city', 'escalation_level']
    curr_cols = [c for c in curr_cols if c in curr.columns]
    st.dataframe(curr[curr_cols], use_container_width=True)

    # History of THIS site only
    st.markdown(f"#### Previous Downs History — **{selected_site}** only")
    if closed_df is not None and not closed_df.empty and 'site_code' in closed_df.columns:
        hist = closed_df[closed_df['site_code'] == selected_site].copy()

        if hist.empty:
            st.info(f"Site **{selected_site}** pe koi previous closed ticket nahi mila.")
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

            if 'submitted_time' in hist.columns:
                hist['month'] = hist['submitted_time'].dt.to_period('M').astype(str)
                month_df = hist['month'].value_counts().sort_index().reset_index()
                month_df.columns = ['Month', 'Count']
                fig = px.bar(month_df, x='Month', y='Count', text='Count', color='Count',
                             color_continuous_scale='Reds', title=f"Month-wise Downs — {selected_site}")
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
                f"📥 Download History of {selected_site} only",
                data=to_excel(hist[hist_cols]),
                file_name=f"History_{selected_site}_{isp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.warning("Closed data nahi hai. History ke liye Tickets Excel (Auto Split) upload karo.")

# ========== DOWNLOAD ==========
st.markdown("---")
def to_excel_open(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Open_Calls')
    return output.getvalue()

st.download_button(
    "📥 Download Filtered Open Calls",
    data=to_excel_open(show_df),
    file_name=f"XTRNATE_Open_Calls_{isp}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
