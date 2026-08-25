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

st.title("📅 Monthly SLA Report")
st.caption("Daily resolve counts by time bucket • HCIN / OTT split • Weekend & holiday logic")

if st.session_state.get('closed_df') is None:
    with st.spinner("Google Sheet se data load ho raha hai..."):
        auto_load_tickets()

closed_df = st.session_state.get('closed_df')
if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi mila. Sheet share check karo ya Home se Refresh dabao.")
    st.stop()

df = closed_df.copy()

if 'ticket_id' in df.columns:
    df = df.drop_duplicates(subset=['ticket_id'], keep='first')

if 'submitted_time' not in df.columns or 'resolved_time' not in df.columns:
    st.error("submitted_time / resolved_time missing")
    st.stop()

df = df.dropna(subset=['submitted_time', 'resolved_time'])
df['resolution_hours'] = (df['resolved_time'] - df['submitted_time']).dt.total_seconds() / 3600.0
df = df[df['resolution_hours'] >= 0].copy()
df['resolved_date'] = df['resolved_time'].dt.normalize().dt.date
df['resolved_month'] = df['resolved_time'].dt.strftime('%Y-%m')

def sla_bucket(hrs):
    if hrs < 2: return '<2'
    if hrs < 4: return '<4'
    if hrs < 8: return '<8'
    if hrs < 24: return '<24'
    if hrs < 48: return '>24'
    if hrs < 72: return '>48'
    return '>72'

df['bucket'] = df['resolution_hours'].apply(sla_bucket)

def partner_type(row):
    owner = str(row.get('owner', '') or '').upper()
    isp = str(row.get('isp', '') or '').upper()
    text = f"{owner} {isp}"
    if 'HCIN' in text:
        return 'HCIN'
    if any(x in text for x in ['ONEOTT', 'OTT', 'CELERITY']):
        return 'OTT'
    return 'OTHER'

df['partner'] = df.apply(partner_type, axis=1)

def is_holiday(d: date) -> bool:
    wd = d.weekday()
    if wd == 6:
        return True
    if wd == 5:
        day = d.day
        if 8 <= day <= 14 or 22 <= day <= 28:
            return True
    return False

months = sorted(df['resolved_month'].dropna().unique().tolist(), reverse=True)
if not months:
    st.info("Koi valid resolved date nahi mili.")
    st.stop()

selected_month = st.selectbox("Select Month (separate monthly sheet)", months)

try:
    y, m = map(int, selected_month.split('-'))
except Exception:
    y, m = datetime.now().year, datetime.now().month

month_df = df[df['resolved_month'] == selected_month].copy()
days_in_month = calendar.monthrange(y, m)[1]
all_dates = [date(y, m, d) for d in range(1, days_in_month + 1)]

num_cols = ['< 2 HRS', '< 4 HRS', '< 8 HRS', '< 24 HRS', '> 24 HRS', '> 48 HRS', '> 72 HRS',
            'TOTAL RESOLVED', 'HCIN (<24H)', 'HCIN (>24H)', 'OTT (<24H)', 'OTT (>24H)']

rows = []
for d in all_dates:
    date_str = d.strftime('%d-%b-%Y')
    if is_holiday(d):
        # All values as strings so HOLIDAY works without dtype error
        row = {'DATE': date_str, '_holiday': True}
        row['< 2 HRS'] = 'HOLIDAY'
        for c in num_cols[1:]:
            row[c] = ''
        rows.append(row)
        continue

    day = month_df[month_df['resolved_date'] == d]
    b = day['bucket'].value_counts()
    hcin = day[day['partner'] == 'HCIN']
    ott = day[day['partner'] == 'OTT']

    rows.append({
        'DATE': date_str,
        '< 2 HRS': int(b.get('<2', 0)),
        '< 4 HRS': int(b.get('<4', 0)),
        '< 8 HRS': int(b.get('<8', 0)),
        '< 24 HRS': int(b.get('<24', 0)),
        '> 24 HRS': int(b.get('>24', 0)),
        '> 48 HRS': int(b.get('>48', 0)),
        '> 72 HRS': int(b.get('>72', 0)),
        'TOTAL RESOLVED': int(len(day)),
        'HCIN (<24H)': int((hcin['resolution_hours'] < 24).sum()) if len(hcin) else 0,
        'HCIN (>24H)': int((hcin['resolution_hours'] >= 24).sum()) if len(hcin) else 0,
        'OTT (<24H)': int((ott['resolution_hours'] < 24).sum()) if len(ott) else 0,
        'OTT (>24H)': int((ott['resolution_hours'] >= 24).sum()) if len(ott) else 0,
        '_holiday': False,
    })

daily = pd.DataFrame(rows)

# Totals from non-holiday numeric rows
def to_num(val):
    try:
        return int(val)
    except Exception:
        return 0

work = daily[~daily['_holiday']].copy()
totals = {c: int(work[c].map(to_num).sum()) for c in num_cols}

# KPI
st.markdown("### KPI Summary")
k1, k2, k3 = st.columns(3)
hcin_kpi = totals['HCIN (<24H)'] + totals['HCIN (>24H)']
ott_kpi = totals['OTT (<24H)'] + totals['OTT (>24H)']

with k1:
    st.markdown(f"""
    <div style="background:#EFF6FF;border:2px solid #93C5FD;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#1E40AF;font-weight:700;">📊 TOTAL RESOLVED</div>
        <div style="color:#1E40AF;font-weight:800;font-size:2rem;">{totals['TOTAL RESOLVED']}</div>
    </div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
    <div style="background:#ECFDF5;border:2px solid #6EE7B7;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#047857;font-weight:700;">🏢 HCIN TOTAL</div>
        <div style="color:#047857;font-weight:800;font-size:2rem;">{hcin_kpi}</div>
    </div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
    <div style="background:#F3E8FF;border:2px solid #D8B4FE;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#6B21A8;font-weight:700;">🌐 OTT / CELERITY TOTAL</div>
        <div style="color:#6B21A8;font-weight:800;font-size:2rem;">{ott_kpi}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.subheader(f"Daily Sheet — {selected_month}")

# Force all display columns to string-safe object dtype for mixed HOLIDAY + numbers
display_cols = ['DATE'] + num_cols
show = daily[display_cols].copy()
for c in num_cols:
    show[c] = show[c].apply(lambda x: x if x == 'HOLIDAY' or x == '' else to_num(x))

# TOTAL row as strings/numbers mixed safely
total_row = {'DATE': 'TOTAL'}
for c in num_cols:
    total_row[c] = totals[c]
show = pd.concat([show, pd.DataFrame([total_row])], ignore_index=True)

# Convert entire frame to object for Streamlit display safety
show_display = show.astype(object)

st.dataframe(show_display, use_container_width=True, height=520, hide_index=True)
st.caption("HOLIDAY = Sunday + 2nd Saturday + 4th Saturday")

# Charts — only numeric work days
st.markdown("---")
col1, col2 = st.columns(2)

chart_src = work.copy()
for c in num_cols:
    chart_src[c] = chart_src[c].map(to_num)

with col1:
    if not chart_src.empty:
        fig = px.bar(chart_src, x='DATE', y='TOTAL RESOLVED', text='TOTAL RESOLVED',
                     color='TOTAL RESOLVED', color_continuous_scale='Blues',
                     title="Daily Total Resolved")
        fig.update_layout(template='plotly_dark', height=360, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    bucket_order = ['< 2 HRS', '< 4 HRS', '< 8 HRS', '< 24 HRS', '> 24 HRS', '> 48 HRS', '> 72 HRS']
    bdf = pd.DataFrame({'Bucket': bucket_order, 'Count': [totals[b] for b in bucket_order]})
    fig = px.bar(bdf, x='Bucket', y='Count', text='Count', color='Count',
                 color_continuous_scale='Teal', title="Month SLA Bucket Totals")
    fig.update_layout(template='plotly_dark', height=360)
    st.plotly_chart(fig, use_container_width=True)

comp = pd.DataFrame({
    'Segment': ['HCIN (<24H)', 'HCIN (>24H)', 'OTT (<24H)', 'OTT (>24H)'],
    'Count': [totals['HCIN (<24H)'], totals['HCIN (>24H)'], totals['OTT (<24H)'], totals['OTT (>24H)']]
})
fig = px.bar(comp, x='Segment', y='Count', text='Count', color='Count',
             color_continuous_scale='Purples', title="HCIN vs OTT (<24h / >24h)")
fig.update_layout(template='plotly_dark', height=360)
st.plotly_chart(fig, use_container_width=True)

def to_excel():
    out = BytesIO()
    export = show_display.copy()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        export.to_excel(writer, index=False, sheet_name=selected_month[:31])
        summary = pd.DataFrame({
            'KPI': ['TOTAL RESOLVED', 'HCIN TOTAL', 'OTT / CELERITY TOTAL'],
            'Value': [totals['TOTAL RESOLVED'], hcin_kpi, ott_kpi]
        })
        summary.to_excel(writer, index=False, sheet_name='KPI')
    return out.getvalue()

st.download_button(
    f"📥 Download {selected_month} Monthly Sheet (Excel)",
    data=to_excel(),
    file_name=f"XTRNATE_SLA_{selected_month}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
