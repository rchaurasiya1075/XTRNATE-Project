"""Incremental ticket sync: keep existing rows, append new Incident IDs, mark missing opens Resolved.

Daily open list: 1bkXg9iq… gid 407315218
History:
  Xtranet → 1ELusYn2el4… gid 1980854633
  Shell   → same workbook gid 1861519338
  Other   → same workbook gid 1643784953
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from utils.data_processing import process_closed_tickets, process_open_tickets
from utils.data_source import save_google
from utils.google_sheets import load_sheet_as_csv
from utils.sheets_config import xtranet_id, ops_id, gid as sheet_gid

IST = ZoneInfo("Asia/Kolkata")
HISTORY_SHEET_ID = xtranet_id()
DAILY_SHEET_ID = ops_id()
DAILY_GID = sheet_gid("daily_open")
XTRANET_GID = sheet_gid("tickets_xtranet")
SHELL_GID = sheet_gid("tickets_shell")
OTHER_GID = sheet_gid("tickets_other")

OPEN_HINTS = ("assign to fe", "call on hold", "on hold")


def history_gid(project: str | None = None) -> int:
    name = str(project or "").strip().lower()
    if name == "shell":
        return int(sheet_gid("tickets_shell") or 0)
    if name in ("", "xtranet"):
        return int(sheet_gid("tickets_xtranet") or 0)
    return int(sheet_gid("tickets_other") or 0)


def _norm_id(v) -> str:
    s = str(v or "").strip().upper()
    if s in ("", "--", "NAN", "NONE", "NAT", "NULL"):
        return ""
    return s


def _is_open_status(v) -> bool:
    t = str(v or "").strip().lower()
    if not t or t in ("--", "nan", "none"):
        return False
    if "resolved" in t or t == "closed" or "close" == t:
        return False
    return any(h in t for h in OPEN_HINTS)


def _col(df: pd.DataFrame, *names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


@st.cache_data(ttl=90, show_spinner=False)
def _fetch(sheet_id: str, gid: int) -> pd.DataFrame:
    try:
        df = load_sheet_as_csv(sheet_id, gid=gid)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _id_series(df: pd.DataFrame) -> pd.Series:
    col = _col(df, "Incident ID", "incident id", "ticket_id")
    if col is None:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].map(_norm_id)


def _align_new_rows(history: pd.DataFrame, daily: pd.DataFrame, new_ids: set) -> pd.DataFrame:
    if daily is None or daily.empty or not new_ids:
        return pd.DataFrame(columns=list(history.columns) if history is not None else [])
    dcol = _col(daily, "Incident ID", "incident id", "ticket_id")
    ids = daily[dcol].map(_norm_id) if dcol else _id_series(daily)
    chunk = daily.loc[ids.isin(new_ids)].copy()
    chunk = chunk.loc[~ids.loc[chunk.index].duplicated()].copy()
    if history is None or history.empty:
        return chunk
    out = pd.DataFrame(index=chunk.index)
    daily_map = {str(c).strip().lower(): c for c in chunk.columns}
    for h in history.columns:
        src = daily_map.get(str(h).strip().lower())
        if src is None:
            out[h] = ""
        else:
            out[h] = chunk[src]
    sno = _col(out, "S.no", "S.No", "S No", "Sr No", "Sno")
    if sno:
        start = 0
        hcol = _col(history, "S.no", "S.No", "S No", "Sr No", "Sno")
        if hcol is not None:
            nums = pd.to_numeric(history[hcol], errors="coerce")
            start = int(nums.max()) if nums.notna().any() else len(history)
        out[sno] = range(start + 1, start + 1 + len(out))
    return out.reset_index(drop=True)


def _mark_resolved(history: pd.DataFrame, still_open: set) -> tuple[pd.DataFrame, int]:
    if history is None or history.empty:
        return history, 0
    idc = _col(history, "Incident ID", "incident id", "ticket_id")
    stc = _col(history, "CurrentStatus", "Current Status", "status")
    if idc is None or stc is None:
        return history, 0
    ids = history[idc].map(_norm_id)
    open_mask = history[stc].map(_is_open_status)
    gone = open_mask & ids.ne("") & ~ids.isin(still_open)
    n = int(gone.sum())
    if n == 0:
        return history, 0
    out = history.copy()
    out.loc[gone, stc] = "Resolved"
    rtc = _col(out, "Resolved Time-Active", "Resolved Time")
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    if rtc:
        blank = out[rtc].isna() | out[rtc].astype(str).str.strip().isin(["", "--", "nan", "None", "NaT"])
        out.loc[gone & blank, rtc] = now
    return out, n


def _split_and_save(raw: pd.DataFrame, note: str):
    if raw is None or raw.empty:
        save_google(None, None, raw, note=note)
        return 0, 0
    processed = process_closed_tickets(raw)
    if processed is None or processed.empty:
        save_google(None, None, raw, note=note)
        return 0, 0
    if "ticket_id" in processed.columns:
        processed = processed.drop_duplicates(subset=["ticket_id"], keep="first")
    closed, opened = processed, None
    if "status" in processed.columns:
        status_str = processed["status"].astype(str).str.lower()
        open_mask = (
            status_str.str.contains("assign to fe", na=False)
            | status_str.str.contains("call on hold", na=False)
            | status_str.str.contains("on hold", na=False)
        )
        opened = processed[open_mask].copy()
        closed = processed[~open_mask].copy()
        if opened is not None and not opened.empty:
            opened = process_open_tickets(opened)
            if "ticket_id" in opened.columns:
                opened = opened.drop_duplicates(subset=["ticket_id"], keep="first")
        else:
            opened = None
        if closed is None or closed.empty:
            closed = None
    save_google(closed, opened, processed, note=note)
    return (0 if closed is None else len(closed)), (0 if opened is None else len(opened))


def sync_daily_tickets(project: str | None = None) -> dict:
    """Keep old history rows. Append new daily Incident IDs. Opens missing from daily → Resolved."""
    project = project or st.session_state.get("active_project") or "Xtranet"
    gid = sheet_gid("tickets_xtranet")
    daily = _fetch(ops_id(), sheet_gid("daily_open"))
    history = _fetch(xtranet_id(), gid)

    if history is None or history.empty:
        return {
            "project": "Xtranet",
            "gid": gid,
            "added": 0,
            "resolved": 0,
            "daily_open": 0,
            "history_rows": 0,
            "closed": 0,
            "open": 0,
            "written": False,
            "write_error": "Xtranet history tab did not load — existing data left as-is.",
            "note": "",
        }

    daily_ids = {i for i in _id_series(daily).tolist() if i} if daily is not None and not daily.empty else set()
    hist_ids = {i for i in _id_series(history).tolist() if i} if history is not None and not history.empty else set()
    new_ids = daily_ids - hist_ids
    new_rows = _align_new_rows(history if history is not None else pd.DataFrame(), daily, new_ids)

    if history is None or history.empty:
        merged = new_rows.copy()
    elif new_rows is None or new_rows.empty:
        merged = history.copy()
    else:
        merged = pd.concat([history, new_rows], ignore_index=True)

    merged, n_resolved = _mark_resolved(merged, daily_ids)

    write = {"ok": False, "error": "", "appended": 0, "resolved": 0}
    try:
        from utils.sheet_write import apply_ticket_sync
        write = apply_ticket_sync(gid, new_rows, daily_ids)
    except Exception as e:
        write["error"] = f"{type(e).__name__}: {e}"

    note = f"Xtranet history  •  +{len(new_rows)} new  •  {n_resolved} resolved"
    if write.get("ok"):
        note += "  •  sheet updated"
    elif write.get("error"):
        note += "  •  in-app merge (sheet write skipped)"
    n_c = n_o = 0
    if str(project).strip().lower() == "xtranet":
        n_c, n_o = _split_and_save(merged, note=note)
    return {
        "project": "Xtranet",
        "gid": gid,
        "added": int(len(new_rows)),
        "resolved": int(n_resolved),
        "daily_open": len(daily_ids),
        "history_rows": 0 if merged is None else len(merged),
        "closed": n_c,
        "open": n_o,
        "written": bool(write.get("ok")),
        "write_error": write.get("error") or "",
        "note": note,
    }
