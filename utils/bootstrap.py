"""Call at top of every page: ensure data + ISP ready + last TT raise banner."""
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.auto_load import auto_load_tickets

IST = ZoneInfo("Asia/Kolkata")


def last_ticket_raise():
    """Last TT raise = max Submitted Time (not resolve / not last modified)."""
    best_ts, best_id, best_site = None, "", ""
    for key in ("raw_tickets_df", "closed_df", "open_df"):
        df = st.session_state.get(key)
        if df is None or getattr(df, "empty", True):
            continue
        col = None
        if "submitted_time" in df.columns:
            col = "submitted_time"
        elif "Submitted Time" in df.columns:
            col = "Submitted Time"
        if not col:
            continue
        ser = pd.to_datetime(df[col], errors="coerce")
        if ser.dropna().empty:
            continue
        idx = ser.idxmax()
        ts = ser.loc[idx]
        if pd.isna(ts):
            continue
        tid = ""
        site = ""
        if "ticket_id" in df.columns:
            tid = str(df.loc[idx, "ticket_id"] or "")
        elif "Incident ID" in df.columns:
            tid = str(df.loc[idx, "Incident ID"] or "")
        if "site_code" in df.columns:
            site = str(df.loc[idx, "site_code"] or "")
        if best_ts is None or ts > best_ts:
            best_ts, best_id, best_site = ts, tid, site
    if best_ts is None:
        return None, "", ""
    ts = best_ts
    if getattr(ts, "tzinfo", None) is None:
        try:
            ts = ts.tz_localize(IST)
        except Exception:
            ts = pd.Timestamp(ts).tz_localize(IST, ambiguous="infer")
    else:
        ts = ts.tz_convert(IST)
    ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    return ts, best_id, best_site


def last_ticket_time():
    ts, _, _ = last_ticket_raise()
    return ts


def show_last_update():
    ts, tid, site = last_ticket_raise()
    if ts is None:
        msg = "Last TT raise: data not loaded"
    else:
        now = datetime.now(IST)
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=IST)
        delta = now - ts
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            ago = "just now"
        elif mins < 60:
            ago = f"{mins} min pehle"
        elif mins < 1440:
            ago = f"{mins // 60} hr {mins % 60} min pehle"
        else:
            ago = f"{mins // 1440} day pehle"
        stamp = ts.strftime("%d-%b-%Y %I:%M:%S %p IST")
        extra = []
        if tid and tid.lower() not in ("nan", "none"):
            extra.append(f"TT {tid}")
        if site and site.lower() not in ("nan", "none"):
            extra.append(site)
        tail = (" • " + " • ".join(extra)) if extra else ""
        msg = f"Last TT raise: {stamp}{tail}  ({ago})"

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
        st.markdown("**⏱️ Last TT raise**")
        st.caption(msg)


def ensure_ready():
    if 'selected_isp' not in st.session_state or not st.session_state.selected_isp:
        st.session_state.selected_isp = "ALL"
    if st.session_state.get('closed_df') is None:
        with st.spinner("Data auto-fetch..."):
            auto_load_tickets()
    show_last_update()
    return st.session_state.get('selected_isp', 'ALL')
