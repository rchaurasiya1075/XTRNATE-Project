import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import process_closed_tickets, process_open_tickets, process_site_master, merge_with_site_master
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv

st.set_page_config(page_title="Upload Data | XTRNATE", page_icon="📤", layout="wide")

st.title("📤 Upload Data")
st.markdown("Excel upload **ya** Google Sheet se load karo. Google Sheet data refresh ke baad bhi rahega.")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

st.info(f"Active ISP context: **{isp}**")

tab1, tab2, tab3, tab4 = st.tabs([
    "📁 Tickets Excel (Auto Split)",
    "☁️ Google Sheet Load",
    "📂 Open Tickets (Optional)",
    "🗺️ Site Master"
])

# ========== TAB 1: Excel Auto Split ==========
with tab1:
    st.subheader("Tickets Excel (Auto Split by Status)")
    st.caption("Current Status = Assign to FE / Call on Hold → Open | Resolved / Close → Closed")
    
    tickets_file = st.file_uploader("Upload Tickets Excel", type=['xlsx', 'xls', 'csv'], key="tickets_upload")
    
    if tickets_file is not None:
        try:
            if tickets_file.name.lower().endswith('.csv'):
                df = pd.read_csv(tickets_file)
            else:
                df = pd.read_excel(tickets_file, engine='openpyxl')
            
            df.columns = [str(c).strip() for c in df.columns]
            st.write("Raw Preview:")
            st.dataframe(df.head(5), use_container_width=True)
            
            processed = process_closed_tickets(df)
            
            if processed is None or processed.empty:
                st.error("Processing returned empty data.")
            else:
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
                    
                    st.success(f"✅ Auto-split done! Closed: {len(closed_part)} | Open: {len(open_part)}")
                else:
                    st.session_state.closed_df = processed
                    st.warning("Status column nahi mila. Saara data Closed mein.")
                
                if st.session_state.get('site_master') is not None:
                    try:
                        if st.session_state.get('closed_df') is not None:
                            st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, st.session_state.site_master)
                        if st.session_state.get('open_df') is not None:
                            st.session_state.open_df = merge_with_site_master(st.session_state.open_df, st.session_state.site_master)
                    except:
                        pass
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

# ========== TAB 2: Google Sheet ==========
with tab2:
    st.subheader("☁️ Load from Google Sheet")
    st.markdown("""
    **Kaise use karein:**
    1. Apni Google Sheet kholo
    2. **Share** → **Anyone with the link** → **Viewer**
    3. Sheet ka full link yahan paste karo
    4. **gid** (sheet tab number) bhi daal sakte ho (default 0)
    """)
    
    sheet_url = st.text_input(
        "Google Sheet URL or ID",
        value="https://docs.google.com/spreadsheets/d/1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I/edit",
        help="Pehle wala Site Master sheet already bhar diya hai"
    )
    
    col_a, col_b = st.columns(2)
    with col_a:
        gid = st.number_input("Sheet Tab GID (0 = first tab)", min_value=0, value=0, step=1)
    with col_b:
        data_type = st.selectbox("Yeh data kya hai?", ["Site Master", "Tickets (Auto Split)", "Closed Only", "Open Only"])
    
    if st.button("🔄 Load from Google Sheet", type="primary"):
        sheet_id = extract_sheet_id(sheet_url)
        if not sheet_id:
            st.error("Invalid Google Sheet URL / ID")
        else:
            try:
                with st.spinner("Loading from Google Sheet..."):
                    df = load_sheet_as_csv(sheet_id, gid=gid)
                
                st.success(f"Loaded {len(df)} rows from Google Sheet")
                st.dataframe(df.head(8), use_container_width=True)
                st.write("Columns:", list(df.columns))
                
                if data_type == "Site Master":
                    processed = process_site_master(df)
                    st.session_state.site_master = processed
                    st.success(f"✅ Site Master loaded: {len(processed)} sites")
                    
                    # Re-merge existing tickets
                    if st.session_state.get('closed_df') is not None:
                        st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, processed)
                    if st.session_state.get('open_df') is not None:
                        st.session_state.open_df = merge_with_site_master(st.session_state.open_df, processed)
                
                elif data_type == "Tickets (Auto Split)":
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
                        st.success(f"✅ Split done! Closed: {len(closed_part)} | Open: {len(open_part)}")
                    else:
                        st.session_state.closed_df = processed
                        st.warning("Status column nahi mila → saara Closed")
                
                elif data_type == "Closed Only":
                    processed = process_closed_tickets(df)
                    st.session_state.closed_df = processed
                    st.success(f"✅ Closed loaded: {len(processed)}")
                
                elif data_type == "Open Only":
                    processed = process_open_tickets(df)
                    st.session_state.open_df = processed
                    st.success(f"✅ Open loaded: {len(processed)}")
                
                # Auto merge site master
                if st.session_state.get('site_master') is not None and data_type != "Site Master":
                    try:
                        if st.session_state.get('closed_df') is not None:
                            st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, st.session_state.site_master)
                        if st.session_state.get('open_df') is not None:
                            st.session_state.open_df = merge_with_site_master(st.session_state.open_df, st.session_state.site_master)
                    except:
                        pass
                        
            except Exception as e:
                st.error(str(e))
                st.info("Tip: Sheet ko Share → Anyone with the link → Viewer banao.")

# ========== TAB 3: Open Optional ==========
with tab3:
    st.subheader("Open Tickets Excel (Optional)")
    open_file = st.file_uploader("Upload Open Tickets Excel", type=['xlsx', 'xls', 'csv'], key="open_upload")
    if open_file is not None:
        try:
            if open_file.name.lower().endswith('.csv'):
                df = pd.read_csv(open_file)
            else:
                df = pd.read_excel(open_file, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            processed = process_open_tickets(df)
            if st.session_state.get('site_master') is not None:
                processed = merge_with_site_master(processed, st.session_state.site_master)
            st.session_state.open_df = processed
            st.success(f"✅ Open tickets: {len(processed)}")
            st.dataframe(processed.head(8), use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

# ========== TAB 4: Site Master Excel ==========
with tab4:
    st.subheader("Site Master Excel")
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
            st.success(f"✅ Site Master: {len(processed)}")
            st.dataframe(processed.head(10), use_container_width=True)
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
