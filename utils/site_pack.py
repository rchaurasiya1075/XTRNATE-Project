"""Multi-site pack: paste many site codes → history + SIM + last mile + LC + circuit."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from utils.google_sheets import load_sheet_as_csv
from utils.report_download import download_pack

XTRANET = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
SIM_GID = "1240520075"
CKT_GID = "886642043"
LC_GID = "401145054"
MASTER_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
MASTER_GID = "1181450647"

HIST_COLS = [
    "ticket_id", "site_code", "submitted_time", "resolved_time", "resolution_days",
    "down_time_min", "status", "category", "reason_clean", "reason", "owner", "isp",
    "state", "city", "open_hours",
]


def parse_site_codes(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[\s,;|]+", str(text).strip().upper())
    out, seen = [], set()
    for p in parts:
        s = re.sub(r"[^A-Z0-9\-_]", "", p)
        if not s or s in seen or s in ("SITE", "CODE", "SITECODE", "SITES"):
            continue
        seen.add(s)
        out.append(s)
    return out


def _col(df, *names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    for key, col in lower.items():
        for n in names:
            if n.lower() in key:
                return col
    return None


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "--") else s


@st.cache_data(ttl=180, show_spinner=False)
def _load_sim():
    df = load_sheet_as_csv(XTRANET, gid=SIM_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "site code", "sitecode") or df.columns[0]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


@st.cache_data(ttl=180, show_spinner=False)
def _load_ckt():
    df = load_sheet_as_csv(XTRANET, gid=CKT_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


@st.cache_data(ttl=180, show_spinner=False)
def _load_lc():
    df = load_sheet_as_csv(XTRANET, gid=LC_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughes site code", "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


@st.cache_data(ttl=180, show_spinner=False)
def _load_master():
    df = load_sheet_as_csv(MASTER_ID, gid=MASTER_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughessitecode", "site code", "sitecode") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


def _safe_load(fn):
    try:
        return fn()
    except Exception:
        return pd.DataFrame()


def _slice(df, site):
    if df is None or getattr(df, "empty", True) or "site_code" not in df.columns:
        return df.iloc[0:0].copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return df[df["site_code"].astype(str).str.strip().str.upper() == site].copy()


def _first(df, *names):
    if df is None or df.empty:
        return ""
    row = df.iloc[0]
    for n in names:
        if n in row.index:
            v = _clean(row.get(n))
            if v:
                return v
    lower = {str(i).strip().lower(): i for i in row.index}
    for n in names:
        if n.lower() in lower:
            v = _clean(row.get(lower[n.lower()]))
            if v:
                return v
    return ""


def build_pack(codes: list[str]) -> dict:
    closed = st.session_state.get("closed_df")
    open_df = st.session_state.get("open_df")
    raw = st.session_state.get("raw_tickets_df")
    sim = _safe_load(_load_sim)
    ckt = _safe_load(_load_ckt)
    lc = _safe_load(_load_lc)
    master = _safe_load(_load_master)

    summary_rows = []
    hist_all, open_all, sim_all, ckt_all, lc_all, lm_all = [], [], [], [], [], []

    for site in codes:
        hist = _slice(closed, site)
        if hist.empty:
            hist = _slice(raw, site)
        opens = _slice(open_df, site)
        srow = _slice(sim, site)
        crow = _slice(ckt, site)
        lrow = _slice(lc, site)
        mrow = _slice(master, site)

        if not hist.empty:
            hist_all.append(hist)
        if not opens.empty:
            open_all.append(opens)
        if not srow.empty:
            sim_all.append(srow)
        if not crow.empty:
            ckt_all.append(crow)
        if not lrow.empty:
            lc_all.append(lrow)
        if not mrow.empty:
            lm_all.append(mrow)

        downs = len(hist)
        dt_hrs = 0
        if not hist.empty and "down_time_min" in hist.columns:
            dt_hrs = round(pd.to_numeric(hist["down_time_min"], errors="coerce").fillna(0).sum() / 60, 1)
        summary_rows.append({
            "site_code": site,
            "found": "Yes" if any(len(x) for x in (hist, opens, srow, crow, lrow, mrow)) else "No",
            "past_downs": downs,
            "open_now": len(opens),
            "downtime_hrs": dt_hrs,
            "isp": _first(mrow, "ISP Name", "ISP", "isp") or _first(crow, "ISP", "isp") or _first(hist, "isp", "owner"),
            "media": _first(mrow, "Media"),
            "ckt_id": _first(mrow, "Ckt ID") or _first(crow, "Ckt ID", "ckt_id"),
            "bank": _first(mrow, "Bank Name") or _first(crow, "Bank Name", "bank_name"),
            "branch": _first(mrow, "Branch Name") or _first(crow, "Branch Name", "branch_name"),
            "state": _first(mrow, "State") or _first(hist, "state") or _first(crow, "State", "state"),
            "lc_name": _first(lrow, "Branch Person Name", "lc_name") or _first(mrow, "Branch Person Name"),
            "lc_phone": _first(lrow, "Contact Number", "lc_phone") or _first(mrow, "Branch Person Contact Number"),
            "sim_status": _first(srow, "Status", "status"),
            "sim_mdn": _first(srow, "MDN Number", "MDN", "mdn"),
            "sim_ip": _first(srow, "IP Address", "IP", "ip"),
            "sim_telco": _first(srow, "Telco", "telco"),
        })

    def cat(frames):
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        return out.loc[:, ~out.columns.duplicated()]

    return {
        "summary": pd.DataFrame(summary_rows),
        "history": cat(hist_all),
        "open": cat(open_all),
        "sim": cat(sim_all),
        "circuit": cat(ckt_all),
        "lc": cat(lc_all),
        "last_mile": cat(lm_all),
    }


def _hist_view(df):
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [c for c in HIST_COLS if c in df.columns]
    return df[cols] if cols else df


def render_multi_site_pack():
    st.markdown("**Paste site codes** — comma / space / new line. Ek saath history + SIM + last mile + LC + circuit.")
    blob = st.text_area(
        "Site codes",
        placeholder="XTNNTL358\nXTNCHG364, XTNSLN354  XTNDEL201",
        height=110,
        key="dash_multi_sites",
        label_visibility="collapsed",
    )
    go = st.button("Load all sites", type="primary", key="dash_multi_go")
    if not go:
        n = len(parse_site_codes(blob or ""))
        if n:
            st.caption(f"{n} site code ready — **Load all sites** dabao.")
        return

    codes = parse_site_codes(blob or "")
    if not codes:
        st.warning("Koi site code nahi mila. Paste karke Load dabao.")
        return
    if len(codes) > 80:
        st.warning(f"{len(codes)} codes — pehle 80 dikha raha hoon.")
        codes = codes[:80]

    with st.spinner(f"{len(codes)} sites ka pack ban raha hai..."):
        pack = build_pack(codes)

    summary = pack["summary"]
    found_n = int((summary["found"] == "Yes").sum()) if not summary.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Codes", len(codes))
    k2.metric("Found", found_n)
    k3.metric("Not found", len(codes) - found_n)
    k4.metric("Past downs", int(summary["past_downs"].sum()) if not summary.empty else 0)

    st.markdown("#### Overall — har site ek row")
    st.dataframe(summary, use_container_width=True, height=min(420, 48 + 32 * min(len(summary), 12)))

    missing = summary[summary["found"] == "No"]["site_code"].tolist() if not summary.empty else []
    if missing:
        st.caption("Not found: " + ", ".join(missing[:40]) + ("…" if len(missing) > 40 else ""))

    sheets = {"Summary": summary}
    hv = _hist_view(pack["history"])
    if not hv.empty:
        sheets["Ticket_History"] = hv
    ov = _hist_view(pack["open"])
    if not ov.empty:
        sheets["Open_Tickets"] = ov
    if not pack["sim"].empty:
        sheets["SIM"] = pack["sim"]
    if not pack["circuit"].empty:
        sheets["Circuit"] = pack["circuit"]
    if not pack["lc"].empty:
        sheets["LC"] = pack["lc"]
    if not pack["last_mile"].empty:
        sheets["Last_Mile"] = pack["last_mile"]

    download_pack(
        f"{len(codes)} sites pack",
        sheets,
        file_stem=f"XTRNATE_MultiSite_{len(codes)}",
        title="Multi-site pack  ·  History + SIM + Last Mile + LC",
        subtitle=f"{len(codes)} site codes",
        key="dash_multisite_dl",
    )

    st.markdown("#### Site-wise detail")
    for site in codes:
        row = summary[summary["site_code"] == site].iloc[0]
        with st.expander(
            f"{site}  ·  downs {int(row['past_downs'])}  ·  open {int(row['open_now'])}  ·  {row['isp'] or '—'}  ·  {row['found']}",
            expanded=False,
        ):
            a, b, c = st.columns(3)
            a.write(f"**Bank / Branch:** {row['bank'] or '—'} / {row['branch'] or '—'}")
            a.write(f"**State:** {row['state'] or '—'}")
            a.write(f"**Media / ISP:** {row['media'] or '—'} / {row['isp'] or '—'}")
            b.write(f"**Circuit:** `{row['ckt_id'] or '—'}`")
            b.write(f"**LC:** {row['lc_name'] or '—'}  {row['lc_phone'] or ''}")
            c.write(f"**SIM:** {row['sim_status'] or '—'}")
            c.write(f"**MDN:** `{row['sim_mdn'] or '—'}`")
            c.write(f"**IP:** `{row['sim_ip'] or '—'}`  ·  {row['sim_telco'] or ''}")

            hist = _slice(pack["history"], site) if not pack["history"].empty else pd.DataFrame()
            opens = _slice(pack["open"], site) if not pack["open"].empty else pd.DataFrame()
            if not opens.empty:
                st.markdown("**Open tickets**")
                st.dataframe(_hist_view(opens), use_container_width=True)
            if not hist.empty:
                st.markdown("**Down history**")
                st.dataframe(_hist_view(hist), use_container_width=True, height=240)
            if hist.empty and opens.empty:
                st.caption("Is site pe ticket history nahi mili.")
