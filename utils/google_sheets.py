import pandas as pd
import streamlit as st
from io import StringIO
import re

def extract_sheet_id(url_or_id):
    """Extract Google Sheet ID from URL or return as-is if already ID"""
    if not url_or_id:
        return None
    url_or_id = str(url_or_id).strip()
    # Pattern for spreadsheet ID
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url_or_id)
    if match:
        return match.group(1)
    # If it's already just the ID
    if re.match(r'^[a-zA-Z0-9-_]{20,}$', url_or_id):
        return url_or_id
    return None

def load_sheet_as_csv(sheet_id, gid=0):
    """
    Load a Google Sheet using public CSV export.
    Sheet must be shared as 'Anyone with the link can view'.
    """
    try:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        raise Exception(f"Google Sheet load failed: {e}. Make sure the sheet is shared as 'Anyone with the link can view'.")

def load_sheet_with_gspread(sheet_id, worksheet_name=None):
    """
    Load using service account credentials stored in Streamlit secrets.
    Requires secrets.toml with [google_service_account] section.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]

        if "google_service_account" not in st.secrets:
            raise Exception("google_service_account not found in Streamlit secrets")

        creds_dict = dict(st.secrets["google_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(sheet_id)
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1

        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        raise Exception(f"gspread load failed: {e}")
