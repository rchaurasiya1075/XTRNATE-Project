import os
import sys
from datetime import datetime
from io import BytesIO
from html import escape

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, show_last_update

st.set_page_config(page_title="Pending Mail | XTRNATE", page_icon="📧", layout="wide")
show_last_update()


def is_open_status(s):
    t = str(s or "").lower()
    return (
        "assign to fe" in t
        or "call on hold" in t
        or t.strip() == "on hold"
        or "under progress" in t
        or "underprogress" in t
    )


def pick_col(df, names):
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def aging_text(submitted):
    if pd.isna(submitted):
        return ""
    delta = datetime.now() - pd.Timestamp(submitted).to_pydatetime()
    total = int(delta.total_seconds())
    if total < 0:
        total = 0
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}D {h}H {m:02d}M"


def group_reason(row):
    blob = " ".join(
        str(row.get(c, "") or "")
        for c in ("problem_class", "category", "reason", "problem_reported", "root_cause")
    ).lower()
    if any(x in blob for x in ["fibre cut", "fiber cut", "backend", "upstream", "node isolation", "rain", "network outage"]):
        return "FIBER CUT / BACKEND ISSUE / NETWORK OUTAGE / RAIN FALL"
    if "team is checking" in blob or "team checking" in blob:
        return "TEAM IS CHECKING"
    if "link up confirmation" in blob or "confirmation pending" in blob:
        return "Link up confirmation pending"
    if "rechecking" in blob or "pending update" in blob:
        return "ISP RECHECKING PENDING UPDATES"
    if "migration" in blob:
        return "LINK MIGRATION"
    if "modem" in blob or "onu" in blob or "media converter" in blob:
        return "MODEM FAULTY"
    if "fe will visit" in blob or "visit at site" in blob or "fe visit" in blob:
        return "FE will visit at site"
    raw = str(row.get("problem_class") or row.get("category") or row.get("reason") or "Others").strip()
    if not raw or raw.lower() in ("nan", "none", "--"):
        return "Others"
    return raw[:80]


def owner_label(val, partner):
    s = str(val or "")
    if partner == "ONEOTT":
        return "Celerity" if s else "Celerity"
    if "HCIN" in s.upper():
        return "HCIN"
    return s or "HCIN"


def fmt_dt(v):
    if pd.isna(v):
        return ""
    try:
        return pd.Timestamp(v).strftime("%d, %b, %Y at %-I:%M:%S %p")
    except Exception:
        try:
            return pd.Timestamp(v).strftime("%d, %b, %Y at %I:%M:%S %p")
        except Exception:
            return str(v)


def build_html(partner, brand, df, reason_tbl, loc_tbl, rows):
    r_rows = "".join(
        f"<tr><td>{escape(str(a))}</td><td style='text-align:center;font-weight:700'>{b}</td></tr>"
        for a, b in reason_tbl
    )
    l_rows = "".join(
        f"<tr><td>{escape(str(a))}</td><td style='text-align:center;font-weight:700'>{b}</td></tr>"
        for a, b in loc_tbl
    )
    body_rows = []
    for i, r in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#f1f5f9"
        st_raw = str(r.get("CurrentStatus", ""))
        st_col = "#b91c1c" if "hold" in st_raw.lower() else "#1d4ed8"
        aging = str(r.get("Down Time Aging", ""))
        age_bg = "#16a34a"
        try:
            days = int(str(aging).split("D")[0])
            if days >= 7:
                age_bg = "#dc2626"
            elif days >= 2:
                age_bg = "#ca8a04"
        except Exception:
            pass
        tds = "".join(
            f"<td style='padding:6px 8px;border:1px solid #94a3b8;font-size:12px;color:#0f172a'>{escape(str(r.get(c, '') or ''))}</td>"
            for c in [
                "Incident ID", "Site Code", "State", "Submitted Time",
                "CurrentStatus", "Owner", "Remarks", "Branch Person Name",
                "Branch Person Contact Number", "Alternate Number",
            ]
        )
        tds = tds.replace(
            f">{escape(st_raw)}<",
            f" style='padding:6px 8px;border:1px solid #94a3b8;font-size:12px;color:{st_col};font-weight:700'>{escape(st_raw)}<",
            1,
        )
        tds += (
            f"<td style='padding:6px 8px;border:1px solid #94a3b8;font-size:12px;font-weight:800;"
            f"background:{age_bg};color:#fff;white-space:nowrap'>{escape(aging)}</td>"
            f"<td style='padding:6px 8px;border:1px solid #94a3b8;font-size:12px'>{escape(str(r.get('ETR', '') or ''))}</td>"
        )
        body_rows.append(f"<tr style='background:{bg}'>{tds}</tr>")

    heads = [
        "Incident ID", "Site Code", "State", "Submitted Time", "CurrentStatus",
        "Owner", "Remarks", "Branch Person Name", "Branch Person Contact Number",
        "Alternate Number", "Down Time Aging", "ETR",
    ]
    th = "".join(
        f"<th style='background:#0f4c81;color:#fff;padding:8px;border:1px solid #0b3a63;font-size:12px'>{h}</th>"
        for h in heads
    )
    subject = f"OPEN PENDING CALL OF ISP ({partner})"
    greeting = f"""
    <p style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#111">Dear Support,</p>
    <p style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#111;line-height:1.5">
    Please prioritize and resolve all high-aging and long-pending cases at the earliest.
    Also, ensure that the latest progress, revised ETR, outage reason, and resolution updates
    are updated in the MARS portal.
    </p>
    <p style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#111">
    Please find the attached list of pending cases for your reference.
    </p>
    """
    html = f"""
    <div style="font-family:Calibri,Arial,sans-serif;max-width:1400px">
      <div style="background:#0f4c81;color:#fff;padding:12px 16px;font-size:18px;font-weight:800">
        Re: {escape(subject)}
      </div>
      {greeting}
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
      <p style="font-size:13px;color:#334155;margin-top:16px">
      Regards,<br>NOC Team — Xtranet / Hughes
      </p>
    </div>
    """
    return subject, html


st.title("📧 Pending Call Mail")
st.caption("HCIN / ONEOTT alag mail • screenshot jaisa format • purane pages same")
ensure_ready()

partner = st.radio("ISP / Mail for", ["ONEOTT", "HCIN"], horizontal=True)
brand = "CELERITY" if partner == "ONEOTT" else "HCIN"

opened = st.session_state.get("open_df")
raw = st.session_state.get("raw_tickets_df")
closed = st.session_state.get("closed_df")

frames = []
for part in (opened, raw, closed):
    if part is not None and not getattr(part, "empty", True):
        frames.append(part.copy())
if not frames:
    st.warning("Open data nahi mila. Home pe load karo.")
    st.stop()

all_df = pd.concat(frames, ignore_index=True)
if "ticket_id" in all_df.columns:
    all_df = all_df.drop_duplicates(subset=["ticket_id"], keep="first")

if "status" not in all_df.columns:
    st.error("Status column missing")
    st.stop()

work = all_df[all_df["status"].apply(is_open_status)].copy()
if "isp" in work.columns:
    if partner == "ONEOTT":
        work = work[work["isp"].isin(["ONEOTT", "OTT"]) | work.get("owner", pd.Series("", index=work.index)).astype(str).str.upper().str.contains("CELERITY|ONEOTT|OTT", na=False)]
    else:
        work = work[work["isp"].eq("HCIN") | work.get("owner", pd.Series("", index=work.index)).astype(str).str.upper().str.contains("HCIN", na=False)]

if work.empty:
    st.info(f"{partner} ke liye koi open / pending ticket nahi.")
    st.stop()

work = work.sort_values("submitted_time", ascending=False) if "submitted_time" in work.columns else work
work["outage_bucket"] = work.apply(group_reason, axis=1)

reason_counts = work["outage_bucket"].value_counts()
reason_tbl = [(k, int(v)) for k, v in reason_counts.items()]
reason_tbl.append(("TOTAL", int(reason_counts.sum())))

loc_counts = work["state"].fillna("Unknown").astype(str).value_counts() if "state" in work.columns else pd.Series(dtype=int)
loc_tbl = [(k, int(v)) for k, v in loc_counts.items()]
loc_tbl.append(("TOTAL", int(loc_counts.sum()) if len(loc_counts) else 0))

bname = pick_col(work, ["Branch Person Name", "Caller Name", "caller_name", "Contact Person", "Branch Person"])
bph = pick_col(work, ["Branch Person Contact Number", "Caller Number", "Contact Number", "Mobile", "Phone"])
alt = pick_col(work, ["Alternate Number", "Alt Number", "Alternate Contact"])
etr_c = pick_col(work, ["ETR", "ETA", "eta", "Expected Resolution"])

rows = []
for _, r in work.iterrows():
    rows.append({
        "Incident ID": r.get("ticket_id", ""),
        "Site Code": r.get("site_code", ""),
        "State": r.get("state", ""),
        "Submitted Time": fmt_dt(r.get("submitted_time")),
        "CurrentStatus": r.get("status", ""),
        "Owner": owner_label(r.get("owner", ""), partner),
        "Remarks": str(r.get("reason", "") or "")[:220],
        "Branch Person Name": r.get(bname, "") if bname else "",
        "Branch Person Contact Number": r.get(bph, "") if bph else "",
        "Alternate Number": r.get(alt, "") if alt else "",
        "Down Time Aging": aging_text(r.get("submitted_time")),
        "ETR": r.get(etr_c, "") if etr_c else "",
    })

subject, html = build_html(partner, brand, work, reason_tbl, loc_tbl, rows)

st.markdown(f"**Subject:** `{subject}`")
st.code(subject, language=None)

plain = (
    f"Dear Support,\n\n"
    f"Please prioritize and resolve all high-aging and long-pending cases at the earliest. "
    f"Also, ensure that the latest progress, revised ETR, outage reason, and resolution updates "
    f"are updated in the MARS portal.\n\n"
    f"Please find the attached list of pending cases for your reference.\n\n"
    f"Open pending ({partner} / {brand}): {len(work)} tickets.\n"
)
st.text_area("Mail body (copy)", plain, height=140)

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
st.subheader("Ticket list")
st.dataframe(det, use_container_width=True, height=420)

buf = BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
    pd.DataFrame(reason_tbl, columns=["OUTAGE REASON", brand]).to_excel(w, index=False, sheet_name="Reason")
    pd.DataFrame(loc_tbl, columns=["LOCATION", brand]).to_excel(w, index=False, sheet_name="Location")
    det.to_excel(w, index=False, sheet_name="Pending")

st.download_button(
    f"📥 Download {partner} pending mail Excel",
    data=buf.getvalue(),
    file_name=f"OPEN_PENDING_{partner}_{datetime.now().strftime('%Y%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
st.download_button(
    "📥 Download HTML mail",
    data=html.encode("utf-8"),
    file_name=f"OPEN_PENDING_{partner}.html",
    mime="text/html",
)
