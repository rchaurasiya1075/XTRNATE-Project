import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.escalation import load_escalation_matrix, apply_escalation_to_open, get_escalation_color

st.set_page_config(page_title="Open Escalation | XTRNATE", page_icon="🚨", layout="wide")

st.title("🚨 Open Tickets & Live Escalation Matrix")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

open_df = st.session_state.get('open_df')

if open_df is None or open_df.empty:
    st.warning("No open tickets data found. Please upload from **Upload Data** page.")
    st.stop()

if isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()

st.markdown(f"**ISP:** `{isp}` | **Open Tickets:** {len(open_df)}")

matrix = load_escalation_matrix(isp if isp != "ALL" else "HCIN")
open_esc = apply_escalation_to_open(open_df, matrix)

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

f1, f2, f3 = st.columns(3)
with f1:
    levels = ['All'] + sorted(open_esc['escalation_level'].unique().tolist())
    sel_level = st.selectbox("Filter by Level", levels)
with f2:
    states = ['All'] + sorted(open_esc['state'].dropna().unique().tolist()) if 'state' in open_esc.columns else ['All']
    sel_state = st.selectbox("Filter by State", states)
with f3:
    min_hours = st.number_input("Min Open Hours", min_value=0.0, value=0.0, step=0.5)

filtered = open_esc.copy()
if sel_level != 'All':
    filtered = filtered[filtered['escalation_level'] == sel_level]
if sel_state != 'All':
    filtered = filtered[filtered['state'] == sel_state]
if 'open_hours' in filtered.columns:
    filtered = filtered[filtered['open_hours'] >= min_hours]

st.write(f"Showing **{len(filtered)}** tickets")

def highlight_level(row):
    color = get_escalation_color(row.get('escalation_level', 'L1'))
    return [f'background-color: {color}33'] * len(row)

display_cols = ['ticket_id', 'site_code', 'status', 'state', 'open_hours', 'escalation_level', 'escalation_person', 'owner', 'reason', 'bank_name', 'branch_name']
display_cols = [c for c in display_cols if c in filtered.columns]

styled = filtered[display_cols].sort_values('open_hours', ascending=False)

st.dataframe(styled.style.apply(highlight_level, axis=1), use_container_width=True, height=500)

st.subheader("Open Hours Distribution")
if 'open_hours' in filtered.columns:
    fig = px.histogram(filtered, x='open_hours', nbins=20, color='escalation_level',
                       color_discrete_map={'L1':'#22c55e', 'L2':'#eab308', 'L3':'#f97316', 'L4':'#ef4444'})
    fig.update_layout(template='plotly_dark', height=350, xaxis_title="Open Hours")
    st.plotly_chart(fig, use_container_width=True)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Open_Escalation')
    return output.getvalue()

st.download_button(
    "📥 Download Open Escalation Report",
    data=to_excel(filtered[display_cols]),
    file_name=f"XTRNATE_Open_Escalation_{isp}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
