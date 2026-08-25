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

# Auto-load
if st.session_state.get('closed_df') is None:
    with st.spinner("Google Sheet se data load ho raha hai..."):
        auto_load_tickets()

closed_df = st.session_state.get('closed_df')
if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi mila. Sheet share (Anyone with link) check karo ya Home se Refresh dabao.")
    st.stop()

df = closed_df.copy()

# Deduplicate Incident ID
if 'ticket_id' in df.columns:
    df = df.drop_duplicates(subset=['ticket_id'], keep='first')

# Must have times
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
    """Sunday + 2nd Saturday + 4th Saturday"""
    wd = d.weekday()  # Mon=0 ... Sun=6
    if wd == 6:
        return True
    if wd == 5:
        day = d.day
        if 8 <= day <= 14 or 22 <= day <= 28:
            return True
    return False

# Month list
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

# ========== BUILD DAILY ROWS ==========
rows = []
for d in all_dates:
    date_str = d.strftime('%d-%b-%Y')
    if is_holiday(d):
        rows.append({
            'DATE': date_str,
            '< 2 HRS': None, '< 4 HRS': None, '< 8 HRS': None, '< 24 HRS': None,
            '> 24 HRS': None, '> 48 HRS': None, '> 72 HRS': None,
            'TOTAL RESOLVED': None,
            'HCIN (<24H)': None, 'HCIN (>24H)': None,
            'OTT (<24H)': None, 'OTT (>24H)': None,
            '_holiday': True, '_sort': d
        })
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
        'TOTAL RESOLVED': len(day),
        'HCIN (<24H)': int((hcin['resolution_hours'] < 24).sum()),
        'HCIN (>24H)': int((hcin['resolution_hours'] >= 24).sum()),
        'OTT (<24H)': int((ott['resolution_hours'] < 24).sum()),
        'OTT (>24H)': int((ott['resolution_hours'] >= 24).sum()),
        '_holiday': False, '_sort': d
    })

daily = pd.DataFrame(rows)

# Totals (non-holiday only)
num_cols = ['< 2 HRS', '< 4 HRS', '< 8 HRS', '< 24 HRS', '> 24 HRS', '> 48 HRS', '> 72 HRS',
            'TOTAL RESOLVED', 'HCIN (<24H)', 'HCIN (>24H)', 'OTT (<24H)', 'OTT (>24H)']
work = daily[~daily['_holiday']]
totals = {c: int(work[c].fillna(0).sum()) for c in num_cols}

# ========== KPI CARDS (same as sheet) ==========
st.markdown("### KPI Summary")
k1, k2, k3 = st.columns(3)
with k1:
    st.markdown(f"""
    <div style="background:#EFF6FF;border:2px solid #93C5FD;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#1E40AF;font-weight:700;font-size:0.95rem;">📊 TOTAL RESOLVED</div>
        <div style="color:#1E40AF;font-weight:800;font-size:2rem;">{totals['TOTAL RESOLVED']}</div>
    </div>
    """, unsafe_allow_html=True)
with k2:
    hcin_kpi = totals['HCIN (<24H)'] + totals['HCIN (>24H)']
    st.markdown(f"""
    <div style="background:#ECFDF5;border:2px solid #6EE7B7;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#047857;font-weight:700;font-size:0.95rem;">🏢 HCIN TOTAL</div>
        <div style="color:#047857;font-weight:800;font-size:2rem;">{hcin_kpi}</div>
    </div>
    """, unsafe_allow_html=True)
with k3:
    ott_kpi = totals['OTT (<24H)'] + totals['OTT (>24H)']
    st.markdown(f"""
    <div style="background:#F3E8FF;border:2px solid #D8B4FE;border-radius:12px;padding:1.2rem;text-align:center;">
        <div style="color:#6B21A8;font-weight:700;font-size:0.95rem;">🌐 OTT / CELERITY TOTAL</div>
        <div style="color:#6B21A8;font-weight:800;font-size:2rem;">{ott_kpi}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.subheader(f"Daily Sheet — {selected_month}")

# Display table: holiday rows show HOLIDAY text in a single visual way
show = daily.copy()
for idx, row in show.iterrows():
    if row['_holiday']:
        show.at[idx, '< 2 HRS'] = 'HOLIDAY'
        for c in num_cols[1:]:
            show.at[idx, c] = ''

# TOTAL row
total_row = {'DATE': 'TOTAL', **{c: totals[c] for c in num_cols}, '_holiday': False, '_sort': date(y, m, 28)}
show = pd.concat([show, pd.DataFrame([total_row])], ignore_index=True)

display_cols = ['DATE'] + num_cols
st.dataframe(
    show[display_cols],
    use_container_width=True,
    height=520,
    hide_index=True
)

st.caption("HOLIDAY = Sunday + 2nd Saturday + 4th Saturday (same logic as your Apps Script)")

# ========== CHARTS ==========
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    chart_df = work[work['TOTAL RESOLVED'] > 0] if not work.empty else work
    if not chart_df.empty:
        fig = px.bar(chart_df, x='DATE', y='TOTAL RESOLVED', text='TOTAL RESOLVED',
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

# HCIN vs OTT
comp = pd.DataFrame({
    'Segment': ['HCIN (<24H)', 'HCIN (>24H)', 'OTT (<24H)', 'OTT (>24H)'],
    'Count': [totals['HCIN (<24H)'], totals['HCIN (>24H)'], totals['OTT (<24H)'], totals['OTT (>24H)']]
})
fig = px.bar(comp, x='Segment', y='Count', text='Count', color='Count',
             color_continuous_scale='Purples', title="HCIN vs OTT (<24h / >24h)")
fig.update_layout(template='plotly_dark', height=360)
st.plotly_chart(fig, use_container_width=True)

# ========== DOWNLOAD ==========
def to_excel():
    out = BytesIO()
    export = show[display_cols].copy()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        export.to_excel(writer, index=False, sheet_name=selected_month)
        # Simple summary sheet
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
