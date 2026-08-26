import streamlit as st
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.site_search import render_site_history_panel

st.set_page_config(page_title="Site Search | XTRNATE", page_icon="🔍", layout="wide")

st.markdown("""
<style>
@media (max-width: 768px) {
  .block-container { padding: 0.6rem !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("🔍 Site Code Search")
st.caption("Koi bhi Site Code likho → kab-kab down hua, reason, resolution — pura history")

# Auto load if needed
if st.session_state.get('closed_df') is None:
    with st.spinner("Data auto-load..."):
        auto_load_tickets()

if 'selected_isp' not in st.session_state:
    st.session_state.selected_isp = "ALL"

q = st.text_input(
    "Site Code",
    placeholder="XTNNTL358 / XTNSLN354 ...",
    key="page_site_search",
)

if q:
    render_site_history_panel(q.strip().upper())
else:
    st.info("Upar box mein Site Code type karo.")

# Quick suggestions from data
closed = st.session_state.get('closed_df')
if closed is not None and not closed.empty and 'site_code' in closed.columns:
    top = closed['site_code'].value_counts().head(12)
    st.markdown("#### Top repeated sites (click to copy-paste in search)")
    st.write(", ".join([f"`{s}`" for s in top.index.tolist()]))
