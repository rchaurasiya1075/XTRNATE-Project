import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period
from utils.auto_load import auto_load_tickets

st.set_page_config(page_title="Penalty & SLA | XTRNATE", page_icon="📜", layout="wide")

st.title("📜 Automated Penalty — HCIN vs ONEOTT")
st.markdown("Period-wise SLA breach + **Site-wise down count & total downtime** (dono ISP alag)")

if st.session_state.get('closed_df') is None:
    with st.spinner("Auto-loading data..."):
        auto_load_tickets()

if 'selected_isp' not in st.session_state:
    st.session_state.selected_isp = "ALL"

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("Closed data nahi mila. Sheet share check karo.")
    st.stop()

period = st.radio("Period", ["Last 1 Month", "Last 3 Months", "Last 6 Months", "Overall"], horizontal=True)
period_map = {"Last 1 Month": "1M", "Last 3 Months": "3M", "Last 6 Months": "6M", "Overall": "ALL"}
df_all = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

if 'resolution_days' not in df_all.columns:
    st.error("resolution_days nahi hai. Submitted + Resolved Time-Active chahiye.")
    st.stop()

if 'penalty_rules' not in st.session_state:
    st.session_state.penalty_rules = {
        'l1_hours': 24, 'l1_penalty': 500,
        'l2_hours': 72, 'l2_penalty': 2000,
        'l3_hours': 120, 'l3_penalty': 5000,
    }

with st.expander("⚙️ Penalty Rules"):
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
    if df is None or df.empty or 'isp' not in df.columns:
        return pd.DataFrame()
    return df[df['isp'] == name].copy()

def site_summary(d):
    """Per site: count, avg hours, total downtime, penalty."""
    if d is None or d.empty or 'site_code' not in d.columns:
        return pd.DataFrame()
    x = d.copy()
    if 'down_time_min' not in x.columns:
        x['down_time_min'] = x.get('resolution_hours', 0) * 60
    x['down_time_min'] = pd.to_numeric(x['down_time_min'], errors='coerce').fillna(0)
    x['resolution_hours'] = pd.to_numeric(x.get('resolution_hours', 0), errors='coerce').fillna(0)
    x['penalty_est'] = pd.to_numeric(x.get('penalty_est', 0), errors='coerce').fillna(0)

    g = x.groupby('site_code').agg(
        down_count=('ticket_id', 'count'),
        total_downtime_min=('down_time_min', 'sum'),
        avg_resolution_hrs=('resolution_hours', 'mean'),
        max_resolution_hrs=('resolution_hours', 'max'),
        total_penalty_inr=('penalty_est', 'sum'),
    ).reset_index()
    g['total_downtime_hrs'] = (g['total_downtime_min'] / 60).round(1)
    g['avg_resolution_hrs'] = g['avg_resolution_hrs'].round(1)
    g['max_resolution_hrs'] = g['max_resolution_hrs'].round(1)
    g['total_penalty_inr'] = g['total_penalty_inr'].astype(int)
    g = g.sort_values(['down_count', 'total_downtime_hrs'], ascending=False)

    if 'state' in x.columns:
        g['state'] = g['site_code'].map(x.groupby('site_code')['state'].first())
    return g

hcin = apply_penalty(get_isp_slice(df_all, 'HCIN'))
ott = apply_penalty(get_isp_slice(df_all, 'ONEOTT'))

def summary_block(d):
    if d.empty:
        return {'total': 0, 'within': 0, 'l1': 0, 'l2': 0, 'l3': 0, 'penalty': 0, 'breaches': 0}
    return {
        'total': len(d),
        'within': int((d['sla_status'] == 'Within SLA').sum()),
        'l1': int((d['sla_status'] == 'L1 Breach').sum()),
        'l2': int((d['sla_status'] == 'L2 Breach').sum()),
        'l3': int((d['sla_status'] == 'L3 Critical').sum()),
        'penalty': int(d['penalty_est'].sum()),
        'breaches': int((d['penalty_est'] > 0).sum()),
    }

h = summary_block(hcin)
o = summary_block(ott)

st.subheader("⚡ HCIN vs ONEOTT Penalty")
col_h, col_o = st.columns(2)
with col_h:
    st.markdown("### 🏢 HCIN")
    st.metric("Tickets", h['total'])
    a, b, c, d_ = st.columns(4)
    a.metric("Within", h['within']); b.metric("L1", h['l1']); c.metric("L2", h['l2']); d_.metric("L3", h['l3'])
    st.metric("Penalty ₹", f"{h['penalty']:,}")
with col_o:
    st.markdown("### 🌐 ONEOTT")
    st.metric("Tickets", o['total'])
    a, b, c, d_ = st.columns(4)
    a.metric("Within", o['within']); b.metric("L1", o['l1']); c.metric("L2", o['l2']); d_.metric("L3", o['l3'])
    st.metric("Penalty ₹", f"{o['penalty']:,}")

fig = px.bar(pd.DataFrame({'ISP': ['HCIN', 'ONEOTT'], 'Penalty_INR': [h['penalty'], o['penalty']]}),
             x='ISP', y='Penalty_INR', color='ISP',
             color_discrete_map={'HCIN': '#38bdf8', 'ONEOTT': '#f97316'}, text='Penalty_INR')
fig.update_layout(template='plotly_dark', height=320)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader(f"📍 Site-wise Down Count & Downtime — {period}")
st.caption("Har site: kitni baar down | avg/max hours | total downtime | estimated penalty")

tab_h, tab_o, tab_all = st.tabs(["🏢 HCIN Sites", "🌐 ONEOTT Sites", "📋 Combined"])

h_sites = site_summary(hcin)
o_sites = site_summary(ott)

with tab_h:
    if h_sites.empty:
        st.info("HCIN site data nahi")
    else:
        st.metric("Unique sites (HCIN)", len(h_sites))
        st.dataframe(h_sites, use_container_width=True, height=420)
        st.download_button("📥 HCIN Site Summary", h_sites.to_csv(index=False).encode('utf-8'),
                           file_name=f"Penalty_Sites_HCIN_{period.replace(' ','_')}.csv", mime="text/csv", key="h_sites_dl")

with tab_o:
    if o_sites.empty:
        st.info("ONEOTT site data nahi")
    else:
        st.metric("Unique sites (ONEOTT)", len(o_sites))
        st.dataframe(o_sites, use_container_width=True, height=420)
        st.download_button("📥 ONEOTT Site Summary", o_sites.to_csv(index=False).encode('utf-8'),
                           file_name=f"Penalty_Sites_OTT_{period.replace(' ','_')}.csv", mime="text/csv", key="o_sites_dl")

with tab_all:
    if not h_sites.empty:
        h_sites = h_sites.copy(); h_sites.insert(0, 'ISP', 'HCIN')
    if not o_sites.empty:
        o_sites2 = o_sites.copy(); o_sites2.insert(0, 'ISP', 'ONEOTT')
    else:
        o_sites2 = o_sites
    combined = pd.concat([h_sites, o_sites2], ignore_index=True) if not h_sites.empty or not o_sites2.empty else pd.DataFrame()
    if combined.empty:
        st.info("No data")
    else:
        st.dataframe(combined, use_container_width=True, height=420)

        def to_excel():
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                if not h_sites.empty:
                    h_sites.to_excel(writer, index=False, sheet_name='HCIN_Sites')
                if not o_sites.empty:
                    o_sites.to_excel(writer, index=False, sheet_name='ONEOTT_Sites')
                combined.to_excel(writer, index=False, sheet_name='Combined')
            return out.getvalue()

        st.download_button("📥 Download Site Downtime Report",
                           data=to_excel(),
                           file_name=f"XTRNATE_Site_Downtime_{period.replace(' ','_')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
tab1, tab2 = st.tabs(["HCIN Breach Tickets", "ONEOTT Breach Tickets"])
show_cols = ['ticket_id', 'site_code', 'submitted_time', 'resolved_time', 'resolution_hours',
             'sla_status', 'penalty_est', 'state', 'reason_clean', 'owner']

with tab1:
    if not hcin.empty:
        hb = hcin[hcin['penalty_est'] > 0].sort_values('resolution_hours', ascending=False)
        if hb.empty:
            st.success("No HCIN breaches")
        else:
            cols = [c for c in show_cols if c in hb.columns]
            st.dataframe(hb[cols], use_container_width=True, height=350)

with tab2:
    if not ott.empty:
        ob = ott[ott['penalty_est'] > 0].sort_values('resolution_hours', ascending=False)
        if ob.empty:
            st.success("No ONEOTT breaches")
        else:
            cols = [c for c in show_cols if c in ob.columns]
            st.dataframe(ob[cols], use_container_width=True, height=350)
