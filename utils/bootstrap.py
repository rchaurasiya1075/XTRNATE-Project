"""Call at top of every page: ensure data + ISP ready + last update banner."""
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.auto_load import auto_load_tickets

IST = ZoneInfo("Asia/Kolkata")

def show_last_update():
    """Top banner: last data load time. Safe to call on every page."""
    ts = st.session_state.get("data_last_updated")
    if ts is None:
        if st.session_state.get("closed_df") is not None or st.session_state.get("open_df") is not None:
            ts = datetime.now(IST)
            st.session_state.data_last_updated = ts
        else:
            msg = "Last data update: not loaded yet"
            ago = ""
    if ts is not None:
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=IST)
        now = datetime.now(IST)
        delta = now - ts
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            ago = "just now"
        elif mins < 60:
            ago = f"{mins} min pehle"
        else:
            hrs = mins // 60
            rem = mins % 60
            ago = f"{hrs} hr {rem} min pehle" if hrs < 24 else f"{hrs // 24} day pehle"
        stamp = ts.strftime("%d-%b-%Y %I:%M:%S %p IST")
        msg = f"Last data update: {stamp} ({ago})"
    st.markdown(
        f"""
        <div style="background:#0f172a;border:1px solid #38bdf8;border-radius:10px;
                    padding:8px 14px;margin:0 0 12px 0;color:#e2e8f0;
                    font-weight:700;font-size:0.95rem;">
          ⏱️ {msg}
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.caption(f"⏱️ {msg}")

def ensure_ready():
    if 'selected_isp' not in st.session_state or not st.session_state.selected_isp:
        st.session_state.selected_isp = "ALL"
    if st.session_state.get('closed_df') is None:
        with st.spinner("Data auto-fetch..."):
            auto_load_tickets()
    show_last_update()
    return st.session_state.get('selected_isp', 'ALL')
