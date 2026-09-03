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
    /* Sidebar: category headers + tidy page names */
    [data-testid="stSidebarNav"] {
        padding-top: 0.15rem;
    }
    [data-testid="stSidebarNav"] a {
        border-radius: 8px !important;
        margin: 1px 4px !important;
        padding: 0.38rem 0.65rem !important;
        color: #e2e8f0 !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebarNav"] a:hover {
        background: rgba(56, 189, 248, 0.16) !important;
    }
    [data-testid="stSidebarNav"] a span {
        font-size: 0.9rem !important;
        letter-spacing: 0.01em;
    }
    [data-testid="stSidebarNav"] [class*="stSidebarNavSection"],
    [data-testid="stSidebarNav"] ul ul {
        margin-bottom: 0.15rem;
    }
    [data-testid="stSidebarNav"] li div:not(:has(a)) {
        color: #38bdf8 !important;
        font-size: 0.68rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        padding: 0.55rem 0.7rem 0.2rem 0.7rem !important;
        opacity: 0.95;
    }
    .nav-cat {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 0.85rem 1rem 0.7rem 1rem;
        height: 100%;
        margin-bottom: 0.6rem;
    }
    .nav-cat h4 {
        margin: 0 0 0.55rem 0;
        color: #38bdf8;
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

if "selected_isp" not in st.session_state:
    st.session_state.selected_isp = "ALL"
if "selected_isps" not in st.session_state:
    st.session_state.selected_isps = None
if "closed_df" not in st.session_state:
    st.session_state.closed_df = None
if "open_df" not in st.session_state:
    st.session_state.open_df = None
if "site_master" not in st.session_state:
    st.session_state.site_master = None

home = st.Page("home_page.py", title="Home", icon="📡", default=True)

tickets = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊"),
    st.Page("pages/4_Open_Escalation.py", title="Open Escalation", icon="🚨"),
    st.Page("pages/7_Open_Calls_Dashboard.py", title="Open Calls", icon="📞"),
    st.Page("pages/3_Closed_Analysis.py", title="Closed Analysis", icon="✅"),
    st.Page("pages/6_Repeat_Analysis.py", title="Repeat Analysis", icon="🔁"),
]
isp_partner = [
    st.Page("pages/8_ISP_Comparison.py", title="ISP Comparison", icon="⚖️"),
    st.Page("pages/12_Partner_Report.py", title="Partner Report", icon="📄"),
    st.Page("pages/9_Vendor_Performance.py", title="Vendor Performance", icon="📈"),
    st.Page("pages/20_Vendor_Change.py", title="Vendor Change", icon="🔄"),
]
sla_reports = [
    st.Page("pages/11_Monthly_SLA_Report.py", title="Monthly SLA", icon="📅"),
    st.Page("pages/10_Penalty_SLA.py", title="Penalty SLA", icon="⚠️"),
    st.Page("pages/17_Holiday_Downtime.py", title="Holiday Downtime", icon="🎆"),
    st.Page("pages/16_Conclusion.py", title="Conclusion PPT", icon="📚"),
]
daily_ops = [
    st.Page("pages/14_VPN_Update.py", title="VPN Update", icon="📡"),
    st.Page("pages/15_Pending_Mail.py", title="Pending Mail", icon="✉️"),
]
sim_lastmile = [
    st.Page("pages/19_SIM_Inventory.py", title="SIM Inventory", icon="📱"),
    st.Page("pages/18_SIM_Backup_Usage.py", title="SIM Data Usage", icon="📶"),
    st.Page("pages/13_Circuit_ID.py", title="Circuit ID", icon="🔗"),
    st.Page("pages/21_LC_Master.py", title="LC Master", icon="📋"),
    st.Page("pages/22_Last_Mile_Update.py", title="Last Mile Update", icon="📍"),
]
tools = [
    st.Page("pages/0_Site_Search.py", title="Site Search", icon="🔍"),
    st.Page("pages/2_Upload_Data.py", title="Upload Data", icon="📤"),
    st.Page("pages/5_Escalation_Matrix.py", title="Escalation Matrix", icon="⚙️"),
]

pg = st.navigation({
    "Home": [home],
    "Tickets": tickets,
    "ISP & Partner": isp_partner,
    "SLA & Reports": sla_reports,
    "Daily Ops": daily_ops,
    "SIM & Last Mile": sim_lastmile,
    "Tools": tools,
})
pg.run()
