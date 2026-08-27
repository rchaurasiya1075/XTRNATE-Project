"""Call at top of every page: ensure data + ISP ready + last ticket time banner."""
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.auto_load import auto_load_tickets

IST = ZoneInfo("Asia/Kolkata")


def last_ticket_time():
    """Latest ticket that arrived = max Submitted Time across loaded data."""
    frames = []
    for key in ("raw_tickets_df", "closed_df", "open_df"):
        df = st.session_state.get(key)
        if df is not None and not getattr(df, "empty", True) and "submitted_time" in df.columns:
            frames.append(pd.to_datetime(df["submitted_time"], errors="coerce"))
    if not frames:
        return None
    series = pd.concat(frames, ignore_index=True).dropna()
    if series.empty:
        return None
    ts = series.max()
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is None:
        try:
            ts = ts.tz_localize(IST)
        except Exception:
            ts = pd.Timestamp(ts).tz_localize(IST, ambiguous="infer")
    else:
        ts = ts.tz_convert(IST)
    return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts


def show_last_update():
    ts = last_ticket_time()
    if ts is None:
        msg = "Last ticket: data not loaded"
    else:
        now = datetime.now(IST)
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=IST)
        delta = now - ts
        mins = int(delta.total_seconds() // 60)
        if mins < 0:
            ago = "just now"
        elif mins < 1:
            ago = "just now"
        elif mins < 60:
            ago = f"{mins} min pehle"
        elif mins < 1440:
            ago = f"{mins // 60} hr {mins % 60} min pehle"
        else:
            ago = f"{mins // 1440} day pehle"
        stamp = ts.strftime("%d-%b-%Y %I:%M:%S %p IST")
        msg = f"Last ticket received: {stamp}  ({ago})"

    st.markdown(
        f"""
        <div style="position:sticky;top:0;z-index:999;
                    background:#0b1220;border-bottom:2px solid #38bdf8;
                    padding:10px 16px;margin:0 0 14px 0;color:#f8fafc;
                    font-weight:800;font-size:1.02rem;letter-spacing:0.02em;">
          ⏱️ {msg}
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown(f"**⏱️ Last ticket**")
        st.caption(msg)


def ensure_ready():
    if 'selected_isp' not in st.session_state or not st.session_state.selected_isp:
        st.session_state.selected_isp = "ALL"
    if st.session_state.get('closed_df') is None:
        with st.spinner("Data auto-fetch..."):
            auto_load_tickets()
    show_last_update()
    return st.session_state.get('selected_isp', 'ALL')
