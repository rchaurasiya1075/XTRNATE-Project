"""Call at top of every page: ensure data + ISP ready."""
import streamlit as st
from utils.auto_load import auto_load_tickets

def ensure_ready():
    if 'selected_isp' not in st.session_state or not st.session_state.selected_isp:
        st.session_state.selected_isp = "ALL"
    if st.session_state.get('closed_df') is None:
        with st.spinner("Data auto-fetch..."):
            auto_load_tickets()
    return st.session_state.get('selected_isp', 'ALL')
