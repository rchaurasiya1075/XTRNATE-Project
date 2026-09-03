import streamlit as st
import pandas as pd
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.auto_load import auto_load_tickets
from utils.firebase_store import firebase_ready, upsert, list_all

st.set_page_config(page_title="Vendor Change | XTRNATE", page_icon="🔄", layout="wide")

st.title("🔄 Vendor Change Register")
st.caption("Remark se vendor change tickets → Firebase save • site-wise restore / status update")

ensure_ready()
if st.session_state.get("closed_df") is None:
    auto_load_tickets()

if not firebase_ready():
    st.error("Firebase secrets nahi mile. Streamlit Cloud → Settings → Secrets mein service account JSON dalo.")
    st.code("[firebase]\nprojectId = \"xtranet-d7dca\"\n\n[google_service_account]\n...json fields...", language="toml")
    st.stop()


def is_vendor_change(text):
    t = str(text or "").lower().replace("/", " ").replace(".", " ")
    keys = [
        "vendor change", "alternate service provider", "provisioned on alternate",
        "existing operator", "not stable", "migration", "not feasible",
        "rolled back", "isp change", "link provisioned on alternate",
    ]
    return any(k in t for k in keys)


frames = []
for key in ("closed_df", "open_df", "raw_tickets_df"):
    df = st.session_state.get(key)
    if df is not None and not getattr(df, "empty", True):
        frames.append(df)
if not frames:
    st.warning("Ticket data nahi mila.")
    st.stop()

all_df = pd.concat(frames, ignore_index=True)
all_df = all_df.loc[:, ~all_df.columns.duplicated()]
if "ticket_id" in all_df.columns:
    all_df = all_df.drop_duplicates(subset=["ticket_id"], keep="first")

reason_col = "reason" if "reason" in all_df.columns else None
mask = all_df[reason_col].apply(is_vendor_change) if reason_col else pd.Series(False, index=all_df.index)
vendor_tix = all_df[mask].copy() if reason_col else all_df.iloc[0:0].copy()

st.metric("Vendor-change remarks (sheet)", len(vendor_tix))

col_a, col_b = st.columns(2)
with col_a:
    if st.button("🔄 Sheet se Firebase sync", type="primary"):
        n = 0
        for _, row in vendor_tix.iterrows():
            tid = str(row.get("ticket_id", "") or "").strip() or f"row-{n}"
            site = str(row.get("site_code", "") or "").strip().upper()
            doc = {
                "ticket_id": tid,
                "site_code": site,
                "isp": str(row.get("isp", row.get("owner", "")) or ""),
                "status_ticket": str(row.get("status", "") or ""),
                "remark": str(row.get("reason", "") or ""),
                "submitted_time": str(row.get("submitted_time", "") or ""),
                "resolved_time": str(row.get("resolved_time", "") or ""),
                "work_status": "OPEN",
                "new_isp": "",
                "lc_note": "",
            }
            upsert("vendor_changes", tid, doc)
            n += 1
        st.success(f"{n} records Firebase mein save/merge.")
        st.rerun()

with col_b:
    st.caption("Pehle se saved record overwrite nahi hota except sheet fields. work_status / new_isp tumhara rehta hai (merge).")

try:
    saved = list_all("vendor_changes")
except Exception as e:
    st.error(f"Firebase read fail: {e}")
    st.stop()

saved_df = pd.DataFrame(saved) if saved else pd.DataFrame()
st.subheader("Firebase register")
if saved_df.empty:
    st.info("Abhi Firebase empty hai. Upar Sync dabao.")
else:
    show = saved_df[[c for c in [
        "site_code", "ticket_id", "isp", "work_status", "new_isp",
        "remark", "submitted_time", "updated_at",
    ] if c in saved_df.columns]]
    st.dataframe(show, use_container_width=True, height=360)

st.markdown("### Manual update")
sites = sorted({str(x) for x in (saved_df["site_code"].tolist() if not saved_df.empty else []) if x})
pick_site = st.selectbox("Site", ["—"] + sites)
if pick_site and pick_site != "—":
    rows = saved_df[saved_df["site_code"] == pick_site]
    st.dataframe(rows, use_container_width=True)
    pick_id = st.selectbox("Ticket", rows["_id"].tolist() if "_id" in rows.columns else [])
    if pick_id:
        cur = rows[rows["_id"] == pick_id].iloc[0].to_dict()
        ws = st.selectbox("Work status", ["OPEN", "IN PROGRESS", "DONE", "NOT FEASIBLE"],
                          index=["OPEN", "IN PROGRESS", "DONE", "NOT FEASIBLE"].index(str(cur.get("work_status", "OPEN"))) if str(cur.get("work_status", "OPEN")) in ["OPEN", "IN PROGRESS", "DONE", "NOT FEASIBLE"] else 0)
        new_isp = st.text_input("New ISP / vendor", value=str(cur.get("new_isp", "") or ""))
        note = st.text_area("LC / restore note", value=str(cur.get("lc_note", "") or ""))
        if st.button("Save to Firebase"):
            upsert("vendor_changes", pick_id, {
                **{k: cur.get(k, "") for k in ("ticket_id", "site_code", "isp", "status_ticket", "remark", "submitted_time", "resolved_time")},
                "work_status": ws,
                "new_isp": new_isp,
                "lc_note": note,
            })
            st.success("Saved")
            st.rerun()

if not saved_df.empty:
    buf = BytesIO()
    saved_df.to_excel(buf, index=False)
    st.download_button("📥 Excel vendor change register", data=buf.getvalue(), file_name="vendor_change_firebase.xlsx")
