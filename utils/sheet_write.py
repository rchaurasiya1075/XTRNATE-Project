"""Append / update Google Sheet rows using Firebase service account."""
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MASTER_SHEET_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
XTRANET_SHEET_ID = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
LOG_TAB = "LastMile_Updates"
LC_LOG_TAB = "LC_Updates"
LC_SOURCE_GID = 401145054
LC_TARGET_GID = 658119379
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
        raise RuntimeError(f"Worksheet gid={gid} nahi mili")


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


def _digit_key(part):
    d = "".join(ch for ch in str(part or "") if ch.isdigit())
    if len(d) >= 10:
        return d[-10:]
    return d if len(d) >= 8 else ""


def merge_contact(old, new):
    """Keep old number, append only new ones as: old, new"""
    old = str(old or "").strip()
    new = str(new or "").strip()
    if not old:
        return new, new
    if not new:
        return old, ""
    have = set()
    for part in re.split(r"[/,;|\n]", old):
        k = _digit_key(part)
        if k:
            have.add(k)
    extra = []
    for part in re.split(r"[/,;|\n]", new):
        part = part.strip()
        k = _digit_key(part)
        if k and k not in have:
            extra.append(part)
            have.add(k)
    if not extra:
        return old, ""
    added = ", ".join(extra)
    return old + ", " + added, added


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
        ss = _retry(lambda: gc.open_by_key(XTRANET_SHEET_ID))
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
    ss = _retry(lambda: gc.open_by_key(MASTER_SHEET_ID))
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
    ss = _retry(lambda: gc.open_by_key(XTRANET_SHEET_ID))
    ts = _now()
    target = _ws_by_gid(ss, LC_TARGET_GID)
    src = _ws_by_gid(ss, LC_SOURCE_GID)
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
        if not site or not phone:
            continue
        prev_name = prev_phone = ""
        if site in tmap:
            row = _pad(tvals[tmap[site]], 24)
            prev_name, prev_phone = row[11], row[12]
        if site in smap:
            row = _pad(svals[smap[site]], 11)
            prev_name = row[2] or prev_name
            prev_phone = row[3] or prev_phone

        live_phone, added = merge_contact(prev_phone, phone)
        if not added and prev_phone:
            continue
        live_name = prev_name or name
        new_phone = added or phone

        if site in tmap:
            r = tmap[site]
            t_updates.append({
                "range": f"L{r+1}:S{r+1}",
                "values": [[live_name, live_phone, name, new_phone, prev_name, prev_phone, ts, src_label]],
            })
        else:
            nrow = [""] * 24
            nrow[0] = len(tvals) + len(t_appends)
            nrow[1] = site
            nrow[11] = live_name
            nrow[12] = live_phone
            nrow[13] = name
            nrow[14] = new_phone
            nrow[17] = ts
            nrow[18] = src_label
            t_appends.append(nrow)
        if site in smap:
            r = smap[site]
            row = _pad(svals[r], 11)
            s_updates.append({
                "range": f"C{r+1}:K{r+1}",
                "values": [[live_name, live_phone, handled or row[4], name, new_phone, prev_name, prev_phone, ts, src_label]],
            })
        else:
            s_appends.append([
                len(svals) + len(s_appends), site, live_name, live_phone, handled,
                name, new_phone, prev_name, prev_phone, ts, src_label,
            ])
        logs.append([ts, site, prev_name, prev_phone, name, new_phone, src_label])

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
