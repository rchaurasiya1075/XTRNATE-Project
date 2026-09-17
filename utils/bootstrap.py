"""Call at top of every page: ensure data + ISP ready + last TT raise banner."""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from utils.auto_load import auto_load_tickets
from utils.data_source import init_data_source, source_status, set_project, ensure_project_loaded

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
        msg = "Last update (Last TT raise): data not loaded"
    else:
        now = datetime.now(IST)
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=IST)
        delta = now - ts
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            ago = "just now"
        elif mins < 60:
            ago = f"{mins} min ago"
        elif mins < 1440:
            ago = f"{mins // 60} hr {mins % 60} min ago"
        else:
            ago = f"{mins // 1440} day ago"
        stamp = ts.strftime("%d-%b-%Y %I:%M:%S %p IST")
        extra = []
        if tid and tid.lower() not in ("nan", "none"):
            extra.append(f"TT {tid}")
        if site and site.lower() not in ("nan", "none"):
            extra.append(site)
        tail = (" • " + " • ".join(extra)) if extra else ""
        msg = f"Last update = Last TT raise: {stamp}{tail}  ({ago})"
    try:
        msg = f"{msg}  •  {source_status()}"
    except Exception:
        pass

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
        st.markdown("**⏱️ Last update (Last TT raise)**")
        st.caption(msg)


def available_isps():
    from utils.data_processing import isp_options
    opts = isp_options(
        st.session_state.get("closed_df"),
        st.session_state.get("open_df"),
        st.session_state.get("raw_tickets_df"),
        add_all=False,
    )
    return opts or ["HCIN", "ONEOTT"]


def get_selected_isps():
    """List of currently selected ISP names. Empty list means none."""
    opts = available_isps()
    val = st.session_state.get("selected_isps")
    if val is None:
        old = st.session_state.get("selected_isp", "ALL")
        if old in (None, "", "ALL"):
            val = list(opts)
            st.session_state["_isp_all_mode"] = True
        elif old == "NONE":
            val = []
            st.session_state["_isp_all_mode"] = False
        elif " + " in str(old):
            val = [x.strip() for x in str(old).split("+") if x.strip() in opts] or list(opts)
            st.session_state["_isp_all_mode"] = set(val) >= set(opts)
        elif old in opts:
            val = [old]
            st.session_state["_isp_all_mode"] = False
        else:
            val = list(opts)
            st.session_state["_isp_all_mode"] = True
        st.session_state.selected_isps = val
    if st.session_state.get("_isp_all_mode"):
        val = list(opts)
        st.session_state.selected_isps = val
    else:
        val = [x for x in (val or []) if x in opts]
        st.session_state.selected_isps = val
    return val


def isp_label(selected=None):
    opts = available_isps()
    selected = list(selected) if selected is not None else get_selected_isps()
    if not selected:
        return "NONE"
    if set(selected) >= set(opts):
        return "ALL"
    return " + ".join(selected)


def apply_period_filter(df):
    """Last 1–7 months or custom From–To on submitted_time. Default = all data."""
    if df is None or getattr(df, "empty", True):
        return df
    mode = st.session_state.get("period_mode") or "All time"
    if mode == "All time":
        return df
    col = None
    for c in ("submitted_time", "Submitted Time", "resolved_time"):
        if c in df.columns:
            col = c
            break
    if col is None:
        return df
    ts = pd.to_datetime(df[col], errors="coerce")
    if mode == "Custom":
        d0 = st.session_state.get("period_from")
        d1 = st.session_state.get("period_to")
        if not d0 or not d1:
            return df
        start = pd.Timestamp(d0)
        end = pd.Timestamp(d1) + pd.Timedelta(days=1)
        return df.loc[ts.notna() & (ts >= start) & (ts < end)].copy()
    months = int(st.session_state.get("period_months") or 0)
    if months <= 0:
        return df
    cutoff = pd.Timestamp(datetime.now(IST).replace(tzinfo=None)) - pd.DateOffset(months=months)
    return df.loc[ts.notna() & (ts >= cutoff)].copy()


def apply_isp_filter(df):
    from utils.data_processing import filter_by_isps
    if df is None:
        return df
    picked = get_selected_isps()
    opts = available_isps()
    out = df
    if not (st.session_state.get("_isp_all_mode") or (picked and set(picked) >= set(opts))):
        out = filter_by_isps(df, picked)
    return apply_period_filter(out)


def render_project_pick():
    """Page-level project switch — VPN / Mail / Report use this, not leftover Xtranet."""
    init_data_source()
    opts = list(st.session_state.projects)
    cur = st.session_state.active_project
    if cur not in opts:
        opts = [cur] + opts
    idx = opts.index(cur) if cur in opts else 0
    picked = st.selectbox("Project data", opts, index=idx)
    if picked != cur:
        set_project(picked)
        if st.session_state.get("data_source") != "upload":
            auto_load_tickets(force=True)
            st.session_state._view_project = picked
        st.rerun()
    st.caption(f"This page uses **{picked}** only.")


def render_period_filter():
    init_data_source()
    if "period_mode" not in st.session_state:
        st.session_state.period_mode = "All time"
        st.session_state.period_months = 3
        st.session_state.period_from = date.today() - timedelta(days=90)
        st.session_state.period_to = date.today()
    c1, c2, c3 = st.columns([1.4, 1.4, 2.2])
    with c1:
        mode = st.radio(
            "View period",
            ["All time", "Last N months", "Custom dates"],
            horizontal=True,
            key="period_mode_radio",
        )
        st.session_state.period_mode = {"All time": "All time", "Last N months": "Months", "Custom dates": "Custom"}[mode]
    with c2:
        n = st.selectbox(
            "Months",
            [1, 2, 3, 4, 5, 6, 7],
            index=2,
            key="period_months_sel",
            disabled=(st.session_state.period_mode != "Months"),
        )
        st.session_state.period_months = int(n)
    with c3:
        disabled = st.session_state.period_mode != "Custom"
        rng = st.date_input(
            "From → To",
            value=(st.session_state.period_from, st.session_state.period_to),
            key="period_custom_rng",
            disabled=disabled,
        )
        if isinstance(rng, (list, tuple)) and len(rng) == 2 and rng[0] and rng[1]:
            st.session_state.period_from, st.session_state.period_to = rng[0], rng[1]
    mode = st.session_state.period_mode
    if mode == "Months":
        st.caption(f"Showing last **{st.session_state.period_months}** month(s).")
    elif mode == "Custom":
        st.caption(f"Showing **{st.session_state.period_from}** → **{st.session_state.period_to}**.")
    else:
        st.caption("Showing all dates.")


def render_isp_multiselect(location="main", key="isp_multi_main"):
    """Multi-select ISP picker. Sidebar + page dono se sync."""
    opts = available_isps()
    stored = get_selected_isps()
    stored = [x for x in stored if x in opts]
    src = st.session_state.get("_isp_src")

    if st.session_state.pop(f"{key}_set_all", False):
        st.session_state[key] = list(opts)
        st.session_state.selected_isps = list(opts)
        st.session_state["_isp_all_mode"] = True
        stored = list(opts)
    if st.session_state.pop(f"{key}_set_clr", False):
        st.session_state[key] = []
        st.session_state.selected_isps = []
        st.session_state["_isp_all_mode"] = False
        stored = []

    if key not in st.session_state:
        st.session_state[key] = stored
    elif src and src != key:
        st.session_state[key] = stored

    if location == "sidebar":
        box = st.sidebar
    else:
        box = st.container()
    with box:
        if location == "sidebar":
            st.markdown("**ISP / Partner filter**")
            st.caption("You can select more than one")
        picked = st.multiselect(
            "ISP / Partner (multiple)",
            options=opts,
            key=key,
            help="Tick every ISP you need — only their data is shown.",
            placeholder="Select one or more ISP…",
        )
        c1, c2 = st.columns(2)
        if c1.button("All ISPs", key=f"{key}_all", use_container_width=True):
            st.session_state[f"{key}_set_all"] = True
            st.session_state._isp_src = key
            st.rerun()
        if c2.button("Clear", key=f"{key}_clr", use_container_width=True):
            st.session_state[f"{key}_set_clr"] = True
            st.session_state._isp_src = key
            st.rerun()

    st.session_state.selected_isps = list(picked)
    st.session_state._isp_src = key
    st.session_state["_isp_all_mode"] = bool(picked) and set(picked) >= set(opts)
    label = isp_label(picked)
    st.session_state.selected_isp = label
    if location == "main":
        if not picked:
            st.warning("No ISP selected — click All ISPs or tick names from the list.")
        else:
            st.success(f"**Active ISP:** {label}")
    else:
        st.sidebar.caption(f"Active: **{label}**")
    return picked


def ensure_ready():
    init_data_source()
    if "selected_isp" not in st.session_state or not st.session_state.selected_isp:
        st.session_state.selected_isp = "ALL"
    if "selected_isps" not in st.session_state:
        st.session_state.selected_isps = None
    ensure_project_loaded()
    if st.session_state.get("closed_df") is None:
        if st.session_state.get("data_source") == "upload":
            from utils.data_source import apply_active
            apply_active()
        else:
            with st.spinner("Data auto-fetch..."):
                auto_load_tickets()
            st.session_state._view_project = st.session_state.active_project
    show_last_update()
    render_project_pick()
    render_period_filter()
    render_isp_multiselect(location="main", key="isp_multi_main")
    with st.sidebar:
        st.markdown("**Active ISP / Partner**")
        st.caption(isp_label() + "  •  Change: multi-select at the top of the page")
        st.caption(source_status())
    return isp_label()
