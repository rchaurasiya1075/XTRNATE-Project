import os
import sys
from datetime import datetime
from io import BytesIO
from html import escape

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, get_selected_isps, isp_label
from utils.google_sheets import extract_sheet_id
from utils.data_processing import classify_isp, isp_options
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

st.set_page_config(page_title="Pending Mail | XTRNATE", page_icon="📧", layout="wide")
ensure_ready()

MAIL_SHEET_URL = "https://docs.google.com/spreadsheets/d/1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I/edit?gid=762980214#gid=762980214"
MAIL_GID = 762980214


@st.cache_data(ttl=120, show_spinner=False)
def load_mail_sheet():
    sid = extract_sheet_id(MAIL_SHEET_URL)
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={MAIL_GID}"
    raw = pd.read_csv(url, header=None)
    # Row 3 is the real header on this tab
    header = [str(c).strip() for c in raw.iloc[3].tolist()]
    seen = {}
    cols = []
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
    if "Incident ID" in df.columns:
        df = df[df["Incident ID"].notna()]
        df = df[df["Incident ID"].astype(str).str.strip().str.len() > 3]
        df = df.drop_duplicates(subset=["Incident ID"], keep="first")
    return df.reset_index(drop=True)


def partner_of(owner):
    return classify_isp(owner)


def build_html(partner, brand, reason_tbl, loc_tbl, rows):
    r_rows = "".join(
        f"<tr><td style='padding:5px 8px;border:1px solid #94a3b8'>{escape(str(a))}</td>"
        f"<td style='text-align:center;font-weight:700;padding:5px 8px;border:1px solid #94a3b8'>{b}</td></tr>"
        for a, b in reason_tbl
    )
    l_rows = "".join(
        f"<tr><td style='padding:5px 8px;border:1px solid #94a3b8'>{escape(str(a))}</td>"
        f"<td style='text-align:center;font-weight:700;padding:5px 8px;border:1px solid #94a3b8'>{b}</td></tr>"
        for a, b in loc_tbl
    )
    heads = [
        "Incident ID", "Site Code", "State", "Submitted Time", "CurrentStatus",
        "Owner", "Remarks", "Branch Person Name", "Branch Person Contact Number",
        "Alternate Number", "Down Time Aging", "ETR",
    ]
    th = "".join(
        f"<th style='background:#0f4c81;color:#fff;padding:8px;border:1px solid #0b3a63;font-size:12px'>{h}</th>"
        for h in heads
    )
    body_rows = []
    for i, r in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#f1f5f9"
        st_raw = str(r.get("CurrentStatus", ""))
        aging = str(r.get("Down Time Aging", "") or "")
        age_bg = "#16a34a"
        try:
            days = int(str(aging).split("D")[0].strip() or 0)
            if days >= 7:
                age_bg = "#dc2626"
            elif days >= 2:
                age_bg = "#ca8a04"
        except Exception:
            pass
        cells = []
        for h in heads:
            val = escape(str(r.get(h, "") or ""))
            extra = ""
            if h == "CurrentStatus" and "hold" in st_raw.lower():
                extra = "color:#b91c1c;font-weight:700"
            elif h == "CurrentStatus":
                extra = "color:#1d4ed8;font-weight:700"
            if h == "Down Time Aging":
                extra = f"background:{age_bg};color:#fff;font-weight:800;white-space:nowrap"
            cells.append(
                f"<td style='padding:6px 8px;border:1px solid #94a3b8;font-size:12px;color:#0f172a;{extra}'>{val}</td>"
            )
        body_rows.append(f"<tr style='background:{bg}'>{''.join(cells)}</tr>")

    subject = f"OPEN PENDING CALL OF ISP ({partner})"
    html = f"""
    <div style="font-family:Calibri,Arial,sans-serif;max-width:1400px">
      <div style="background:#0f4c81;color:#fff;padding:12px 16px;font-size:18px;font-weight:800">
        Re: {escape(subject)}
      </div>
      <p style="font-size:14px;color:#111">Dear Support,</p>
      <p style="font-size:14px;color:#111;line-height:1.5">
      Please prioritize and resolve all high-aging and long-pending cases at the earliest.
      Also, ensure that the latest progress, revised ETR, outage reason, and resolution updates
      are updated in the MARS portal.
      </p>
      <p style="font-size:14px;color:#111">Please find the attached list of pending cases for your reference.</p>
      <table style="border-collapse:collapse;margin:8px 16px 16px 0;display:inline-table;vertical-align:top">
        <tr><th style="background:#0f4c81;color:#fff;padding:6px 10px;border:1px solid #0b3a63">OUTAGE REASON</th>
            <th style="background:#0f4c81;color:#fff;padding:6px 10px;border:1px solid #0b3a63">{escape(brand)}</th></tr>
        {r_rows}
      </table>
      <table style="border-collapse:collapse;margin:8px 0 16px 12px;display:inline-table;vertical-align:top">
        <tr><th style="background:#0f4c81;color:#fff;padding:6px 10px;border:1px solid #0b3a63">LOCATION</th>
            <th style="background:#0f4c81;color:#fff;padding:6px 10px;border:1px solid #0b3a63">{escape(brand)}</th></tr>
        {l_rows}
      </table>
      <table style="border-collapse:collapse;width:100%;margin-top:8px">
        <tr>{th}</tr>
        {''.join(body_rows)}
      </table>
      <p style="font-size:13px;color:#334155;margin-top:16px">Regards,<br>NOC Team — Xtranet / Hughes</p>
    </div>
    """
    return subject, html


st.title("📧 Pending Call Mail")
st.caption("Data sirf OPEN CALLS sheet se • Owner ke saare ISP alag • purane pages same")

if st.button("🔄 Reload mail sheet"):
    load_mail_sheet.clear()
    st.rerun()

try:
    with st.spinner("OPEN CALLS sheet load ho rahi hai..."):
        df = load_mail_sheet()
except Exception as e:
    st.error(str(e))
    st.info("Sheet Share → Anyone with the link → Viewer hona chahiye.")
    st.stop()

if df.empty:
    st.warning("Is sheet tab pe ticket nahi mile.")
    st.stop()

df["_partner"] = df.get("Owner", "").apply(partner_of)
tmp = df.copy()
tmp["isp"] = tmp["_partner"]
opts = isp_options(tmp, add_all=False)
if not opts:
    opts = [x for x in tmp["_partner"].dropna().astype(str).unique() if x not in ("UNKNOWN", "OTHER", "")]
if not opts:
    opts = ["ONEOTT", "HCIN"]

picked = [x for x in get_selected_isps() if x in opts]
if not picked:
    picked = list(opts) if isp_label() in ("ALL", "NONE") else []
if not picked:
    st.warning("Selected ISP is pending-mail sheet pe nahi. Top / sidebar se ISP tick karo.")
    st.stop()
st.caption("Selected ISP ke hisaab se mail. Multiple select ho to har ISP ka alag tab.")


def render_mail(partner, src):
    brand = {"ONEOTT": "CELERITY", "HCIN": "HICOM"}.get(partner, partner)
    work = src[src["_partner"] == partner].copy()
    if work.empty:
        st.info(f"{partner} ke pending tickets is sheet pe nahi hain.")
        return

    reason_col = "Down Category" if "Down Category" in work.columns else None
    if reason_col:
        reasons = work[reason_col].fillna("Others").astype(str).str.strip()
        reasons = reasons.replace({"": "Others", "nan": "Others"})
    else:
        reasons = pd.Series(["Others"] * len(work))
    reason_counts = reasons.value_counts()
    reason_tbl = [(k, int(v)) for k, v in reason_counts.items()]
    reason_tbl.append(("TOTAL", int(reason_counts.sum())))

    states = work["State"].fillna("Unknown").astype(str) if "State" in work.columns else pd.Series(["Unknown"] * len(work))
    loc_counts = states.value_counts()
    loc_tbl = [(k, int(v)) for k, v in loc_counts.items()]
    loc_tbl.append(("TOTAL", int(loc_counts.sum())))

    def col(name):
        if name in work.columns:
            return name
        for c in work.columns:
            if c.strip().lower() == name.strip().lower():
                return c
        return None

    bname = col("Branch Person Name")
    bph = col("Branch Person Contact Number")
    alt = col("Alternate Number")

    rows = []
    for _, r in work.iterrows():
        rows.append({
            "Incident ID": r.get("Incident ID", ""),
            "Site Code": r.get("Site Code", ""),
            "State": r.get("State", ""),
            "Submitted Time": r.get("Submitted Time", ""),
            "CurrentStatus": r.get("CurrentStatus", ""),
            "Owner": r.get("Owner", brand),
            "Remarks": r.get("Remarks", ""),
            "Branch Person Name": r.get(bname, "") if bname else "",
            "Branch Person Contact Number": r.get(bph, "") if bph else "",
            "Alternate Number": r.get(alt, "") if alt else "",
            "Down Time Aging": r.get("Down Time Aging", ""),
            "ETR": r.get("ETR", ""),
        })

    subject, html = build_html(partner, brand, reason_tbl, loc_tbl, rows)

    st.markdown(f"**Subject:** `{subject}`  •  Tickets: **{len(work)}**")
    st.code(subject, language=None)
    plain = (
        "Dear Support,\n\n"
        "Please prioritize and resolve all high-aging and long-pending cases at the earliest. "
        "Also, ensure that the latest progress, revised ETR, outage reason, and resolution updates "
        "are updated in the MARS portal.\n\n"
        "Please find the attached list of pending cases for your reference.\n\n"
        f"Open pending ({partner} / {brand}): {len(work)} tickets.\n"
    )
    st.text_area("Mail body (copy)", plain, height=140, key=f"mail_body_{partner}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Outage Reason**")
        st.dataframe(pd.DataFrame(reason_tbl, columns=["OUTAGE REASON", brand]), hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**Location**")
        st.dataframe(pd.DataFrame(loc_tbl, columns=["LOCATION", brand]), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Mail preview")
    st.markdown(html, unsafe_allow_html=True)

    det = pd.DataFrame(rows)
    st.dataframe(det, use_container_width=True, height=420)

    download_pack(
        f"{partner} pending mail",
        {
            "Reason": pd.DataFrame(reason_tbl, columns=["OUTAGE REASON", brand]),
            "Location": pd.DataFrame(loc_tbl, columns=["LOCATION", brand]),
            "Pending": det,
        },
        file_stem=f"OPEN_PENDING_{partner}_{datetime.now().strftime('%Y%m%d')}",
        title=f"Pending Mail  ·  {partner}",
        subtitle=datetime.now().strftime("%d-%b-%Y"),
        key=f"mail_xlsx_{partner}",
    )
    st.download_button(
        "📥 Download HTML mail",
        data=html.encode("utf-8"),
        file_name=f"OPEN_PENDING_{partner}.html",
        mime="text/html",
        key=f"mail_html_{partner}",
    )


if len(picked) == 1:
    render_mail(picked[0], df)
else:
    tabs = st.tabs(picked)
    for tab, partner in zip(tabs, picked):
        with tab:
            render_mail(partner, df)

