"""Shared Site Code history search."""
import pandas as pd
import streamlit as st

def render_site_search_box(key_prefix="global"):
    """Top search bar — returns searched site code or None."""
    st.markdown("""
    <style>
    .site-search-box {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([4, 1])
    with c1:
        q = st.text_input(
            "🔍 Site Code Search",
            placeholder="e.g. XTNNTL358 — type & Enter",
            key=f"{key_prefix}_site_q",
            label_visibility="collapsed",
        )
    with c2:
        go = st.button("Search", type="primary", use_container_width=True, key=f"{key_prefix}_site_go")

    if q:
        return str(q).strip().upper()
    return None

def get_site_history(site_code: str):
    """Return closed history + open tickets for a site code."""
    site = str(site_code).strip().upper()
    closed = st.session_state.get('closed_df')
    open_df = st.session_state.get('open_df')

    hist = pd.DataFrame()
    opens = pd.DataFrame()

    if closed is not None and not closed.empty and 'site_code' in closed.columns:
        hist = closed[closed['site_code'].astype(str).str.strip().str.upper() == site].copy()
        if 'submitted_time' in hist.columns:
            hist = hist.sort_values('submitted_time', ascending=False)

    if open_df is not None and not open_df.empty and 'site_code' in open_df.columns:
        opens = open_df[open_df['site_code'].astype(str).str.strip().str.upper() == site].copy()

    return hist, opens

def render_site_history_panel(site_code: str):
    """Full history UI for one site."""
    hist, opens = get_site_history(site_code)

    st.markdown(f"### 📍 Site: `{site_code}`")

    if hist.empty and opens.empty:
        st.warning(f"Site **{site_code}** ka koi data nahi mila. Spelling / code check karo.")
        return

    # KPIs
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Past Downs", len(hist))
    m2.metric("Currently Open", len(opens))
    if not hist.empty and 'resolution_days' in hist.columns:
        m3.metric("Avg Resolve Days", round(hist['resolution_days'].mean(), 1))
        if 'down_time_min' in hist.columns:
            m4.metric("Total Downtime Hrs", round(hist['down_time_min'].sum() / 60, 1))
        else:
            m4.metric("Max Resolve Days", round(hist['resolution_days'].max(), 1))
    elif not hist.empty and 'down_time_min' in hist.columns:
        m3.metric("Total Downtime Hrs", round(hist['down_time_min'].sum() / 60, 1))

    if not opens.empty:
        st.markdown("#### 🚨 Currently Open")
        cols = [c for c in ['ticket_id', 'status', 'submitted_time', 'open_hours', 'reason', 'owner', 'state'] if c in opens.columns]
        st.dataframe(opens[cols], use_container_width=True)

    if not hist.empty:
        st.markdown("#### 📜 Complete Down History")
        cols = [c for c in [
            'ticket_id', 'submitted_time', 'resolved_time', 'resolution_days',
            'down_time_min', 'category', 'reason_clean', 'reason', 'owner', 'isp', 'state', 'city'
        ] if c in hist.columns]
        st.dataframe(hist[cols], use_container_width=True, height=420)

        if 'category' in hist.columns:
            st.markdown("#### Reasons / Category breakdown")
            cat = hist['category'].value_counts().reset_index()
            cat.columns = ['Category', 'Count']
            st.dataframe(cat, use_container_width=True)

        st.download_button(
            f"📥 Download {site_code} History",
            data=hist[cols].to_csv(index=False).encode('utf-8'),
            file_name=f"History_{site_code}.csv",
            mime="text/csv",
            key=f"dl_hist_{site_code}"
        )
