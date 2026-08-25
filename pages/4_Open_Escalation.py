import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.escalation import load_escalation_matrix, apply_escalation_to_open, get_escalation_color

st.set_page_config(page_title="Open Escalation | XTRNATE", page_icon="🚨", layout="wide")

st.title("🚨 Open Tickets & Live Escalation + Site History")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

open_df = st.session_state.get('open_df')
closed_df = st.session_state.get('closed_df')

if open_df is None or open_df.empty:
    st.warning("No open tickets data found. Please upload from **Upload Data** page.")
    st.stop()

# Filter by ISP
if isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()
if closed_df is not None and not closed_df.empty and isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()

# Treat "Assign to FE" as Open (already expected in open file, but ensure)
if 'status' in open_df.columns:
    # Keep all, but highlight Assign to FE
    pass

st.markdown(f"**ISP:** `{isp}` | **Open Tickets:** {len(open_df)}")

matrix = load_escalation_matrix(isp if isp != "ALL" else "HCIN")
open_esc = apply_escalation_to_open(open_df, matrix)

# ===================== SUMMARY =====================
st.subheader("Escalation Level Summary")
level_counts = open_esc['escalation_level'].value_counts().reindex(['L1', 'L2', 'L3', 'L4'], fill_value=0)

cols = st.columns(4)
colors = ['#22c55e', '#eab308', '#f97316', '#ef4444']
for i, level in enumerate(['L1', 'L2', 'L3', 'L4']):
    with cols[i]:
        st.markdown(f"""
        <div style="background:{colors[i]}22; border:2px solid {colors[i]}; border-radius:12px; padding:1rem; text-align:center;">
            <h2 style="margin:0; color:{colors[i]}">{level_counts.get(level, 0)}</h2>
            <p style="margin:0; color:#cbd5e1;">{level}</p>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ===================== FILTERS =====================
f1, f2, f3 = st.columns(3)
with f1:
    levels = ['All'] + sorted(open_esc['escalation_level'].dropna().unique().tolist())
    sel_level = st.selectbox("Filter by Level", levels)
with f2:
    states = ['All'] + sorted(open_esc['state'].dropna().unique().tolist()) if 'state' in open_esc.columns else ['All']
    sel_state = st.selectbox("Filter by State", states)
with f3:
    min_hours = st.number_input("Min Open Hours", min_value=0.0, value=0.0, step=0.5)

filtered = open_esc.copy()
if sel_level != 'All':
    filtered = filtered[filtered['escalation_level'] == sel_level]
if sel_state != 'All' and 'state' in filtered.columns:
    filtered = filtered[filtered['state'] == sel_state]
if 'open_hours' in filtered.columns:
    filtered = filtered[filtered['open_hours'] >= min_hours]

st.write(f"Showing **{len(filtered)}** open tickets")

# ===================== OPEN LIST =====================
def highlight_level(row):
    color = get_escalation_color(row.get('escalation_level', 'L1'))
    return [f'background-color: {color}33'] * len(row)

display_cols = ['ticket_id', 'site_code', 'status', 'state', 'city', 'open_hours',
                'escalation_level', 'escalation_person', 'owner', 'reason', 'submitted_time']
display_cols = [c for c in display_cols if c in filtered.columns]

styled = filtered[display_cols].sort_values('open_hours', ascending=False) if 'open_hours' in filtered.columns else filtered[display_cols]

st.dataframe(styled.style.apply(highlight_level, axis=1), use_container_width=True, height=400)

# ===================== SITE HISTORY FOR OPEN TICKETS =====================
st.markdown("---")
st.subheader("📜 Site History for Open Tickets")
st.caption("Kisi bhi Open ticket ka Site Code select karo → us site pe pehle kab-kab down hua, kitne din me resolve hua, Last Enclosure reason kya tha — poora history.")

if 'site_code' not in filtered.columns:
    st.warning("site_code column missing in open data.")
else:
    open_sites = filtered['site_code'].dropna().unique().tolist()
    if not open_sites:
        st.info("No site codes in filtered open tickets.")
    else:
        selected_open_site = st.selectbox("Select Open Ticket Site Code to see History", sorted(open_sites))

        # Current open ticket(s) on this site
        current_open = filtered[filtered['site_code'] == selected_open_site]
        st.markdown(f"### Currently Open on **{selected_open_site}**")
        curr_cols = ['ticket_id', 'status', 'submitted_time', 'open_hours', 'reason', 'state', 'city']
        curr_cols = [c for c in curr_cols if c in current_open.columns]
        st.dataframe(current_open[curr_cols], use_container_width=True)

        # Past history from closed data
        st.markdown(f"### Previous Downs History for **{selected_open_site}**")
        if closed_df is not None and not closed_df.empty and 'site_code' in closed_df.columns:
            history = closed_df[closed_df['site_code'] == selected_open_site].copy()

            if history.empty:
                st.info("Is site pe pehle koi closed ticket nahi mila (ya Closed data upload nahi hua).")
            else:
                history = history.sort_values('submitted_time', ascending=False) if 'submitted_time' in history.columns else history

                st.success(f"Total previous downs found: **{len(history)}**")

                # Summary metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Past Occurrences", len(history))
                if 'resolution_days' in history.columns:
                    m2.metric("Avg Days to Resolve", round(history['resolution_days'].mean(), 1))
                    m3.metric("Max Days", round(history['resolution_days'].max(), 1))
                if 'category' in history.columns:
                    top_cat = history['category'].mode().iloc[0] if not history['category'].mode().empty else "-"
                    m4.metric("Most Common Category", top_cat)

                # Month-wise count
                if 'submitted_time' in history.columns:
                    history['month'] = history['submitted_time'].dt.to_period('M').astype(str)
                    month_counts = history['month'].value_counts().sort_index().reset_index()
                    month_counts.columns = ['Month', 'Count']
                    st.markdown("#### Month-wise Down Count")
                    fig = px.bar(month_counts, x='Month', y='Count', text='Count', color='Count',
                                 color_continuous_scale='Reds')
                    fig.update_layout(template='plotly_dark', height=300)
                    st.plotly_chart(fig, use_container_width=True)

                # Full history table
                hist_cols = ['ticket_id', 'submitted_time', 'resolved_time', 'resolution_days',
                             'category', 'reason_clean', 'state', 'city', 'down_time_min']
                hist_cols = [c for c in hist_cols if c in history.columns]
                st.markdown("#### Full History Details")
                st.dataframe(history[hist_cols], use_container_width=True, height=400)

                # Download history
                def to_excel(df):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Site_History')
                    return output.getvalue()

                st.download_button(
                    f"📥 Download History of {selected_open_site}",
                    data=to_excel(history[hist_cols]),
                    file_name=f"XTRNATE_History_{selected_open_site}_{isp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("Closed tickets data nahi hai. Site history ke liye Closed Tickets Excel bhi upload karo.")

# ===================== CHART =====================
st.markdown("---")
st.subheader("Open Hours Distribution")
if 'open_hours' in filtered.columns:
    fig = px.histogram(filtered, x='open_hours', nbins=20, color='escalation_level',
                       color_discrete_map={'L1':'#22c55e', 'L2':'#eab308', 'L3':'#f97316', 'L4':'#ef4444'})
    fig.update_layout(template='plotly_dark', height=350, xaxis_title="Open Hours")
    st.plotly_chart(fig, use_container_width=True)

# Download open list
def to_excel_open(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Open_Tickets')
    return output.getvalue()

st.download_button(
    "📥 Download Current Open Tickets",
    data=to_excel_open(filtered[display_cols]),
    file_name=f"XTRNATE_Open_{isp}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
