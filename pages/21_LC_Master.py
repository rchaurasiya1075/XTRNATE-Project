import os
import sys
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.google_sheets import load_sheet_as_csv
from utils.firebase_store import firebase_ready, upsert
from utils.excel_export import excel_bytes
from utils.report_download import download_pack
from utils.sheet_write import (
    update_lc_excel, update_lc_excel_batch, test_sheet_write,
    phone_keys, unique_contact,
)

XTRANET = "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I"
MAIL_ID = "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I"
LC_GID = "401145054"
TARGET_GID = "658119379"
MAIL_GID = "762980214"

st.set_page_config(page_title="LC Master | XTRNATE", page_icon="📋", layout="wide")
ensure_ready()

st.title("LC Master")
st.caption(
    "Site code search → LC details. Same number 2 baar nahi. Naya number hi next column."
)

st.markdown("""
<style>
.lc-search input { font-size: 1.15rem !important; }
.lc-card { background:#0f172a;border:1px solid #38bdf8;border-radius:16px;padding:1.1rem 1.3rem;margin:0.6rem 0 1rem 0; }
.lc-k { color:#94a3b8;font-size:0.75rem;letter-spacing:.05em;text-transform:uppercase;margin-bottom:2px; }
.lc-v { color:#f8fafc;font-size:1.05rem;font-weight:700; }
</style>
""", unsafe_allow_html=True)

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
    return set(phone_keys(text))


def join_phones(*texts):
    seen, parts = set(), []
    for t in texts:
        for p in phone_keys(t):
            if p not in seen:
                seen.add(p)
                parts.append(p)
    return ", ".join(parts), seen


def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def map_col(df, dest, *names):
    c = _col(df, *names)
    df[dest] = df[c].map(clean) if c else ""
    return df


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
    df = map_col(df, "new_lc_name", "new lc name")
    df = map_col(df, "new_lc_phone", "new lc contact")
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
    df = map_col(df, "bank", "bank name")
    df = map_col(df, "branch", "branch name")
    df = map_col(df, "state", "state")
    df = map_col(df, "isp", "isp name", "isp")
    df = map_col(df, "ckt_id", "ckt id")
    df = map_col(df, "tgt_new_name", "new lc name")
    df = map_col(df, "tgt_new_phone", "new lc contact")
    return df


def apply_rows(rows, name_col, phone_col, src_label):
    items = []
    seen_sites = set()
    for _, r in rows.iterrows():
        site = clean(r["site_code"])
        name = clean(r.get(name_col)) or clean(r.get("lc_name"))
        phone = unique_contact(clean(r.get(phone_col)))
        if not site or not phone or site in seen_sites:
            continue
        seen_sites.add(site)
        items.append({
            "site": site,
            "name": name,
            "phone": phone,
            "handled_by": clean(r.get("handled_by")),
            "source": src_label,
            "old_name": clean(r.get("lc_name")),
            "old_phone": unique_contact(clean(r.get("lc_phone"))),
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
        return int(res.get("ok") or 0), []
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
        "phone": unique_contact(r["lc_phone"]),
        "handled_by": clean(r.get("handled_by")),
        "new_lc_name": clean(r.get("new_lc_name", "")),
        "new_lc_phone": unique_contact(r.get("new_lc_phone", "")),
        "digits": last10s(r["lc_phone"]),
    }
if not target.empty and "site_code" in target.columns:
    for _, r in target.iterrows():
        site = clean(r["site_code"])
        if not site:
            continue
        d = exist_map.setdefault(site, {
            "name": "", "phone": "", "handled_by": "",
            "new_lc_name": "", "new_lc_phone": "", "digits": set(),
        })
        extra = last10s(r.get("tgt_phone", ""))
        d["digits"] |= extra
        if not d["phone"] and clean(r.get("tgt_phone")):
            d["phone"] = unique_contact(r.get("tgt_phone"))
            d["name"] = d["name"] or clean(r.get("tgt_name"))
        d["bank"] = clean(r.get("bank"))
        d["branch"] = clean(r.get("branch"))
        d["state"] = clean(r.get("state"))
        d["isp"] = clean(r.get("isp"))
        d["ckt_id"] = clean(r.get("ckt_id"))
        if clean(r.get("tgt_new_phone")):
            d["new_lc_phone"] = unique_contact(r.get("tgt_new_phone"))
            d["new_lc_name"] = d.get("new_lc_name") or clean(r.get("tgt_new_name"))

mail_s = mail.copy() if not mail.empty else pd.DataFrame(columns=["site_code", "mail_name", "mail_phone"])
rows = []
all_sites = set(exist_map.keys())
if not mail_s.empty:
    all_sites |= set(mail_s["site_code"].tolist())
for site in sorted(all_sites):
    ex = exist_map.get(site, {
        "name": "", "phone": "", "handled_by": "",
        "new_lc_name": "", "new_lc_phone": "", "digits": set(),
    })
    mhit = mail_s[mail_s["site_code"] == site] if not mail_s.empty else mail_s
    mail_name = clean(mhit.iloc[0]["mail_name"]) if len(mhit) else ""
    mail_phone = unique_contact(mhit.iloc[0]["mail_phone"]) if len(mhit) else ""
    mail_d = last10s(mail_phone)
    old_d = ex["digits"]
    extra = mail_d - old_d
    if not mail_d and not old_d:
        status = "NO CONTACT"
    elif not mail_d:
        status = "LC ONLY (mail empty)"
    elif not old_d:
        status = "FIRST FILL (live only)"
    elif not extra:
        status = "SAME — skip"
    else:
        status = "NEW NUMBER"
    rows.append({
        "site_code": site,
        "lc_name": ex.get("name", ""),
        "lc_phone": ex.get("phone", ""),
        "handled_by": ex.get("handled_by", ""),
        "new_lc_name": ex.get("new_lc_name", ""),
        "new_lc_phone": ex.get("new_lc_phone", ""),
        "bank": ex.get("bank", ""),
        "branch": ex.get("branch", ""),
        "state": ex.get("state", ""),
        "isp": ex.get("isp", ""),
        "ckt_id": ex.get("ckt_id", ""),
        "mail_name": mail_name,
        "mail_phone": mail_phone,
        "status": status,
        "extra_phone": ", ".join(sorted(extra)) if extra else "",
    })
merged = pd.DataFrame(rows)

st.markdown("---")
st.subheader("🔍 Site code search — LC details")
sq = st.text_input(
    "Site code likho",
    placeholder="XTNFAT357",
    key="lc_lookup_box",
    label_visibility="collapsed",
).strip().upper()

if sq:
    hits = merged[merged["site_code"].astype(str).str.contains(sq, na=False)].copy()
    exact = hits[hits["site_code"] == sq]
    rest = hits[hits["site_code"] != sq]
    hits = pd.concat([exact, rest], ignore_index=True)
    if hits.empty:
        st.warning(f"`{sq}` ka LC data nahi mila.")
    else:
        for i, row in hits.head(12).iterrows():
            site = clean(row.get("site_code"))
            lc_name = clean(row.get("lc_name")) or "—"
            lc_phone = unique_contact(row.get("lc_phone")) or "—"
            new_ph = unique_contact(row.get("new_lc_phone") or row.get("extra_phone")) or "—"
            with st.container(border=True):
                st.markdown(f"#### {site}")
                a, b, c = st.columns(3)
                a.metric("LC Name", lc_name)
                b.metric("LC Number", lc_phone)
                c.metric("New LC Number", new_ph)
                d1, d2 = st.columns(2)
                with d1:
                    st.caption("Site code — copy")
                    st.code(site, language=None)
                    st.markdown(f"**Handled by:** {clean(row.get('handled_by')) or '—'}")
                    st.markdown(f"**Bank:** {clean(row.get('bank')) or '—'}")
                    st.markdown(f"**Branch:** {clean(row.get('branch')) or '—'}")
                with d2:
                    st.caption("LC number — copy")
                    st.code(lc_phone, language=None)
                    st.markdown(f"**State:** {clean(row.get('state')) or '—'}")
                    st.markdown(f"**ISP:** {clean(row.get('isp')) or '—'}")
                    st.markdown(f"**Ckt ID:** {clean(row.get('ckt_id')) or '—'}")
                st.markdown(
                    f"**Pending mail:** {clean(row.get('mail_name')) or '—'} / "
                    f"{unique_contact(row.get('mail_phone')) or '—'}"
                )
                st.caption(f"Status: {clean(row.get('status'))}")
        show = [c for c in [
            "site_code", "lc_name", "lc_phone", "new_lc_phone", "handled_by",
            "mail_name", "mail_phone", "extra_phone", "bank", "branch", "state", "isp", "ckt_id", "status",
        ] if c in hits.columns]
        st.dataframe(hits[show], use_container_width=True, hide_index=True)
else:
    st.info("Upar box mein site code likho — LC name, number, mail, bank/branch turant dikhega.")

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
new_only = merged[merged["status"] == "NEW NUMBER"].copy()
first_fill = merged[merged["status"].str.startswith("FIRST FILL")].copy()

k1, k2, k3, k4 = st.columns(4)
k1.metric("LC tab sites", len(old))
k2.metric("Pending-mail sites", len(mail))
k3.metric("New number → next col", len(new_only))
k4.metric("Already hai → skip", int((merged["status"] == "SAME — skip").sum()))

sig = (
    tuple(sorted(new_only["site_code"].tolist())),
    tuple(sorted(first_fill["site_code"].tolist()) if not first_fill.empty else ()),
    tuple(sorted(fill_df["site_code"].tolist()) if not fill_df.empty else ()),
)
if st.session_state.get("lc_auto_sig") != sig:
    with st.spinner("Batch Excel update (quota-safe)..."):
        ok_f, fail_f = (0, [])
        if not fill_df.empty:
            ok_f, fail_f = apply_rows(fill_df, "mail_name", "mail_phone", "lc_tab_fill")
        ok_1, fail_1 = (0, [])
        if not first_fill.empty:
            ok_1, fail_1 = apply_rows(first_fill, "mail_name", "mail_phone", "pending_mail_first")
        ok_n, fail_n = (0, [])
        if not new_only.empty:
            ok_n, fail_n = apply_rows(new_only, "mail_name", "mail_phone", "pending_mail_auto")
    st.session_state["lc_auto_sig"] = sig
    if ok_f:
        st.success(f"LC tab se {ok_f} sites live column fill (New LC empty).")
    if ok_1:
        st.success(f"Pehla number {ok_1} sites — live column only.")
    if ok_n:
        st.success(f"Naya number {ok_n} sites — live + New LC Contact.")
    fails = fail_f + fail_1 + fail_n
    if fails:
        st.error(fails[0])
    if ok_f or ok_1 or ok_n:
        load_old_lc.clear()
        load_target.clear()

st.subheader("Pending mail vs LC")
show_cols = [c for c in ["site_code", "lc_name", "lc_phone", "mail_name", "mail_phone", "extra_phone", "status"] if c in merged.columns]
st.dataframe(merged[show_cols].sort_values("status"), use_container_width=True, height=320)

st.markdown("---")
st.subheader("Manual LC update (site code)")
q = st.text_input("Site code", placeholder="XTNFAT357", key="lc_manual_site").strip().upper()
if q:
    hit = merged[merged["site_code"] == q]
    old_name = clean(hit.iloc[0]["lc_name"]) if len(hit) else ""
    old_ph = unique_contact(hit.iloc[0]["lc_phone"]) if len(hit) else ""
    mail_name = clean(hit.iloc[0]["mail_name"]) if len(hit) else ""
    mail_ph = unique_contact(hit.iloc[0]["mail_phone"]) if len(hit) else ""
    extra = ", ".join(k for k in phone_keys(mail_ph) if k not in last10s(old_ph))
    st.write(f"**LC tab:** {old_name} / {old_ph}")
    st.write(f"**Pending mail (unique):** {mail_name} / {mail_ph}")
    if extra:
        st.warning(f"Naya number (next column): {extra}")
        default_name, default_ph = mail_name or old_name, mail_ph or old_ph
    elif mail_ph and last10s(mail_ph) <= last10s(old_ph):
        st.info("Yahi number pehle se LC mein hai — skip. Duplicate nahi likhega.")
        default_name, default_ph = old_name, old_ph
    else:
        default_name, default_ph = mail_name or old_name, mail_ph or old_ph
    n1, n2 = st.columns(2)
    with n1:
        new_name = st.text_input("LC name", value=default_name)
    with n2:
        new_ph = st.text_input("LC contact number", value=default_ph)
    note = st.text_input("Note", value="")
    if st.button("Save manual (Excel + Firebase)"):
        new_ph_u = unique_contact(new_ph)
        if not new_name and not new_ph_u:
            st.warning("Name ya number dalo.")
        elif last10s(new_ph_u) and last10s(new_ph_u) <= last10s(old_ph) and clean(new_name) == clean(old_name):
            st.info("Same details — skip. Duplicate write nahi.")
        else:
            if firebase_ready():
                try:
                    upsert("site_lc", q, {
                        "site_code": q, "lc_name": new_name.strip(), "lc_number": new_ph_u,
                        "old_lc_name": old_name, "old_lc_number": old_ph, "note": note.strip(), "source": "manual",
                    })
                    st.success("Firebase save.")
                except Exception as e:
                    st.error(f"Firebase: {e}")
            try:
                how = update_lc_excel(q, new_name.strip(), new_ph_u, source="manual")
                st.success(f"Excel update: {how}")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

st.markdown("---")
st.subheader("LC tab (401145054) poori list")
st.dataframe(old[["site_code", "lc_name", "lc_phone", "handled_by"]], use_container_width=True, height=300)
download_pack(
    "LC tab",
    old[["site_code", "lc_name", "lc_phone", "handled_by"]] if set(["site_code", "lc_name", "lc_phone", "handled_by"]).issubset(old.columns) else old,
    file_stem="lc_tab",
    title="LC Master",
    sheet_name="LC_Tab",
    key="lc_tab_dl",
)
