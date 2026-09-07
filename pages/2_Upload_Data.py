import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import process_closed_tickets, process_open_tickets, process_site_master, merge_with_site_master
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.bootstrap import ensure_ready
from utils.data_source import render_source_bar, save_google, save_upload, set_source

st.set_page_config(page_title="Upload Data | Xtranet", page_icon="📤", layout="wide")

st.title("📤 Upload Data")
st.caption("Manual Excel and Google Sheet are stored separately. Choose which one all reports should use.")

isp = ensure_ready()
st.caption(f"Active ISP: **{isp}**")
render_source_bar()
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "☁️ Google Sheet Load",
    "📁 Tickets Excel (Auto Split)",
    "📂 Open Tickets (Optional)",
    "🗺️ Site Master"
])

# ========== TAB 1: Google Sheet (Primary) ==========
with tab1:
    st.subheader("Load from Google Sheet")
    st.markdown("""
    Default sheet is already set.

    1. Sheet **Share → Anyone with the link → Viewer** is required
    2. Select the data type
    3. Click **Load** — reports switch to this Google Sheet
    """)
    
    sheet_url = st.text_input(
        "Google Sheet URL",
        value="https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing",
        help="Tickets sheet"
    )
    
    col_a, col_b = st.columns(2)
    with col_a:
        gid = st.number_input("Sheet Tab GID (0 = first tab)", min_value=0, value=0, step=1)
    with col_b:
        data_type = st.selectbox("What is this data?", [
            "Tickets (Auto Split by Status)",
            "Site Master",
            "Closed Only",
            "Open Only"
        ])
    
    if st.button("🔄 Load from Google Sheet", type="primary"):
        sheet_id = extract_sheet_id(sheet_url)
        if not sheet_id:
            st.error("Invalid Google Sheet URL")
        else:
            try:
                with st.spinner("Loading Google Sheet..."):
                    df = load_sheet_as_csv(sheet_id, gid=gid)
                
                st.success(f"✅ Loaded **{len(df)}** rows from Google Sheet")
                st.dataframe(df.head(6), use_container_width=True)
                st.write("Columns:", list(df.columns))
                
                if data_type == "Site Master":
                    processed = process_site_master(df)
                    st.session_state.site_master = processed
                    st.success(f"Site Master loaded: {len(processed)} sites")
                    if st.session_state.get('closed_df') is not None:
                        st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, processed)
                    if st.session_state.get('open_df') is not None:
                        st.session_state.open_df = merge_with_site_master(st.session_state.open_df, processed)
                
                elif data_type == "Tickets (Auto Split by Status)":
                    processed = process_closed_tickets(df)
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
                        save_google(
                            st.session_state.closed_df,
                            st.session_state.open_df,
                            processed,
                            note="Google Sheet",
                        )
                        set_source("google")
                        st.success(f"✅ Auto-split done!\n- Closed / Resolved: **{len(closed_part)}**\n- Open (Assign to FE / On Hold): **{len(open_part)}**")
                        if not open_part.empty:
                            st.write("Open preview:")
                            st.dataframe(open_part.head(5), use_container_width=True)
                    else:
                        st.session_state.closed_df = processed
                        save_google(processed, st.session_state.get("open_df"), processed, note="Google Sheet")
                        set_source("google")
                        st.warning("Status column not found → treated as Closed")
                
                elif data_type == "Closed Only":
                    processed = process_closed_tickets(df)
                    st.session_state.closed_df = processed
                    save_google(processed, st.session_state.get("open_df"), processed, note="Google Sheet")
                    set_source("google")
                    st.success(f"Closed loaded: {len(processed)}")
                
                elif data_type == "Open Only":
                    processed = process_open_tickets(df)
                    st.session_state.open_df = processed
                    save_google(st.session_state.get("closed_df"), processed, st.session_state.get("raw_tickets_df"), note="Google Sheet")
                    set_source("google")
                    st.success(f"Open loaded: {len(processed)}")
                
                # Merge site master if available
                if st.session_state.get('site_master') is not None and data_type != "Site Master":
                    try:
                        if st.session_state.get('closed_df') is not None:
                            st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, st.session_state.site_master)
                        if st.session_state.get('open_df') is not None:
                            st.session_state.open_df = merge_with_site_master(st.session_state.open_df, st.session_state.site_master)
                        save_google(
                            st.session_state.get("closed_df"),
                            st.session_state.get("open_df"),
                            st.session_state.get("raw_tickets_df"),
                            note="Google Sheet",
                        )
                    except Exception:
                        pass
                        
            except Exception as e:
                st.error(str(e))
                st.info("Share the sheet: Anyone with the link → Viewer.")

# ========== TAB 2: Excel Auto Split ==========
with tab2:
    st.subheader("Tickets Excel (Auto Split)")
    st.caption("Upload, then click **Use this Excel for all reports**. Refreshing Google Sheet will not replace it.")
    tickets_file = st.file_uploader("Upload Tickets Excel", type=['xlsx', 'xls', 'csv'], key="tickets_upload")
    if tickets_file is not None:
        try:
            if tickets_file.name.lower().endswith('.csv'):
                df = pd.read_csv(tickets_file)
            else:
                df = pd.read_excel(tickets_file, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            st.dataframe(df.head(5), use_container_width=True)
            st.caption(f"{len(df)} rows • {tickets_file.name}")
            if st.button("Use this Excel for all reports", type="primary", key="use_excel_btn"):
                processed = process_closed_tickets(df)
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
                    else:
                        open_part = None
                    if closed_part.empty:
                        closed_part = None
                    save_upload(closed_part, open_part, processed, note=tickets_file.name)
                    n_c = 0 if closed_part is None else len(closed_part)
                    n_o = 0 if open_part is None else len(open_part)
                    st.success(f"Reports now use **{tickets_file.name}** — Closed {n_c} | Open {n_o}")
                else:
                    save_upload(processed, None, processed, note=tickets_file.name)
                    st.warning("No status column → all Closed. Reports now use this file.")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

# ========== TAB 3: Open Optional ==========
with tab3:
    st.subheader("Open Tickets Excel (Optional)")
    open_file = st.file_uploader("Upload Open Tickets", type=['xlsx', 'xls', 'csv'], key="open_upload")
    if open_file is not None:
        try:
            if open_file.name.lower().endswith('.csv'):
                df = pd.read_csv(open_file)
            else:
                df = pd.read_excel(open_file, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            processed = process_open_tickets(df)
            if st.button("Add this Open Excel to Manual reports", type="primary", key="use_open_btn"):
                closed = st.session_state.get("closed_df")
                raw = st.session_state.get("raw_tickets_df")
                save_upload(closed, processed, raw if raw is not None else closed, note=open_file.name)
                st.success(f"Open tickets from **{open_file.name}** attached to Manual Excel reports.")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# ========== TAB 4: Site Master ==========
with tab4:
    st.subheader("Site Master")
    site_file = st.file_uploader("Upload Site Master", type=['xlsx', 'xls', 'csv'], key="site_upload")
    if site_file is not None:
        try:
            if site_file.name.lower().endswith('.csv'):
                df = pd.read_csv(site_file)
            else:
                df = pd.read_excel(site_file, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            processed = process_site_master(df)
            st.session_state.site_master = processed
            st.success(f"Site Master: {len(processed)}")
        except Exception as e:
            st.error(f"Error: {e}")

# ========== STATUS ==========
st.markdown("---")
st.subheader("Current Loaded Data")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Closed / Resolved", len(st.session_state.closed_df) if st.session_state.get('closed_df') is not None else 0)
with c2:
    st.metric("Open (Assign to FE / On Hold)", len(st.session_state.open_df) if st.session_state.get('open_df') is not None else 0)
with c3:
    st.metric("Site Master", len(st.session_state.site_master) if st.session_state.get('site_master') is not None else 0)
