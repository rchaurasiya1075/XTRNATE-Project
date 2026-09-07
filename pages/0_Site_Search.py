import os
import sys

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.bootstrap import show_last_update
from utils.data_source import (
    has_google,
    has_upload,
    ingest_tickets_file,
    init_data_source,
    render_data_mode,
    source_status,
)
from utils.site_search import render_last_month_down_categories, render_site_history_panel

st.set_page_config(page_title="Site Search | Xtranet", page_icon="🔍", layout="wide")
init_data_source()

st.markdown("""
<style>
@media (max-width: 768px) { .block-container { padding: 0.6rem !important; } }
div[data-testid="stMetric"] {
  background: #F3F5F4; border: 1px solid #D4D9D6; border-left: 4px solid #1B4D3E;
  border-radius: 12px; padding: 0.5rem 0.75rem;
}
.search-hero {
  background: linear-gradient(135deg, #1B4D3E 0%, #2D6A4F 80%);
  border-radius: 16px; padding: 1rem 1.25rem; margin-bottom: 0.9rem; color: #fff;
}
.search-hero h1 { margin: 0 0 0.15rem 0; font-size: 1.45rem; }
.search-hero p { margin: 0; color: #E8F0EC; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

show_last_update()
st.markdown("""
<div class="search-hero">
  <h1>🔍 Site Search</h1>
  <p>Pick Google Sheet or Uploaded Excel — search uses only that source</p>
</div>
""", unsafe_allow_html=True)

mode = render_data_mode(key="site_data_mode")
st.caption(source_status())

if mode == "upload":
    up = st.file_uploader(
        "Excel / CSV for this search",
        type=["xlsx", "xls", "csv"],
        key="site_mode_file",
        help="Loaded file is stored as Manual Excel. Google Sheet is not read.",
    )
    b1, b2 = st.columns([1, 2])
    with b1:
        load_it = st.button("Load file", type="primary", use_container_width=True, disabled=up is None)
    if load_it and up is not None:
        with st.spinner("Reading Excel…"):
            try:
                msg = ingest_tickets_file(up)
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(str(e))
    if not has_upload():
        st.warning("Upload mode is on. Load an Excel file above — Google Sheet will not be used.")
        st.stop()
else:
    if st.session_state.get("closed_df") is None and not has_google():
        with st.spinner("Loading Google Sheet…"):
            auto_load_tickets()
    if st.session_state.get("closed_df") is None:
        st.warning("Google Sheet has no tickets yet.")
        st.stop()

closed = st.session_state.get("closed_df")
n = 0 if closed is None else len(closed)
src_lab = "Uploaded Excel" if mode == "upload" else "Google Sheet"
note = st.session_state.get("data_source_note") or ""
st.success(f"{src_lab}{(' · ' + note) if note else ''}  •  {n} tickets")

s1, s2 = st.columns([5, 1])
with s1:
    q = st.text_input(
        "Site code",
        placeholder="XTNNTL358  ·  type and press Enter",
        key="page_site_search",
        label_visibility="collapsed",
    )
with s2:
    go = st.button("Search", type="primary", use_container_width=True, key="page_site_go")

if q and (go or q.strip()):
    render_site_history_panel(q.strip().upper())
else:
    st.caption("Type a site code to see down history, reasons and resolution.")

with st.expander("Last 30 days — 3 / 5 / 6 / 7+ downs", expanded=False):
    render_last_month_down_categories()

if closed is not None and not closed.empty and "site_code" in closed.columns:
    with st.expander("Frequent sites in this source", expanded=False):
        top = closed["site_code"].astype(str).str.upper().value_counts().head(12)
        pick = st.selectbox("Jump to site", ["—"] + list(top.index), key="freq_jump")
        st.caption("  ·  ".join(f"{k} ({int(v)})" for k, v in top.items()))
        if pick and pick != "—":
            render_site_history_panel(pick)
