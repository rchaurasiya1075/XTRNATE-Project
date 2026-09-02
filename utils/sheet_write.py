"""Append / update Google Sheet rows using Firebase service account."""
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
    "Updated At",
    "Site Code",
    "Bank",
    "Branch",
    "State",
    "Old Media",
    "Old ISP / Last Mile",
    "Old Partner",
    "Old Ckt ID",
    "Old LC Name",
    "Old LC Contact",
    "New Media",
    "New ISP / Last Mile",
    "New LC Name",
    "New LC Contact",
    "Note",
]
LC_LOG_HEADERS = [
    "Updated At",
    "Site Code",
    "Old LC Name",
    "Old LC Contact",
    "New LC Name",
    "New LC Contact",
    "Source",
]

# gid 658119379 — extra columns after Branch Person Contact (col 13)
TARGET_EXTRA = {
    14: "New LC Name",
    15: "New LC Contact",
    16: "Prev LC Name",
    17: "Prev LC Contact",
    18: "LC Updated At",
    19: "LC Update Source",
    20: "New Last Mile Media",
    21: "New Last Mile ISP",
    22: "Prev Media",
    23: "Prev ISP",
    24: "Last Mile Updated At",
}
SOURCE_EXTRA = {
    6: "New LC Name",
    7: "New LC Contact",
    8: "Prev LC Name",
    9: "Prev LC Contact",
    10: "LC Updated At",
    11: "LC Update Source",
}


def _now():
    return datetime.now(IST).strftime("%d-%b-%Y %I:%M %p")


def sa_email():
    from utils.firebase_store import _load_sa_info
    info = _load_sa_info()
    return info.get("client_email", "")


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


def append_last_mile_log(row):
    gc, email = _client()
    ss = gc.open_by_key(MASTER_SHEET_ID)
    try:
        ws = ss.worksheet(LOG_TAB)
    except Exception:
        ws = ss.add_worksheet(title=LOG_TAB, rows=3000, cols=len(HEADERS) + 2)
        ws.append_row(HEADERS)
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(HEADERS)
    ws.append_row(row, value_input_option="USER_ENTERED")
    return email


def _find_row(ws, site, col_idx=1):
    site = str(site or "").strip().upper()
    col = ws.col_values(col_idx + 1)
    for i, v in enumerate(col):
        if str(v).strip().upper() == site:
            return i + 1
    return None


def _ensure_cols(ws, extra, min_cols):
    if ws.col_count < min_cols:
        ws.resize(rows=max(ws.row_count, 2), cols=min_cols)
    hdr = ws.row_values(1)
    for idx, name in extra.items():
        cur = hdr[idx - 1] if len(hdr) >= idx else ""
        if str(cur).strip() != name:
            ws.update_cell(1, idx, name)


def _ensure_log_tab(ss):
    try:
        ws = ss.worksheet(LC_LOG_TAB)
    except Exception:
        ws = ss.add_worksheet(title=LC_LOG_TAB, rows=4000, cols=len(LC_LOG_HEADERS) + 2)
        ws.append_row(LC_LOG_HEADERS)
    if not ws.row_values(1):
        ws.append_row(LC_LOG_HEADERS)
    return ws


def update_lc_excel(site, lc_name, lc_phone, handled_by="", source="auto"):
    """Write LC onto Xtranet sheet 1ELusYn2... — new columns + LC_Updates tab."""
    gc, email = _client()
    ss = gc.open_by_key(XTRANET_SHEET_ID)
    site = str(site).strip().upper()
    name = str(lc_name or "").strip()
    phone = str(lc_phone or "").strip()
    ts = _now()
    prev_name = prev_phone = ""

    target = _ws_by_gid(ss, LC_TARGET_GID)
    _ensure_cols(target, TARGET_EXTRA, 24)
    trow = _find_row(target, site, col_idx=1)
    if trow:
        prev_name = target.cell(trow, 12).value or ""
        prev_phone = target.cell(trow, 13).value or ""
        # L-S: live name/phone, New LC Name/Contact, Prev, Updated At, Source
        target.update(
            f"L{trow}:S{trow}",
            [[name, phone, name, phone, prev_name, prev_phone, ts, source]],
            value_input_option="USER_ENTERED",
        )
        target_how = f"gid658119379 row {trow} + New LC columns"
    else:
        nxt = len(target.col_values(1)) + 1
        row = [""] * 24
        row[0] = nxt - 1
        row[1] = site
        row[11] = name
        row[12] = phone
        row[13] = name
        row[14] = phone
        row[17] = ts
        row[18] = source
        target.append_row(row, value_input_option="USER_ENTERED")
        target_how = "gid658119379 new row"

    src = _ws_by_gid(ss, LC_SOURCE_GID)
    _ensure_cols(src, SOURCE_EXTRA, 11)
    srow = _find_row(src, site, col_idx=1)
    if srow:
        prev_name = src.cell(srow, 3).value or prev_name
        prev_phone = src.cell(srow, 4).value or prev_phone
        src.update_cell(srow, 3, name)
        src.update_cell(srow, 4, phone)
        if handled_by:
            src.update_cell(srow, 5, handled_by)
        src.update(
            f"F{srow}:K{srow}",
            [[name, phone, prev_name, prev_phone, ts, source]],
            value_input_option="USER_ENTERED",
        )
        src_how = f"gid401145054 row {srow} + New LC columns"
    else:
        nxt = len(src.col_values(1)) + 1
        src.append_row(
            [nxt - 1, site, name, phone, handled_by, name, phone, "", "", ts, source],
            value_input_option="USER_ENTERED",
        )
        src_how = "gid401145054 new row"

    log = _ensure_log_tab(ss)
    log.append_row(
        [ts, site, prev_name, prev_phone, name, phone, source],
        value_input_option="USER_ENTERED",
    )

    return {"email": email, "target": target_how, "source": src_how, "log": LC_LOG_TAB}
