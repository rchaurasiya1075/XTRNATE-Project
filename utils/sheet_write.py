"""Append / update Google Sheet rows using Firebase service account."""
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
    """col_idx 0-based. Returns 1-based row number or None."""
    site = str(site or "").strip().upper()
    col = ws.col_values(col_idx + 1)
    for i, v in enumerate(col):
        if str(v).strip().upper() == site:
            return i + 1
    return None


def update_lc_excel(site, lc_name, lc_phone, handled_by=""):
    """Update LC name/phone on site-master gid 658119379 and LC tab 401145054."""
    gc, email = _client()
    ss = gc.open_by_key(XTRANET_SHEET_ID)
    site = str(site).strip().upper()
    name = str(lc_name or "").strip()
    phone = str(lc_phone or "").strip()

    target = ss.get_worksheet_by_id(LC_TARGET_GID)
    trow = _find_row(target, site, col_idx=1)  # HughesSitecode
    if trow:
        target.update_cell(trow, 12, name)
        target.update_cell(trow, 13, phone)
        target_how = f"updated row {trow}"
    else:
        nxt = len(target.col_values(1)) + 1
        target.append_row([nxt - 1, site, "", "", "", "", "", "", "", "", "", name, phone], value_input_option="USER_ENTERED")
        target_how = "appended new row"

    src = ss.get_worksheet_by_id(LC_SOURCE_GID)
    srow = _find_row(src, site, col_idx=1)  # Hughes Site code
    if srow:
        src.update_cell(srow, 3, name)
        src.update_cell(srow, 4, phone)
        if handled_by:
            src.update_cell(srow, 5, handled_by)
        src_how = f"updated row {srow}"
    else:
        nxt = len(src.col_values(1)) + 1
        src.append_row([nxt - 1, site, name, phone, handled_by], value_input_option="USER_ENTERED")
        src_how = "appended new row"

    return {"email": email, "target": target_how, "source": src_how}
