import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats
from utils.bootstrap import ensure_ready, apply_isp_filter
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

st.set_page_config(page_title="Vendor Performance | XTRNATE", page_icon="🏭", layout="wide")

st.title("🏭 Vendor / Partner Performance Metrics")
st.markdown("Owner / Partner wise tickets, downtime, resolution time aur repeat analysis")

isp = ensure_ready()

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi hai. Pehle Google Sheet / Excel load karo.")
    st.stop()

closed_df = apply_isp_filter(closed_df)
open_df = apply_isp_filter(open_df)

period = st.radio(
    "Period",
    ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"],
    horizontal=True
)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

st.markdown(f"**ISP:** `{isp}` | **Closed tickets in period:** {len(df)}")

# Decide vendor column: owner preferred, then partner from site master
vendor_col = None
for col in ['owner', 'partner', 'isp_name']:
    if col in df.columns and df[col].notna().any():
        vendor_col = col
        break

if vendor_col is None:
    st.error("Owner / Partner column nahi mila data mein.")
    st.stop()

st.caption(f"Vendor grouping by column: **{vendor_col}**")

# ========== OVERALL VENDOR SUMMARY ==========
st.subheader("📊 Vendor Summary")

agg = {'ticket_id': 'count'}
if 'down_time_min' in df.columns:
    agg['down_time_min'] = 'sum'
if 'resolution_days' in df.columns:
    agg['resolution_days'] = 'mean'

vendor_stats = df.groupby(vendor_col).agg(agg).reset_index()
vendor_stats = vendor_stats.rename(columns={
    'ticket_id': 'ticket_count',
    'down_time_min': 'total_downtime_min',
    'resolution_days': 'avg_resolution_days'
})

if 'total_downtime_min' in vendor_stats.columns:
    vendor_stats['total_downtime_hrs'] = (vendor_stats['total_downtime_min'] / 60).round(1)
if 'avg_resolution_days' in vendor_stats.columns:
    vendor_stats['avg_resolution_days'] = vendor_stats['avg_resolution_days'].round(1)

vendor_stats = vendor_stats.sort_values('ticket_count', ascending=False)
st.dataframe(vendor_stats, use_container_width=True, height=300)

# Charts
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Tickets by Vendor")
    fig = px.bar(vendor_stats, x=vendor_col, y='ticket_count', color='ticket_count',
                 color_continuous_scale='Blues', text='ticket_count')
    fig.update_layout(template='plotly_dark', height=380, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    if 'total_downtime_hrs' in vendor_stats.columns:
        st.markdown("#### Total Downtime (Hrs) by Vendor")
        fig = px.bar(vendor_stats, x=vendor_col, y='total_downtime_hrs', color='total_downtime_hrs',
                     color_continuous_scale='Reds', text='total_downtime_hrs')
        fig.update_layout(template='plotly_dark', height=380, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
    elif 'avg_resolution_days' in vendor_stats.columns:
        st.markdown("#### Avg Resolution Days by Vendor")
        fig = px.bar(vendor_stats, x=vendor_col, y='avg_resolution_days', color='avg_resolution_days',
                     color_continuous_scale='Oranges', text='avg_resolution_days')
        fig.update_layout(template='plotly_dark', height=380, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========== REPEAT SITES BY VENDOR ==========
st.subheader("🔁 Repeat Sites by Vendor")

if 'site_code' in df.columns:
    site_vendor = df.groupby(['site_code', vendor_col]).size().reset_index(name='count')
    repeats = site_vendor[site_vendor['count'] >= 2].sort_values('count', ascending=False)

    if repeats.empty:
        st.info("Is period mein koi site 2+ baar nahi aaya.")
    else:
        st.dataframe(repeats.head(30), use_container_width=True, height=350)

        top_repeat_vendors = repeats.groupby(vendor_col)['count'].sum().reset_index()
        top_repeat_vendors.columns = [vendor_col, 'repeat_ticket_count']
        top_repeat_vendors = top_repeat_vendors.sort_values('repeat_ticket_count', ascending=False)

        fig = px.bar(top_repeat_vendors, x=vendor_col, y='repeat_ticket_count', color='repeat_ticket_count',
                     color_continuous_scale='Purples', text='repeat_ticket_count',
                     title="Repeat-related tickets by Vendor")
        fig.update_layout(template='plotly_dark', height=350, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("site_code missing")

st.markdown("---")

# ========== CATEGORY BY VENDOR ==========
st.subheader("📁 Category Mix by Vendor")

if 'category' in df.columns:
    cat_vendor = df.groupby([vendor_col, 'category']).size().reset_index(name='count')
    fig = px.bar(cat_vendor, x=vendor_col, y='count', color='category', barmode='stack',
                 title="Category breakdown per Vendor")
    fig.update_layout(template='plotly_dark', height=400, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Category column nahi hai")

st.markdown("---")

# ========== OPEN BY VENDOR ==========
st.subheader("📞 Current Open by Vendor")

if open_df is not None and not open_df.empty and vendor_col in open_df.columns:
    open_v = open_df[vendor_col].value_counts().reset_index()
    open_v.columns = [vendor_col, 'open_count']
    fig = px.bar(open_v, x=vendor_col, y='open_count', color='open_count',
                 color_continuous_scale='Oranges', text='open_count')
    fig.update_layout(template='plotly_dark', height=350, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(open_v, use_container_width=True)
else:
    st.info("Open data nahi / vendor column missing in open")

st.markdown("---")

# ========== DETAILED VENDOR DRILL-DOWN ==========
st.subheader("🔍 Vendor Detail")

vendors = sorted(df[vendor_col].dropna().unique().tolist())
selected = st.selectbox("Select Vendor / Owner", vendors)

v_data = df[df[vendor_col] == selected].copy()
st.markdown(f"### {selected} — {len(v_data)} closed tickets")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Tickets", len(v_data))
if 'down_time_min' in v_data.columns:
    m2.metric("Total Downtime Hrs", round(v_data['down_time_min'].sum() / 60, 1))
if 'resolution_days' in v_data.columns:
    m3.metric("Avg Resolution Days", round(v_data['resolution_days'].mean(), 1))
if 'site_code' in v_data.columns:
    m4.metric("Unique Sites", v_data['site_code'].nunique())

detail_cols = ['ticket_id', 'site_code', 'submitted_time', 'resolved_time', 'resolution_days',
               'category', 'reason_clean', 'state', 'city']
detail_cols = [c for c in detail_cols if c in v_data.columns]
st.dataframe(v_data[detail_cols].sort_values(
    'submitted_time' if 'submitted_time' in v_data.columns else detail_cols[0],
    ascending=False
), use_container_width=True, height=400)

# Download
download_pack(
    "Vendor Summary",
    vendor_stats,
    file_stem=f"XTRNATE_Vendor_Performance_{isp}_{period.replace(' ', '_')}",
    title=f"Vendor Performance  ·  {isp}",
    subtitle=period,
    sheet_name="Vendor",
    key="vendor_dl",
)
