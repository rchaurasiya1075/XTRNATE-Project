"""Append / update Google Sheet rows using Firebase service account."""
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.sheets_config import xtranet_id, ops_id, gid as sheet_gid

IST = ZoneInfo("Asia/Kolkata")
LOG_TAB = "LastMile_Updates"
LC_LOG_TAB = "LC_Updates"
HEADERS = [
    "Updated At", "Site Code", "Bank", "Branch", "State",
    "Old Media", "Old ISP / Last Mile", "Old Partner", "Old Ckt ID",
    "Old LC Name", "Old LC Contact", "New Media", "New ISP / Last Mile",
    "New LC Name", "New LC Contact", "Note",
]
LC_LOG_HEADERS = [
    "Updated At", "Site Code", "Old LC Name", "Old LC Contact",
    "New LC Name", "New LC Contact", "Source",
]
TARGET_EXTRA = {
    14: "New LC Name", 15: "New LC Contact", 16: "Prev LC Name",
    17: "Prev LC Contact", 18: "LC Updated At", 19: "LC Update Source",
    20: "New Last Mile Media", 21: "New Last Mile ISP", 22: "Prev Media",
    23: "Prev ISP", 24: "Last Mile Updated At",
}
SOURCE_EXTRA = {
    6: "New LC Name", 7: "New LC Contact", 8: "Prev LC Name",
    9: "Prev LC Contact", 10: "LC Updated At", 11: "LC Update Source",
}


def _now():
    return datetime.now(IST).strftime("%d-%b-%Y %I:%M %p")


def sa_email():
    from utils.firebase_store import _load_sa_info
    return _load_sa_info().get("client_email", "")


def _retry(fn, tries=6):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = str(e)
            if "429" in msg or "Quota" in msg:
                time.sleep(20 + i * 15)
                continue
            raise
    raise last


def _client():
    import gspread
    from google.oauth2.service_account import Credentials
    from utils.firebase_store import _load_sa_info

    info = _load_sa_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds), info.get("client_email", "")


def _ws_by_gid(ss, gid):
    gid = int(gid)
    try:
        return ss.get_worksheet_by_id(gid)
    except Exception:
        for w in ss.worksheets():
            if int(getattr(w, "id", -1)) == gid:
                return w
        raise RuntimeError(f"Worksheet gid={gid} not found")


def _pad(row, n):
    r = list(row) + [""] * n
    return r[:n]


def _site_index(values, col=1):
    idx = {}
    for i, row in enumerate(values):
        if i == 0:
            continue
        if col < len(row):
            key = str(row[col]).strip().upper()
            if key:
                idx[key] = i
    return idx


def phone_keys(text):
    """Unique 10-digit keys from a contact cell. No duplicates."""
    keys = []
    raw = str(text or "")
    for part in re.split(r"[,/;|\n]+", raw):
        d = "".join(ch for ch in part if ch.isdigit())
        if not d:
            continue
        if d.startswith("91") and len(d) >= 12:
            d = d[-10:]
        elif d.startswith("0") and len(d) >= 11:
            d = d[-10:]
        elif len(d) >= 10:
            d = d[-10:]
        elif len(d) < 8:
            continue
        if d not in keys:
            keys.append(d)
    return keys


def unique_contact(text):
    return ", ".join(phone_keys(text))


def merge_contact(old, new):
    """Live = unique old+new. added = only numbers not already in old.
    First fill (no old) does NOT copy into New LC column."""
    old_keys = phone_keys(old)
    new_keys = phone_keys(new)
    have = set(old_keys)
    extra = [k for k in new_keys if k not in have]
    live = ", ".join(old_keys + extra)
    if not old_keys:
        return live, ""
    return live, ", ".join(extra)


def _ensure_cols_batch(ws, values, extra, min_cols):
    if ws.col_count < min_cols:
        _retry(lambda: ws.resize(rows=max(ws.row_count, 2), cols=min_cols))
    hdr = _pad(values[0] if values else [], min_cols)
    changed = False
    for idx, name in extra.items():
        if hdr[idx - 1] != name:
            hdr[idx - 1] = name
            changed = True
    if changed:
        _retry(lambda: ws.update("A1", [hdr], value_input_option="USER_ENTERED"))
        if values:
            values[0] = hdr
        else:
            values.append(hdr)
    return values


def _ensure_log_tab(ss):
    try:
        ws = ss.worksheet(LC_LOG_TAB)
    except Exception:
        ws = _retry(lambda: ss.add_worksheet(title=LC_LOG_TAB, rows=4000, cols=len(LC_LOG_HEADERS) + 2))
        _retry(lambda: ws.append_row(LC_LOG_HEADERS))
    hdr = _retry(lambda: ws.row_values(1))
    if not hdr:
        _retry(lambda: ws.append_row(LC_LOG_HEADERS))
    return ws


def test_sheet_write():
    out = {"ok": False, "email": "", "tabs": [], "error": ""}
    try:
        out["email"] = sa_email()
        gc, email = _client()
        out["email"] = email
        ss = _retry(lambda: gc.open_by_key(xtranet_id()))
        out["title"] = ss.title
        out["tabs"] = [f"{w.title} (gid={w.id})" for w in ss.worksheets()]
        log = _ensure_log_tab(ss)
        _retry(lambda: log.append_row(
            [_now(), "TEST", "", "", "connection-ok", "", "test"],
            value_input_option="USER_ENTERED",
        ))
        out["ok"] = True
        out["log_tab"] = log.title
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def append_last_mile_log(row):
    gc, email = _client()
    ss = _retry(lambda: gc.open_by_key(ops_id()))
    try:
        ws = ss.worksheet(LOG_TAB)
    except Exception:
        ws = ss.add_worksheet(title=LOG_TAB, rows=3000, cols=len(HEADERS) + 2)
        ws.append_row(HEADERS)
    if not ws.row_values(1):
        ws.append_row(HEADERS)
    _retry(lambda: ws.append_row(row, value_input_option="USER_ENTERED"))
    return email


def update_lc_excel_batch(items, source="auto"):
    if not items:
        return {"ok": 0}
    gc, email = _client()
    ss = _retry(lambda: gc.open_by_key(xtranet_id()))
    ts = _now()
    target = _ws_by_gid(ss, int(sheet_gid("site_fallback") or 658119379))
    src = _ws_by_gid(ss, int(sheet_gid("lc_master") or 401145054))
    tvals = _retry(lambda: target.get_all_values())
    svals = _retry(lambda: src.get_all_values())
    tvals = _ensure_cols_batch(target, tvals, TARGET_EXTRA, 24)
    svals = _ensure_cols_batch(src, svals, SOURCE_EXTRA, 11)
    tmap = _site_index(tvals, 1)
    smap = _site_index(svals, 1)

    t_updates, s_updates = [], []
    t_appends, s_appends, logs = [], [], []

    for it in items:
        site = str(it.get("site") or "").strip().upper()
        name = str(it.get("name") or "").strip()
        phone = str(it.get("phone") or "").strip()
        handled = str(it.get("handled_by") or "").strip()
        src_label = str(it.get("source") or source)
        if not site or not phone_keys(phone):
            continue
        prev_name = prev_phone = ""
        prev_new_phone = ""
        if site in tmap:
            row = _pad(tvals[tmap[site]], 24)
            prev_name, prev_phone = row[11], row[12]
            prev_new_phone = row[14] if len(row) > 14 else ""
        if site in smap:
            row = _pad(svals[smap[site]], 11)
            prev_name = row[2] or prev_name
            prev_phone = row[3] or prev_phone
            if len(row) > 6:
                prev_new_phone = row[6] or prev_new_phone

        live_phone, added = merge_contact(prev_phone, phone)
        live_unique = unique_contact(live_phone)
        prev_unique = unique_contact(prev_phone)
        already_in_new = set(phone_keys(prev_new_phone))
        extra_keys = [k for k in phone_keys(added) if k not in already_in_new]
        added = ", ".join(extra_keys)

        if prev_unique and live_unique == prev_unique and not added:
            continue
        if not live_unique:
            continue

        live_name = prev_name or name
        new_name = name if added else ""
        new_phone = added

        if site in tmap:
            r = tmap[site]
            t_updates.append({
                "range": f"L{r+1}:S{r+1}",
                "values": [[live_name, live_unique, new_name, new_phone, prev_name, prev_unique, ts, src_label]],
            })
        else:
            nrow = [""] * 24
            nrow[0] = len(tvals) + len(t_appends)
            nrow[1] = site
            nrow[11] = live_name
            nrow[12] = live_unique
            nrow[13] = new_name
            nrow[14] = new_phone
            nrow[17] = ts
            nrow[18] = src_label
            t_appends.append(nrow)
        if site in smap:
            r = smap[site]
            row = _pad(svals[r], 11)
            s_updates.append({
                "range": f"C{r+1}:K{r+1}",
                "values": [[live_name, live_unique, handled or row[4], new_name, new_phone, prev_name, prev_unique, ts, src_label]],
            })
        else:
            s_appends.append([
                len(svals) + len(s_appends), site, live_name, live_unique, handled,
                new_name, new_phone, prev_name, prev_unique, ts, src_label,
            ])
        logs.append([ts, site, prev_name, prev_unique, new_name, new_phone or live_unique, src_label])

    def _chunk(seq, n=40):
        for i in range(0, len(seq), n):
            yield seq[i : i + n]

    for chunk in _chunk(t_updates):
        _retry(lambda c=chunk: target.batch_update(c, value_input_option="USER_ENTERED"))
    for chunk in _chunk(s_updates):
        _retry(lambda c=chunk: src.batch_update(c, value_input_option="USER_ENTERED"))
    if t_appends:
        _retry(lambda: target.append_rows(t_appends, value_input_option="USER_ENTERED"))
    if s_appends:
        _retry(lambda: src.append_rows(s_appends, value_input_option="USER_ENTERED"))
    if logs:
        log = _ensure_log_tab(ss)
        _retry(lambda: log.append_rows(logs, value_input_option="USER_ENTERED"))
    return {"ok": len(logs), "email": email, "log": LC_LOG_TAB}


def update_lc_excel(site, lc_name, lc_phone, handled_by="", source="auto"):
    return update_lc_excel_batch([
        {"site": site, "name": lc_name, "phone": lc_phone, "handled_by": handled_by, "source": source}
    ], source=source)


def _col_letter(i0: int) -> str:
    n = int(i0) + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def apply_ticket_sync(history_gid: int, new_rows, still_open_ids):
    """Append new Incident ID rows and mark disappeared opens as Resolved on the history tab."""
    import pandas as pd

    gc, email = _client()
    ss = _retry(lambda: gc.open_by_key(xtranet_id()))
    ws = _ws_by_gid(ss, int(history_gid))
    values = _retry(lambda: ws.get_all_values()) or []
    if not values:
        values = [[]]
    header = [str(h).strip() for h in (values[0] if values else [])]
    if not header:
        raise RuntimeError("History tab has no header row")

    lower = {h.lower(): i for i, h in enumerate(header)}
    id_i = lower.get("incident id")
    st_i = lower.get("currentstatus", lower.get("current status"))
    rt_i = lower.get("resolved time-active", lower.get("resolved time"))
    if id_i is None:
        raise RuntimeError("Incident ID column missing on history tab")

    def nid(v):
        s = str(v or "").strip().upper()
        return "" if s in ("", "--", "NAN", "NONE", "NAT", "NULL") else s

    def is_open(v):
        t = str(v or "").strip().lower()
        if not t or t in ("--", "nan", "none") or "resolved" in t or t in ("closed", "close"):
            return False
        return "assign to fe" in t or "on hold" in t

    existing = set()
    for i, row in enumerate(values):
        if i == 0:
            continue
        if id_i < len(row):
            k = nid(row[id_i])
            if k:
                existing.add(k)

    appends = []
    if new_rows is not None and not getattr(new_rows, "empty", True):
        cmap = {str(c).strip().lower(): c for c in new_rows.columns}
        for _, rec in new_rows.iterrows():
            iid = nid(rec.get(cmap.get("incident id"), ""))
            if not iid or iid in existing:
                continue
            line = []
            for h in header:
                src = cmap.get(h.lower())
                val = rec.get(src, "") if src is not None else ""
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    val = ""
                elif str(val).lower() in ("nan", "nat", "none"):
                    val = ""
                line.append("" if val is None else str(val))
            appends.append(_pad(line, len(header)))
            existing.add(iid)

    open_ids = {nid(x) for x in (still_open_ids or set()) if nid(x)}
    now = _now()
    updates = []
    n_resolved = 0
    if st_i is not None:
        for i, row in enumerate(values):
            if i == 0:
                continue
            rid = nid(row[id_i]) if id_i < len(row) else ""
            if not rid or rid in open_ids:
                continue
            status = row[st_i] if st_i < len(row) else ""
            if not is_open(status):
                continue
            cell = f"{_col_letter(st_i)}{i + 1}"
            updates.append({"range": cell, "values": [["Resolved"]]})
            if rt_i is not None:
                prev = row[rt_i] if rt_i < len(row) else ""
                if str(prev).strip() in ("", "--", "nan", "None"):
                    updates.append({"range": f"{_col_letter(rt_i)}{i + 1}", "values": [[now]]})
            n_resolved += 1

    if appends:
        _retry(lambda: ws.append_rows(appends, value_input_option="USER_ENTERED"))
    for i in range(0, len(updates), 40):
        chunk = updates[i : i + 40]
        _retry(lambda c=chunk: ws.batch_update(c, value_input_option="USER_ENTERED"))
    return {
        "ok": True,
        "email": email,
        "appended": len(appends),
        "resolved": n_resolved,
        "error": "",
    }
