import streamlit as st
import pandas as pd
import sys
import os
from datetime import date
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets
from utils.bootstrap import show_last_update

st.set_page_config(page_title="VPN Update | XTRNATE", page_icon="📡", layout="wide")
show_last_update()


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


def build_note(ho_open, branch_sites, backup_on):
    ho_open = max(0, int(ho_open or 0))
    branch_sites = max(0, int(branch_sites or 0))
    backup_on = max(0, min(int(backup_on or 0), branch_sites))
    down = max(0, branch_sites - backup_on)
    ho_line = f"{ho_open} HO OT : Primary down, site live on secondary link"
    site_word = "site" if down == 1 else "sites"
    verb = "is" if down == 1 else "are"
    branch_line = (
        f"Out of {branch_sites} sites, {backup_on} are running on the backup link, "
        f"and {down} {site_word} {verb} down."
    )
    return ho_line, branch_line, down, backup_on


def _font(size):
    from PIL import ImageFont
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_update_png(rows, ho_line, branch_line, dlabel=""):
    from PIL import Image, ImageDraw

    W, header_h, row_h, footer_h = 1600, 150, 92, 180
    H = header_h + row_h * len(rows) + footer_h
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    font_h = _font(64)
    font_sub = _font(26)
    font_l = _font(36)
    font_n = _font(48)
    font_f = _font(28)

    d.rectangle([0, 0, W, header_h], fill="#1B4F72")
    title = "XTRANET UPDATE"
    bbox = d.textbbox((0, 0), title, font=font_h)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, 28), title, fill="#FFFFFF", font=font_h)
    if dlabel:
        sb = d.textbbox((0, 0), dlabel, font=font_sub)
        sw = sb[2] - sb[0]
        d.text(((W - sw) / 2, 104), dlabel, fill="#D6EAF8", font=font_sub)

    val_w = 280
    y = header_h
    for i, (label, val, color) in enumerate(rows):
        bg = "#F7FAFC" if i % 2 == 0 else "#EEF3F8"
        d.rectangle([0, y, W - val_w, y + row_h], fill=bg)
        d.rectangle([W - val_w, y, W, y + row_h], fill=color)
        d.line([0, y + row_h - 2, W, y + row_h - 2], fill="#C5D0DA", width=2)
        d.text((36, y + 26), label, fill="#0F172A", font=font_l)
        num = str(val)
        nb = d.textbbox((0, 0), num, font=font_n)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        d.text((W - val_w + (val_w - nw) / 2, y + (row_h - nh) / 2 - 6), num, fill="#FFFFFF", font=font_n)
        y += row_h

    d.rectangle([0, y, W, H], fill="#FFFFFF")
    for i, line in enumerate([ho_line, branch_line]):
        bb = d.textbbox((0, 0), line, font=font_f)
        lw = bb[2] - bb[0]
        d.text(((W - lw) / 2, y + 36 + i * 48), line, fill="#111111", font=font_f)

    d.rectangle([0, 0, W - 1, H - 1], outline="#1B4F72", width=8)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


st.markdown(
    """
    <style>
    .vpn-head {
      background:#1B4F72; color:#fff; text-align:center;
      padding:22px 12px 8px 12px; font-size:2.4rem; font-weight:800;
      letter-spacing:2px;
    }
    .vpn-sub { background:#1B4F72; color:#D6EAF8; text-align:center;
      padding:0 12px 16px 12px; font-size:1.05rem; font-weight:600; }
    .vpn-wrap { border:6px solid #1B4F72; border-radius:6px; overflow:hidden; max-width:1100px; }
    .vpn-foot {
      background:#fff; color:#111; text-align:center;
      padding:18px 16px; font-weight:700; font-size:1.15rem; line-height:1.6;
    }
    .vpn-label { font-size:1.25rem !important; padding:16px 20px !important; }
    .vpn-num { font-size:1.7rem !important; width:200px !important; padding:16px 12px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def metric_row(label, value, color):
    st.markdown(
        f"""
        <div style="display:flex;align-items:stretch;margin:0;border-bottom:2px solid #c5d0da;">
          <div class="vpn-label" style="flex:1;background:#f7fafc;color:#0f172a;font-weight:800;">{label}</div>
          <div class="vpn-num" style="background:{color};color:#fff;text-align:center;font-weight:800;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("📡 VPN Update")
st.caption("Bada readable card • HO / backup manual • HD image download")

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

open_as_of = (
    all_df["submitted_time"].notna()
    & (all_df["submitted_time"] < day_end)
    & (all_df["resolved_time"].isna() | (all_df["resolved_time"] >= day_end))
)

if "status" in all_df.columns:
    status_open_now = all_df["status"].apply(is_open_status)
    if ref_day == date.today():
        open_as_of = open_as_of | status_open_now
    hold_mask = all_df["status"].apply(is_hold)
else:
    hold_mask = pd.Series(False, index=all_df.index)

open_now = all_df[open_as_of].copy()
old_open = all_df[open_as_of & raised_before].copy()
today_raised = all_df[raised_on_day].copy()
call_hold = all_df[open_as_of & hold_mask].copy()
old_resolved = all_df[resolved_on_day & raised_before].copy()
same_day_resolved = all_df[resolved_on_day & raised_on_day].copy()

open_now["vendor"] = open_now.apply(vendor_bucket, axis=1)
celerity_open = open_now[open_now["vendor"] == "CELERITY / ONEOTT"]
hicom_open = open_now[open_now["vendor"] == "HICOM / HCIN"]

total_open = int(len(open_now))

st.markdown("### HO / Backup (manual)")
m1, m2, m3 = st.columns(3)
with m1:
    ho_open = st.number_input("HO open sites", min_value=0, max_value=max(total_open, 0), value=min(1, total_open), step=1)
with m2:
    branch_sites = max(0, total_open - int(ho_open))
    st.metric("Branch open (Total − HO)", branch_sites)
with m3:
    backup_on = st.number_input(
        "Branch pe backup chal raha (manual)",
        min_value=0,
        max_value=max(branch_sites, 0),
        value=max(0, branch_sites - 1) if branch_sites else 0,
        step=1,
    )

ho_line, branch_line, down_n, backup_n = build_note(ho_open, branch_sites, backup_on)

kpis = [
    ("Total Open Tickets", total_open, "#2E7D32"),
    ("Old Open Tickets", int(len(old_open)), "#F9A825"),
    ("Today Raised Tickets", int(len(today_raised)), "#1565C0"),
    ("Call On Hold", int(len(call_hold)), "#6A1B9A"),
    ("Old Tickets Resolved", int(len(old_resolved)), "#C62828"),
    ("Same Day Tickets Resolved", int(len(same_day_resolved)), "#558B2F"),
    ("CELERITY Open", int(len(celerity_open)), "#0288D1"),
    ("HICOM Open", int(len(hicom_open)), "#1A237E"),
]

st.markdown('<div class="vpn-wrap">', unsafe_allow_html=True)
st.markdown('<div class="vpn-head">XTRANET UPDATE</div>', unsafe_allow_html=True)
st.markdown(f'<div class="vpn-sub">{dlabel}</div>', unsafe_allow_html=True)
for label, val, color in kpis:
    metric_row(label, val, color)
st.markdown(
    f'<div class="vpn-foot">{ho_line}<br>{branch_line}</div></div>',
    unsafe_allow_html=True,
)

try:
    png = render_update_png(kpis, ho_line, branch_line, dlabel)
except Exception as e:
    png = None
    st.warning(f"Image build issue: {e}")

if png:
    st.download_button(
        "🖼️ HD Image download (WhatsApp / mail)",
        data=png,
        file_name=f"XTRANET_UPDATE_{ref_day}.png",
        mime="image/png",
        use_container_width=True,
    )
    st.image(png, caption="HD card — yahi image download hogi")

st.markdown("---")
tabs = st.tabs([
    f"Open ({dlabel})",
    "Old open",
    f"Raised {dlabel}",
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
    table(call_hold)
with tabs[4]:
    table(old_resolved)
with tabs[5]:
    table(same_day_resolved)
with tabs[6]:
    table(celerity_open)
with tabs[7]:
    table(hicom_open)

sum_df = pd.DataFrame([(a, b) for a, b, _ in kpis], columns=["Metric", "Count"])
sum_df.loc[len(sum_df)] = ["HO Open (manual)", int(ho_open)]
sum_df.loc[len(sum_df)] = ["Branch Open", int(branch_sites)]
sum_df.loc[len(sum_df)] = ["Backup running (manual)", int(backup_n)]
sum_df.loc[len(sum_df)] = ["Branch down (no backup)", int(down_n)]
buf = BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
    sum_df.to_excel(w, index=False, sheet_name="Snapshot")
    for name, df in [
        ("Open", open_now), ("Old_Open", old_open), ("Raised", today_raised),
        ("Call_On_Hold", call_hold),
        ("Old_Resolved", old_resolved), ("Same_Day_Resolved", same_day_resolved),
        ("Celerity_Open", celerity_open), ("Hicom_Open", hicom_open),
    ]:
        cols = [c for c in show_cols if c in df.columns]
        if cols and not df.empty:
            df[cols].to_excel(w, index=False, sheet_name=name[:31])

st.download_button(
    f"📥 Excel VPN Update {dlabel}",
    data=buf.getvalue(),
    file_name=f"XTRANET_VPN_Update_{ref_day}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
