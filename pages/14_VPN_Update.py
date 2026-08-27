import streamlit as st
import pandas as pd
import sys
import os
from datetime import date
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets

st.set_page_config(page_title="VPN Update | XTRNATE", page_icon="📡", layout="wide")


def is_open_status(s):
    t = str(s or "").lower()
    return (
        ("assign to fe" in t)
        or ("call on hold" in t)
        or ("on hold" in t)
        or ("under progress" in t)
        or ("underprogress" in t)
    )


def is_hold(s):
    t = str(s or "").lower()
    return ("call on hold" in t) or (t.strip() == "on hold")


def vendor_bucket(row):
    for col in ("isp", "owner"):
        v = str(row.get(col, "") or "").upper()
        if "HCIN" in v or "HICOM" in v:
            return "HICOM / HCIN"
        if "ONEOTT" in v or "OTT" in v or "CELERITY" in v:
            return "CELERITY / ONEOTT"
    return "OTHER"


def metric_row(label, value, color):
    st.markdown(
        f"""
        <div style="display:flex;align-items:stretch;margin:0;border-bottom:1px solid #1e3a5f;">
          <div style="flex:1;background:#f4f7fb;color:#0f172a;padding:10px 16px;font-weight:700;font-size:1.05rem;">{label}</div>
          <div style="width:180px;background:{color};color:#fff;padding:10px 12px;text-align:center;font-weight:800;font-size:1.35rem;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(
    """
    <style>
    .vpn-head {
      background:#1B4F72; color:#fff; text-align:center;
      padding:16px 12px; font-size:1.8rem; font-weight:800;
      letter-spacing:1px; border-radius:4px 4px 0 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📡 VPN Update")
st.caption("Jo date select karoge, usi din ka snapshot. Purane pages same hain.")

if st.session_state.get("closed_df") is None and st.session_state.get("open_df") is None:
    with st.spinner("Data auto-load..."):
        auto_load_tickets()

closed = st.session_state.get("closed_df")
opened = st.session_state.get("open_df")
raw = st.session_state.get("raw_tickets_df")

frames = []
for part in (closed, opened, raw):
    if part is not None and not getattr(part, "empty", True):
        frames.append(part)
if not frames:
    st.warning("Data nahi mila. Home / Upload se sheet load karo.")
    st.stop()

all_df = pd.concat(frames, ignore_index=True)
if "ticket_id" in all_df.columns:
    all_df = all_df.drop_duplicates(subset=["ticket_id"], keep="first")

if "submitted_time" not in all_df.columns:
    st.error("Submitted Time nahi mili.")
    st.stop()

all_df = all_df.copy()
all_df["submitted_time"] = pd.to_datetime(all_df["submitted_time"], errors="coerce")
if "resolved_time" in all_df.columns:
    all_df["resolved_time"] = pd.to_datetime(all_df["resolved_time"], errors="coerce")
else:
    all_df["resolved_time"] = pd.NaT

ref_day = st.date_input("Kaunse din ka update?", value=date.today())
day_start = pd.Timestamp(ref_day)
day_end = day_start + pd.Timedelta(days=1)
dlabel = ref_day.strftime("%d-%b-%Y")

raised_on_day = all_df["submitted_time"].notna() & (all_df["submitted_time"] >= day_start) & (all_df["submitted_time"] < day_end)
raised_before = all_df["submitted_time"].notna() & (all_df["submitted_time"] < day_start)
resolved_on_day = all_df["resolved_time"].notna() & (all_df["resolved_time"] >= day_start) & (all_df["resolved_time"] < day_end)

# Open AS OF end of selected day:
# submitted before day_end AND (no resolve time OR resolved after day_end)
open_as_of = (
    all_df["submitted_time"].notna()
    & (all_df["submitted_time"] < day_end)
    & (all_df["resolved_time"].isna() | (all_df["resolved_time"] >= day_end))
)

# If ticket still has open-like status and no resolved_time, keep it
# (covers Assign to FE / Hold / Under Progress living in current dump)
if "status" in all_df.columns:
    status_open_now = all_df["status"].apply(is_open_status)
    # For the selected day == today, prefer live open statuses too
    if ref_day == date.today():
        open_as_of = open_as_of | status_open_now
    hold_mask = all_df["status"].apply(is_hold)
else:
    status_open_now = pd.Series(False, index=all_df.index)
    hold_mask = pd.Series(False, index=all_df.index)

open_now = all_df[open_as_of].copy()
old_open = all_df[open_as_of & raised_before].copy()
today_raised = all_df[raised_on_day].copy()
closed_on_day = all_df[resolved_on_day].copy()
call_hold = all_df[open_as_of & hold_mask].copy() if ref_day == date.today() else all_df[resolved_on_day & hold_mask].copy()
# Call on hold for a past day: current dump rarely has historical status.
# If selected day is today use live hold; else show holds that are still open as-of that day AND status is hold (best available).
if ref_day != date.today():
    call_hold = all_df[open_as_of & hold_mask].copy()

old_resolved = all_df[resolved_on_day & raised_before].copy()
same_day_resolved = all_df[resolved_on_day & raised_on_day].copy()

open_now["vendor"] = open_now.apply(vendor_bucket, axis=1)
celerity_open = open_now[open_now["vendor"] == "CELERITY / ONEOTT"]
hicom_open = open_now[open_now["vendor"] == "HICOM / HCIN"]

kpis = [
    (f"Total Open Tickets (as of {dlabel})", len(open_now), "#2E7D32"),
    (f"Old Open Tickets (raised before {dlabel})", len(old_open), "#F9A825"),
    (f"Raised on {dlabel}", len(today_raised), "#1565C0"),
    (f"Closed on {dlabel}", len(closed_on_day), "#37474F"),
    (f"Call On Hold (as of {dlabel})", len(call_hold), "#6A1B9A"),
    (f"Old Tickets Resolved on {dlabel}", len(old_resolved), "#C62828"),
    (f"Same Day Resolved on {dlabel}", len(same_day_resolved), "#558B2F"),
    (f"CELERITY Open (as of {dlabel})", len(celerity_open), "#0288D1"),
    (f"HICOM Open (as of {dlabel})", len(hicom_open), "#1A237E"),
]

st.markdown(f'<div class="vpn-head">XTRANET UPDATE &nbsp;•&nbsp; {dlabel}</div>', unsafe_allow_html=True)
for label, val, color in kpis:
    metric_row(label, val, color)

st.caption(
    f"Snapshot date: **{dlabel}**  •  "
    f"Raised = Submitted Time us din  •  Closed = Resolved Time-Active us din  •  "
    f"Same day = usi din raise + usi din resolve  •  "
    f"Old resolved = us din se pehle raise, us din close  •  "
    f"Open as of date = raise ho chuka, resolve us din ke baad / abhi pending"
)

st.markdown("---")
tabs = st.tabs([
    f"Open ({dlabel})",
    "Old open",
    f"Raised {dlabel}",
    f"Closed {dlabel}",
    "Call on Hold",
    "Old resolved",
    "Same-day resolved",
    "CELERITY open",
    "HICOM open",
])

show_cols = [c for c in [
    "ticket_id", "site_code", "status", "submitted_time", "resolved_time",
    "owner", "isp", "state", "city", "reason"
] if c in all_df.columns]


def table(df):
    if df is None or df.empty:
        st.info("No rows")
        return
    cols = [c for c in show_cols if c in df.columns]
    sort = "submitted_time" if "submitted_time" in cols else cols[0]
    st.dataframe(df[cols].sort_values(sort, ascending=False), use_container_width=True, height=360)


with tabs[0]:
    table(open_now)
with tabs[1]:
    table(old_open)
with tabs[2]:
    table(today_raised)
with tabs[3]:
    table(closed_on_day)
with tabs[4]:
    table(call_hold)
with tabs[5]:
    table(old_resolved)
with tabs[6]:
    table(same_day_resolved)
with tabs[7]:
    table(celerity_open)
with tabs[8]:
    table(hicom_open)

sum_df = pd.DataFrame([(a, b) for a, b, _ in kpis], columns=["Metric", "Count"])
buf = BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
    sum_df.to_excel(w, index=False, sheet_name="Snapshot")
    for name, df in [
        ("Open", open_now), ("Old_Open", old_open), ("Raised", today_raised),
        ("Closed", closed_on_day), ("Call_On_Hold", call_hold),
        ("Old_Resolved", old_resolved), ("Same_Day_Resolved", same_day_resolved),
        ("Celerity_Open", celerity_open), ("Hicom_Open", hicom_open),
    ]:
        cols = [c for c in show_cols if c in df.columns]
        if cols and not df.empty:
            df[cols].to_excel(w, index=False, sheet_name=name[:31])

st.download_button(
    f"📥 Download VPN Update {dlabel}",
    data=buf.getvalue(),
    file_name=f"XTRANET_VPN_Update_{ref_day}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
