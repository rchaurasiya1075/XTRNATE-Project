import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, isp_label
from utils.excel_to_ppt import load_workbook, workbook_to_pptx

st.set_page_config(page_title="Excel to PPT | XTRNATE", page_icon="🎬", layout="wide")
ensure_ready()

st.title("🎬 Excel → PPT automation")
st.caption("Excel / CSV upload → forest-green PPT with tables + animated graphs. Slideshow (F5) mein charts play honge.")

c1, c2 = st.columns([2, 1])
with c1:
    up = st.file_uploader("Excel ya CSV", type=["xlsx", "xls", "csv"], key="x2p_file")
with c2:
    title = st.text_input("PPT title", value=f"XTRNATE  ·  {isp_label()}", key="x2p_title")

use_live = st.checkbox("Loaded tickets se bhi PPT banao (Closed data)", value=False, key="x2p_live")

sheets = {}
src_name = "workbook"
if up is not None:
    try:
        sheets = load_workbook(up)
        src_name = up.name.rsplit(".", 1)[0]
        st.success(f"{len(sheets)} sheet(s) read: " + ", ".join(sheets.keys()))
        for k, df in list(sheets.items())[:3]:
            st.caption(f"**{k}** — {len(df)} rows × {len(df.columns)} cols")
            st.dataframe(df.head(5), use_container_width=True, height=160)
    except Exception as e:
        st.error(f"Excel read fail: {e}")

if use_live:
    closed = st.session_state.get("closed_df")
    if closed is not None and not closed.empty:
        work = closed.copy()
        sheets["Tickets"] = work.head(400)
        if "site_code" in work.columns:
            g = work.groupby("site_code").size().reset_index(name="Count").sort_values("Count", ascending=False)
            sheets["Top_Sites"] = g.head(30)
        if "state" in work.columns:
            sheets["State"] = work["state"].fillna("Unknown").astype(str).value_counts().reset_index()
            sheets["State"].columns = ["State", "Count"]
        if "submitted_time" in work.columns:
            tmp = work.copy()
            tmp["Date"] = pd.to_datetime(tmp["submitted_time"], errors="coerce").dt.strftime("%d-%b")
            sheets["Daily"] = tmp.dropna(subset=["Date"]).groupby("Date").size().reset_index(name="Count")
        st.info(f"Live tickets add: {len(work)} rows")
    else:
        st.warning("Closed tickets loaded nahi. Home pe data load karo ya Excel upload karo.")

go = st.button("Generate PPT", type="primary", use_container_width=True, key="x2p_go")
if go:
    if not sheets:
        st.warning("Pehle Excel upload karo ya live tickets tick karo.")
    else:
        with st.spinner("PPT + animated graphs ban rahe hain..."):
            try:
                ppt = workbook_to_pptx(
                    sheets,
                    title=title or src_name,
                    subtitle=f"{src_name}  •  {datetime.now().strftime('%d-%b-%Y %I:%M %p')}",
                )
                st.session_state["x2p_bytes"] = ppt
                st.session_state["x2p_stem"] = src_name
            except Exception as e:
                st.error(f"PPT build fail: {e}")

ppt = st.session_state.get("x2p_bytes")
if ppt:
    st.download_button(
        "📥 Download automated PPT",
        data=ppt,
        file_name=f"XTRNATE_{st.session_state.get('x2p_stem', 'Excel')}_Auto.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        use_container_width=True,
        key="x2p_dl",
    )
    st.caption("PowerPoint → **F5 Slideshow**. Tables forest-green. Graphs animate.")
