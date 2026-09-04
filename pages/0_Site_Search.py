import streamlit as st
import sys
import os
import pandas as pd
import io

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.site_search import render_site_history_panel
from utils.bootstrap import ensure_ready
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

st.set_page_config(page_title="Site Search | XTRNATE", page_icon="🔍", layout="wide")
ensure_ready()

# Circuit ID page wala exact CSS theme & styles
st.markdown("""
<style>
@media (max-width: 768px) {
  .block-container { padding: 0.6rem !important; }
}

.ckt-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 70%);
  border: 1px solid #38bdf8;
  border-radius: 18px;
  padding: 1.4rem 1.6rem 1.1rem 1.6rem;
  margin-bottom: 1.2rem;
  box-shadow: 0 10px 30px rgba(15,23,42,0.35);
}
.ckt-hero h1 { color: #fff; margin: 0 0 0.25rem 0; font-size: 1.7rem; }
.ckt-hero p { color: #cbd5e1; margin: 0; }

.ckt-card {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 1.2rem 1.4rem;
  margin-top: 0.8rem;
  margin-bottom: 1rem;
}
.ckt-label { color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.2rem; }
</style>
""", unsafe_allow_html=True)

# Hero Header (Same as Circuit ID Page)
st.markdown("""
<div class="ckt-hero">
  <h1>🔍 Site Code Search</h1>
  <p>Koi bhi Site Code likho &nbsp;•&nbsp; Kab-kab down hua, reason, resolution — pura history breakdown</p>
</div>
""", unsafe_allow_html=True)

# Auto load if needed
if st.session_state.get('closed_df') is None:
    with st.spinner("Data auto-load..."):
        auto_load_tickets()

if 'selected_isp' not in st.session_state:
    st.session_state.selected_isp = "ALL"

closed = st.session_state.get('closed_df')
if closed is not None and not closed.empty:
    st.caption(f"Total History Records Loaded: **{len(closed)}** tickets")

q = st.text_input(
    "Search Site Code",
    placeholder="XTNNTL358 / XTNSLN354 ...",
    key="page_site_search",
)

if q and q.strip():
    site_code = q.strip().upper()
    
    # Quick copy snippet box matching CKT theme
    with st.container():
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="ckt-label">Searching Site Code — copy</div>', unsafe_allow_html=True)
            st.code(site_code, language=None)
        with c2:
            st.download_button(
                "📋 Site Code txt",
                data=site_code,
                file_name=f"{site_code}_site.txt",
                mime="text/plain",
                key=f"dl_site_{site_code}",
                use_container_width=True,
            )
            
    # Render main history panel
    render_site_history_panel(site_code)

    # Export history data if available in closed_df
    if closed is not None and not closed.empty and 'site_code' in closed.columns:
        filtered_history = closed[closed['site_code'].astype(str).str.upper() == site_code]
        if not filtered_history.empty:
            st.markdown("#### Export Site History")
            download_pack(
                f"{site_code} History",
                filtered_history,
                file_stem=f"Site_History_{site_code}",
                title=f"Site History  ·  {site_code}",
                sheet_name="Site_History",
                key=f"site_hist_{site_code}",
            )
else:
    st.info("Upar box mein Site Code type karo. Example: `XTNSLN354`")

# Quick suggestions from data formatted in CKT Dark Card style
if closed is not None and not closed.empty and 'site_code' in closed.columns:
    top = closed['site_code'].value_counts().head(12)
    st.markdown("""
    <div class="ckt-card">
        <div class="ckt-label">Top Repeated Sites (Click to copy-paste in search)</div>
    """, unsafe_allow_html=True)
    st.write(", ".join([f"`{s}`" for s in top.index.tolist()]))
    st.markdown("</div>", unsafe_allow_html=True)
