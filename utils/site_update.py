"""Bulk site master: one-row-per-site dump + template + Google Updated_Master tab."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from utils.excel_export import excel_bytes
from utils.sheets_config import all_config, save_config, xtranet_id, tab_url, gid as sheet_gid
from utils.google_sheets import load_sheet_as_csv
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
FORMAT_TITLE = "Update_Format"

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


def _norm_remark(v) -> str:
    return _as_text(v).lower().replace("_", " ")


def _is_vendor(t: str) -> bool:
    if "alternate service provider" in t or "provisioned on alternate" in t:
        return True
    if "existing operator" in t and "not stable" in t:
        return True
    keys = (
        "vendor change",
        "change of vendor",
        "vendor changed",
        "change service provider",
        "changed service provider",
        "link delivered",
        "link deliver",
    )
    return any(k in t for k in keys)


def _is_not_feasible(t: str) -> bool:
    keys = (
        "technically not feasible",
        "technical not feasible",
        "not feasible",
        "rolled back by isp",
    )
    return any(k in t for k in keys)


def _new_mile_from_remark(t: str) -> str:
    if "alternate service provider" in t or "provisioned on alternate" in t:
        return "Alternate service provider"
    if "link delivered" in t or "link deliver" in t:
        return "Link delivered"
    if _is_vendor(t):
        return "Vendor changed"
    return ""


@st.cache_data(ttl=180, show_spinner=False)
def _ticket_updates() -> dict:
    """Latest remark per site from the Xtranet ticket tab. Not the filtered report view."""
    try:
        df = load_sheet_as_csv(xtranet_id(), gid=sheet_gid("tickets_xtranet"))
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    df.columns = [str(c).strip() for c in df.columns]
    site_col = next((c for c in df.columns if c.lower() in ("request title", "site code", "sitecode")), None)
    remark_col = next((c for c in df.columns if "last enclosure" in c.lower()), None)
    time_col = next((c for c in df.columns if c.lower() == "submitted time"), None)
    id_col = next((c for c in df.columns if c.lower() == "incident id"), None)
    if site_col is None:
        return {}
    work = df.copy()
    work["_site"] = work[site_col].map(_site_key)
    work = work[work["_site"].str.len() >= 4]
    if time_col:
        work["_ts"] = pd.to_datetime(work[time_col], errors="coerce")
    else:
        work["_ts"] = pd.NaT
    work = work.sort_values("_ts")
    out = {}
    for site, grp in work.groupby("_site", sort=False):
        remarks = []
        for _, row in grp.iterrows():
            text = _norm_remark(row.get(remark_col)) if remark_col else ""
            remarks.append(text)
        last = remarks[-1] if remarks else ""
        vendor = next((r for r in reversed(remarks) if _is_vendor(r)), "")
        update = ""
        new_mile = ""
        if last and _is_not_feasible(last):
            update = "Non Feasible"
        elif vendor:
            update = "Vendor Change"
            new_mile = _new_mile_from_remark(vendor)
        last_row = grp.iloc[-1]
        out[site] = {
            "update": update,
            "new_last_mile": new_mile,
            "last_remark": _as_text(last_row.get(remark_col)) if remark_col else "",
            "last_ticket": _as_text(last_row.get(id_col)) if id_col else "",
            "last_time": _as_text(last_row.get(time_col)) if time_col else "",
        }
    return out


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
    flags = _ticket_updates()
    if not codes:
        codes = _all_codes(frames)
        have = set(codes)
        for s in flags:
            if s not in have:
                codes.append(s)
                have.add(s)
    usage = frames["usage"]
    gb_cols = _gb_month_cols(usage.columns) if usage is not None and not usage.empty else []
    maps = {k: _index_sites(v) for k, v in frames.items()}
    flags = _ticket_updates()
    rows = []
    for site in codes:
        prow = _row_frame(maps["primary"], site)
        urow = _row_frame(maps["usage"], site)
        frow = _row_frame(maps["fallback"], site)
        srow = _row_frame(maps["sim"], site)
        crow = _row_frame(maps["ckt"], site)
        mrow = _row_frame(maps["master"], site)
        flag = flags.get(site) or {}
        new_mile = _fill(("New Last Mile", "New Last Mile Media", "New Last Mile ISP"), prow, frow, mrow)
        if not new_mile:
            new_mile = flag.get("new_last_mile") or ""
        rec = {
            "Site Code": site,
            "Bank Name": _fill(("Bank Name", "bank_name"), prow, urow, frow, mrow, crow),
            "Branch Name": _fill(("Branch Name", "Branch", "branch_name"), prow, urow, frow, mrow, crow),
            "State": _fill(("State", "state"), prow, urow, frow, mrow, crow),
            "Branch Address": _fill(("Branch Address", "address"), prow, urow, frow, mrow, crow),
            "Last Mile": _fill(("Last Mile", "Media"), prow, urow, frow, mrow),
            "New Last mile": new_mile,
            "CKT ID": _fill(("CKT ID", "Ckt ID", "ckt_id"), prow, urow, frow, mrow, crow),
            "Telco": _fill(("Telco", "telco"), prow, urow, srow),
            "SIM Number": _fill(("SIMNumber", "SIM Number", "SIMS", "Asset Number"), prow, urow, srow),
            "Status": _fill(("Status", "CMDB Status", "status"), prow, srow, urow),
            "MDN Number": _fill_mdn(prow, urow, srow),
            "IP Address": _fill(("IP Address", "IP", "ip"), prow, urow, srow),
            "Site Update": flag.get("update") or "",
            "Last Remark": flag.get("last_remark") or "",
            "Last Ticket": flag.get("last_ticket") or "",
            "Last Ticket Time": flag.get("last_time") or "",
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


def master_export(df: pd.DataFrame) -> pd.DataFrame:
    """Column order the master sheet uses."""
    if df is None or getattr(df, "empty", True):
        return df
    head = [
        "Site Code", "Bank Name", "Branch Name", "State", "Branch Address",
        "Last Mile", "New Last mile", "CKT ID", "Telco", "SIM Number", "Status",
        "MDN Number", "IP Address", "Site Update", "Last Remark", "Last Ticket", "Last Ticket Time",
    ]
    cols = [c for c in head if c in df.columns] + [c for c in df.columns if c not in head]
    return df[cols].rename(columns={
        "Site Code": "Sitecode",
        "Telco": "Sim Telco",
        "SIM Number": "SIMNumber",
        "IP Address": "Sim IP Address",
    })


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


def _save_tab(key: str, gid: int, label: str):
    cfg = all_config()
    tabs = cfg.setdefault("tabs", {})
    tabs[key] = {"book": "xtranet", "gid": int(gid), "label": label}
    save_config(cfg)


def _save_gid(gid: int):
    _save_tab("site_updated", gid, "Updated_Master (bulk site updates)")


def _open_book():
    return _write_client().open_by_key(xtranet_id())


def _ensure_ws(ss, title: str, rows: int, header: list[str]):
    try:
        ws = ss.worksheet(title)
    except Exception:
        ws = ss.add_worksheet(title=title, rows=rows, cols=max(len(header) + 4, 20))
        ws.update("A1", [header], value_input_option="USER_ENTERED")
        try:
            ws.freeze(rows=1)
        except Exception:
            pass
    return ws


def ensure_format_and_master():
    """Create Update_Format + Updated_Master tabs in the Xtranet workbook if missing."""
    ss = _open_book()
    fmt = _ensure_ws(ss, FORMAT_TITLE, 2000, UPDATE_COLS)
    master = _ensure_ws(ss, WS_TITLE, 3000, UPDATE_COLS + ["Updated At"])
    try:
        _save_tab("site_update_format", int(fmt.id), "Update_Format (paste bulk changes here)")
        _save_tab("site_updated", int(master.id), "Updated_Master (bulk site updates)")
    except Exception:
        pass
    return fmt, master


def ensure_updated_worksheet():
    _, master = ensure_format_and_master()
    return master


def _ws_to_df(ws) -> pd.DataFrame:
    values = ws.get_all_values() or []
    if not values:
        return pd.DataFrame(columns=UPDATE_COLS)
    header = [str(h).strip() for h in values[0]]
    body = values[1:]
    if not header or not any(header):
        return pd.DataFrame(columns=UPDATE_COLS)
    df = pd.DataFrame(body, columns=header)
    return df


def load_format_tab() -> pd.DataFrame:
    fmt, _ = ensure_format_and_master()
    return _normalize_update_df(_ws_to_df(fmt))


def apply_format_sheet_to_master() -> dict:
    """Read Update_Format tab and merge filled site rows into Updated_Master."""
    incoming = load_format_tab()
    if incoming.empty:
        raise RuntimeError(
            f"No site codes on the {FORMAT_TITLE} tab. "
            "Paste Site Code and only the columns you want to change, then apply again."
        )
    result = apply_updates_to_google(incoming)
    result["format_rows"] = int(len(incoming))
    result["format_title"] = FORMAT_TITLE
    return result


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
    if "Updated At" not in header_out:
        header_out.append("Updated At")

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
