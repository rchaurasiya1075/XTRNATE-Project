import os
import sys
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.google_sheets import load_sheet_as_csv
from utils.firebase_store import firebase_ready, upsert, get_one, list_all, _now
from utils.excel_export import excel_bytes
from utils.report_download import download_pack
from utils.sheet_write import HEADERS, append_last_mile_log, sa_email

IST = ZoneInfo("Asia/Kolkata")
MASTER_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
MASTER_GID = "1181450647"
MAIL_GID = "762980214"
CKT_ID = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
CKT_GID = "886642043"

st.set_page_config(page_title="Last Mile Update | XTRNATE", page_icon="📍", layout="wide")
ensure_ready()

st.title("Last Mile / LC Contact Update")
st.caption("Old last mile + LC dikhega • naya data save = Firebase + Google Sheet mein nayi row")


def _col(df, *names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    for key, col in lower.items():
        for n in names:
            if n.lower() in key:
                return col
    return None


@st.cache_data(ttl=180, show_spinner=False)
def load_master():
    df = load_sheet_as_csv(MASTER_ID, gid=MASTER_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughessitecode", "site code", "sitecode") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


@st.cache_data(ttl=120, show_spinner=False)
def load_open_calls():
    url = f"https://docs.google.com/spreadsheets/d/{MASTER_ID}/export?format=csv&gid={MAIL_GID}"
    raw = pd.read_csv(url, header=None)
    header = [str(c).strip() for c in raw.iloc[3].tolist()]
    seen, cols = {}, []
    for h in header:
        name = h if h and h.lower() != "nan" else "col"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cols.append(name)
    df = raw.iloc[4:].copy()
    df.columns = cols
    df = df.dropna(how="all")
    sc = _col(df, "site code")
    if sc:
        df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df.reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_ckt():
    df = load_sheet_as_csv(CKT_ID, gid=CKT_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


def val(row, *names):
    if row is None:
        return ""
    for n in names:
        if n in row.index:
            v = row.get(n, "")
            if pd.notna(v) and str(v).strip() and str(v).lower() != "nan":
                return str(v).strip()
    lower = {str(i).strip().lower(): i for i in row.index}
    for n in names:
        if n.lower() in lower:
            v = row.get(lower[n.lower()], "")
            if pd.notna(v) and str(v).strip() and str(v).lower() != "nan":
                return str(v).strip()
    return ""


try:
    master = load_master()
except Exception as e:
    st.error(f"Site master load fail: {e}")
    st.stop()

try:
    calls = load_open_calls()
except Exception:
    calls = pd.DataFrame()
try:
    ckt = load_ckt()
except Exception:
    ckt = pd.DataFrame()

q = st.text_input("Site code", placeholder="XTNCHG364").strip().upper()

if not q:
    st.info("Site code likho — old last mile, LC, branch contact dikhega.")
else:
    mhit = master[master["site_code"] == q]
    chit = calls[calls["site_code"] == q] if "site_code" in calls.columns else calls.iloc[0:0]
    khit = ckt[ckt["site_code"] == q] if "site_code" in ckt.columns else ckt.iloc[0:0]
    mrow = mhit.iloc[0] if not mhit.empty else None
    crow = chit.iloc[0] if not chit.empty else None
    krow = khit.iloc[0] if not khit.empty else None
    fb = None
    if firebase_ready():
        try:
            fb = get_one("last_mile_updates", q)
        except Exception:
            fb = None

    old_media = val(mrow, "Media") or val(crow, "Media")
    old_isp = val(mrow, "ISP Name") or val(crow, "ISP Name") or val(krow, "ISP")
    old_partner = val(mrow, "Partner")
    old_ckt = val(mrow, "Ckt ID") or val(krow, "Ckt ID")
    old_lc = val(crow, "Branch Person Name") or val(mrow, "Branch Person Name")
    old_ph = val(crow, "Branch Person Contact Number") or val(mrow, "Branch Person Contact Number")
    bank = val(mrow, "Bank Name")
    branch = val(mrow, "Branch Name") or val(crow, "Branch")
    state = val(mrow, "State") or val(crow, "State")

    st.markdown("### Old details")
    a, b, c = st.columns(3)
    a.write(f"**Site:** `{q}`")
    a.write(f"**Bank:** {bank}")
    a.write(f"**Branch:** {branch}")
    b.write(f"**State:** {state}")
    b.write(f"**Old last mile / media:** {old_media}")
    b.write(f"**Old ISP:** {old_isp}")
    c.write(f"**Partner:** {old_partner}")
    c.write(f"**Ckt ID:** {old_ckt}")
    c.write(f"**Old LC:** {old_lc} / {old_ph}")

    if fb:
        st.success(
            f"Last app update: {fb.get('new_isp') or fb.get('new_media')} • "
            f"LC {fb.get('new_lc_name')} {fb.get('new_lc_contact')} • {fb.get('updated_at')}"
        )

    st.markdown("### New update")
    n1, n2 = st.columns(2)
    with n1:
        new_media = st.selectbox(
            "New last mile (media)",
            ["", "Fiber", "Air Fiber", "Copper", "RF", "Other"],
            index=0,
        )
        new_isp = st.text_input("New last mile / ISP", placeholder="BSNL / Airtel / Jio ...")
    with n2:
        new_lc = st.text_input("New LC name", value="")
        new_ph = st.text_input("New LC contact number", value="")
    note = st.text_area("Note", placeholder="Vendor change / contact update ...")

    if st.button("Save update (Firebase + Google Sheet new row)", type="primary"):
        if not new_isp and not new_lc and not new_ph and not new_media:
            st.warning("Kam se kam naya ISP / LC name / number dalo.")
        else:
            payload = {
                "site_code": q,
                "bank": bank,
                "branch": branch,
                "state": state,
                "old_media": old_media,
                "old_isp": old_isp,
                "old_partner": old_partner,
                "old_ckt": old_ckt,
                "old_lc_name": old_lc,
                "old_lc_contact": old_ph,
                "new_media": new_media,
                "new_isp": new_isp.strip(),
                "new_lc_name": new_lc.strip(),
                "new_lc_contact": new_ph.strip(),
                "note": note.strip(),
            }
            fb_ok = False
            sh_ok = False
            sh_err = ""
            if firebase_ready():
                try:
                    upsert("last_mile_updates", q, payload)
                    hist_id = f"{q}_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}"
                    upsert("last_mile_history", hist_id, payload)
                    fb_ok = True
                except Exception as e:
                    st.error(f"Firebase save fail: {e}")
            else:
                st.error("Firebase secrets nahi mile — pehle secrets lagao.")
            try:
                append_last_mile_log([
                    _now(), q, bank, branch, state,
                    old_media, old_isp, old_partner, old_ckt, old_lc, old_ph,
                    new_media, new_isp.strip(), new_lc.strip(), new_ph.strip(), note.strip(),
                ])
                sh_ok = True
            except Exception as e:
                sh_err = str(e)
            if fb_ok:
                st.success("Firebase save ho gaya.")
            if sh_ok:
                st.success("Google Sheet tab **LastMile_Updates** mein nayi row add ho gayi.")
            elif sh_err:
                try:
                    mail = sa_email()
                except Exception:
                    mail = "(service account email secrets se)"
                st.warning(
                    "Sheet write fail. Is sheet ko service account ko **Editor** share karo:\n\n"
                    f"{mail}\n\n"
                    f"Sheet: https://docs.google.com/spreadsheets/d/{MASTER_ID}\n\n"
                    f"Error: {sh_err}"
                )

st.markdown("---")
st.subheader("Update history (Firebase)")
if firebase_ready():
    try:
        hist = list_all("last_mile_history")
        hdf = pd.DataFrame(hist) if hist else pd.DataFrame()
        if not hdf.empty:
            cols = [c for c in [
                "updated_at", "site_code", "old_isp", "new_isp", "old_media", "new_media",
                "old_lc_name", "new_lc_name", "old_lc_contact", "new_lc_contact", "note",
            ] if c in hdf.columns]
            st.dataframe(hdf[cols].sort_values(cols[0] if cols else hdf.columns[0], ascending=False), use_container_width=True, height=360)
            download_pack(
                "Last-mile history",
                hdf[cols] if cols else hdf,
                file_stem="last_mile_updates",
                title="Last Mile Updates",
                sheet_name="History",
                key="lm_hist_dl",
            )
        else:
            st.caption("Abhi koi update save nahi.")
    except Exception as e:
        st.info(f"History read: {e}")
else:
    st.caption("Firebase ready hone ke baad history yahan dikhegi.")
