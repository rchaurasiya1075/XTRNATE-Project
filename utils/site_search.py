"""Shared Site Code history search."""
import pandas as pd
import streamlit as st
from utils.report_download import download_pack

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
        st.warning(f"No data found for site **{site_code}**. Check the spelling / code.")
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

        download_pack(
            f"{site_code} History",
            hist[cols],
            file_stem=f"History_{site_code}",
            title=f"Site History  ·  {site_code}",
            sheet_name="History",
            key=f"dl_hist_{site_code}",
        )


def last_month_down_counts(closed=None):
    """Site → down count in the last 30 days (from latest ticket)."""
    if closed is None:
        closed = st.session_state.get("closed_df")
    empty = pd.Series(dtype=int)
    if closed is None or closed.empty or "site_code" not in closed.columns:
        return empty, None, None, pd.DataFrame()
    df = closed.copy()
    tcol = "submitted_time" if "submitted_time" in df.columns else None
    start = end = None
    if tcol:
        df[tcol] = pd.to_datetime(df[tcol], errors="coerce")
        end = df[tcol].max()
        if pd.isna(end):
            end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=30)
        df = df[df[tcol].notna() & (df[tcol] >= start) & (df[tcol] <= end)]
    vc = df["site_code"].astype(str).str.strip().str.upper()
    vc = vc[vc.ne("") & vc.ne("NAN") & vc.ne("NONE")].value_counts()
    return vc, start, end, df


def render_last_month_down_categories():
    """3 / 5 / 6 / 7+ downs in the last 30 days — click a site for history."""
    vc, start, end, month_df = last_month_down_counts()
    rng = ""
    if start is not None and end is not None:
        rng = f"{pd.Timestamp(start).strftime('%d-%b-%Y')} → {pd.Timestamp(end).strftime('%d-%b-%Y')}"
    st.markdown("### Last 30 days — down frequency")
    st.caption(
        "How many times each site went down in the last month. "
        f"{rng}".strip()
        + "  •  Open a category, then a site, to see full history."
    )
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
            st.info(f"No sites with {label.lower()} down in the last 30 days.")
            return
        top = ser.reset_index()
        top.columns = ["Site Code", "Downs (last 30 days)"]
        st.dataframe(top, use_container_width=True, hide_index=True, height=min(360, 48 + 32 * min(len(top), 10)))
        pick = st.selectbox(
            f"Open site history — {label}",
            ["—"] + list(ser.index),
            key=f"freq_pick_{label.replace(' ', '_')}",
        )
        if pick and pick != "—":
            render_site_history_panel(pick)
            if month_df is not None and not month_df.empty and "site_code" in month_df.columns:
                one = month_df[month_df["site_code"].astype(str).str.upper() == pick]
                cols = [c for c in [
                    "ticket_id", "submitted_time", "resolved_time", "state", "reason",
                    "reason_clean", "category", "down_time_min", "owner",
                ] if c in one.columns]
                if not one.empty and cols:
                    st.caption(f"{pick} — tickets in this 30-day window")
                    st.dataframe(one[cols], use_container_width=True, height=220)

    tabs = st.tabs([f"{lab} ({len(ser)})" for lab, ser in cats] + ["1 / 2 / 4 times"])
    for tab, (label, ser) in zip(tabs[:4], cats):
        with tab:
            _show_bucket(label, ser)
    with tabs[4]:
        for label, ser in extra:
            st.markdown(f"**{label} down — {len(ser)} sites**")
            _show_bucket(label, ser)
            st.markdown("---")

