import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period

st.set_page_config(page_title="Penalty & SLA | XTRNATE", page_icon="📜", layout="wide")

st.title("📜 Automated Penalty — HCIN vs ONEOTT (Alag-alag)")
st.markdown("Dono vendors ka penalty **separate** calculate hota hai")

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("Closed data load karo (Google Sheet / Excel).")
    st.stop()

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df_all = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

if 'resolution_days' not in df_all.columns:
    st.error("resolution_days nahi hai. Submitted + Resolved Time-Active chahiye.")
    st.stop()

# ========== RULES ==========
if 'penalty_rules' not in st.session_state:
    st.session_state.penalty_rules = {
        'l1_hours': 24, 'l1_penalty': 500,
        'l2_hours': 72, 'l2_penalty': 2000,
        'l3_hours': 120, 'l3_penalty': 5000,
    }

with st.expander("⚙️ Penalty Rules (dono vendors pe same apply)")
    r = st.session_state.penalty_rules
    c1, c2, c3 = st.columns(3)
    with c1:
        r['l1_hours'] = st.number_input("L1 SLA (hrs)", value=int(r['l1_hours']), min_value=1)
        r['l1_penalty'] = st.number_input("L1 Penalty ₹", value=int(r['l1_penalty']), min_value=0, step=100)
    with c2:
        r['l2_hours'] = st.number_input("L2 SLA (hrs)", value=int(r['l2_hours']), min_value=1)
        r['l2_penalty'] = st.number_input("L2 Penalty ₹", value=int(r['l2_penalty']), min_value=0, step=100)
    with c3:
        r['l3_hours'] = st.number_input("L3 SLA (hrs)", value=int(r['l3_hours']), min_value=1)
        r['l3_penalty'] = st.number_input("L3 Penalty ₹", value=int(r['l3_penalty']), min_value=0, step=500)
    st.session_state.penalty_rules = r

rules = st.session_state.penalty_rules

def apply_penalty(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    d['resolution_hours'] = pd.to_numeric(d['resolution_days'], errors='coerce') * 24

    def calc(hours):
        if pd.isna(hours):
            return 'Unknown', 0
        if hours > rules['l3_hours']:
            return 'L3 Critical', rules['l3_penalty']
        if hours > rules['l2_hours']:
            return 'L2 Breach', rules['l2_penalty']
        if hours > rules['l1_hours']:
            return 'L1 Breach', rules['l1_penalty']
        return 'Within SLA', 0

    res = d['resolution_hours'].apply(calc)
    d['sla_status'] = res.apply(lambda x: x[0])
    d['penalty_est'] = res.apply(lambda x: x[1])
    return d

def get_isp_slice(df, name):
    if df is None or df.empty:
        return pd.DataFrame()
    if 'isp' not in df.columns:
        return pd.DataFrame()
    return df[df['isp'] == name].copy()

hcin_raw = get_isp_slice(df_all, 'HCIN')
ott_raw = get_isp_slice(df_all, 'ONEOTT')

hcin = apply_penalty(hcin_raw)
ott = apply_penalty(ott_raw)

def summary_block(d, title):
    if d.empty:
        return {
            'title': title, 'total': 0, 'within': 0, 'l1': 0, 'l2': 0, 'l3': 0,
            'penalty': 0, 'breaches': 0
        }
    return {
        'title': title,
        'total': len(d),
        'within': int((d['sla_status'] == 'Within SLA').sum()),
        'l1': int((d['sla_status'] == 'L1 Breach').sum()),
        'l2': int((d['sla_status'] == 'L2 Breach').sum()),
        'l3': int((d['sla_status'] == 'L3 Critical').sum()),
        'penalty': int(d['penalty_est'].sum()),
        'breaches': int((d['penalty_est'] > 0).sum()),
    }

h = summary_block(hcin, 'HCIN')
o = summary_block(ott, 'ONEOTT')

# ========== SIDE BY SIDE ==========
st.subheader("⚡ HCIN vs ONEOTT — Alag Penalty")

col_h, col_o = st.columns(2)

with col_h:
    st.markdown("### 🏢 HCIN")
    st.metric("Total Tickets", h['total'])
    a, b, c, d = st.columns(4)
    a.metric("Within SLA", h['within'])
    b.metric("L1", h['l1'])
    c.metric("L2", h['l2'])
    d.metric("L3", h['l3'])
    st.metric("**HCIN Total Penalty ₹**", f"{h['penalty']:,}")
    st.caption(f"Breaches: {h['breaches']}")

with col_o:
    st.markdown("### 🌐 ONEOTT")
    st.metric("Total Tickets", o['total'])
    a, b, c, d = st.columns(4)
    a.metric("Within SLA", o['within'])
    b.metric("L1", o['l1'])
    c.metric("L2", o['l2'])
    d.metric("L3", o['l3'])
    st.metric("**ONEOTT Total Penalty ₹**", f"{o['penalty']:,}")
    st.caption(f"Breaches: {o['breaches']}")

# Comparison bar
st.markdown("#### Penalty Comparison")
comp = pd.DataFrame({
    'ISP': ['HCIN', 'ONEOTT', 'HCIN', 'ONEOTT'],
    'Type': ['Penalty ₹', 'Penalty ₹', 'Breach Count', 'Breach Count'],
    'Value': [h['penalty'], o['penalty'], h['breaches'], o['breaches']]
})
fig = px.bar(comp[comp['Type'] == 'Penalty ₹'], x='ISP', y='Value', color='ISP',
             color_discrete_map={'HCIN': '#38bdf8', 'ONEOTT': '#f97316'},
             text='Value', title="Total Estimated Penalty (₹)")
fig.update_layout(template='plotly_dark', height=350)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========== DETAILED BREACH LISTS ==========
tab1, tab2, tab3 = st.tabs(["🏢 HCIN Breaches", "🌐 ONEOTT Breaches", "📋 Summary Table"])

show_cols = ['ticket_id', 'site_code', 'submitted_time', 'resolved_time', 'resolution_hours',
             'sla_status', 'penalty_est', 'state', 'city', 'reason_clean', 'owner']

with tab1:
    if hcin.empty:
        st.info("HCIN data nahi")
    else:
        hb = hcin[hcin['penalty_est'] > 0].sort_values('resolution_hours', ascending=False)
        if hb.empty:
            st.success("HCIN — koi penalty breach nahi")
        else:
            cols = [c for c in show_cols if c in hb.columns]
            st.dataframe(hb[cols], use_container_width=True, height=400)
            st.download_button(
                "📥 HCIN Penalty List",
                data=hb[cols].to_csv(index=False).encode('utf-8'),
                file_name=f"Penalty_HCIN_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="dl_hcin"
            )

with tab2:
    if ott.empty:
        st.info("ONEOTT data nahi")
    else:
        ob = ott[ott['penalty_est'] > 0].sort_values('resolution_hours', ascending=False)
        if ob.empty:
            st.success("ONEOTT — koi penalty breach nahi")
        else:
            cols = [c for c in show_cols if c in ob.columns]
            st.dataframe(ob[cols], use_container_width=True, height=400)
            st.download_button(
                "📥 ONEOTT Penalty List",
                data=ob[cols].to_csv(index=False).encode('utf-8'),
                file_name=f"Penalty_ONEOTT_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="dl_ott"
            )

with tab3:
    summary = pd.DataFrame({
        'Metric': ['Total Tickets', 'Within SLA', 'L1 Breach', 'L2 Breach', 'L3 Critical',
                   'Total Breaches', 'Estimated Penalty (₹)'],
        'HCIN': [h['total'], h['within'], h['l1'], h['l2'], h['l3'], h['breaches'], h['penalty']],
        'ONEOTT': [o['total'], o['within'], o['l1'], o['l2'], o['l3'], o['breaches'], o['penalty']],
    })
    st.dataframe(summary, use_container_width=True)

    def to_excel():
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            summary.to_excel(writer, index=False, sheet_name='Summary')
            if not hcin.empty:
                hcin[hcin['penalty_est'] > 0].to_excel(writer, index=False, sheet_name='HCIN_Breaches')
            if not ott.empty:
                ott[ott['penalty_est'] > 0].to_excel(writer, index=False, sheet_name='ONEOTT_Breaches')
        return output.getvalue()

    st.download_button(
        "📥 Download Both ISPs Penalty Report",
        data=to_excel(),
        file_name=f"XTRNATE_Penalty_HCIN_ONEOTT_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.markdown("---")

# Open projected — separate
st.subheader("📞 Open Tickets — Projected Penalty (Alag)")
if open_df is not None and not open_df.empty and 'open_hours' in open_df.columns:
    def proj(d):
        if d is None or d.empty:
            return 0, 0
        x = d.copy()
        def calc(hours):
            if pd.isna(hours):
                return 0
            if hours > rules['l3_hours']:
                return rules['l3_penalty']
            if hours > rules['l2_hours']:
                return rules['l2_penalty']
            if hours > rules['l1_hours']:
                return rules['l1_penalty']
            return 0
        x['proj'] = x['open_hours'].apply(calc)
        return int((x['proj'] > 0).sum()), int(x['proj'].sum())

    hcin_o = get_isp_slice(open_df, 'HCIN')
    ott_o = get_isp_slice(open_df, 'ONEOTT')
    hb_c, hb_p = proj(hcin_o)
    ob_c, ob_p = proj(ott_o)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**HCIN Open**")
        st.metric("Past SLA (open)", hb_c)
        st.metric("Projected ₹", f"{hb_p:,}")
    with c2:
        st.markdown("**ONEOTT Open**")
        st.metric("Past SLA (open)", ob_c)
        st.metric("Projected ₹", f"{ob_p:,}")
else:
    st.info("Open data nahi")
