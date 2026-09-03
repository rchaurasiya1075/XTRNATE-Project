import os
import sys
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, show_last_update
from utils.holiday_sla import PUBLIC, adjust_ticket, parse_extra_dates
from utils.data_processing import isp_options, classify_isp

st.set_page_config(page_title="Holiday Downtime | XTRNATE", page_icon="🎉", layout="wide")
show_last_update()
ensure_ready()

st.title("🎉 Holiday Adjusted Downtime")
st.caption(
    "Sunday + 2nd/4th Saturday + national/festival holiday ko Submitted→Resolved window se minus. "
    "Down Time column minutes mein consider."
)

closed = st.session_state.get("closed_df")
raw = st.session_state.get("raw_tickets_df")
if closed is None or closed.empty:
    closed = raw if raw is not None else pd.DataFrame()
if closed is None or closed.empty:
    st.warning("Data nahi hai. Home pe sheet load karo.")
    st.stop()

work = closed.copy()
for c in ("submitted_time", "resolved_time"):
    if c in work.columns:
        work[c] = pd.to_datetime(work[c], errors="coerce")
if "isp" not in work.columns and "owner" in work.columns:
    work["isp"] = work["owner"].map(classify_isp)

opts = isp_options(work)
partner = st.radio("ISP", opts or ["ALL"], horizontal=True)
today = date.today()
c1, c2 = st.columns(2)
with c1:
    start_day = st.date_input("From", value=today - timedelta(days=29))
with c2:
    end_day = st.date_input("To", value=today)

extra_txt = st.text_area(
    "Extra holidays (optional) — ek line: YYYY-MM-DD Name",
    placeholder="2026-10-24 State Holiday",
    height=80,
)
extra = parse_extra_dates(extra_txt)

if partner != "ALL" and "isp" in work.columns:
    view = work[work["isp"] == partner].copy()
else:
    view = work.copy()

if "submitted_time" in view.columns:
    start_ts = pd.Timestamp(start_day)
    end_ts = pd.Timestamp(end_day) + pd.Timedelta(days=1)
    view = view[view["submitted_time"].notna() & (view["submitted_time"] >= start_ts) & (view["submitted_time"] < end_ts)]

if view.empty:
    st.info("Is range mein ticket nahi.")
    st.stop()

rows = []
for _, r in view.iterrows():
    adj = adjust_ticket(r.get("submitted_time"), r.get("resolved_time"), r.get("down_time_min"), extra)
    rows.append({
        "Incident ID": r.get("ticket_id", ""),
        "Site Code": r.get("site_code", ""),
        "ISP": r.get("isp", r.get("owner", "")),
        "State": r.get("state", ""),
        "Submitted Time": r.get("submitted_time"),
        "Resolved Time": r.get("resolved_time"),
        "Reported DT (min)": adj["raw_min"],
        "Reported DT (hrs)": round(adj["raw_min"] / 60.0, 2),
        "Holiday minus (min)": adj["holiday_min"],
        "Holiday minus (hrs)": round(adj["holiday_min"] / 60.0, 2),
        "Adjusted DT (min)": adj["adj_min"],
        "Adjusted DT (hrs)": round(adj["adj_min"] / 60.0, 2),
        "Holiday days in window": adj["holiday_days"],
        "Explanation": adj["why"],
        "Last Remark": str(r.get("reason", "") or "")[:160],
    })

out = pd.DataFrame(rows)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Tickets", len(out))
k2.metric("Reported DT hrs", round(out["Reported DT (hrs)"].sum(), 1))
k3.metric("Holiday minus hrs", round(out["Holiday minus (hrs)"].sum(), 1))
k4.metric("Adjusted DT hrs", round(out["Adjusted DT (hrs)"].sum(), 1))

st.info(
    "Logic: Submitted Time se Resolved Time tak window. Usme Sunday, 2nd Saturday, 4th Saturday, "
    "national/festival holiday ke overlapping minutes nikaal ke Reported Down Time (minutes) se minus. "
    "Minus isliye — bank/NOC holiday pe working SLA clock nahi chalti. Adjusted DT = working-hour downtime."
)

with st.expander("Built-in public / festival list"):
    cal = pd.DataFrame([{"Date": d.strftime("%d-%b-%Y"), "Holiday": n} for d, n in sorted(PUBLIC.items())])
    st.dataframe(cal, hide_index=True, use_container_width=True)

hit = out[out["Holiday minus (min)"] > 0]
st.subheader(f"Holiday overlap wale tickets ({len(hit)})")
st.dataframe(hit, use_container_width=True, height=360)

st.subheader("Saari tickets — raw vs adjusted")
st.dataframe(out, use_container_width=True, height=420)

buf = BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    out.to_excel(writer, index=False, sheet_name="Adjusted_DT", startrow=2)
    hit.to_excel(writer, index=False, sheet_name="Holiday_Hits")
    pd.DataFrame(
        [{"Date": d.strftime("%Y-%m-%d"), "Holiday": n} for d, n in sorted({**PUBLIC, **extra}.items())]
    ).to_excel(writer, index=False, sheet_name="Holiday_Calendar")
    wb = writer.book
    ws = writer.sheets["Adjusted_DT"]
    title = wb.add_format({"bold": True, "font_size": 16, "font_color": "white", "bg_color": "#0F4C81", "align": "left"})
    header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#0F4C81", "border": 1, "align": "center", "text_wrap": True})
    even = wb.add_format({"bg_color": "#E8F1FA", "border": 1, "text_wrap": True, "valign": "top"})
    odd = wb.add_format({"bg_color": "#FFFFFF", "border": 1, "text_wrap": True, "valign": "top"})
    red = wb.add_format({"bg_color": "#FECACA", "border": 1, "bold": True})
    green = wb.add_format({"bg_color": "#BBF7D0", "border": 1, "bold": True})
    wrap = wb.add_format({"text_wrap": True, "border": 1, "valign": "top"})
    ws.merge_range(0, 0, 0, 14, f"XTRNATE Holiday Adjusted Downtime  |  {partner}  |  {start_day} to {end_day}", title)
    ws.set_row(0, 24)
    ws.set_row(2, 28)
    for i, col in enumerate(out.columns):
        ws.write(2, i, col, header)
        ws.set_column(i, i, 18 if i < 12 else 46)
    minus_col = list(out.columns).index("Holiday minus (min)")
    adj_col = list(out.columns).index("Adjusted DT (min)")
    why_col = list(out.columns).index("Explanation")
    for ridx, row in out.iterrows():
        excel_r = ridx + 3
        base = even if ridx % 2 == 0 else odd
        for cidx, col in enumerate(out.columns):
            val = row[col]
            if isinstance(val, pd.Timestamp):
                val = val.strftime("%d-%b-%Y %H:%M")
            fmt = base
            if cidx == minus_col and row["Holiday minus (min)"] > 0:
                fmt = red
            if cidx == adj_col:
                fmt = green
            if cidx == why_col:
                fmt = wrap
            ws.write(excel_r, cidx, val if pd.notna(val) else "", fmt)
    ws.freeze_panes(3, 2)
    ws.autofilter(2, 0, 2 + len(out), len(out.columns) - 1)

st.download_button(
    "📥 Download styled Excel (raw / minus / adjusted + explanation)",
    data=buf.getvalue(),
    file_name=f"XTRNATE_Holiday_DT_{partner}_{start_day}_{end_day}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
