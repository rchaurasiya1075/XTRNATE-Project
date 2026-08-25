import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import process_closed_tickets, process_open_tickets, process_site_master, merge_with_site_master

st.set_page_config(page_title="Upload Data | XTRNATE", page_icon="📤", layout="wide")

st.title("📤 Upload Data")
st.markdown("Ek hi Excel upload karo. **Current Status** se system automatic Open / Closed alag kar lega.")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

st.info(f"Active ISP context: **{isp}**")

tab1, tab2, tab3 = st.tabs(["📁 Tickets Excel (Auto Split)", "📂 Open Tickets (Optional)", "🗺️ Site Master"])

with tab1:
    st.subheader("Tickets Excel (Recommended)")
    st.caption("Is Excel mein Current Status column hona chahiye (Assign to FE / Call on Hold / Resolved / Close). System automatic Open aur Closed alag kar dega.")
    
    tickets_file = st.file_uploader("Upload Tickets Excel", type=['xlsx', 'xls', 'csv'], key="tickets_upload")
    
    if tickets_file is not None:
        try:
            if tickets_file.name.lower().endswith('.csv'):
                df = pd.read_csv(tickets_file)
            else:
                df = pd.read_excel(tickets_file, engine='openpyxl')
            
            df.columns = [str(c).strip() for c in df.columns]
            
            st.write("Raw Preview (first 5 rows):")
            st.dataframe(df.head(5), use_container_width=True)
            st.write("Detected columns:", list(df.columns))
            
            # Process full data first (to get standardized columns)
            processed = process_closed_tickets(df)
            
            if processed is None or processed.empty:
                st.error("Processing returned empty data. Check column names.")
            else:
                # Split by status
                if 'status' in processed.columns:
                    status_str = processed['status'].astype(str).str.lower()
                    open_mask = (
                        status_str.str.contains('assign to fe', na=False) |
                        status_str.str.contains('call on hold', na=False) |
                        status_str.str.contains('on hold', na=False)
                    )
                    closed_mask = ~open_mask
                    
                    open_part = processed[open_mask].copy()
                    closed_part = processed[closed_mask].copy()
                    
                    # For open part, also run open processing for open_hours etc.
                    if not open_part.empty:
                        # Re-process open part lightly for open_hours
                        open_part = process_open_tickets(open_part)
                    
                    st.session_state.closed_df = closed_part if not closed_part.empty else None
                    st.session_state.open_df = open_part if not open_part.empty else None
                    
                    st.success(f"✅ Auto-split done!")
                    st.write(f"- **Closed / Resolved tickets:** {len(closed_part)}")
                    st.write(f"- **Open (Assign to FE / Call on Hold):** {len(open_part)}")
                    
                    if not open_part.empty:
                        st.write("Open tickets preview:")
                        st.dataframe(open_part.head(5), use_container_width=True)
                    if not closed_part.empty:
                        st.write("Closed tickets preview:")
                        st.dataframe(closed_part.head(5), use_container_width=True)
                else:
                    # No status column → treat all as closed
                    st.session_state.closed_df = processed
                    st.warning("Current Status column nahi mila. Saara data Closed mein daal diya.")
                    st.dataframe(processed.head(8), use_container_width=True)
                
                # Merge site master if available
                if st.session_state.get('site_master') is not None:
                    try:
                        if st.session_state.get('closed_df') is not None:
                            st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, st.session_state.site_master)
                        if st.session_state.get('open_df') is not None:
                            st.session_state.open_df = merge_with_site_master(st.session_state.open_df, st.session_state.site_master)
                        st.success("Merged with Site Master")
                    except Exception as me:
                        st.warning(f"Site Master merge skipped: {me}")
                
                with st.expander("Final columns"):
                    st.write(list(processed.columns))
                
        except Exception as e:
            st.error(f"Error processing file: {e}")
            st.exception(e)

with tab2:
    st.subheader("Open Tickets Excel (Optional - agar alag file hai)")
    st.caption("Agar aapke paas alag Open tickets file hai to yahan upload kar sakte ho. Warna upar wale tab se automatic split ho jayega.")
    
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
                try:
                    processed = merge_with_site_master(processed, st.session_state.site_master)
                except:
                    pass
            
            st.session_state.open_df = processed
            st.success(f"✅ Open tickets loaded! Total: {len(processed)}")
            st.dataframe(processed.head(8), use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

with tab3:
    st.subheader("Site Master Data")
    st.caption("Site Code → Bank, Branch, State, ISP, Partner etc.")
    
    site_file = st.file_uploader("Upload Site Master Excel/CSV", type=['xlsx', 'xls', 'csv'], key="site_upload")
    
    if site_file is not None:
        try:
            if site_file.name.lower().endswith('.csv'):
                df = pd.read_csv(site_file)
            else:
                df = pd.read_excel(site_file, engine='openpyxl')
            
            df.columns = [str(c).strip() for c in df.columns]
            processed = process_site_master(df)
            st.session_state.site_master = processed
            st.success(f"✅ Site Master loaded! Total sites: {len(processed)}")
            st.dataframe(processed.head(10), use_container_width=True)
            
            if st.session_state.get('closed_df') is not None:
                try:
                    st.session_state.closed_df = merge_with_site_master(st.session_state.closed_df, processed)
                except:
                    pass
            if st.session_state.get('open_df') is not None:
                try:
                    st.session_state.open_df = merge_with_site_master(st.session_state.open_df, processed)
                except:
                    pass
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

st.markdown("---")
st.subheader("Current Loaded Data Status")

c1, c2, c3 = st.columns(3)
with c1:
    closed_len = len(st.session_state.closed_df) if st.session_state.get('closed_df') is not None else 0
    st.metric("Closed / Resolved", closed_len)
with c2:
    open_len = len(st.session_state.open_df) if st.session_state.get('open_df') is not None else 0
    st.metric("Open (Assign to FE / On Hold)", open_len)
with c3:
    site_len = len(st.session_state.site_master) if st.session_state.get('site_master') is not None else 0
    st.metric("Site Master", site_len)
