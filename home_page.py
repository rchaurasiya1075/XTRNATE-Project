import streamlit as st
from utils.auto_load import auto_load_tickets
from utils.site_search import render_site_history_panel
from utils.bootstrap import show_last_update

if "selected_isp" not in st.session_state:
    st.session_state.selected_isp = "ALL"
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

st.markdown("### ISP Filter (optional)")
st.caption("Default = ALL. Specific partner chahiye to select karo.")
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
    if st.button("📊 ALL", use_container_width=True,
                 type="primary" if st.session_state.selected_isp == "ALL" else "secondary"):
        st.session_state.selected_isp = "ALL"
        st.rerun()

st.success(f"**Active:** {st.session_state.selected_isp}  |  Data loaded automatically")

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
    closed_count = len(st.session_state.closed_df) if st.session_state.closed_df is not None else 0
    open_count = len(st.session_state.open_df) if st.session_state.open_df is not None else 0
    c1.metric("Closed", closed_count)
    c2.metric("Open", open_count)
    c3.metric("ISP", st.session_state.selected_isp)

st.markdown("---")
st.caption("Sidebar categories: Tickets • SIM & Data • Reports • Tools")
