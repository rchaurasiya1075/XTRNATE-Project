import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import process_closed_tickets, process_open_tickets, process_site_master, merge_with_site_master

st.set_page_config(page_title="Upload Data | XTRNATE", page_icon="📤", layout="wide")

st.title("📤 Upload Data")
st.markdown("Upload your CRM Excel files and Site Master data here.")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

st.info(f"Active ISP context: **{isp}** (data will be filtered accordingly in analysis pages)")

tab1, tab2, tab3 = st.tabs(["📁 Closed Tickets", "📂 Open Tickets", "🗺️ Site Master"])

with tab1:
    st.subheader("Closed Tickets Excel")
    st.caption("Columns expected: Incident ID, Request Title, Submitted Time, Owner, Down Time, State, Last Enclosure Comment(Active), Resolved Time-Active etc.")
    
    closed_file = st.file_uploader("Upload Closed Tickets Excel", type=['xlsx', 'xls', 'csv'], key="closed_upload")
    
    if closed_file is not None:
        try:
            if closed_file.name.lower().endswith('.csv'):
                df = pd.read_csv(closed_file)
            else:
                # Force openpyxl for better compatibility
                df = pd.read_excel(closed_file, engine='openpyxl')
            
            # Clean column names early
            df.columns = [str(c).strip() for c in df.columns]
            
            st.write("Raw Preview (first 5 rows):")
            st.dataframe(df.head(5), use_container_width=True)
            
            st.write("Detected columns:")
            st.write(list(df.columns))
            
            processed = process_closed_tickets(df)
            
            if processed is None or processed.empty:
                st.error("Processing returned empty data. Check column names.")
            else:
                if st.session_state.get('site_master') is not None:
                    try:
                        processed = merge_with_site_master(processed, st.session_state.site_master)
                        st.success("Merged with Site Master data")
                    except Exception as me:
                        st.warning(f"Site Master merge skipped: {me}")
                
                st.session_state.closed_df = processed
                st.success(f"✅ Closed tickets loaded successfully! Total rows: {len(processed)}")
                
                st.write("Processed Preview:")
                st.dataframe(processed.head(8), use_container_width=True)
                
                with st.expander("Final Processed Columns"):
                    st.write(list(processed.columns))
                
        except Exception as e:
            st.error(f"Error processing file: {e}")
            st.exception(e)   # shows full traceback for debugging

with tab2:
    st.subheader("Open Tickets Excel")
    st.caption("Columns expected: Incident ID, Request Title, Submitted Time, CurrentStatus, Owner, State, Last Enclosure Comment(Active) etc.")
    
    open_file = st.file_uploader("Upload Open Tickets Excel", type=['xlsx', 'xls', 'csv'], key="open_upload")
    
    if open_file is not None:
        try:
            if open_file.name.lower().endswith('.csv'):
                df = pd.read_csv(open_file)
            else:
                df = pd.read_excel(open_file, engine='openpyxl')
            
            df.columns = [str(c).strip() for c in df.columns]
            
            st.write("Raw Preview:")
            st.dataframe(df.head(5), use_container_width=True)
            
            processed = process_open_tickets(df)
            
            if st.session_state.get('site_master') is not None:
                try:
                    processed = merge_with_site_master(processed, st.session_state.site_master)
                    st.success("Merged with Site Master data")
                except Exception as me:
                    st.warning(f"Site Master merge skipped: {me}")
            
            st.session_state.open_df = processed
            st.success(f"✅ Open tickets loaded successfully! Total rows: {len(processed)}")
            
            st.write("Processed Preview:")
            st.dataframe(processed.head(8), use_container_width=True)
            
        except Exception as e:
            st.error(f"Error processing file: {e}")
            st.exception(e)

with tab3:
    st.subheader("Site Master Data")
    st.caption("Upload the master list containing Site Code → Bank, Branch, State, ISP, Partner etc.")
    
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
                    st.info("Closed tickets re-merged with new Site Master")
                except:
                    pass
            if st.session_state.get('open_df') is not None:
                try:
                    st.session_state.open_df = merge_with_site_master(st.session_state.open_df, processed)
                    st.info("Open tickets re-merged with new Site Master")
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
    st.metric("Closed Tickets", closed_len)
with c2:
    open_len = len(st.session_state.open_df) if st.session_state.get('open_df') is not None else 0
    st.metric("Open Tickets", open_len)
with c3:
    site_len = len(st.session_state.site_master) if st.session_state.get('site_master') is not None else 0
    st.metric("Site Master", site_len)
