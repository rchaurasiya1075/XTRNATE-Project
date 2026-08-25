import streamlit as st
import os
import sys

sys.path.append(os.path.dirname(__file__))

st.set_page_config(
    page_title="XTRNATE Project | NOC Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
        padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem;
        color: white; box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }
    .main-header h1 {
        margin: 0; font-size: 2.2rem; font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .main-header p { margin: 0.3rem 0 0 0; opacity: 0.8; font-size: 1rem; }
    div[data-testid="stSidebar"] { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); }
    .stButton > button { border-radius: 10px; font-weight: 600; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Session defaults
if 'selected_isp' not in st.session_state:
    st.session_state.selected_isp = None
if 'closed_df' not in st.session_state:
    st.session_state.closed_df = None
if 'open_df' not in st.session_state:
    st.session_state.open_df = None
if 'site_master' not in st.session_state:
    st.session_state.site_master = None

# ========== AUTO LOAD FROM GOOGLE SHEET ==========
from utils.auto_load import auto_load_tickets

if st.session_state.closed_df is None:
    with st.spinner("Google Sheet se data auto-load ho raha hai..."):
        ok, msg = auto_load_tickets()
    if ok and msg != "already_loaded":
        st.toast(f"Auto-loaded: {msg}", icon="✅")
    elif not ok:
        st.sidebar.warning(f"Auto-load fail: {msg}. Upload Data se manually load karo.")

st.markdown("""
<div class="main-header">
    <h1>📡 XTRNATE Project</h1>
    <p>NOC Command Center • Advanced Ticket Analytics & Escalation System</p>
</div>
""", unsafe_allow_html=True)

st.markdown("### Select ISP Partner")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🏢 HCIN", use_container_width=True,
                 type="primary" if st.session_state.selected_isp == "HCIN" else "secondary"):
        st.session_state.selected_isp = "HCIN"
        st.rerun()
with col2:
    if st.button("🌐 ONEOTT", use_container_width=True,
                 type="primary" if st.session_state.selected_isp == "ONEOTT" else "secondary"):
        st.session_state.selected_isp = "ONEOTT"
        st.rerun()
with col3:
    if st.button("📊 ALL / Overview", use_container_width=True,
                 type="primary" if st.session_state.selected_isp == "ALL" else "secondary"):
        st.session_state.selected_isp = "ALL"
        st.rerun()

st.markdown("---")

if st.session_state.selected_isp:
    st.success(f"**Active ISP:** {st.session_state.selected_isp}")
else:
    st.warning("Please select an ISP above to continue")

# Force refresh button
if st.button("🔄 Refresh data from Google Sheet"):
    st.cache_data.clear()
    ok, msg = auto_load_tickets(force=True)
    if ok:
        st.success(f"Refreshed: {msg}")
        st.rerun()
    else:
        st.error(msg)

if st.session_state.closed_df is not None or st.session_state.open_df is not None:
    st.markdown("### Quick Status")
    c1, c2, c3, c4 = st.columns(4)
    closed_count = len(st.session_state.closed_df) if st.session_state.closed_df is not None else 0
    open_count = len(st.session_state.open_df) if st.session_state.open_df is not None else 0
    with c1:
        st.metric("Closed Tickets", closed_count)
    with c2:
        st.metric("Open Tickets", open_count)
    with c3:
        site_count = len(st.session_state.site_master) if st.session_state.site_master is not None else 0
        st.metric("Sites in Master", site_count)
    with c4:
        st.metric("Active ISP", st.session_state.selected_isp or "None")

st.markdown("---")
st.caption("XTRNATE Project • Data auto-loads from Google Sheet on refresh")
