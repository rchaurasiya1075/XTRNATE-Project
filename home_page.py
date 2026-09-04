import streamlit as st
from utils.auto_load import auto_load_tickets
from utils.site_search import render_site_history_panel
from utils.bootstrap import show_last_update, render_isp_multiselect, isp_label, apply_isp_filter
from utils.site_pack import render_multi_site_pack

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

if st.session_state.closed_df is None:
    with st.spinner("📡 Data auto-fetch ho raha hai (Google Sheet)..."):
        ok, msg = auto_load_tickets()
    if ok and msg != "already_loaded":
        st.toast(f"✅ Auto-loaded: {msg}", icon="📡")
    elif not ok:
        st.sidebar.error(f"Auto-load fail: {msg}")

show_last_update()

st.markdown("""
<div class="main-header">
    <h1>📡 XTRNATE Project :- KD</h1>
    <p>Hughes NOC • Xtranet Data • Site Search • SLA </p>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="search-card">', unsafe_allow_html=True)
st.markdown("**🔍 Site Code Quick Search** — type code → full down history + reasons")
sc1, sc2 = st.columns([5, 1])
with sc1:
    site_q = st.text_input(
        "Site Code",
        placeholder="e.g. XTNNTL358",
        key="home_site_search",
        label_visibility="collapsed",
    )
with sc2:
    search_btn = st.button("Search", type="primary", use_container_width=True, key="home_search_btn")
st.markdown("</div>", unsafe_allow_html=True)

if site_q and (search_btn or site_q):
    render_site_history_panel(site_q.strip().upper())
    st.markdown("---")

st.markdown("### 📋 Multi-site pack")
st.caption("Kai site codes ek saath paste — SIM, last mile, LC, circuit, full history. Excel + PDF.")
render_multi_site_pack()
st.markdown("---")

st.markdown("### ISP / Partner filter")
st.caption("Ek se zyada ISP tick karo — sirf selected ka data har page pe dikhega. Naya ISP sheet mein aaya to list mein auto add.")
render_isp_multiselect(location="main", key="isp_multi_main")

if st.button("🔄 Force Refresh Google Sheet"):
    st.cache_data.clear()
    ok, msg = auto_load_tickets(force=True)
    if ok:
        st.success(f"Refreshed: {msg}")
        st.rerun()
    else:
        st.error(msg)

if st.session_state.closed_df is not None or st.session_state.open_df is not None:
    st.markdown("### Live Status")
    c1, c2, c3 = st.columns(3)
    closed_f = apply_isp_filter(st.session_state.get("closed_df"))
    open_f = apply_isp_filter(st.session_state.get("open_df"))
    closed_count = 0 if closed_f is None else len(closed_f)
    open_count = 0 if open_f is None else len(open_f)
    c1.metric("Closed (selected ISP)", closed_count)
    c2.metric("Open (selected ISP)", open_count)
    c3.metric("ISP", isp_label())
    if closed_f is not None and not closed_f.empty and "isp" in closed_f.columns:
        vc = closed_f["isp"].value_counts()
        st.caption("Tickets by ISP: " + " • ".join(f"{k}={int(v)}" for k, v in vc.items()))

st.markdown("---")
st.markdown("### Pages")
st.caption("Category-wise — click karke page kholo. Sidebar mein bhi yahi groups hain.")

PAGE_CATS = [
    ("🎫 Tickets", [
        ("pages/1_Dashboard.py", "Dashboard", "📊"),
        ("pages/4_Open_Escalation.py", "Open Escalation", "🚨"),
        ("pages/7_Open_Calls_Dashboard.py", "Open Calls", "📞"),
        ("pages/3_Closed_Analysis.py", "Closed Analysis", "✅"),
        ("pages/6_Repeat_Analysis.py", "Repeat Analysis", "🔁"),
    ]),
    ("⚖️ ISP & Partner", [
        ("pages/8_ISP_Comparison.py", "ISP Comparison", "⚖️"),
        ("pages/12_Partner_Report.py", "Partner Report", "📄"),
        ("pages/9_Vendor_Performance.py", "Vendor Performance", "📈"),
        ("pages/20_Vendor_Change.py", "Vendor Change", "🔄"),
    ]),
    ("📅 SLA & Reports", [
        ("pages/11_Monthly_SLA_Report.py", "Monthly SLA", "📅"),
        ("pages/10_Penalty_SLA.py", "Penalty SLA", "⚠️"),
        ("pages/17_Holiday_Downtime.py", "Holiday Downtime", "🎆"),
        ("pages/16_Conclusion.py", "Conclusion PPT", "📚"),
    ]),
    ("📡 Daily Ops", [
        ("pages/14_VPN_Update.py", "VPN Update", "📡"),
        ("pages/15_Pending_Mail.py", "Pending Mail", "✉️"),
    ]),
    ("📶 SIM & Last Mile", [
        ("pages/19_SIM_Inventory.py", "SIM Inventory", "📱"),
        ("pages/18_SIM_Backup_Usage.py", "SIM Data Usage", "📶"),
        ("pages/13_Circuit_ID.py", "Circuit ID", "🔗"),
        ("pages/21_LC_Master.py", "LC Master", "📋"),
        ("pages/22_Last_Mile_Update.py", "Last Mile Update", "📍"),
    ]),
    ("🔧 Tools", [
        ("pages/0_Site_Search.py", "Site Search", "🔍"),
        ("pages/2_Upload_Data.py", "Upload Data", "📤"),
        ("pages/5_Escalation_Matrix.py", "Escalation Matrix", "⚙️"),
    ]),
]

r1 = PAGE_CATS[:3]
r2 = PAGE_CATS[3:]
for row in (r1, r2):
    cols = st.columns(len(row), gap="small")
    for col, (cat, items) in zip(cols, row):
        with col:
            with st.container(border=True):
                st.markdown(f"**{cat}**")
                for path, label, icon in items:
                    st.page_link(path, label=label, icon=icon)
