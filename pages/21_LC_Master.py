import streamlit as st
import pandas as pd
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import show_last_update
from utils.firebase_store import firebase_ready, upsert, get_one, list_all, delete_one
from utils.google_sheets import load_sheet_as_csv

SHEET_ID = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
CKT_GID = "886642043"

st.set_page_config(page_title="LC Master | XTRNATE", page_icon="📋", layout="wide")
show_last_update()

st.title("📋 LC / Site Restore Master")
st.caption("Har site ka LC number + BB/WiFi telco Firebase mein — refresh ke baad bhi rehta hai")

if not firebase_ready():
    st.error("Firebase secrets nahi mile. Streamlit Secrets mein service account dalo.")
    st.stop()

try:
    ckt = load_sheet_as_csv(SHEET_ID, gid=CKT_GID)
    ckt.columns = [str(c).strip() for c in ckt.columns]
except Exception:
    ckt = pd.DataFrame()

site_q = st.text_input("Site code search", placeholder="XTNCHG364").strip().upper()

try:
    saved = list_all("site_lc")
except Exception as e:
    st.error(f"Firebase read fail: {e}")
    st.stop()

saved_df = pd.DataFrame(saved) if saved else pd.DataFrame()

seed = {}
if site_q and not ckt.empty:
    sc = next((c for c in ckt.columns if str(c).lower() in ("site code", "sitecode")), None)
    if sc:
        hit = ckt[ckt[sc].astype(str).str.strip().str.upper() == site_q]
        if not hit.empty:
            row = hit.iloc[0]
            seed = {str(c): row[c] for c in hit.columns}

fb = get_one("site_lc", site_q) if site_q else None

if site_q:
    st.markdown(f"### {site_q}")
    c1, c2 = st.columns(2)
    with c1:
        lc_no = st.text_input("LC Number", value=str((fb or {}).get("lc_number", "") or ""))
        bb = st.text_input("BB / primary telco", value=str((fb or {}).get("bb_telco", seed.get("ISP", "") or "")))
        wifi = st.text_input("WiFi / last-mile telco", value=str((fb or {}).get("wifi_telco", "") or ""))
    with c2:
        ckt_id = st.text_input("Circuit ID", value=str((fb or {}).get("ckt_id", seed.get("Ckt ID", "") or "")))
        isp = st.text_input("ISP partner", value=str((fb or {}).get("isp", seed.get("ISP", "") or "")))
        note = st.text_area("Restore / change note", value=str((fb or {}).get("note", "") or ""))
    if st.button("💾 Save LC to Firebase", type="primary"):
        upsert("site_lc", site_q, {
            "site_code": site_q,
            "lc_number": lc_no.strip(),
            "bb_telco": bb.strip(),
            "wifi_telco": wifi.strip(),
            "ckt_id": ckt_id.strip(),
            "isp": isp.strip(),
            "note": note.strip(),
        })
        st.success("Saved — next refresh pe bhi yehi data aayega")
        st.rerun()

st.subheader("Saved LC sites")
if saved_df.empty:
    st.info("Abhi koi LC save nahi.")
else:
    q2 = st.text_input("Filter saved list", key="lc_filter").strip().upper()
    show = saved_df
    if q2 and "site_code" in show.columns:
        show = show[show["site_code"].astype(str).str.upper().str.contains(q2, na=False)]
    cols = [c for c in ["site_code", "lc_number", "bb_telco", "wifi_telco", "ckt_id", "isp", "note", "updated_at"] if c in show.columns]
    st.dataframe(show[cols] if cols else show, use_container_width=True, height=420)
    buf = BytesIO()
    show.to_excel(buf, index=False)
    st.download_button("📥 Excel LC master", data=buf.getvalue(), file_name="site_lc_firebase.xlsx")

    drop = st.selectbox("Delete site record", ["—"] + (saved_df["site_code"].astype(str).tolist() if "site_code" in saved_df.columns else []))
    if drop and drop != "—" and st.button("Delete from Firebase"):
        delete_one("site_lc", drop)
        st.rerun()
