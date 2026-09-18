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
USAGE_GID = "710549453"
MASTER_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
MASTER_GID = "1181450647"

HIST_COLS = [
    "ticket_id", "site_code", "submitted_time", "resolved_time", "resolution_days",
    "down_time_min", "status", "category", "reason_clean", "reason", "owner", "isp",
    "state", "city", "open_hours",
]

MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_ALIAS = {
    "jan": "January", "january": "January",
    "feb": "February", "february": "February",
    "mar": "March", "march": "March",
    "apr": "April", "april": "April",
    "may": "May",
    "jun": "June", "june": "June",
    "jul": "July", "july": "July",
    "aug": "August", "august": "August",
    "sep": "September", "sept": "September", "september": "September",
    "oct": "October", "october": "October",
    "nov": "November", "november": "November",
    "dec": "December", "december": "December",
}


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


def _parse_gb(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).lower().replace(",", " ").replace("gb", "").strip()
    try:
        return round(float(s), 2)
    except Exception:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
        return round(float(m.group(1)), 2) if m else None


def _month_from_col(col):
    tokens = re.findall(r"[a-z]+", str(col).lower())
    hit = None
    for tok in tokens:
        if tok in MONTH_ALIAS:
            name = MONTH_ALIAS[tok]
            if hit is None or len(tok) > 3:
                hit = name
    return hit


def _gb_month_cols(columns):
    best = {}
    for c in columns:
        mon = _month_from_col(c)
        if not mon:
            continue
        cl = str(c).lower()
        score = 0
        if "gb" in cl:
            score += 5
        if "usage" in cl or "uses" in cl:
            score += 2
        if "in gb" in cl:
            score += 3
        prev = best.get(mon)
        if prev is None or score > prev[1]:
            best[mon] = (c, score)
    return [(m, best[m][0]) for m in MONTH_ORDER if m in best]


def _dt_hours(hist, months=None):
    if hist is None or getattr(hist, "empty", True) or "down_time_min" not in hist.columns:
        return 0.0
    work = hist
    if months:
        tcol = "submitted_time" if "submitted_time" in hist.columns else (
            "Submitted Time" if "Submitted Time" in hist.columns else None
        )
        if tcol is None:
            return 0.0
        ts = pd.to_datetime(hist[tcol], errors="coerce")
        cutoff = pd.Timestamp.now() - pd.DateOffset(months=int(months))
        work = hist.loc[ts.notna() & (ts >= cutoff)]
    mins = pd.to_numeric(work["down_time_min"], errors="coerce").fillna(0).sum()
    return round(float(mins) / 60.0, 1)


def _ticket_ts(hist):
    if hist is None or getattr(hist, "empty", True):
        return None
    for c in ("submitted_time", "Submitted Time"):
        if c in hist.columns:
            return pd.to_datetime(hist[c], errors="coerce")
    return None


def _down_count(hist, months=None):
    if hist is None or getattr(hist, "empty", True):
        return 0
    ts = _ticket_ts(hist)
    if ts is None:
        return 0 if months else int(len(hist))
    if not months:
        return int(ts.notna().sum())
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=int(months))
    return int((ts.notna() & (ts >= cutoff)).sum())


def _month_down_map(hist):
    ts = _ticket_ts(hist)
    if ts is None:
        return {}
    s = ts.dropna()
    if s.empty:
        return {}
    vc = s.dt.to_period("M").value_counts()
    return {str(p): int(n) for p, n in vc.items()}


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


@st.cache_data(ttl=180, show_spinner=False)
def _load_usage():
    df = load_sheet_as_csv(XTRANET, gid=USAGE_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "site code", "sitecode", "hughessitecode") or df.columns[0]
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
    usage = _safe_load(_load_usage)
    gb_cols = _gb_month_cols(usage.columns) if usage is not None and not usage.empty else []

    summary_rows = []
    hist_all, open_all, sim_all, ckt_all, lc_all, lm_all, usage_all = [], [], [], [], [], [], []

    for site in codes:
        hist = _slice(closed, site)
        if hist.empty:
            hist = _slice(raw, site)
        opens = _slice(open_df, site)
        srow = _slice(sim, site)
        crow = _slice(ckt, site)
        lrow = _slice(lc, site)
        mrow = _slice(master, site)
        urow = _slice(usage, site)

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
        if not urow.empty:
            usage_all.append(urow)

        downs = len(hist)
        rec = {
            "site_code": site,
            "found": "Yes" if any(len(x) for x in (hist, opens, srow, crow, lrow, mrow, urow)) else "No",
            "past_downs": downs,
            "open_now": len(opens),
            "downs_1m": _down_count(hist, 1),
            "downs_2m": _down_count(hist, 2),
            "downs_3m": _down_count(hist, 3),
            "downs_6m": _down_count(hist, 6),
            "downtime_hrs": _dt_hours(hist),
            "dt_1m_hrs": _dt_hours(hist, 1),
            "dt_2m_hrs": _dt_hours(hist, 2),
            "dt_3m_hrs": _dt_hours(hist, 3),
            "dt_6m_hrs": _dt_hours(hist, 6),
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
        }
        for mon, col in gb_cols:
            key = f"usage_{mon[:3]}_GB"
            val = None
            if not urow.empty and col in urow.columns:
                val = _parse_gb(urow.iloc[0].get(col))
            rec[key] = val if val is not None else ""
        rec["_month_downs"] = _month_down_map(hist)
        summary_rows.append(rec)

    periods = sorted({p for rec in summary_rows for p in rec.get("_month_downs", {})})
    for rec in summary_rows:
        mmap = rec.pop("_month_downs", {})
        for p in periods:
            try:
                label = pd.Period(p, freq="M").strftime("%b-%y")
            except Exception:
                label = str(p)
            rec[f"downs_{label}"] = int(mmap.get(p, 0))

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
        "usage": cat(usage_all),
        "usage_months": [m for m, _ in gb_cols],
    }


def _hist_view(df):
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [c for c in HIST_COLS if c in df.columns]
    return df[cols] if cols else df


def render_multi_site_pack():
    st.markdown("**Paste site codes** — comma / space / new line. History + SIM + last mile + LC + circuit together.")
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
            st.caption(f"{n} site code(s) ready — click **Load all sites**.")
        return

    codes = parse_site_codes(blob or "")
    if not codes:
        st.warning("No site code found. Paste codes and click Load.")
        return
    if len(codes) > 80:
        st.warning(f"{len(codes)} codes — showing the first 80.")
        codes = codes[:80]

    with st.spinner(f"{len(codes)} sites — building pack..."):
        pack = build_pack(codes)

    summary = pack["summary"]
    found_n = int((summary["found"] == "Yes").sum()) if not summary.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Codes", len(codes))
    k2.metric("Found", found_n)
    k3.metric("Not found", len(codes) - found_n)
    k4.metric("Past downs", int(summary["past_downs"].sum()) if not summary.empty else 0)

    st.markdown("#### Overall — one row per site")
    show = summary.copy()
    rename = {
        "downtime_hrs": "DT overall hrs",
        "dt_1m_hrs": "DT 1M hrs",
        "dt_2m_hrs": "DT 2M hrs",
        "dt_3m_hrs": "DT 3M hrs",
        "dt_6m_hrs": "DT 6M hrs",
        "downs_1m": "Downs 1M",
        "downs_2m": "Downs 2M",
        "downs_3m": "Downs 3M",
        "downs_6m": "Downs 6M",
        "past_downs": "Downs overall",
    }
    for c in list(show.columns):
        if c.startswith("usage_") and c.endswith("_GB"):
            mon = c.replace("usage_", "").replace("_GB", "")
            rename[c] = f"Usage {mon} GB"
        elif c.startswith("downs_") and c not in rename:
            rename[c] = "Downs " + c.replace("downs_", "")
    st.dataframe(show.rename(columns=rename), use_container_width=True, height=min(420, 48 + 32 * min(len(summary), 12)))

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
    if not pack.get("usage", pd.DataFrame()).empty:
        sheets["SIM_Usage"] = pack["usage"]

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
            st.caption(
                f"Down count — overall {int(row.get('past_downs', 0))}  ·  "
                f"1M {int(row.get('downs_1m', 0))}  ·  2M {int(row.get('downs_2m', 0))}  ·  "
                f"3M {int(row.get('downs_3m', 0))}  ·  6M {int(row.get('downs_6m', 0))}"
            )
            cal = [
                f"{c.replace('downs_', '')} {int(row.get(c, 0))}"
                for c in summary.columns
                if str(c).startswith("downs_") and c not in ("downs_1m", "downs_2m", "downs_3m", "downs_6m")
                and int(row.get(c, 0) or 0) > 0
            ]
            if cal:
                st.caption("Downs by month: " + "  ·  ".join(cal))
            st.caption(
                f"Downtime hrs — overall {row.get('downtime_hrs', 0)}  ·  "
                f"1M {row.get('dt_1m_hrs', 0)}  ·  2M {row.get('dt_2m_hrs', 0)}  ·  "
                f"3M {row.get('dt_3m_hrs', 0)}  ·  6M {row.get('dt_6m_hrs', 0)}"
            )
            months = pack.get("usage_months") or []
            bits = []
            for mon in months:
                key = f"usage_{mon[:3]}_GB"
                val = row.get(key, "")
                if val not in ("", None):
                    bits.append(f"{mon[:3]} {val} GB")
            st.caption("SIM usage: " + ("  ·  ".join(bits) if bits else "not on usage sheet"))
            hist = _slice(pack["history"], site) if not pack["history"].empty else pd.DataFrame()
            opens = _slice(pack["open"], site) if not pack["open"].empty else pd.DataFrame()
            if not opens.empty:
                st.markdown("**Open tickets**")
                st.dataframe(_hist_view(opens), use_container_width=True)
            if not hist.empty:
                st.markdown("**Down history**")
                st.dataframe(_hist_view(hist), use_container_width=True, height=240)
            if hist.empty and opens.empty:
                st.caption("No ticket history for this site.")
