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
from utils.sheet_write import update_lc_excel, update_lc_excel_batch, sa_email, test_sheet_write

XTRANET = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
MAIL_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
LC_GID = "401145054"
TARGET_GID = "658119379"
MAIL_GID = "762980214"

st.set_page_config(page_title="LC Master | XTRNATE", page_icon="📋", layout="wide")
show_last_update()

st.title("LC Master")
st.caption(
    "Poori sheet padhke: LC tab (401145054) → pending-mail dono contact columns match. "
    "Number pehle se hai to skip, naya hai to automatic update. Manual bhi hai."
)

if st.button("Test Google Sheet write"):
    res = test_sheet_write()
    if res.get("ok"):
        st.success(f"Sheet write OK — {res.get('title')} • LC_Updates TEST row")
        st.write(res.get("tabs"))
    else:
        st.error(res.get("error") or "unknown error")
        st.markdown(
            f"Share Editor: `{res.get('email') or 'firebase-adminsdk-fbsvc@xtranet-d7dca.iam.gserviceaccount.com'}`"
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
    for part in re.split(r"[/,;|\n]", str(text or "")):
        d = "".join(ch for ch in part if ch.isdigit())
        if len(d) >= 10:
            out.add(d[-10:])
        elif len(d) >= 8:
            out.add(d)
    return out


def join_phones(*texts):
    seen, parts = set(), []
    for t in texts:
        for p in last10s(t):
            if p not in seen:
                seen.add(p)
                parts.append(p)
    return " / ".join(parts), seen


def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


@st.cache_data(ttl=120, show_spinner=False)
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


@st.cache_data(ttl=90, show_spinner=False)
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
    df["mail_name"] = df[nm].map(clean) if nm else ""
    phone_cols = [
        c for c in df.columns
        if str(c).strip().lower() in {
            "branch person contact number",
            "alternate number",
            "contact number",
            "contact number_1",
        }
        or str(c).strip().lower().startswith("contact number")
    ]
    df["mail_phone"] = df.apply(
        lambda r: join_phones(*[r.get(c, "") for c in phone_cols])[0],
        axis=1,
    )
    df = df[df["site_code"].str.len() > 3]
    rows = []
    for site, g in df.groupby("site_code", dropna=True):
        names = [clean(x) for x in g["mail_name"].tolist() if clean(x)]
        phones, _ = join_phones(*g["mail_phone"].tolist())
        rows.append({
            "site_code": site,
            "mail_name": names[0] if names else "",
            "mail_phone": phones,
            "mail_rows": len(g),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=180, show_spinner=False)
def load_target():
    df = load_sheet_as_csv(XTRANET, gid=TARGET_GID)
    df.columns = [str(c).strip() for c in df.columns]
    sc = _col(df, "hughessitecode", "site code") or df.columns[1]
    df["site_code"] = df[sc].astype(str).str.strip().str.upper()
    nm = _col(df, "branch person name")
    ph = _col(df, "branch person contact number", "contact number")
    df["tgt_name"] = df[nm].map(clean) if nm else ""
    df["tgt_phone"] = df[ph].map(clean) if ph else ""
    return df


def apply_rows(rows, name_col, phone_col, src_label):
    items = []
    for _, r in rows.iterrows():
        site = clean(r["site_code"])
        name = clean(r.get(name_col)) or clean(r.get("lc_name"))
        phone = clean(r.get(phone_col))
        if not site or not phone:
            continue
        items.append({
            "site": site,
            "name": name,
            "phone": phone,
            "handled_by": clean(r.get("handled_by")),
            "source": src_label,
            "old_name": clean(r.get("lc_name")),
            "old_phone": clean(r.get("lc_phone")),
        })
    if not items:
        return 0, []
    try:
        res = update_lc_excel_batch(items, source=src_label)
        if firebase_ready():
            for it in items:
                try:
                    upsert("site_lc", it["site"], {
                        "site_code": it["site"],
                        "lc_name": it["name"],
                        "lc_number": it["phone"],
                        "old_lc_name": it["old_name"],
                        "old_lc_number": it["old_phone"],
                        "source": src_label,
                    })
                except Exception:
                    pass
        return int(res.get("ok") or len(items)), []
    except Exception as e:
        return 0, [f"{type(e).__name__}: {e}"]


try:
    old = load_old_lc()
except Exception as e:
    st.error(f"LC tab load fail: {e}")
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

if st.button("Reload + auto (poori sheet dubara padho)"):
    load_old_lc.clear()
    load_pending_mail.clear()
    load_target.clear()
    st.session_state.pop("lc_auto_sig", None)
    st.rerun()

exist_map = {}
for _, r in old.iterrows():
    exist_map[r["site_code"]] = {
        "name": clean(r["lc_name"]),
        "phone": clean(r["lc_phone"]),
        "handled_by": clean(r.get("handled_by")),
        "digits": last10s(r["lc_phone"]),
    }
if not target.empty and "site_code" in target.columns:
    for _, r in target.iterrows():
        site = clean(r["site_code"])
        if not site:
            continue
        d = exist_map.setdefault(site, {"name": "", "phone": "", "handled_by": "", "digits": set()})
        extra = last10s(r.get("tgt_phone", ""))
        d["digits"] |= extra
        if not d["phone"] and clean(r.get("tgt_phone")):
            d["phone"] = clean(r.get("tgt_phone"))
            d["name"] = d["name"] or clean(r.get("tgt_name"))

mail_s = mail.copy() if not mail.empty else pd.DataFrame(columns=["site_code", "mail_name", "mail_phone"])
rows = []
all_sites = set(exist_map.keys())
if not mail_s.empty:
    all_sites |= set(mail_s["site_code"].tolist())
for site in sorted(all_sites):
    ex = exist_map.get(site, {"name": "", "phone": "", "handled_by": "", "digits": set()})
    mhit = mail_s[mail_s["site_code"] == site] if not mail_s.empty else mail_s
    mail_name = clean(mhit.iloc[0]["mail_name"]) if len(mhit) else ""
    mail_phone = clean(mhit.iloc[0]["mail_phone"]) if len(mhit) else ""
    mail_d = last10s(mail_phone)
    old_d = ex["digits"]
    if not mail_d and not old_d:
        status = "NO CONTACT"
    elif not mail_d:
        status = "LC ONLY (mail empty)"
    elif not old_d:
        status = "NEW (LC empty)"
    elif mail_d <= old_d:
        status = "SAME — skip"
    else:
        status = "NEW NUMBER"
    rows.append({
        "site_code": site,
        "lc_name": ex["name"],
        "lc_phone": ex["phone"],
        "handled_by": ex.get("handled_by", ""),
        "mail_name": mail_name,
        "mail_phone": mail_phone,
        "status": status,
    })
merged = pd.DataFrame(rows)

need_fill = []
if not target.empty:
    tgt_empty = set()
    for _, r in target.iterrows():
        if not last10s(r.get("tgt_phone", "")):
            tgt_empty.add(clean(r["site_code"]))
    tset = set(target["site_code"])
    for site, ex in exist_map.items():
        if ex["digits"] and (site in tgt_empty or site not in tset):
            need_fill.append({
                "site_code": site,
                "lc_name": ex["name"],
                "lc_phone": ex["phone"],
                "mail_name": ex["name"],
                "mail_phone": ex["phone"],
                "handled_by": ex.get("handled_by", ""),
            })
fill_df = pd.DataFrame(need_fill).drop_duplicates("site_code") if need_fill else pd.DataFrame()
new_only = merged[merged["status"].str.startswith("NEW")].copy()

k1, k2, k3, k4 = st.columns(4)
k1.metric("LC tab sites", len(old))
k2.metric("Pending-mail sites", len(mail))
k3.metric("New number → update", len(new_only))
k4.metric("Already hai → skip", int((merged["status"] == "SAME — skip").sum()))

sig = (
    tuple(sorted(new_only["site_code"].tolist())),
    tuple(sorted(fill_df["site_code"].tolist()) if not fill_df.empty else ()),
)
if st.session_state.get("lc_auto_sig") != sig:
    with st.spinner("Batch Excel update (quota-safe)..."):
        ok_f, fail_f = (0, [])
        if not fill_df.empty:
            ok_f, fail_f = apply_rows(fill_df, "mail_name", "mail_phone", "lc_tab_fill")
        ok_n, fail_n = (0, [])
        if not new_only.empty:
            ok_n, fail_n = apply_rows(new_only, "mail_name", "mail_phone", "pending_mail_auto")
    st.session_state["lc_auto_sig"] = sig
    if ok_f:
        st.success(f"LC tab se {ok_f} sites fill.")
    if ok_n:
        st.success(f"Pending mail se {ok_n} NEW numbers update.")
    fails = fail_f + fail_n
    if fails:
        st.error(fails[0])
    if ok_f or ok_n:
        load_old_lc.clear()
        load_target.clear()

st.subheader("Pending mail vs LC (dono contact columns)")
show_cols = [c for c in ["site_code", "lc_name", "lc_phone", "mail_name", "mail_phone", "status"] if c in merged.columns]
st.dataframe(merged[show_cols].sort_values("status"), use_container_width=True, height=320)

st.markdown("---")
st.subheader("Manual LC update (site code)")
q = st.text_input("Site code", placeholder="XTNFAT357").strip().upper()
if q:
    hit = merged[merged["site_code"] == q]
    old_name = clean(hit.iloc[0]["lc_name"]) if len(hit) else ""
    old_ph = clean(hit.iloc[0]["lc_phone"]) if len(hit) else ""
    mail_name = clean(hit.iloc[0]["mail_name"]) if len(hit) else ""
    mail_ph = clean(hit.iloc[0]["mail_phone"]) if len(hit) else ""
    st.write(f"**LC tab:** {old_name} / {old_ph}")
    st.write(f"**Pending mail (dono columns merge):** {mail_name} / {mail_ph}")
    if mail_ph and last10s(mail_ph) and last10s(mail_ph) <= last10s(old_ph):
        st.info("Yahi number pehle se LC mein hai — auto skip.")
        default_name, default_ph = old_name, old_ph
    elif mail_ph:
        st.warning("Mail pe extra/naya number hai.")
        default_name, default_ph = mail_name or old_name, mail_ph or old_ph
    else:
        default_name, default_ph = old_name, old_ph
    n1, n2 = st.columns(2)
    with n1:
        new_name = st.text_input("LC name", value=default_name)
    with n2:
        new_ph = st.text_input("LC contact number", value=default_ph)
    note = st.text_input("Note", value="")
    if st.button("Save manual (Excel + Firebase)"):
        if not new_name and not new_ph:
            st.warning("Name ya number dalo.")
        elif last10s(new_ph) and last10s(new_ph) <= last10s(old_ph) and clean(new_name) == clean(old_name):
            st.info("Same details — skip.")
        else:
            if firebase_ready():
                try:
                    upsert("site_lc", q, {
                        "site_code": q, "lc_name": new_name.strip(), "lc_number": new_ph.strip(),
                        "old_lc_name": old_name, "old_lc_number": old_ph, "note": note.strip(), "source": "manual",
                    })
                    st.success("Firebase save.")
                except Exception as e:
                    st.error(f"Firebase: {e}")
            try:
                how = update_lc_excel(q, new_name.strip(), new_ph.strip(), source="manual")
                st.success(f"Excel update: {how}")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

st.markdown("---")
st.subheader("LC tab (401145054) poori list")
st.dataframe(old[["site_code", "lc_name", "lc_phone", "handled_by"]], use_container_width=True, height=300)
buf = BytesIO()
old.to_excel(buf, index=False)
st.download_button("Excel LC tab", data=buf.getvalue(), file_name="lc_tab.xlsx")
