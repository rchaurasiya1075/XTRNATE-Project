import os
import sys
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, apply_isp_filter, isp_label
from utils.data_processing import detect_category, get_summary_stats, isp_options, classify_isp
from utils.meeting_deck import build_meeting_pptx
from utils.remark_tags import apply_tags, dt_hrs

st.set_page_config(page_title="Conclusion | XTRNATE", page_icon="🧠", layout="wide")
ensure_ready()

st.title("🧠 Conclusion Dashboard")
st.caption("Meeting report • saare ISP (Owner) • Last remark tags • Outage click → site details • 15-slide PPT")

closed = st.session_state.get("closed_df")
opened = st.session_state.get("open_df")
raw = st.session_state.get("raw_tickets_df")
if closed is None or closed.empty:
    closed = raw if raw is not None else pd.DataFrame()
if closed is None or closed.empty:
    st.warning("Data nahi hai. Home pe load karo.")
    st.stop()

work = closed.copy()
for c in ("submitted_time", "resolved_time"):
    if c in work.columns:
        work[c] = pd.to_datetime(work[c], errors="coerce")
work["outage_class"] = (work["reason"] if "reason" in work.columns else pd.Series("", index=work.index)).apply(detect_category)
if "category" in work.columns:
    blank = work["outage_class"].isin(["Others", ""])
    work.loc[blank, "outage_class"] = work.loc[blank, "category"].astype(str)
work = apply_tags(work)

partner = isp_label()
today = date.today()
c1, c2 = st.columns(2)
with c1:
    start_day = st.date_input("From", value=today - timedelta(days=29))
with c2:
    end_day = st.date_input("To", value=today)

def isp_filter(df):
    return apply_isp_filter(df)

hist = isp_filter(work)
start_ts, end_ts = pd.Timestamp(start_day), pd.Timestamp(end_day) + pd.Timedelta(days=1)
time_col = "submitted_time" if "submitted_time" in hist.columns else None
if time_col:
    view = hist[hist[time_col].notna() & (hist[time_col] >= start_ts) & (hist[time_col] < end_ts)].copy()
else:
    view = hist.copy()

open_view = isp_filter(opened) if opened is not None else pd.DataFrame()

if view.empty:
    st.info("Is range / ISP pe ticket nahi.")
    st.stop()

view["dt_hrs"] = view.apply(dt_hrs, axis=1)
stats = get_summary_stats(view)
total = len(view)
sites_n = view["site_code"].nunique() if "site_code" in view.columns else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Tickets", total)
k2.metric("Sites", sites_n)
k3.metric("DT Hrs", stats.get("total_downtime_hrs", 0))
k4.metric("Avg Hrs", stats.get("avg_downtime_hrs", 0))
k5.metric("Open now", len(open_view))

cls = view["outage_class"].fillna("Others").astype(str).value_counts().reset_index()
cls.columns = ["Outage Category", "Count"]
cls["%"] = (cls["Count"] / cls["Count"].sum() * 100).round(1)
tags = view["remark_tag"].value_counts().reset_index()
tags.columns = ["Tag", "Count"]
tags["%"] = (tags["Count"] / tags["Count"].sum() * 100).round(1)

st.subheader("Outage reason — click karke sites")
pick = st.selectbox("Category", ["All"] + cls["Outage Category"].tolist())
shown = view if pick == "All" else view[view["outage_class"] == pick]
left, right = st.columns([1, 2])
with left:
    st.dataframe(cls, hide_index=True, use_container_width=True, height=320)
    fig = px.pie(cls, names="Outage Category", values="Count", hole=0.35)
    fig.update_layout(template="plotly_dark", height=280)
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown(f"**{pick}** — {len(shown)} tickets")
    cols = [c for c in ["ticket_id", "site_code", "state", "city", "submitted_time", "resolved_time", "dt_hrs", "outage_class", "remark_tag", "reason"] if c in shown.columns]
    st.dataframe(shown[cols].sort_values("submitted_time", ascending=False) if "submitted_time" in shown.columns else shown[cols], use_container_width=True, height=520)

st.subheader("Remark micro-tags (vendor / migration / feasibility / ISP change)")
st.dataframe(tags, hide_index=True, use_container_width=True)
tag_pick = st.selectbox("Tag drill-down", ["All"] + tags["Tag"].tolist())
tag_df = view if tag_pick == "All" else view[view["remark_tag"] == tag_pick]
st.dataframe(tag_df[cols] if cols else tag_df, use_container_width=True, height=280)

# repeats
rep_sum = pd.DataFrame()
if "site_code" in view.columns and time_col:
    look3 = end_ts - pd.DateOffset(months=3)
    look6 = end_ts - pd.DateOffset(months=6)
    period_sites = view["site_code"].dropna().astype(str).str.upper().unique().tolist()
    h = hist[hist["site_code"].astype(str).str.upper().isin(period_sites)]
    rows = []
    for sc in period_sites:
        s3 = h[(h["site_code"].astype(str).str.upper() == sc) & (h[time_col] >= look3) & (h[time_col] < end_ts)]
        s6 = h[(h["site_code"].astype(str).str.upper() == sc) & (h[time_col] >= look6) & (h[time_col] < end_ts)]
        pn = view[view["site_code"].astype(str).str.upper() == sc]
        hrs6 = [dt_hrs(r) for _, r in s6.iterrows()]
        hrs6 = [x for x in hrs6 if x is not None]
        rows.append({
            "Site": sc,
            "Period downs": len(pn),
            "3M": len(s3),
            "6M": len(s6),
            "6M DT Hrs": round(sum(hrs6), 2) if hrs6 else 0,
            "Reasons": ", ".join(sorted(set(s6["outage_class"].dropna().astype(str))))[:80] if "outage_class" in s6.columns else "",
        })
    rep_sum = pd.DataFrame(rows).sort_values("6M", ascending=False)
    st.subheader("Repeat 3M / 6M")
    st.dataframe(rep_sum, use_container_width=True, height=320)

state_df = pd.DataFrame()
if "state" in view.columns:
    state_df = view["state"].fillna("?").astype(str).value_counts().reset_index()
    state_df.columns = ["State", "Count"]
    state_df["%"] = (state_df["Count"] / state_df["Count"].sum() * 100).round(1)

site_tbl = pd.DataFrame()
if "site_code" in view.columns:
    site_tbl = view.groupby("site_code").agg(
        tickets=("ticket_id", "count") if "ticket_id" in view.columns else ("site_code", "count"),
        dt_hrs=("dt_hrs", "sum"),
        reasons=("outage_class", lambda s: ", ".join(sorted(set(s.astype(str)))[:4])),
    ).reset_index().sort_values("dt_hrs", ascending=False)

# SLA bands
def band(h):
    if pd.isna(h):
        return "Unknown"
    if h < 2:
        return "<2h"
    if h < 8:
        return "2-8h"
    if h < 24:
        return "8-24h"
    if h < 48:
        return "24-48h"
    return ">48h"
view["sla"] = view["dt_hrs"].apply(band)
sla = view["sla"].value_counts().reindex(["<2h", "2-8h", "8-24h", "24-48h", ">48h", "Unknown"], fill_value=0).reset_index()
sla.columns = ["Band", "Count"]
sla["%"] = (sla["Count"] / max(sla["Count"].sum(), 1) * 100).round(1)

st.subheader("Resolution bands")
st.dataframe(sla, hide_index=True, use_container_width=True)

# narrative
top_cls = cls.iloc[0]["Outage Category"] if not cls.empty else "-"
rep2 = int((rep_sum["3M"] >= 2).sum()) if not rep_sum.empty else 0
rep3 = int((rep_sum["6M"] >= 3).sum()) if not rep_sum.empty else 0
vendor_n = int((view["remark_tag"] == "Vendor Change").sum())
mig_n = int((view["remark_tag"] == "Migration").sum())
isp_n = int((view["remark_tag"] == "ISP Change").sum())
feas_n = int((view["remark_tag"] == "Feasibility").sum())
fib_n = int((view["remark_tag"] == "Fibre Cut").sum())

goods = (
    f"• {total} tickets closed/logged in selected window across {sites_n} sites.\n"
    f"• Average resolution ~ {stats.get('avg_downtime_hrs', 0)} hrs.\n"
    f"• Same-day / <8h share visible in resolution bands (see deck).\n"
    f"• Partner has active last-remark trail on MARS for most cases."
)
gaps = (
    f"• Dominant outage: {top_cls}.\n"
    f"• Repeat pressure: {rep2} sites 2+ times in 3M; {rep3} sites 3+ in 6M.\n"
    f"• Fibre cut tagged: {fib_n} | Vendor change: {vendor_n} | Migration: {mig_n} | ISP change: {isp_n} | Feasibility: {feas_n}.\n"
    f"• Open now: {len(open_view)} — ageing cases need revised ETR on MARS."
)
focus = (
    f"1. Repeat sites (6M ≥ 3) — joint walkdown + last-mile hardening.\n"
    f"2. {top_cls} cluster — root-cause pack with photos / OTDR / POP logs.\n"
    f"3. Vendor / ISP change & migration tickets — freeze calendar, no silent cutover.\n"
    f"4. Feasibility pending — 7-day closure or official drop.\n"
    f"5. Open ≥ 8 hrs — daily huddle till ETR met."
)
ask = (
    f"• Written action plan on top repeat sites within 48 hrs.\n"
    f"• Fibre / backend prevention tracker weekly.\n"
    f"• All vendor-change / migration cases with customer NOC named owner."
)

st.markdown("### Meeting conclusion")
st.markdown("**Working**")
st.write(goods)
st.markdown("**Gaps / focus**")
st.write(gaps)

def tbl3(df, a, b, c):
    data = [[a, b, c]]
    if df is None or df.empty:
        return data
    for _, r in df.head(14).iterrows():
        data.append([str(r.iloc[0])[:48], str(r.iloc[1]), str(r.iloc[2])])
    return data

class_table = tbl3(cls, "Category", "Count", "%")
tag_table = tbl3(tags, "Tag", "Count", "%")
state_table = tbl3(state_df, "State", "Count", "%") if not state_df.empty else [["State", "Count", "%"]]
sla_table = tbl3(sla, "Band", "Count", "%")

rep_table = [["Site", "Period", "3M", "6M", "6M DT Hrs"]]
if not rep_sum.empty:
    for _, r in rep_sum.head(12).iterrows():
        rep_table.append([str(r["Site"]), str(r["Period downs"]), str(r["3M"]), str(r["6M"]), str(r["6M DT Hrs"])])

site_table = [["Site", "Tickets", "DT Hrs", "Reasons"]]
if not site_tbl.empty:
    for _, r in site_tbl.head(12).iterrows():
        site_table.append([str(r["site_code"]), str(r["tickets"]), str(round(float(r["dt_hrs"] or 0), 1)), str(r["reasons"])[:40]])

open_table = [["Ticket", "Site", "Status", "State", "Hrs"]]
if open_view is not None and not open_view.empty:
    ov = open_view.copy()
    for _, r in ov.head(10).iterrows():
        open_table.append([
            str(r.get("ticket_id", ""))[:18],
            str(r.get("site_code", "")),
            str(r.get("status", ""))[:16],
            str(r.get("state", "")),
            str(r.get("open_hours", "")),
        ])

chg = view[view["remark_tag"].isin(["Vendor Change", "ISP Change", "Migration", "Feasibility"])]
chg_table = [["Type", "Tickets", "Sites"]]
for t in ["Vendor Change", "ISP Change", "Migration", "Feasibility"]:
    part = view[view["remark_tag"] == t]
    chg_table.append([t, str(len(part)), str(part["site_code"].nunique() if "site_code" in part.columns else 0)])

pack = {
    "isp": partner,
    "range": f"{start_day.strftime('%d %b %Y')}  →  {end_day.strftime('%d %b %Y')}",
    "kpis": [
        ("TICKETS", total),
        ("SITES", sites_n),
        ("DT HRS", stats.get("total_downtime_hrs", 0)),
        ("AVG HRS", stats.get("avg_downtime_hrs", 0)),
        ("OPEN", len(open_view)),
    ],
    "snapshot_note": f"Top outage {top_cls}. Repeat 3M (2+): {rep2} sites. Fibre/vendor/migration tags in remark analysis.",
    "goods": goods,
    "gaps": gaps,
    "focus": focus,
    "ask": ask,
    "class_table": class_table,
    "tag_table": tag_table,
    "state_table": state_table,
    "repeat_table": rep_table,
    "site_table": site_table,
    "sla_table": sla_table,
    "open_note": f"{len(open_view)} open tickets on {partner}. Ageing first.",
    "open_table": open_table,
    "change_table": chg_table,
}

xl = BytesIO()
with pd.ExcelWriter(xl, engine="xlsxwriter") as w:
    cls.to_excel(w, index=False, sheet_name="Outage")
    tags.to_excel(w, index=False, sheet_name="RemarkTags")
    if not rep_sum.empty:
        rep_sum.to_excel(w, index=False, sheet_name="Repeat")
    if not site_tbl.empty:
        site_tbl.to_excel(w, index=False, sheet_name="Sites")
    shown[cols].to_excel(w, index=False, sheet_name="Drill")
    view[cols].to_excel(w, index=False, sheet_name="AllTickets")

d1, d2 = st.columns(2)
with d1:
    st.download_button(
        f"📥 Excel — {partner} conclusion",
        data=xl.getvalue(),
        file_name=f"XTRNATE_Conclusion_{partner}_{start_day}_{end_day}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with d2:
    try:
        ppt = build_meeting_pptx(pack)
        st.download_button(
            f"📚 15-slide PPT — {partner} meeting",
            data=ppt,
            file_name=f"XTRNATE_{partner}_Meeting_{start_day}_{end_day}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"PPT: {e}")
