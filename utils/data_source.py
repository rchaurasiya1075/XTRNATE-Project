"""Active project + data source (Google Sheet vs Manual Excel).

Reports always read closed_df / open_df / raw_tickets_df.
Those pointers follow the selected project + source, so a Google
refresh cannot overwrite a manual upload unless the user switches.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

DEFAULT_PROJECTS = ["Xtranet", "Shell", "Backhaul", "Link", "DGLL"]


def init_data_source():
    ss = st.session_state
    if "projects" not in ss:
        ss.projects = list(DEFAULT_PROJECTS)
    if "active_project" not in ss:
        ss.active_project = "Xtranet"
    if ss.active_project not in ss.projects:
        ss.projects = [ss.active_project] + [p for p in ss.projects if p != ss.active_project]
    if "data_source" not in ss:
        ss.data_source = "google"
    if "project_store" not in ss:
        ss.project_store = {}
    if "data_source_note" not in ss:
        ss.data_source_note = ""


def _empty_slot():
    return {"closed": None, "open": None, "raw": None, "note": "", "n_closed": 0, "n_open": 0}


def _bucket(project: str) -> dict:
    init_data_source()
    store = st.session_state.project_store
    if project not in store:
        store[project] = {"google": _empty_slot(), "upload": _empty_slot()}
    b = store[project]
    if "google" not in b:
        b["google"] = _empty_slot()
    if "upload" not in b:
        b["upload"] = _empty_slot()
    return b


def _pack(closed, opened, raw, note: str) -> dict:
    n_c = 0 if closed is None else len(closed)
    n_o = 0 if opened is None else len(opened)
    raw_df = raw if raw is not None else closed
    return {
        "closed": None if closed is None else closed.copy(),
        "open": None if opened is None else opened.copy(),
        "raw": None if raw_df is None else raw_df.copy(),
        "note": note or "",
        "n_closed": n_c,
        "n_open": n_o,
    }


def _slot_has_data(slot: dict) -> bool:
    if not slot:
        return False
    c, o, r = slot.get("closed"), slot.get("open"), slot.get("raw")
    for df in (c, o, r):
        if df is not None and not getattr(df, "empty", True):
            return True
    return False


def apply_active():
    """Point live session frames at the selected project + source."""
    init_data_source()
    project = st.session_state.active_project
    source = st.session_state.data_source
    if source not in ("google", "upload"):
        source = "google"
        st.session_state.data_source = source
    slot = _bucket(project).get(source) or _empty_slot()
    # Never silently swap Upload → Google. Empty upload stays empty.
    st.session_state.closed_df = slot.get("closed")
    st.session_state.open_df = slot.get("open")
    st.session_state.raw_tickets_df = slot.get("raw") if slot.get("raw") is not None else slot.get("closed")
    st.session_state.data_source_note = slot.get("note") or ""
    st.session_state.data_auto_loaded = True


def save_google(closed, opened=None, raw=None, note="Google Sheet"):
    init_data_source()
    project = st.session_state.active_project
    _bucket(project)["google"] = _pack(closed, opened, raw, note)
    if st.session_state.data_source == "google" or not _slot_has_data(_bucket(project)["upload"]):
        st.session_state.data_source = "google"
        apply_active()
    # If reports are on Manual Excel, leave closed_df on the upload pack.


def save_upload(closed, opened=None, raw=None, note="Manual Excel"):
    init_data_source()
    project = st.session_state.active_project
    _bucket(project)["upload"] = _pack(closed, opened, raw, note)
    st.session_state.data_source = "upload"
    apply_active()


def set_source(source: str):
    init_data_source()
    if source not in ("google", "upload"):
        return
    st.session_state.data_source = source
    apply_active()


def ingest_tickets_file(uploaded, *, note=None) -> str:
    """Parse Excel/CSV into the Manual Excel slot and make it the active source."""
    from utils.data_processing import process_closed_tickets, process_open_tickets

    name = getattr(uploaded, "name", "upload.xlsx")
    low = str(name).lower()
    if low.endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    processed = process_closed_tickets(df)
    closed, opened = processed, None
    if processed is not None and not processed.empty and "status" in processed.columns:
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
        else:
            opened = None
        if closed is None or closed.empty:
            closed = None
    save_upload(closed, opened, processed, note=note or name)
    n_c = 0 if closed is None else len(closed)
    n_o = 0 if opened is None else len(opened)
    return f"Using {name}  •  Closed {n_c}  •  Open {n_o}"


def render_data_mode(*, key="data_mode"):
    """Compact Google vs Upload switch. Returns 'google' or 'upload'."""
    init_data_source()
    labels = ["Google Sheet", "Uploaded Excel"]
    if key not in st.session_state:
        st.session_state[key] = labels[1 if st.session_state.data_source == "upload" else 0]
    pick = st.radio(
        "Data mode",
        labels,
        horizontal=True,
        key=key,
        help="Uploaded Excel uses only the file you loaded. Google Sheet is not read in that mode.",
    )
    want = "upload" if pick == "Uploaded Excel" else "google"
    if want != st.session_state.data_source:
        set_source(want)
        st.rerun()
    return want



def set_project(name: str):
    init_data_source()
    name = (name or "").strip()
    if not name:
        return
    if name not in st.session_state.projects:
        st.session_state.projects.append(name)
    st.session_state.active_project = name
    apply_active()


def source_status() -> str:
    init_data_source()
    src = st.session_state.data_source
    note = st.session_state.get("data_source_note") or ""
    kind = "Manual Excel" if src == "upload" else "Google Sheet"
    closed = st.session_state.get("closed_df")
    n = 0 if closed is None else len(closed)
    extra = f" ({note})" if note else ""
    return f"{st.session_state.active_project}  •  Reports: {kind}{extra}  •  {n} closed tickets"


def has_upload() -> bool:
    init_data_source()
    return _slot_has_data(_bucket(st.session_state.active_project)["upload"])


def has_google() -> bool:
    init_data_source()
    return _slot_has_data(_bucket(st.session_state.active_project)["google"])


def render_source_bar():
    """Project + Google vs Manual Excel. Safe to call on Home / Upload."""
    init_data_source()
    project = st.session_state.active_project
    bucket = _bucket(project)
    g = bucket["google"]
    u = bucket["upload"]

    st.markdown("### Report data")
    st.caption(
        "Xtranet NOC — pick the client project, then which file the reports should use. "
        "A Google Sheet refresh never overwrites a manual Excel unless you switch to Google Sheet."
    )
    r1, r2, r3 = st.columns([1.4, 1.6, 1.2])
    with r1:
        opts = st.session_state.projects
        idx = opts.index(project) if project in opts else 0
        picked = st.selectbox("Client / project", opts, index=idx, key="proj_select")
        if picked != project:
            set_project(picked)
            st.rerun()
        new_p = st.text_input("Add project", placeholder="e.g. Shell East", key="proj_add_name")
        if st.button("Add project", key="proj_add_btn") and new_p.strip():
            set_project(new_p.strip())
            st.rerun()
    with r2:
        g_lab = f"Google Sheet ({g.get('n_closed') or 0} tickets)"
        u_lab = f"Manual Excel ({u.get('n_closed') or 0} tickets)"
        if u.get("note"):
            u_lab = f"Manual Excel — {u.get('note')} ({u.get('n_closed') or 0})"
        choices = ["Google Sheet"]
        if _slot_has_data(u):
            choices.append("Manual Excel")
        current = "Manual Excel" if st.session_state.data_source == "upload" and _slot_has_data(u) else "Google Sheet"
        pick = st.radio(
            "Use this for all reports",
            choices,
            index=0 if current == "Google Sheet" else 1,
            help=g_lab + "  |  " + u_lab,
        )
        want = "upload" if pick == "Manual Excel" else "google"
        if want != st.session_state.data_source:
            set_source(want)
            st.rerun()
        st.caption(source_status())
    with r3:
        st.metric("Closed (active)", 0 if st.session_state.get("closed_df") is None else len(st.session_state.closed_df))
        st.metric("Open (active)", 0 if st.session_state.get("open_df") is None else len(st.session_state.open_df))
        if st.session_state.data_source == "upload":
            st.success("Reports are on the uploaded Excel.")
        else:
            st.info("Reports are on the Google Sheet.")
