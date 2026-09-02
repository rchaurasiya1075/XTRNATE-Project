import os
import re
import sys
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import show_last_update
from utils.google_sheets import load_sheet_as_csv
from utils.firebase_store import firebase_ready, upsert, get_one, list_all
from utils.sheet_write import update_lc_excel, sa_email

XTRANET = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
MAIL_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
LC_GID = "401145054"
TARGET_GID = "658119379"
MAIL_GID = "762980214"

st.set_page_config(page_title="LC Master | XTRNATE", page_icon="📋", layout="wide")
show_last_update()

st.title("LC Master")
st.caption(
    "Naya pending-mail number aate hi purana hata ke Excel mein automatic update + Prev columns"
)


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


def last10s(text):
    out = set()
    for part in re.split(r"[/,;|]", str(text or "")):
        d = "".join(ch for ch in part if ch.isdigit())
        if len(d) >= 10:
            out.add(d[-10:])
        elif len(d) >= 8:
            out.add(d)
    return out


def same_phone(a, b):
    aa, bb = last10s(a), last10s(b)
    if not aa or not bb:
        return False
    return bool(aa & bb)


def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


@st.cache_data(ttl=180, show_spinner=False)
def load_old_lc():
    df = load_sheet_as_csv(XTRANET, gid=LC_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughes site code", "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    df["lc_name"] = df[_col(df, "branch person name") or df.columns[2]].map(clean)
    df["lc_phone"] = df[_col(df, "contact number") or df.columns[3]].map(clean)
    hb = _col(df, "hndled by", "handled by")
    df["handled_by"] = df[hb].map(clean) if hb else ""
    df = df[df["site_code"].str.len() > 3]
    return df.drop_duplicates("site_code", keep="last")


@st.cache_data(ttl=120, show_spinner=False)
def load_pending_mail():
    url = f"https://docs.google.com/spreadsheets/d/{MAIL_ID}/export?format=csv&gid={MAIL_GID}"
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
    df["site_code"] = df[sc].astype(str).str.strip().str.upper() if sc else ""
    nm = _col(df, "branch person name")
    ph = _col(df, "branch person contact number", "contact number")
    df["mail_name"] = df[nm].map(clean) if nm else ""
    df["mail_phone"] = df[ph].map(clean) if ph else ""
    df = df[df["site_code"].str.len() > 3]
    return df.drop_duplicates("site_code", keep="first")


@st.cache_data(ttl=180, show_spinner=False)
def load_target():
    df = load_sheet_as_csv(XTRANET, gid=TARGET_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughessitecode", "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    return df


def apply_new(rows, src_label="auto"):
    ok, fail = 0, []
    for _, r in rows.iterrows():
        site = clean(r["site_code"])
        name = clean(r["mail_name"]) or clean(r.get("lc_name"))
        phone = clean(r["mail_phone"])
        if not site or not phone:
            continue
        try:
            update_lc_excel(site, name, phone, clean(r.get("handled_by")), source=src_label)
            if firebase_ready():
                upsert("site_lc", site, {
                    "site_code": site,
                    "lc_name": name,
                    "lc_number": phone,
                    "old_lc_name": clean(r.get("lc_name")),
                    "old_lc_number": clean(r.get("lc_phone")),
                    "source": src_label,
                })
            ok += 1
        except Exception as e:
            fail.append(f"{site}: {e}")
    return ok, fail


try:
    old = load_old_lc()
except Exception as e:
    st.error(f"Old LC sheet load fail: {e}")
    st.stop()
try:
    mail = load_pending_mail()
except Exception as e:
    st.warning(f"Pending mail load: {e}")
    mail = pd.DataFrame(columns=["site_code", "mail_name", "mail_phone"])
try:
    target = load_target()
except Exception:
    target = pd.DataFrame()

if st.button("Reload LC sheets"):
    load_old_lc.clear()
    load_pending_mail.clear()
    load_target.clear()
    st.session_state.pop("lc_auto_sig", None)
    st.rerun()

merged = old[["site_code", "lc_name", "lc_phone", "handled_by"]].copy()
mail_s = mail[["site_code", "mail_name", "mail_phone"]] if not mail.empty else pd.DataFrame(
    columns=["site_code", "mail_name", "mail_phone"]
)
merged = merged.merge(mail_s, on="site_code", how="outer")


def flag_row(r):
    o, n = clean(r.get("lc_phone")), clean(r.get("mail_phone"))
    if not n:
        return "NO MAIL CONTACT"
    if not o:
        return "NEW (old empty)"
    if same_phone(o, n):
        return "SAME — skip"
    return "NEW NUMBER"


merged["status"] = merged.apply(flag_row, axis=1)
new_only = merged[merged["status"].str.startswith("NEW")].copy()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Old LC sites", len(old))
k2.metric("Pending-mail sites", len(mail))
k3.metric("New number (auto)", len(new_only))
k4.metric("Same — skip", int((merged["status"] == "SAME — skip").sum()))

st.info(
    "Last mile data abhi nahi diya — jab doge tab New Last Mile columns fill honge. "
    "LC ke liye Excel pe Prev LC Name / Prev LC Contact / LC Updated At columns add hote hain."
)

sig = tuple(sorted(new_only["site_code"].astype(str).tolist())) if not new_only.empty else ()
if sig and st.session_state.get("lc_auto_sig") != sig:
    with st.spinner("Naye LC numbers Excel pe automatic update..."):
        ok, fail = apply_new(new_only, "pending_mail_auto")
    st.session_state["lc_auto_sig"] = sig
    if ok:
        st.success(f"Automatic: {ok} sites ka purana LC hata ke naya number Excel + Firebase pe save.")
        load_old_lc.clear()
        load_target.clear()
    if fail:
        st.error("\n".join(fail[:8]))
        try:
            st.warning(
                "Sheet write ke liye Editor share:\n"
                f"{sa_email()}\nhttps://docs.google.com/spreadsheets/d/{XTRANET}"
            )
        except Exception:
            pass

st.subheader("New LC from Pending Mail (old se alag)")
if new_only.empty:
    st.success("Koi naya number nahi — same contacts skip.")
else:
    st.dataframe(
        new_only[["site_code", "lc_name", "lc_phone", "mail_name", "mail_phone", "status"]],
        use_container_width=True,
        height=280,
    )

st.markdown("---")
st.subheader("Manual LC update (site code)")
q = st.text_input("Site code", placeholder="XTNFAT357").strip().upper()
if q:
    o = old[old["site_code"] == q]
    m = mail[mail["site_code"] == q] if not mail.empty else mail
    old_name = clean(o.iloc[0]["lc_name"]) if not o.empty else ""
    old_ph = clean(o.iloc[0]["lc_phone"]) if not o.empty else ""
    mail_name = clean(m.iloc[0]["mail_name"]) if not m.empty else ""
    mail_ph = clean(m.iloc[0]["mail_phone"]) if not m.empty else ""
    st.write(f"**Old LC:** {old_name} / {old_ph}")
    if mail_ph:
        if same_phone(old_ph, mail_ph):
            st.info(f"Pending mail same — skip: {mail_name} / {mail_ph}")
            default_name, default_ph = old_name, old_ph
        else:
            st.warning(f"Pending mail NEW: {mail_name} / {mail_ph}")
            default_name, default_ph = mail_name or old_name, mail_ph
    else:
        default_name, default_ph = old_name, old_ph

    fb = None
    if firebase_ready():
        try:
            fb = get_one("site_lc", q)
        except Exception:
            fb = None
    if fb:
        st.caption(f"Firebase last: {fb.get('lc_name')} {fb.get('lc_number')} ({fb.get('updated_at')})")

    n1, n2 = st.columns(2)
    with n1:
        new_name = st.text_input("LC name", value=default_name)
    with n2:
        new_ph = st.text_input("LC contact number", value=default_ph)
    note = st.text_input("Note", value="")
    if st.button("Save manual (Excel + Firebase)"):
        if not new_name and not new_ph:
            st.warning("Name ya number dalo.")
        else:
            if firebase_ready():
                try:
                    upsert("site_lc", q, {
                        "site_code": q,
                        "lc_name": new_name.strip(),
                        "lc_number": new_ph.strip(),
                        "old_lc_name": old_name,
                        "old_lc_number": old_ph,
                        "note": note.strip(),
                        "source": "manual",
                    })
                    st.success("Firebase save.")
                except Exception as e:
                    st.error(f"Firebase: {e}")
            try:
                how = update_lc_excel(q, new_name.strip(), new_ph.strip(), source="manual")
                st.success(f"Excel: target {how['target']} • LC tab {how['source']} • Prev columns fill")
            except Exception as e:
                try:
                    mail_sa = sa_email()
                except Exception:
                    mail_sa = "(service account)"
                st.warning(
                    f"Sheet write fail. Editor share: {mail_sa}\n"
                    f"https://docs.google.com/spreadsheets/d/{XTRANET}\n{e}"
                )

st.markdown("---")
st.subheader("All LC (sheet)")
st.dataframe(old[["site_code", "lc_name", "lc_phone", "handled_by"]], use_container_width=True, height=320)
buf = BytesIO()
old.to_excel(buf, index=False)
st.download_button("Excel old LC", data=buf.getvalue(), file_name="lc_old.xlsx")

if firebase_ready():
    try:
        saved = list_all("site_lc")
        if saved:
            st.subheader("Firebase LC saves")
            sdf = pd.DataFrame(saved)
            cols = [c for c in [
                "site_code", "lc_name", "lc_number", "old_lc_name", "old_lc_number", "source", "updated_at"
            ] if c in sdf.columns]
            st.dataframe(sdf[cols] if cols else sdf, use_container_width=True, height=240)
    except Exception:
        pass
