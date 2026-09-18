"""One place to see / change every Google Sheet URL used by the app."""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.google_sheets import extract_sheet_id
from utils.sheets_config import all_config, save_config, edit_url, tab_url, csv_url

st.set_page_config(page_title="Sheet Links | Xtranet", page_icon="🔗", layout="wide")

st.title("🔗 Sheet Links")
st.caption(
    "All Google Sheet URLs live here. Change a link once — tickets, mail, SIM, "
    "circuit, LC, Multi Site Tracker and uploads all pick it up."
)

cfg = all_config()
books = cfg.get("workbooks") or {}
tabs = cfg.get("tabs") or {}

st.markdown("### Workbooks")
new_books = {}
for key, item in books.items():
    item = item if isinstance(item, dict) else {"id": str(item), "label": key}
    st.markdown(f"**{item.get('label') or key}**  ·  `{key}`")
    url = st.text_input(
        f"{key} URL",
        value=edit_url(item.get("id") or ""),
        key=f"book_url_{key}",
    )
    sid = extract_sheet_id(url) or (item.get("id") or "").strip()
    new_books[key] = {"id": sid, "label": item.get("label") or key}
    st.caption(f"ID: `{sid}`")

st.markdown("### Tabs (gid)")
rows = []
new_tabs = {}
for key, item in tabs.items():
    item = item if isinstance(item, dict) else {}
    book = item.get("book") or "xtranet"
    g = int(item.get("gid") or 0)
    label = item.get("label") or key
    c1, c2, c3 = st.columns([2.2, 1.2, 1.4])
    with c1:
        st.text_input("Tab", value=label, key=f"tab_lab_{key}", disabled=True)
    with c2:
        book_n = st.selectbox(
            "Workbook",
            list(new_books.keys()) or ["xtranet"],
            index=list(new_books.keys()).index(book) if book in new_books else 0,
            key=f"tab_book_{key}",
        )
    with c3:
        gid_n = st.number_input("GID", min_value=0, value=g, step=1, key=f"tab_gid_{key}")
    new_tabs[key] = {"book": book_n, "gid": int(gid_n), "label": label}
    sid = (new_books.get(book_n) or {}).get("id") or ""
    rows.append({
        "Tab": label,
        "Key": key,
        "Workbook": book_n,
        "GID": int(gid_n),
        "Open": edit_url(sid, int(gid_n)),
    })

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=420)

c1, c2 = st.columns(2)
with c1:
    if st.button("Save links — use on every page", type="primary"):
        save_config({"workbooks": new_books, "tabs": new_tabs})
        st.cache_data.clear()
        st.success("Saved. All pages now use these sheet URLs.")
        st.rerun()
with c2:
    st.caption("Paste a full Google Sheet URL in the workbook box. GID is the tab id from the sheet link (`gid=`).")
