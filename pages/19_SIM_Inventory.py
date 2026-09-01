import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import show_last_update
from utils.google_sheets import load_sheet_as_csv

SHEET_ID = "1oWAJfe5ARZniQdScKArcH8DYqhamQXFC"
GID = "1796870727"

st.set_page_config(page_title="SIM Inventory | XTRNATE", page_icon="📱", layout="wide")
show_last_update()

st.title("📱 SIM Inventory")
st.caption("Site code search • SIM status / Telco / plan limit • IP, MDN, Asset, Remarks")


def uniquify_columns(df):
    seen = {}
    out = []
    for c in df.columns:
        k = str(c).strip()
        if k in seen:
            seen[k] += 1
            out.append(f"{k}_{seen[k]}")
        else:
            seen[k] = 0
            out.append(k)
    df = df.copy()
    df.columns = out
    return df


def pick_col(df, names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    for key, col in lower.items():
        for n in names:
            if n.lower() in key:
                return col
    return None


@st.cache_data(ttl=300)
def load_inventory():
    df = load_sheet_as_csv(SHEET_ID, gid=GID)
    return uniquify_columns(df)


up = st.file_uploader("Agar sheet private ho to Excel yahan upload karo", type=["xlsx", "xls", "csv"])
err = None
inv = None
if up is not None:
    try:
        if up.name.lower().endswith("csv"):
            inv = uniquify_columns(pd.read_csv(up))
        else:
            inv = uniquify_columns(pd.read_excel(up))
    except Exception as e:
        err = str(e)
else:
    try:
        inv = load_inventory()
    except Exception as e:
        err = str(e)

if inv is None or inv.empty:
    st.warning(
        "SIM sheet load nahi hui. Sheet ko **Anyone with the link can view** share karo, "
        "ya upar Excel upload karo.\n\n"
        f"Link: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={GID}"
    )
    if err:
        st.caption(f"Error: {err}")
    st.stop()

site_col = pick_col(inv, ["site code", "sitecode"]) or inv.columns[0]
inv["site_code"] = inv[site_col].astype(str).str.strip().str.upper()
inv = inv[inv["site_code"].notna() & ~inv["site_code"].isin(["", "NAN", "NONE", "SITE CODE"])]

colmap = {
    "ip": pick_col(inv, ["ip address", "ip"]),
    "asset": pick_col(inv, ["asset number", "asset"]),
    "mdn": pick_col(inv, ["mdn number", "mdn"]),
    "status": pick_col(inv, ["status"]),
    "customer": pick_col(inv, ["customer"]),
    "remarks": pick_col(inv, ["remarks", "remark"]),
    "category": pick_col(inv, ["site category", "category"]),
    "telco": pick_col(inv, ["telco"]),
    "apn": pick_col(inv, ["apn"]),
    "act_date": pick_col(inv, ["sim activation date", "activation"]),
    "limit_gb": pick_col(inv, ["data limit in gb", "data limit"]),
    "company": pick_col(inv, ["company"]),
}

def series(name):
    c = colmap.get(name)
    if c and c in inv.columns:
        return inv[c]
    return pd.Series([""] * len(inv), index=inv.index)

inv["status_n"] = series("status").astype(str).str.strip()
inv["telco_n"] = series("telco").astype(str).str.strip()
inv["company_n"] = series("company").astype(str).str.strip()
inv["cat_n"] = series("category").astype(str).str.strip()
inv["limit_n"] = pd.to_numeric(series("limit_gb"), errors="coerce")

st.markdown("### 🔍 Site / MDN / IP search")
q = st.text_input("Search", placeholder="XTNCHG364  ya  MDN  ya  IP  ya  Asset", label_visibility="collapsed")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st_status = st.multiselect("Status", sorted([x for x in inv["status_n"].dropna().unique() if x and x.lower() != "nan"]))
with c2:
    st_telco = st.multiselect("Telco", sorted([x for x in inv["telco_n"].dropna().unique() if x and x.lower() != "nan"]))
with c3:
    st_comp = st.multiselect("Company", sorted([x for x in inv["company_n"].dropna().unique() if x and x.lower() != "nan"]))
with c4:
    limits = sorted([x for x in inv["limit_n"].dropna().unique()])
    st_lim = st.multiselect("Data Limit GB", limits)

view = inv.copy()
if q:
    qq = q.strip().upper()
    mask = view["site_code"].str.contains(qq, na=False)
    for key in ("ip", "asset", "mdn"):
        c = colmap.get(key)
        if c:
            mask = mask | view[c].astype(str).str.upper().str.contains(qq, na=False)
    view = view[mask]
if st_status:
    view = view[view["status_n"].isin(st_status)]
if st_telco:
    view = view[view["telco_n"].isin(st_telco)]
if st_comp:
    view = view[view["company_n"].isin(st_comp)]
if st_lim:
    view = view[view["limit_n"].isin(st_lim)]

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("SIM / Sites", view["site_code"].nunique())
k2.metric("Commissioned", int(view["status_n"].str.lower().str.contains("commission", na=False).sum()))
k3.metric("Disconnected", int(view["status_n"].str.lower().str.contains("disconnect", na=False).sum()))
k4.metric("Jio", int(view["telco_n"].str.lower().str.contains("jio", na=False).sum()))
k5.metric("BSNL", int(view["telco_n"].str.lower().str.contains("bsnl", na=False).sum()))

g1, g2 = st.columns(2)
with g1:
    vc = view["status_n"].replace("", "Unknown").value_counts().reset_index()
    vc.columns = ["Status", "Count"]
    fig = px.pie(vc, names="Status", values="Count", title="Status", hole=0.4)
    fig.update_layout(template="plotly_dark", height=320)
    st.plotly_chart(fig, use_container_width=True)
with g2:
    tc = view["telco_n"].replace("", "Unknown").value_counts().reset_index()
    tc.columns = ["Telco", "Count"]
    fig = px.bar(tc, x="Telco", y="Count", title="Telco", color="Telco")
    fig.update_layout(template="plotly_dark", height=320)
    st.plotly_chart(fig, use_container_width=True)

if q and len(view) == 1:
    row = view.iloc[0]
    st.markdown("### Site card")
    a, b, c = st.columns(3)
    a.markdown(f"**Site Code:** `{row['site_code']}`")
    if colmap["ip"]:
        a.markdown(f"**IP:** `{row[colmap['ip']]}`")
    if colmap["mdn"]:
        b.markdown(f"**MDN:** `{row[colmap['mdn']]}`")
    if colmap["asset"]:
        b.markdown(f"**Asset:** `{row[colmap['asset']]}`")
    c.markdown(f"**Status:** {row['status_n']}")
    c.markdown(f"**Telco:** {row['telco_n']}  |  **Limit:** {row['limit_n']} GB")
    extra = []
    for label, key in [
        ("APN", "apn"), ("Company", "company"), ("Category", "category"),
        ("Customer", "customer"), ("Activation", "act_date"), ("Remarks", "remarks"),
    ]:
        cname = colmap.get(key)
        if cname:
            extra.append(f"**{label}:** {row[cname]}")
    st.markdown("  \n".join(extra))

st.subheader("All SIM details")
show_cols = ["site_code"] + [colmap[k] for k in [
    "ip", "asset", "mdn", "status", "customer", "remarks", "category",
    "telco", "apn", "act_date", "limit_gb", "company",
] if colmap.get(k)]
show_cols = list(dict.fromkeys([c for c in show_cols if c in view.columns]))
st.dataframe(view[show_cols], use_container_width=True, height=480)

buf = BytesIO()
view[show_cols].to_excel(buf, index=False)
st.download_button(
    "📥 Excel SIM Inventory (filtered)",
    data=buf.getvalue(),
    file_name="XTRNATE_SIM_Inventory.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
