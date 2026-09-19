"""Bulk site master: one-row-per-site dump + template + Google Updated_Master tab."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from utils.excel_export import excel_bytes
from utils.sheets_config import all_config, save_config, xtranet_id, tab_url
from utils.site_pack import (
    _fill,
    _fill_mdn,
    _gb_month_cols,
    _load_ckt,
    _load_fallback,
    _load_lc,
    _load_master,
    _load_primary,
    _load_sim,
    _load_usage,
    _parse_gb,
    _safe_load,
    parse_site_codes,
)

IST = ZoneInfo("Asia/Kolkata")
WS_TITLE = "Updated_Master"

UPDATE_COLS = [
    "Site Code",
    "Bank Name",
    "Branch Name",
    "State",
    "Branch Address",
    "Last Mile",
    "ISP",
    "Partner",
    "CKT ID",
    "Telco",
    "SIM Number",
    "Status",
    "MDN Number",
    "IP Address",
    "LC Name",
    "LC Phone",
    "Remarks",
]


def _as_text(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def _blank(v) -> bool:
    s = _as_text(v)
    return s == "" or s.lower() in ("nan", "none", "nat", "--", "<na>")


def _site_key(v) -> str:
    return _as_text(v).upper()


def _load_frames():
    return {
        "primary": _safe_load(_load_primary),
        "usage": _safe_load(_load_usage),
        "fallback": _safe_load(_load_fallback),
        "sim": _safe_load(_load_sim),
        "ckt": _safe_load(_load_ckt),
        "lc": _safe_load(_load_lc),
        "master": _safe_load(_load_master),
    }


def _all_codes(frames: dict) -> list[str]:
    seen, out = set(), []
    skip = {"", "NAN", "NONE", "NAT", "<NA>", "SITE_CODE", "HUGHESSITECODE"}
    for df in frames.values():
        if df is None or getattr(df, "empty", True) or "site_code" not in df.columns:
            continue
        for raw in df["site_code"].tolist():
            s = _site_key(raw)
            if not s or s in skip or s in seen:
                continue
            if len(s) < 4:
                continue
            seen.add(s)
            out.append(s)
    return out


def _row_frame(maps: dict, site: str) -> pd.DataFrame:
    r = maps.get(site)
    if r is None:
        return pd.DataFrame()
    return pd.DataFrame([r])


def _index_sites(df) -> dict:
    if df is None or getattr(df, "empty", True) or "site_code" not in df.columns:
        return {}
    out = {}
    for rec in df.to_dict("records"):
        k = _site_key(rec.get("site_code"))
        if k and k not in out:
            out[k] = rec
    return out


def build_live_master(codes: list[str] | None = None) -> pd.DataFrame:
    frames = _load_frames()
    if not codes:
        codes = _all_codes(frames)
    usage = frames["usage"]
    gb_cols = _gb_month_cols(usage.columns) if usage is not None and not usage.empty else []
    maps = {k: _index_sites(v) for k, v in frames.items()}
    rows = []
    for site in codes:
        prow = _row_frame(maps["primary"], site)
        urow = _row_frame(maps["usage"], site)
        frow = _row_frame(maps["fallback"], site)
        srow = _row_frame(maps["sim"], site)
        crow = _row_frame(maps["ckt"], site)
        lrow = _row_frame(maps["lc"], site)
        mrow = _row_frame(maps["master"], site)
        rec = {
            "Site Code": site,
            "Bank Name": _fill(("Bank Name", "bank_name"), prow, urow, frow, mrow, crow),
            "Branch Name": _fill(("Branch Name", "Branch", "branch_name"), prow, urow, frow, mrow, crow),
            "State": _fill(("State", "state"), prow, urow, frow, mrow, crow),
            "Branch Address": _fill(("Branch Address", "address"), prow, urow, frow, mrow, crow),
            "Last Mile": _fill(("Last Mile", "Media", "New Last Mile Media"), prow, urow, frow, mrow),
            "ISP": _fill(("ISP Name", "ISP", "isp", "Partner", "Last Mile"), urow, frow, mrow, crow, prow),
            "Partner": _fill(("Partner",), frow, mrow, prow),
            "CKT ID": _fill(("CKT ID", "Ckt ID", "ckt_id"), prow, urow, frow, mrow, crow),
            "Telco": _fill(("Telco", "telco"), prow, urow, srow),
            "SIM Number": _fill(("SIMNumber", "SIM Number", "SIMS", "Asset Number"), prow, urow, srow),
            "Status": _fill(("Status", "CMDB Status", "status"), prow, srow, urow),
            "MDN Number": _fill_mdn(prow, urow, srow),
            "IP Address": _fill(("IP Address", "IP", "ip"), prow, urow, srow),
            "LC Name": _fill(("Branch Person Name", "New LC Name", "lc_name"), lrow, mrow, frow),
            "LC Phone": _fill(
                ("Contact Number", "Branch Person Contact Number", "New LC Contact", "lc_phone"),
                lrow, mrow, frow,
            ),
            "Remarks": "",
        }
        for mon, col in gb_cols:
            val = None
            if not urow.empty and col in urow.columns:
                val = _parse_gb(urow.iloc[0].get(col))
            rec[f"Usage {mon[:3]} GB"] = val if val is not None else ""
        rows.append(rec)
    return pd.DataFrame(rows)



def overlay_updates(live: pd.DataFrame, updates: pd.DataFrame) -> pd.DataFrame:
    if live is None or live.empty:
        live = pd.DataFrame(columns=UPDATE_COLS)
    if updates is None or updates.empty:
        return live.copy()
    work = live.copy()
    work["Site Code"] = work["Site Code"].map(_site_key)
    upd = _normalize_update_df(updates)
    if upd.empty:
        return work
    by_site = {r["Site Code"]: r for _, r in work.iterrows()}
    extra = []
    for _, row in upd.iterrows():
        site = row["Site Code"]
        if not site:
            continue
        if site in by_site:
            cur = by_site[site]
            for c in upd.columns:
                if c == "Site Code":
                    continue
                val = row.get(c, "")
                if not _blank(val):
                    cur[c] = val
            by_site[site] = cur
        else:
            extra.append(row)
    out = pd.DataFrame(list(by_site.values()))
    if extra:
        out = pd.concat([out, pd.DataFrame(extra)], ignore_index=True)
    return out


def _normalize_update_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=UPDATE_COLS)
    raw = df.copy()
    raw.columns = [str(c).strip() for c in raw.columns]
    lower = {str(c).strip().lower(): c for c in raw.columns}
    alias = {
        "site code": "Site Code",
        "sitecode": "Site Code",
        "hughessitecode": "Site Code",
        "bank name": "Bank Name",
        "branch name": "Branch Name",
        "branch": "Branch Name",
        "state": "State",
        "branch address": "Branch Address",
        "last mile": "Last Mile",
        "media": "Last Mile",
        "isp": "ISP",
        "isp name": "ISP",
        "partner": "Partner",
        "ckt id": "CKT ID",
        "ckt_id": "CKT ID",
        "telco": "Telco",
        "sim number": "SIM Number",
        "simnumber": "SIM Number",
        "asset number": "SIM Number",
        "status": "Status",
        "mdn number": "MDN Number",
        "mdn": "MDN Number",
        "ip address": "IP Address",
        "ip": "IP Address",
        "lc name": "LC Name",
        "branch person name": "LC Name",
        "lc phone": "LC Phone",
        "branch person contact number": "LC Phone",
        "remarks": "Remarks",
        "remark": "Remarks",
    }
    out = pd.DataFrame()
    for dest in UPDATE_COLS:
        src = None
        if dest in raw.columns:
            src = dest
        else:
            key = dest.lower()
            if key in lower:
                src = lower[key]
            elif key in alias and alias[key]:
                pass
            for a, d in alias.items():
                if d == dest and a in lower:
                    src = lower[a]
                    break
        if src is None:
            out[dest] = ""
        else:
            out[dest] = raw[src]
    out["Site Code"] = out["Site Code"].map(_site_key)
    out = out[out["Site Code"].str.len() >= 4]
    return out.reset_index(drop=True)


def template_excel() -> bytes:
    blank = pd.DataFrame([{c: "" for c in UPDATE_COLS}])
    how = pd.DataFrame([
        {"Step": "1", "What to do": "Fill Site Code (required)."},
        {"Step": "2", "What to do": "Fill ONLY columns you want to change (ISP, CKT ID, Last Mile, SIM, MDN, IP, LC…)."},
        {"Step": "3", "What to do": "Leave a cell blank = do not change that field."},
        {"Step": "4", "What to do": "Upload this file on Site Updates → Apply bulk update."},
        {"Step": "5", "What to do": "App writes those rows into Google tab Updated_Master in the Xtranet workbook."},
        {"Step": "6", "What to do": "Download all sites anytime — live sheets + your updates, one Excel."},
    ])
    return excel_bytes(
        {"Update_Format": blank, "How_to_fill": how},
        title="Site bulk update format",
        subtitle="Fill Site Code + changed fields only",
    )


def full_excel(df: pd.DataFrame) -> bytes:
    return excel_bytes(
        {"All_Sites": df},
        title="All sites — updated master",
        subtitle=datetime.now(IST).strftime("%d-%b-%Y %H:%M IST"),
    )


def _write_client():
    import gspread
    from google.oauth2.service_account import Credentials

    if "google_service_account" not in st.secrets:
        raise RuntimeError("google_service_account not in secrets — cannot write the Google tab.")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(dict(st.secrets["google_service_account"]), scopes=scopes)
    return gspread.authorize(creds)


def _save_gid(gid: int):
    cfg = all_config()
    tabs = cfg.setdefault("tabs", {})
    tabs["site_updated"] = {
        "book": "xtranet",
        "gid": int(gid),
        "label": "Updated_Master (bulk site updates)",
    }
    save_config(cfg)


def ensure_updated_worksheet():
    gc = _write_client()
    ss = gc.open_by_key(xtranet_id())
    try:
        ws = ss.worksheet(WS_TITLE)
    except Exception:
        ws = ss.add_worksheet(title=WS_TITLE, rows=3000, cols=len(UPDATE_COLS) + 8)
        ws.update("A1", [UPDATE_COLS], value_input_option="USER_ENTERED")
    try:
        _save_gid(int(ws.id))
    except Exception:
        pass
    return ws


def load_updated_tab() -> pd.DataFrame:
    from utils.google_sheets import load_sheet_as_csv
    from utils.sheets_config import gid as sheet_gid

    g = sheet_gid("site_updated")
    if not g:
        return pd.DataFrame(columns=UPDATE_COLS)
    try:
        df = load_sheet_as_csv(xtranet_id(), gid=g)
        return _normalize_update_df(df)
    except Exception:
        return pd.DataFrame(columns=UPDATE_COLS)


def apply_updates_to_google(upload_df: pd.DataFrame) -> dict:
    upd = _normalize_update_df(upload_df)
    if upd.empty:
        raise RuntimeError("No site codes found in the uploaded file.")
    ws = ensure_updated_worksheet()
    existing = ws.get_all_values() or []
    header = [str(h).strip() for h in (existing[0] if existing else UPDATE_COLS)]
    if not header or header[0] == "":
        header = list(UPDATE_COLS)
    cols = [c for c in UPDATE_COLS if c in header] or list(header)
    # Keep extra columns from existing sheet
    extra = [h for h in header if h not in cols]
    header_out = cols + extra

    def row_to_dict(line):
        d = {}
        for i, h in enumerate(header_out):
            d[h] = line[i] if i < len(line) else ""
        return d

    by_site = {}
    for line in existing[1:]:
        d = row_to_dict(line)
        site = _site_key(d.get("Site Code"))
        if site:
            by_site[site] = d

    n_new = n_upd = 0
    now = datetime.now(IST).strftime("%d-%b-%Y %H:%M")
    for _, rec in upd.iterrows():
        site = rec["Site Code"]
        cur = by_site.get(site) or {h: "" for h in header_out}
        cur["Site Code"] = site
        changed = False
        for c in UPDATE_COLS:
            if c == "Site Code":
                continue
            val = rec.get(c, "")
            if _blank(val):
                continue
            cur[c] = "" if val is None else str(val).strip()
            changed = True
        if "Updated At" in header_out:
            cur["Updated At"] = now
        elif changed:
            cur["Remarks"] = (str(cur.get("Remarks") or "") + (" | " if cur.get("Remarks") else "") + f"updated {now}").strip(" |")
        if site not in by_site:
            n_new += 1
        elif changed:
            n_upd += 1
        by_site[site] = cur

    body = [header_out]
    for site in sorted(by_site):
        d = by_site[site]
        body.append(["" if _blank(d.get(h, "")) else str(d.get(h, "")) for h in header_out])
    ws.clear()
    ws.update("A1", body, value_input_option="USER_ENTERED")
    return {"updated": n_upd, "added": n_new, "total": len(by_site), "gid": int(ws.id), "title": WS_TITLE}


def combined_master(codes: list[str] | None = None) -> pd.DataFrame:
    live = build_live_master(codes)
    upd = load_updated_tab()
    return overlay_updates(live, upd)
