import streamlit as st
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(__file__))

st.set_page_config(
    page_title="XTRNATE Project | NOC Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
        padding: 1.5rem 2rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .main-header p {
        margin: 0.3rem 0 0 0;
        opacity: 0.8;
        font-size: 1rem;
    }
    
    .isp-card {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
        transition: all 0.3s ease;
        cursor: pointer;
        height: 180px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .isp-card:hover {
        transform: translateY(-5px);
        border-color: #38bdf8;
        box-shadow: 0 15px 40px rgba(56, 189, 248, 0.2);
    }
    
    .metric-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #334155;
        text-align: center;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #38bdf8;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-top: 0.3rem;
    }
    
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: scale(1.02);
    }
    
    /* Hide default streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'selected_isp' not in st.session_state:
    st.session_state.selected_isp = None
if 'closed_df' not in st.session_state:
    st.session_state.closed_df = None
if 'open_df' not in st.session_state:
    st.session_state.open_df = None
if 'site_master' not in st.session_state:
    st.session_state.site_master = None

# Header
st.markdown("""
<div class="main-header">
    <h1>📡 XTRNATE Project</h1>
    <p>NOC Command Center • Advanced Ticket Analytics & Escalation System</p>
</div>
""", unsafe_allow_html=True)

# ISP Selection
st.markdown("### Select ISP Partner")
st.markdown("Choose the partner to view dedicated dashboard and analysis")

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("🏢 HCIN", use_container_width=True, type="primary" if st.session_state.selected_isp == "HCIN" else "secondary"):
        st.session_state.selected_isp = "HCIN"
        st.rerun()

with col2:
    if st.button("🌐 ONEOTT", use_container_width=True, type="primary" if st.session_state.selected_isp == "ONEOTT" else "secondary"):
        st.session_state.selected_isp = "ONEOTT"
        st.rerun()

with col3:
    if st.button("📊 ALL / Overview", use_container_width=True, type="primary" if st.session_state.selected_isp == "ALL" else "secondary"):
        st.session_state.selected_isp = "ALL"
        st.rerun()

st.markdown("---")

# Status
if st.session_state.selected_isp:
    st.success(f"**Active ISP:** {st.session_state.selected_isp}")
    st.info("👉 Use the **sidebar** to navigate: Upload Data → Dashboard → Analysis → Escalation Matrix")
else:
    st.warning("Please select an ISP above to continue")

# Quick Stats if data loaded
if st.session_state.closed_df is not None or st.session_state.open_df is not None:
    st.markdown("### Quick Status")
    c1, c2, c3, c4 = st.columns(4)
    
    closed_count = len(st.session_state.closed_df) if st.session_state.closed_df is not None else 0
    open_count = len(st.session_state.open_df) if st.session_state.open_df is not None else 0
    
    with c1:
        st.metric("Closed Tickets Loaded", closed_count)
    with c2:
        st.metric("Open Tickets Loaded", open_count)
    with c3:
        site_count = len(st.session_state.site_master) if st.session_state.site_master is not None else 0
        st.metric("Sites in Master", site_count)
    with c4:
        st.metric("Active ISP", st.session_state.selected_isp or "None")

# Footer
st.markdown("---")
st.caption("XTRNATE Project • Built for NOC Engineers • Premium Analytics Suite")
