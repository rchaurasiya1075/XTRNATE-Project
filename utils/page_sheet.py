"""Ask for a sheet URL on pages that are not the main ticket file.

Built-in projects keep their saved tabs. A pasted link overrides that tab.
A new project must paste the link before that page reads anything.
"""
from __future__ import annotations

import streamlit as st


def page_source(page_key: str, need: str):
    """Return ('builtin', '', 0), ('custom', sheet_id, gid), or None (page should stop)."""
    from utils.custom_projects import get_project, is_builtin, parse_gid, set_page_sheet
    from utils.google_sheets import extract_sheet_id

    project = str(st.session_state.get("active_project") or "").strip()
    builtin = is_builtin(project)
    cfg = {} if builtin else (get_project(project) or {})
    saved = str((cfg.get("pages") or {}).get(page_key) or "").strip()
    field = f"ps_{page_key}"
    if field not in st.session_state and saved:
        st.session_state[field] = saved

    must = not builtin and not (st.session_state.get(field) or saved)
    with st.expander(
        "Sheet link for this page" if not must else "This page needs a sheet link",
        expanded=must,
    ):
        st.caption(need + " Paste the Google link with gid=, then Load.")
        st.text_input(
            "Google Sheet link",
            key=field,
            placeholder="https://docs.google.com/spreadsheets/d/.../edit?gid=...",
        )
        if st.button("Load this sheet", key=f"ps_btn_{page_key}", type="primary" if must else "secondary"):
            url = str(st.session_state.get(field) or "").strip()
            if not extract_sheet_id(url):
                st.error("Paste the full Google Sheet link. It must contain gid=.")
            else:
                if not builtin:
                    set_page_sheet(project, page_key, url)
                st.cache_data.clear()
                st.rerun()

    url = str(st.session_state.get(field) or saved or "").strip()
    sid = extract_sheet_id(url) if url else ""
    if sid:
        return ("custom", sid, parse_gid(url))
    if builtin:
        return ("builtin", "", 0)
    st.info("Is report ke liye upar wali sheet ka link daalo, phir Load this sheet.")
    return None
