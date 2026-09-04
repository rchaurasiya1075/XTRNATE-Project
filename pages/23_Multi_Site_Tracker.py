import os
import sys

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.site_pack import render_multi_site_pack

st.set_page_config(page_title="Multi Site Tracker | XTRNATE", page_icon="📋", layout="wide")
ensure_ready()

st.title("📋 Multi Site Tracker")
st.caption("Kai site codes ek saath paste karo — history, SIM, last mile, LC, circuit. Excel + PDF.")
render_multi_site_pack()
