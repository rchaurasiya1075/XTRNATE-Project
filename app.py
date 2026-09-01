import streamlit as st
import os
import sys

sys.path.append(os.path.dirname(__file__))

st.set_page_config(
    page_title="XTRNATE Project | NOC Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
        padding: 1.2rem 1.5rem; border-radius: 16px; margin-bottom: 1rem;
        color: white; box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }
    .main-header h1 {
        margin: 0; font-size: 1.8rem; font-weight: 800;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .main-header p { margin: 0.25rem 0 0 0; opacity: 0.85; font-size: 0.9rem; }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    .stButton > button { border-radius: 10px; font-weight: 600; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    @media (max-width: 768px) {
        .main-header h1 { font-size: 1.4rem; }
        .main-header { padding: 1rem; }
        div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
        .block-container { padding: 0.8rem 0.6rem !important; }
    }
    .search-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #38bdf8;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 0 20px rgba(56,189,248,0.15);
    }
</style>
""", unsafe_allow_html=True)

if "selected_isp" not in st.session_state:
    st.session_state.selected_isp = "ALL"
if "closed_df" not in st.session_state:
    st.session_state.closed_df = None
if "open_df" not in st.session_state:
    st.session_state.open_df = None
if "site_master" not in st.session_state:
    st.session_state.site_master = None

home = st.Page("home_page.py", title="Home", icon="📡", default=True)

tickets = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊"),
    st.Page("pages/3_Closed_Analysis.py", title="Closed Analysis", icon="✅"),
    st.Page("pages/4_Open_Escalation.py", title="Open Escalation", icon="🚨"),
    st.Page("pages/7_Open_Calls_Dashboard.py", title="Open Calls", icon="📞"),
    st.Page("pages/6_Repeat_Analysis.py", title="Repeat Analysis", icon="🔁"),
    st.Page("pages/8_ISP_Comparison.py", title="ISP Comparison", icon="⚖️"),
]
sim_data = [
    st.Page("pages/19_SIM_Inventory.py", title="SIM Inventory", icon="📱"),
    st.Page("pages/18_SIM_Backup_Usage.py", title="SIM Data Usage", icon="📶"),
    st.Page("pages/13_Circuit_ID.py", title="Circuit ID", icon="🔗"),
]
reports = [
    st.Page("pages/12_Partner_Report.py", title="Partner Report", icon="📄"),
    st.Page("pages/11_Monthly_SLA_Report.py", title="Monthly SLA", icon="📅"),
    st.Page("pages/9_Vendor_Performance.py", title="Vendor Performance", icon="📈"),
    st.Page("pages/10_Penalty_SLA.py", title="Penalty SLA", icon="⚠️"),
    st.Page("pages/16_Conclusion.py", title="Conclusion PPT", icon="📚"),
    st.Page("pages/15_Pending_Mail.py", title="Pending Mail", icon="✉️"),
    st.Page("pages/14_VPN_Update.py", title="VPN Update", icon="📡"),
    st.Page("pages/17_Holiday_Downtime.py", title="Holiday Downtime", icon="🎆"),
]
tools = [
    st.Page("pages/0_Site_Search.py", title="Site Search", icon="🔍"),
    st.Page("pages/2_Upload_Data.py", title="Upload Data", icon="📤"),
    st.Page("pages/5_Escalation_Matrix.py", title="Escalation Matrix", icon="📋"),
]

pg = st.navigation({
    "Home": [home],
    "Tickets": tickets,
    "SIM & Data": sim_data,
    "Reports": reports,
    "Tools": tools,
})
pg.run()
