"""Append / update Google Sheet rows using Firebase service account."""
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MASTER_SHEET_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
XTRANET_SHEET_ID = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
LOG_TAB = "LastMile_Updates"
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

TARGET_EXTRA = {
    14: "Prev LC Name",
    15: "Prev LC Contact",
    16: "LC Updated At",
    17: "LC Update Source",
    18: "New Last Mile Media",
    19: "New Last Mile ISP",
    20: "Prev Media",
    21: "Prev ISP",
    22: "Last Mile Updated At",
}
SOURCE_EXTRA = {
    6: "Prev LC Name",
    7: "Prev LC Contact",
    8: "LC Updated At",
    9: "LC Update Source",
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


def update_lc_excel(site, lc_name, lc_phone, handled_by="", source="auto"):
    """Replace LC with new contact. Old values go to Prev columns + timestamp."""
    gc, email = _client()
    ss = gc.open_by_key(XTRANET_SHEET_ID)
    site = str(site).strip().upper()
    name = str(lc_name or "").strip()
    phone = str(lc_phone or "").strip()
    ts = _now()

    target = ss.get_worksheet_by_id(LC_TARGET_GID)
    _ensure_cols(target, TARGET_EXTRA, 22)
    trow = _find_row(target, site, col_idx=1)
    if trow:
        prev_name = target.cell(trow, 12).value or ""
        prev_phone = target.cell(trow, 13).value or ""
        target.update(
            f"L{trow}:Q{trow}",
            [[name, phone, prev_name, prev_phone, ts, source]],
            value_input_option="USER_ENTERED",
        )
        target_how = f"updated row {trow}"
    else:
        nxt = len(target.col_values(1)) + 1
        row = [""] * 22
        row[0] = nxt - 1
        row[1] = site
        row[11] = name
        row[12] = phone
        row[13] = ""
        row[14] = ""
        row[15] = ts
        row[16] = source
        target.append_row(row, value_input_option="USER_ENTERED")
        target_how = "appended new row"

    src = ss.get_worksheet_by_id(LC_SOURCE_GID)
    _ensure_cols(src, SOURCE_EXTRA, 9)
    srow = _find_row(src, site, col_idx=1)
    if srow:
        prev_name = src.cell(srow, 3).value or ""
        prev_phone = src.cell(srow, 4).value or ""
        src.update_cell(srow, 3, name)
        src.update_cell(srow, 4, phone)
        if handled_by:
            src.update_cell(srow, 5, handled_by)
        src.update(
            f"F{srow}:I{srow}",
            [[prev_name, prev_phone, ts, source]],
            value_input_option="USER_ENTERED",
        )
        src_how = f"updated row {srow}"
    else:
        nxt = len(src.col_values(1)) + 1
        src.append_row(
            [nxt - 1, site, name, phone, handled_by, "", "", ts, source],
            value_input_option="USER_ENTERED",
        )
        src_how = "appended new row"

    return {"email": email, "target": target_how, "source": src_how}
