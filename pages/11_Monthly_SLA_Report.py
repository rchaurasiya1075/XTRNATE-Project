import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime, date
import calendar

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets

st.set_page_config(page_title="Monthly SLA Report | XTRNATE", page_icon="📅", layout="wide")

st.title("📅 Monthly SLA Report — Daily Basis")
st.markdown("Resolved/Closed only • Duplicate Incident removed • SLA buckets • HCIN / OTT split")

# Auto-load if needed
if st.session_state.get('closed_df') is None:
    with st.spinner("Auto-loading Google Sheet..."):
        auto_load_tickets()

closed_df = st.session_state.get('closed_df')
if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi hai. Google Sheet share + Home pe refresh try karo.")
    st.stop()

df = closed_df.copy()

# Only resolved/closed (extra safety)
if 'status' in df.columns:
    st_upper = df['status'].astype(str).str.upper().str.replace(r'[^A-Z]', '', regex=True)
    # Keep rows that look resolved/closed OR have resolved_time
    mask = st_upper.str.contains('RESOLVED|CLOSED', na=False)
    if mask.any():
        df = df[mask | df.get('resolved_time').notna()].copy() if 'resolved_time' in df.columns else df[mask].copy()

# Deduplicate by ticket_id
if 'ticket_id' in df.columns:
    df = df.drop_duplicates(subset=['ticket_id'], keep='first')

# Need submitted + resolved
if 'submitted_time' not in df.columns or 'resolved_time' not in df.columns:
    st.error("submitted_time / resolved_time missing")
    st.stop()

df = df.dropna(subset=['submitted_time', 'resolved_time'])
df['resolution_hours'] = (df['resolved_time'] - df['submitted_time']).dt.total_seconds() / 3600
df = df[df['resolution_hours'] >= 0].copy()
df['resolved_date'] = df['resolved_time'].dt.date
df['resolved_month'] = df['resolved_time'].dt.to_period('M').astype(str)

def sla_bucket(hrs):
    if hrs < 2: return '< 2 HRS'
    if hrs < 4: return '< 4 HRS'
    if hrs < 8: return '< 8 HRS'
    if hrs < 24: return '< 24 HRS'
    if hrs < 48: return '> 24 HRS'
    if hrs < 72: return '> 48 HRS'
    return '> 72 HRS'

df['sla_bucket'] = df['resolution_hours'].apply(sla_bucket)

def partner_type(row):
    owner = str(row.get('owner', '')).upper()
    isp = str(row.get('isp', '')).upper()
    text = owner + ' ' + isp
    if 'HCIN' in text:
        return 'HCIN'
    if 'ONEOTT' in text or 'OTT' in text or 'CELERITY' in text:
        return 'OTT'
    return 'OTHER'

df['partner'] = df.apply(partner_type, axis=1)

# Month selector
months = sorted(df['resolved_month'].dropna().unique().tolist(), reverse=True)
if not months:
    st.info("No resolved tickets with valid dates.")
    st.stop()

selected_month = st.selectbox("Select Month", months)
month_df = df[df['resolved_month'] == selected_month].copy()

# ========== KPI CARDS ==========
total_res = len(month_df)
hcin_total = len(month_df[month_df['partner'] == 'HCIN'])
ott_total = len(month_df[month_df['partner'] == 'OTT'])

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("📊 TOTAL RESOLVED", total_res)
with c2:
    st.metric("🏢 HCIN TOTAL", hcin_total)
with c3:
    st.metric("🌐 OTT / CELERITY TOTAL", ott_total)

st.markdown("---")

# ========== BUILD DAILY TABLE (same structure as Apps Script) ==========
buckets = ['< 2 HRS', '< 4 HRS', '< 8 HRS', '< 24 HRS', '> 24 HRS', '> 48 HRS', '> 72 HRS']

def is_holiday(d):
    """Sunday + 2nd & 4th Saturday"""
    if not isinstance(d, date):
        return False
    wd = d.weekday()  # Mon=0 ... Sun=6
    if wd == 6:  # Sunday
        return True
    if wd == 5:  # Saturday
        day = d.day
        if 8 <= day <= 14 or 22 <= day <= 28:
            return True
    return False

# All days in month
try:
    y, m = map(int, selected_month.split('-'))
except Exception:
    y, m = datetime.now().year, datetime.now().month

days_in_month = calendar.monthrange(y, m)[1]
all_dates = [date(y, m, d) for d in range(1, days_in_month + 1)]

rows = []
for d in all_dates:
    if is_holiday(d):
        rows.append({
            'DATE': d.strftime('%d-%b-%Y'),
            '< 2 HRS': 'HOLIDAY', '< 4 HRS': '', '< 8 HRS': '', '< 24 HRS': '',
            '> 24 HRS': '', '> 48 HRS': '', '> 72 HRS': '',
            'TOTAL RESOLVED': '',
            'HCIN (<24H)': '', 'HCIN (>24H)': '',
            'OTT (<24H)': '', 'OTT (>24H)': '',
            '_is_holiday': True
        })
        continue

    day_data = month_df[month_df['resolved_date'] == d]
    counts = {b: 0 for b in buckets}
    for b in day_data['sla_bucket']:
        if b in counts:
            counts[b] += 1

    hcin_day = day_data[day_data['partner'] == 'HCIN']
    ott_day = day_data[day_data['partner'] == 'OTT']
    hcin_lt24 = len(hcin_day[hcin_day['resolution_hours'] < 24])
    hcin_gt24 = len(hcin_day[hcin_day['resolution_hours'] >= 24])
    ott_lt24 = len(ott_day[ott_day['resolution_hours'] < 24])
    ott_gt24 = len(ott_day[ott_day['resolution_hours'] >= 24])

    rows.append({
        'DATE': d.strftime('%d-%b-%Y'),
        '< 2 HRS': counts['< 2 HRS'],
        '< 4 HRS': counts['< 4 HRS'],
        '< 8 HRS': counts['< 8 HRS'],
        '< 24 HRS': counts['< 24 HRS'],
        '> 24 HRS': counts['> 24 HRS'],
        '> 48 HRS': counts['> 48 HRS'],
        '> 72 HRS': counts['> 72 HRS'],
        'TOTAL RESOLVED': len(day_data),
        'HCIN (<24H)': hcin_lt24,
        'HCIN (>24H)': hcin_gt24,
        'OTT (<24H)': ott_lt24,
        'OTT (>24H)': ott_gt24,
        '_is_holiday': False
    })

# TOTAL row
num_cols = ['< 2 HRS', '< 4 HRS', '< 8 HRS', '< 24 HRS', '> 24 HRS', '> 48 HRS', '> 72 HRS',
            'TOTAL RESOLVED', 'HCIN (<24H)', 'HCIN (>24H)', 'OTT (<24H)', 'OTT (>24H)']
totals = {'DATE': 'TOTAL', '_is_holiday': False}
for c in num_cols:
    totals[c] = sum(r[c] for r in rows if not r['_is_holiday'] and isinstance(r[c], (int, float)))
rows.append(totals)

daily_df = pd.DataFrame(rows)
display_df = daily_df.drop(columns=['_is_holiday'], errors='ignore')

st.subheader(f"Daily SLA Dashboard — {selected_month}")
st.dataframe(display_df, use_container_width=True, height=500)

# Charts
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    work_days = daily_df[~daily_df['_is_holiday'] & (daily_df['DATE'] != 'TOTAL')]
    if not work_days.empty:
        fig = px.bar(work_days, x='DATE', y='TOTAL RESOLVED', title="Daily Resolved Count",
                     color='TOTAL RESOLVED', color_continuous_scale='Blues')
        fig.update_layout(template='plotly_dark', height=350, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    bucket_totals = {b: totals[b] for b in buckets}
    bdf = pd.DataFrame({'Bucket': list(bucket_totals.keys()), 'Count': list(bucket_totals.values())})
    fig = px.bar(bdf, x='Bucket', y='Count', color='Count', color_continuous_scale='Teal',
                 title="Monthly SLA Bucket Totals", text='Count')
    fig.update_layout(template='plotly_dark', height=350)
    st.plotly_chart(fig, use_container_width=True)

# HCIN vs OTT monthly
st.markdown("#### HCIN vs OTT — <24h vs >24h")
comp = pd.DataFrame({
    'Partner': ['HCIN <24h', 'HCIN >24h', 'OTT <24h', 'OTT >24h'],
    'Count': [totals['HCIN (<24H)'], totals['HCIN (>24H)'], totals['OTT (<24H)'], totals['OTT (>24H)']]
})
fig = px.bar(comp, x='Partner', y='Count', color='Count', text='Count',
             color_continuous_scale='Purples')
fig.update_layout(template='plotly_dark', height=350)
st.plotly_chart(fig, use_container_width=True)

# Download
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=selected_month[:31])
    return output.getvalue()

st.download_button(
    f"📥 Download {selected_month} Daily SLA Report",
    data=to_excel(display_df),
    file_name=f"XTRNATE_Monthly_SLA_{selected_month}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
