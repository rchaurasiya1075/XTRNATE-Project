import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats

st.set_page_config(page_title="Closed Analysis | XTRNATE", page_icon="📈", layout="wide")

st.title("📈 Closed Tickets Deep Analysis")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

closed_df = st.session_state.get('closed_df')

if closed_df is None or closed_df.empty:
    st.warning("No closed tickets data found. Please upload from **Upload Data** page.")
    st.stop()

if isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()

st.markdown(f"**ISP:** `{isp}` | **Total Closed Records:** {len(closed_df)}")

period = st.radio("Select Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "All Time"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "All Time": "ALL"}

df = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

st.success(f"Showing **{len(df)}** tickets for selected period")

stats = get_summary_stats(df)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tickets", stats.get('total_tickets', 0))
c2.metric("Total Downtime (Hrs)", stats.get('total_downtime_hrs', 0))
c3.metric("Average Downtime (Hrs)", stats.get('avg_downtime_hrs', 0))
c4.metric("Max Single Downtime (Min)", int(stats.get('max_downtime_min', 0)))

st.markdown("---")

st.subheader("🔍 Filters")
fcol1, fcol2, fcol3 = st.columns(3)

with fcol1:
    states = ['All'] + sorted(df['state'].dropna().unique().tolist()) if 'state' in df.columns else ['All']
    selected_state = st.selectbox("State", states)

with fcol2:
    if 'bank_name' in df.columns:
        banks = ['All'] + sorted(df['bank_name'].dropna().unique().tolist())
        selected_bank = st.selectbox("Bank", banks)
    else:
        selected_bank = 'All'

with fcol3:
    if 'owner' in df.columns:
        owners = ['All'] + sorted(df['owner'].dropna().unique().tolist())
        selected_owner = st.selectbox("Owner", owners)
    else:
        selected_owner = 'All'

filtered = df.copy()
if selected_state != 'All':
    filtered = filtered[filtered['state'] == selected_state]
if selected_bank != 'All' and 'bank_name' in filtered.columns:
    filtered = filtered[filtered['bank_name'] == selected_bank]
if selected_owner != 'All' and 'owner' in filtered.columns:
    filtered = filtered[filtered['owner'] == selected_owner]

st.write(f"Filtered results: **{len(filtered)}** tickets")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Downtime Distribution by State")
    if 'state' in filtered.columns and 'down_time_min' in filtered.columns:
        g = filtered.groupby('state')['down_time_min'].agg(['sum', 'mean', 'count']).reset_index()
        g.columns = ['State', 'Total_Min', 'Avg_Min', 'Count']
        g['Total_Hrs'] = (g['Total_Min'] / 60).round(1)
        fig = px.bar(g.sort_values('Total_Hrs', ascending=False), x='State', y='Total_Hrs', color='Count', text='Total_Hrs', color_continuous_scale='Viridis')
        fig.update_layout(template='plotly_dark', height=380)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Tickets Over Time")
    if 'submitted_time' in filtered.columns:
        daily = filtered.set_index('submitted_time').resample('D').size().reset_index()
        daily.columns = ['Date', 'Tickets']
        fig = px.area(daily, x='Date', y='Tickets', color_discrete_sequence=['#38bdf8'])
        fig.update_layout(template='plotly_dark', height=380)
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Most Problematic Sites (by total downtime)")
if 'site_code' in filtered.columns and 'down_time_min' in filtered.columns:
    site_g = filtered.groupby('site_code').agg({'down_time_min': 'sum', 'ticket_id': 'count'}).reset_index()
    site_g.columns = ['Site Code', 'Total Downtime (Min)', 'Ticket Count']
    site_g['Total Hrs'] = (site_g['Total Downtime (Min)'] / 60).round(1)
    site_g = site_g.sort_values('Total Downtime (Min)', ascending=False).head(15)
    if 'bank_name' in filtered.columns:
        bank_map = filtered.groupby('site_code')['bank_name'].first().to_dict()
        site_g['Bank'] = site_g['Site Code'].map(bank_map)
    st.dataframe(site_g, use_container_width=True, height=400)

st.subheader("Down Reason Analysis")
if 'reason_clean' in filtered.columns:
    reason_g = filtered['reason_clean'].value_counts().reset_index()
    reason_g.columns = ['Reason', 'Count']
    fig = px.pie(reason_g.head(10), names='Reason', values='Count', hole=0.35)
    fig.update_layout(template='plotly_dark', height=420)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Detailed Data")
st.dataframe(filtered, use_container_width=True, height=350)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Analysis')
    return output.getvalue()

st.download_button(
    label="📥 Download Filtered Data as Excel",
    data=to_excel(filtered),
    file_name=f"XTRNATE_Closed_{isp}_{period.replace(' ', '_')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
