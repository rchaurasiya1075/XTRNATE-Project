"""Shared Site Code history search."""
import pandas as pd
import streamlit as st
from utils.excel_export import excel_bytes


def _upper_col(df, tag):
    if df is None or getattr(df, "empty", True) or "site_code" not in df.columns:
        return None
    n = len(df)
    k, kn = f"_uc_{tag}", f"_uc_{tag}_n"
    if st.session_state.get(kn) != n:
        st.session_state[k] = df["site_code"].astype(str).str.strip().str.upper()
        st.session_state[kn] = n
    return st.session_state.get(k)


def get_site_history(site_code: str):
    """Return closed history + open tickets for a site code."""
    site = str(site_code).strip().upper()
    closed = st.session_state.get("closed_df")
    open_df = st.session_state.get("open_df")
    hist = pd.DataFrame()
    opens = pd.DataFrame()
    uc = _upper_col(closed, "closed")
    if uc is not None:
        hist = closed.loc[uc == site]
        if not hist.empty and "submitted_time" in hist.columns:
            hist = hist.sort_values("submitted_time", ascending=False)
    uo = _upper_col(open_df, "open")
    if uo is not None:
        opens = open_df.loc[uo == site]
    return hist, opens


def render_site_history_panel(site_code: str):
    """Full history UI for one site — Excel download only (no PDF on every search)."""
    hist, opens = get_site_history(site_code)
    st.markdown(f"### `{site_code}`")
    if hist.empty and opens.empty:
        src = "uploaded Excel" if st.session_state.get("data_source") == "upload" else "Google Sheet"
        st.warning(f"No tickets for **{site_code}** in the {src}. Check the code or switch data mode.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Past downs", len(hist))
    m2.metric("Open now", len(opens))
    if not hist.empty and "down_time_min" in hist.columns:
        dt = pd.to_numeric(hist["down_time_min"], errors="coerce")
        m3.metric("Downtime hrs", round(float(dt.sum() or 0) / 60, 1))
    if not hist.empty and "resolution_days" in hist.columns:
        m4.metric("Avg resolve days", round(float(pd.to_numeric(hist["resolution_days"], errors="coerce").mean() or 0), 1))

    if not opens.empty:
        st.markdown("**Open tickets**")
        cols = [c for c in ["ticket_id", "status", "submitted_time", "open_hours", "reason", "owner", "state"] if c in opens.columns]
        st.dataframe(opens[cols], use_container_width=True, hide_index=True)

    if not hist.empty:
        st.markdown("**Down history**")
        cols = [c for c in [
            "ticket_id", "submitted_time", "resolved_time", "resolution_days",
            "down_time_min", "category", "reason_clean", "reason", "owner", "isp", "state", "city",
        ] if c in hist.columns]
        st.dataframe(hist[cols], use_container_width=True, height=min(420, 48 + 28 * min(len(hist), 12)), hide_index=True)
        if "category" in hist.columns:
            cat = hist["category"].value_counts().rename_axis("Category").reset_index(name="Count")
            st.dataframe(cat, use_container_width=True, hide_index=True, height=160)
        xls = excel_bytes(
            hist[cols],
            title=f"Site History  ·  {site_code}",
            sheet_name="History",
        )
        st.download_button(
            f"Download {site_code} Excel",
            data=xls,
            file_name=f"Site_History_{site_code}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_hist_{site_code}",
        )


def last_month_down_counts(closed=None):
    if closed is None:
        closed = st.session_state.get("closed_df")
    empty = pd.Series(dtype=int)
    if closed is None or closed.empty or "site_code" not in closed.columns:
        return empty, None, None, pd.DataFrame()
    tcol = "submitted_time" if "submitted_time" in closed.columns else None
    start = end = None
    df = closed
    if tcol:
        ts = pd.to_datetime(closed[tcol], errors="coerce")
        end = ts.max()
        if pd.isna(end):
            end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=30)
        df = closed.loc[ts.notna() & (ts >= start) & (ts <= end)]
    vc = df["site_code"].astype(str).str.strip().str.upper()
    vc = vc[vc.ne("") & vc.ne("NAN") & vc.ne("NONE")].value_counts()
    return vc, start, end, df


def render_last_month_down_categories():
    vc, start, end, month_df = last_month_down_counts()
    rng = ""
    if start is not None and end is not None:
        rng = f"{pd.Timestamp(start).strftime('%d-%b-%Y')} → {pd.Timestamp(end).strftime('%d-%b-%Y')}"
    st.caption(f"Last 30 days {rng}".strip())
    cats = [
        ("3 times", vc[vc == 3] if not vc.empty else vc),
        ("5 times", vc[vc == 5] if not vc.empty else vc),
        ("6 times", vc[vc == 6] if not vc.empty else vc),
        ("7+ times", vc[vc >= 7] if not vc.empty else vc),
    ]
    extra = [
        ("1 time", vc[vc == 1] if not vc.empty else vc),
        ("2 times", vc[vc == 2] if not vc.empty else vc),
        ("4 times", vc[vc == 4] if not vc.empty else vc),
    ]
    mcols = st.columns(4)
    for col, (label, ser) in zip(mcols, cats):
        col.metric(f"{label} down", int(len(ser)))

    def _show_bucket(label, ser):
        if ser is None or len(ser) == 0:
            st.info(f"No sites with {label.lower()} down in this window.")
            return
        top = ser.reset_index()
        top.columns = ["Site Code", "Downs (last 30 days)"]
        st.dataframe(top, use_container_width=True, hide_index=True, height=min(280, 48 + 28 * min(len(top), 8)))
        pick = st.selectbox(
            f"Open site — {label}",
            ["—"] + list(ser.index),
            key=f"freq_pick_{label.replace(' ', '_')}",
        )
        if pick and pick != "—":
            render_site_history_panel(pick)

    tabs = st.tabs([f"{lab} ({len(ser)})" for lab, ser in cats] + ["1 / 2 / 4"])
    for tab, (label, ser) in zip(tabs[:4], cats):
        with tab:
            _show_bucket(label, ser)
    with tabs[4]:
        for label, ser in extra:
            st.markdown(f"**{label} down — {len(ser)} sites**")
            _show_bucket(label, ser)
