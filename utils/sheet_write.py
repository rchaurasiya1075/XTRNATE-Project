"""Append rows to Google Sheet using the same Firebase service account."""
MASTER_SHEET_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
LOG_TAB = "LastMile_Updates"
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
    """row = list aligned to HEADERS. Creates LastMile_Updates tab if missing."""
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
