import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from datetime import date, timedelta
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, show_last_update
from utils.data_processing import detect_category, get_summary_stats

st.set_page_config(page_title="ISP Comparison | XTRNATE", page_icon="⚖️", layout="wide")
show_last_update()

st.title("⚖️ ISP Report — HCIN / ONEOTT")
st.caption("Date range select karo • HCIN ya OTT click • Last remark se category • Count + % + graph + site list")
ensure_ready()

closed_df = st.session_state.get("closed_df")
open_df = st.session_state.get("open_df")
raw_df = st.session_state.get("raw_tickets_df")

if closed_df is None or closed_df.empty:
    if raw_df is not None and not raw_df.empty:
        closed_df = raw_df.copy()
    else:
        st.warning("Data nahi hai. Home pe sheet load karo.")
        st.stop()

work = closed_df.copy()
if "submitted_time" in work.columns:
    work["submitted_time"] = pd.to_datetime(work["submitted_time"], errors="coerce")
if "resolved_time" in work.columns:
    work["resolved_time"] = pd.to_datetime(work["resolved_time"], errors="coerce")

# Category ALWAYS from last remark / reason text
remark_src = work["reason"] if "reason" in work.columns else pd.Series("", index=work.index)
work["outage_class"] = remark_src.apply(detect_category)

partner = st.radio("ISP (sirf selected ka report)", ["HCIN", "ONEOTT"], horizontal=True)

min_d = work["submitted_time"].min() if "submitted_time" in work.columns else pd.NaT
max_d = work["submitted_time"].max() if "submitted_time" in work.columns else pd.NaT
today = date.today()
def_start = (today - timedelta(days=6))
def_end = today
if pd.notna(min_d):
    def_start = max(min_d.date(), today - timedelta(days=30))
if pd.notna(max_d):
    def_end = max_d.date()

c1, c2, c3 = st.columns(3)
with c1:
    start_day = st.date_input("Starting day", value=def_start)
with c2:
    end_day = st.date_input("End day", value=def_end)
with c3:
    date_on = st.selectbox("Date column", ["Submitted Time", "Resolved Time"])

if start_day > end_day:
    st.error("Starting day end day se pehle hona chahiye.")
    st.stop()

time_col = "submitted_time" if date_on == "Submitted Time" else "resolved_time"
if time_col not in work.columns:
    st.error(f"{date_on} column nahi mili.")
    st.stop()

start_ts = pd.Timestamp(start_day)
end_ts = pd.Timestamp(end_day) + pd.Timedelta(days=1)
period = work[work[time_col].notna() & (work[time_col] >= start_ts) & (work[time_col] < end_ts)].copy()

if "isp" in period.columns:
    view = period[period["isp"] == partner].copy()
else:
    view = period.copy()

# Also include owner text match (Celerity / HICOM)
if view.empty and "owner" in period.columns:
    own = period["owner"].astype(str).str.upper()
    if partner == "HCIN":
        view = period[own.str.contains("HCIN|HICOM", na=False)].copy()
    else:
        view = period[own.str.contains("ONEOTT|OTT|CELERITY", na=False)].copy()

open_view = pd.DataFrame()
if open_df is not None and not open_df.empty:
    ov = open_df.copy()
    if "isp" in ov.columns:
        open_view = ov[ov["isp"] == partner].copy()
    elif "owner" in ov.columns:
        own = ov["owner"].astype(str).str.upper()
        key = "HCIN|HICOM" if partner == "HCIN" else "ONEOTT|OTT|CELERITY"
        open_view = ov[own.str.contains(key, na=False)].copy()

st.markdown(
    f"### {partner} Report  •  {start_day.strftime('%d-%b-%Y')} se {end_day.strftime('%d-%b-%Y')}  "
    f"({date_on})"
)

if view.empty:
    st.info("Is date range / ISP pe closed ticket nahi mila.")
else:
    stats = get_summary_stats(view)
    total = len(view)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Tickets", total)
    k2.metric("Total DT (Hrs)", stats.get("total_downtime_hrs", 0))
    k3.metric("Avg Resolve (Hrs)", stats.get("avg_downtime_hrs", 0))
    k4.metric("Unique Sites", view["site_code"].nunique() if "site_code" in view.columns else 0)
    k5.metric("Open now", len(open_view))

    # ---- Classification count + % ----
    st.subheader("📊 Classification of Outage (Last Remark se)")
    cls = view["outage_class"].fillna("Others").astype(str).value_counts().reset_index()
    cls.columns = ["Outage Category", "Count"]
    cls["%"] = (cls["Count"] / cls["Count"].sum() * 100).round(1)
    cls.loc[len(cls)] = ["TOTAL", int(cls["Count"].sum()), 100.0]
    st.dataframe(cls, use_container_width=True, hide_index=True)

    chart = cls[cls["Outage Category"] != "TOTAL"]
    g1, g2 = st.columns(2)
    with g1:
        fig = px.bar(chart, x="Outage Category", y="Count", text="Count",
                     color="Count", color_continuous_scale="Blues")
        fig.update_layout(template="plotly_dark", height=380, xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig = px.pie(chart, names="Outage Category", values="Count", hole=0.35)
        fig.update_layout(template="plotly_dark", height=380)
        st.plotly_chart(fig, use_container_width=True)

    # ---- Daily count ----
    st.subheader("📅 Daily ticket count")
    daily = view.set_index(time_col).resample("D").size().reset_index()
    daily.columns = ["Date", "Count"]
    fig = px.bar(daily, x="Date", y="Count", text="Count", color="Count")
    fig.update_layout(template="plotly_dark", height=320)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(daily, use_container_width=True, hide_index=True)

    # ---- State ----
    if "state" in view.columns:
        st.subheader("🌍 State-wise count + %")
        stt = view["state"].fillna("Unknown").astype(str).value_counts().reset_index()
        stt.columns = ["State", "Count"]
        stt["%"] = (stt["Count"] / stt["Count"].sum() * 100).round(1)
        stt.loc[len(stt)] = ["TOTAL", int(stt["Count"].sum()), 100.0]
        st.dataframe(stt, use_container_width=True, hide_index=True)
        fig = px.bar(stt[stt["State"] != "TOTAL"], x="State", y="Count", text="Count", color="Count")
        fig.update_layout(template="plotly_dark", height=340, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    # ---- Site codes ----
    st.subheader("📍 Site codes (is period ke)")
    if "site_code" in view.columns:
        site = view.groupby("site_code").agg(
            tickets=("ticket_id", "count") if "ticket_id" in view.columns else ("site_code", "count"),
            state=("state", "first") if "state" in view.columns else ("site_code", "first"),
            last_remark=("reason", "last") if "reason" in view.columns else ("site_code", "first"),
            category=("outage_class", lambda s: ", ".join(sorted(set(s.astype(str))))),
        ).reset_index().sort_values("tickets", ascending=False)
        st.dataframe(site, use_container_width=True, height=360)
    else:
        site = pd.DataFrame()
        st.info("site_code missing")

    # ---- Ticket detail ----
    st.subheader("📋 Ticket-wise detail")
    show_cols = [c for c in [
        "ticket_id", "site_code", "state", "city", "submitted_time", "resolved_time",
        "status", "owner", "isp", "outage_class", "reason", "down_time_min"
    ] if c in view.columns]
    detail = view[show_cols].sort_values(time_col, ascending=False)
    st.dataframe(detail, use_container_width=True, height=420)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        pd.DataFrame({
            "Field": ["ISP", "From", "To", "Date on", "Tickets", "Open now"],
            "Value": [partner, str(start_day), str(end_day), date_on, total, len(open_view)],
        }).to_excel(w, index=False, sheet_name="Cover")
        cls.to_excel(w, index=False, sheet_name="Outage_Class")
        daily.to_excel(w, index=False, sheet_name="Daily")
        if "state" in view.columns:
            stt.to_excel(w, index=False, sheet_name="State")
        if not site.empty:
            site.to_excel(w, index=False, sheet_name="Sites")
        detail.to_excel(w, index=False, sheet_name="Tickets")
    st.download_button(
        f"📥 Download {partner} report Excel",
        data=buf.getvalue(),
        file_name=f"XTRNATE_{partner}_{start_day}_to_{end_day}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.markdown("---")
st.subheader("Current open (selected ISP)")
if open_view is None or open_view.empty:
    st.info("Is ISP pe current open nahi.")
else:
    oc = [c for c in ["ticket_id", "site_code", "status", "state", "submitted_time", "open_hours", "reason"] if c in open_view.columns]
    st.dataframe(open_view[oc], use_container_width=True, height=280)
