"""Auto-load tickets from Google Sheet when session is empty."""
import streamlit as st
import pandas as pd
from utils.google_sheets import load_sheet_as_csv, extract_sheet_id
from utils.data_processing import process_closed_tickets, process_open_tickets

DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
DEFAULT_GID = 0

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_raw_sheet(sheet_id: str, gid: int):
    """Cache raw sheet for 5 minutes to avoid repeated downloads."""
    return load_sheet_as_csv(sheet_id, gid=gid)

def auto_load_tickets(force: bool = False):
    """
    If closed_df/open_df empty (or force=True), load from default Google Sheet
    and auto-split by Current Status.
    Returns (success: bool, message: str)
    """
    if not force and st.session_state.get('closed_df') is not None:
        return True, "already_loaded"

    sheet_id = extract_sheet_id(DEFAULT_SHEET_URL)
    if not sheet_id:
        return False, "Invalid sheet ID"

    try:
        df = _fetch_raw_sheet(sheet_id, DEFAULT_GID)
        processed = process_closed_tickets(df)

        if processed is None or processed.empty:
            return False, "Empty data from sheet"

        if 'status' in processed.columns:
            status_str = processed['status'].astype(str).str.lower()
            open_mask = (
                status_str.str.contains('assign to fe', na=False) |
                status_str.str.contains('call on hold', na=False) |
                status_str.str.contains('on hold', na=False)
            )
            open_part = processed[open_mask].copy()
            closed_part = processed[~open_mask].copy()
            if not open_part.empty:
                open_part = process_open_tickets(open_part)
            st.session_state.closed_df = closed_part if not closed_part.empty else None
            st.session_state.open_df = open_part if not open_part.empty else None
            st.session_state.data_auto_loaded = True
            return True, f"Closed: {len(closed_part)} | Open: {len(open_part)}"
        else:
            st.session_state.closed_df = processed
            st.session_state.open_df = None
            st.session_state.data_auto_loaded = True
            return True, f"Closed: {len(processed)} (no status col)"
    except Exception as e:
        return False, str(e)
