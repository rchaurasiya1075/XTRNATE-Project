import os
import sys
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, apply_isp_filter, isp_label
from utils.data_processing import process_closed_tickets, classify_isp, isp_options
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.excel_export import excel_bytes
from utils.report_download import download_pack

st.set_page_config(
    page_title="Partner Report | XTRNATE", page_icon="📄", layout="wide"
)

DATA_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
DATA_GID = 1980854633

CLASS_ORDER = [
    "Fibre Cut",
    "Backend /Upstream issue/Node isolation at ISP end",
    "Vendor Change",
    "NOT Feasible for service",
    "ONU/Media converter/ZTE modem Rebooted",
    "ONU/Media converter/ZTE modem is faulty",
    "Power outage at ISP Node",
    "Power failure at site",
    "Problem in LAN connectivity.",
    "Interface down/ Cable disconnected from SDWAN",
    "No changes done",
    "Maintenance activity by ISP",
    "Natural Calamity",
    "Payment updation issue",
    "Link OK — Speedtest",
    "Firewall / Ping (Housekeeping)",
    "Coordinated & found no problem",
    "Loose connection/ Power socket issue",
    "Latency Issue",
    "WAN IP Issue",
    "Address mismatch issue",
    "TELCO Sytem Failure",
    "Signal issue",
    "Power cord damaged/unplugged",
    "Ticket logged with wrong inputs",
    "LAN IP changed",
    "Test Call",
    "Others",
]

RELATED_ORDER = [
    "Third Party",
    "House keeping",
    "Force Majeure",
    "Vendor Change",
    "Cannot Duplicate",
]

SLA_ORDER = [
    "<2 Hours",
    "2-4 Hours",
    "4-8 Hours",
    "8-12 Hours",
    "12-24 Hours",
    "24-48 Hours",
    "48-72 Hours",
    "More than 72 Hours",
]


def sheet_class(row):
    raw = str(row.get("problem_class", "") or row.get("category", "") or "").strip()
    if raw and raw.lower() not in ("nan", "--", "none", ""):
        return raw
    return "Others"


def sheet_related(row):
    raw = str(row.get("problem_related", "") or "").strip()
    if raw and raw.lower() not in ("nan", "--", "none", ""):
        return raw
    return None


def remark_text(row):
    parts = []
    for c in (
        "reason", "root_cause", "problem_reported", "last_enclosure",
        "final_action", "Final Action Taken",
    ):
        if c in row.index:
            parts.append(str(row.get(c) or ""))
    return " ".join(parts).lower()


def refine_row(row):
    """Others / Force Majeure / Housekeeping remarks → exact buckets. One class only."""
    cls = sheet_class(row)
    rel = sheet_related(row)
    t = remark_text(row)

    if any(k in t for k in [
        "alternate service provider", "provisioned on alternate",
        "link not stable/working with existing operator",
        "existing operator", "alternate isp", "vendor change",
        "change of vendor", "vendor changed", "isp change", "change of isp",
        "migration", "link migration",
    ]):
        return "Vendor Change", "Vendor Change"

    if any(k in t for k in [
        "post rebooting onu", "rebooting onu by isp",
        "onu by isp with customer intervention",
    ]):
        return "ONU/Media converter/ZTE modem Rebooted", rel or "Third Party"

    if any(k in t for k in [
        "technically not feasible", "rolled back by isp",
        "not feasible for service",
    ]):
        return "NOT Feasible for service", "Force Majeure"

    if any(k in t for k in ["landslide", "heavy rain", "floods", "flood"]):
        return "Natural Calamity", "Force Majeure"

    if "payment updation" in t or "payment update" in t:
        return "Payment updation issue", rel or "Third Party"

    if "speedtest" in t and "good speed" in t:
        return "Link OK — Speedtest", "House keeping"

    if "disabled firewall" in t or ("8.8.8.8" in t and "firewall" in t):
        return "Firewall / Ping (Housekeeping)", "House keeping"

    return cls, rel


def sla_bucket(hrs):
    if pd.isna(hrs) or hrs < 0:
        return None
    if hrs < 2:
        return "<2 Hours"
    if hrs < 4:
        return "2-4 Hours"
    if hrs < 8:
        return "4-8 Hours"
    if hrs < 12:
        return "8-12 Hours"
    if hrs < 24:
        return "12-24 Hours"
    if hrs < 48:
        return "24-48 Hours"
    if hrs < 72:
        return "48-72 Hours"
    return "More than 72 Hours"


def style_blue(df):
    def apply(row):
        if str(row.iloc[0]).strip().lower() == "grand total":
            return ["background-color:#0284C7;color:#fff;font-weight:800;text-align:center"] * len(row)
        return ["background-color:#F8FAFC;color:#0F172A;text-align:center"] * len(row)
    return df.style.apply(apply, axis=1).set_table_styles([
        {"selector": "th", "props": [("background-color", "#0F172A"), ("color", "#fff"), ("font-weight", "800"), ("text-align", "center"), ("padding", "10px")]},
        {"selector": "td", "props": [("border", "1px solid #CBD5E1"), ("padding", "8px")]},
    ])


def style_navy(df):
    def apply(row):
        if str(row.iloc[0]).strip().lower() == "grand total":
            return ["background-color:#1E293B;color:#38BDF8;font-weight:800;text-align:center"] * len(row)
        return ["background-color:#FFFFFF;color:#0F172A;text-align:center"] * len(row)
    return df.style.apply(apply, axis=1).set_table_styles([
        {"selector": "th", "props": [("background-color", "#0F172A"), ("color", "#fff"), ("font-weight", "800"), ("text-align", "center"), ("padding", "10px")]},
        {"selector": "td", "props": [("border", "1px solid #E2E8F0"), ("padding", "8px")]},
    ])


DETAIL_COLS = [
    "ticket_id",
    "site_code",
    "isp",
    "owner",
    "submitted_time",
    "resolved_time",
    "resolution_hours",
    "sla_band",
    "issue_type",
    "related_to",
    "problem_class",
    "problem_reported",
    "reason",
    "root_cause",
    "final_action",
    "state",
    "city",
]


def ticket_view(df):
    """Compact ticket table: times formatted, hours rounded."""
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [c for c in DETAIL_COLS if c in df.columns]
    if not cols:
        return df.head(0)
    out = df.loc[:, cols].copy()
    if "resolution_hours" in out.columns:
        out["resolution_hours"] = pd.to_numeric(out["resolution_hours"], errors="coerce").round(2)
    for c in ("submitted_time", "resolved_time"):
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%d-%b-%Y %H:%M")
    sort_src = "submitted_time" if "submitted_time" in df.columns else cols[0]
    try:
        out = out.assign(_s=pd.to_datetime(df[sort_src], errors="coerce").values)
        out = out.sort_values("_s", ascending=False).drop(columns=["_s"])
    except Exception:
        pass
    return out.reset_index(drop=True)


def show_ticket_groups(groups, prefix="", empty_msg="Is period mein is option ke tickets nahi."):
    """groups = [(label, dataframe), ...] — expander per option with full tickets."""
    groups = [(str(lab), g) for lab, g in groups if g is not None and not getattr(g, "empty", True)]
    if not groups:
        st.caption(empty_msg)
        return
    st.markdown("**Tickets — har option (expand karke dekho)**")
    for lab, g in groups:
        n = len(g)
        short = lab if len(lab) <= 80 else lab[:77] + "…"
        title = f"{prefix}{short}   ·   {n} ticket{'s' if n != 1 else ''}"
        with st.expander(title, expanded=False):
            st.dataframe(
                ticket_view(g),
                use_container_width=True,
                height=min(420, 48 + 32 * min(n, 11)),
            )


def site_repeat_summary(part):
    if part is None or part.empty or "site_code" not in part.columns:
        return pd.DataFrame()
    if "ticket_id" in part.columns:
        named = {"tickets": ("ticket_id", "count")}
    else:
        named = {"tickets": ("site_code", "count")}
    if "resolution_hours" in part.columns:
        named["avg_hrs"] = ("resolution_hours", "mean")
    if "state" in part.columns:
        named["state"] = ("state", "first")
    if "city" in part.columns:
        named["city"] = ("city", "first")
    if "isp" in part.columns:
        named["isp"] = ("isp", "first")
    g = part.groupby("site_code", dropna=False).agg(**named).reset_index()
    if "avg_hrs" in g.columns:
        g["avg_hrs"] = g["avg_hrs"].round(2)
    return g.sort_values("tickets", ascending=False).reset_index(drop=True)


def repeat_buckets(selected):
    """[(label, site_index, tickets_df), ...] for 1 / 2 / 3 / 4 / 5+."""
    if selected is None or selected.empty or "site_code" not in selected.columns:
        return []
    vc = selected.groupby("site_code").size()
    specs = [
        ("SINGLE TIME CALL LOG", vc[vc == 1].index),
        ("2 TIMES CALL LOG", vc[vc == 2].index),
        ("3 TIME CALL LOG", vc[vc == 3].index),
        ("4 Time Repeat", vc[vc == 4].index),
        ("5+ Time Repeat", vc[vc >= 5].index),
    ]
    out = []
    for lab, sites in specs:
        part = selected[selected["site_code"].isin(sites)].copy()
        out.append((lab, sites, part))
    return out


st.title("📄 Partner Performance Report")
st.caption("Date range • 4 points ke har option ke tickets • Repeat sites + detail • Vendor Change alag")

ensure_ready()

with st.expander("🔄 Reload Data from Google Sheet"):
    if st.button("Reload DATA tab", type="primary"):
        try:
            sid = extract_sheet_id(DATA_URL)
            raw = load_sheet_as_csv(sid, gid=DATA_GID)
            processed = process_closed_tickets(raw)
            if "ticket_id" in processed.columns:
                processed = processed.drop_duplicates(subset=["ticket_id"], keep="first")
            st.session_state.raw_tickets_df = processed
            st.session_state.closed_df = processed
            st.success(f"Loaded {len(processed)} unique incidents")
            st.rerun()
        except Exception as e:
            st.error(str(e))

df = st.session_state.get("raw_tickets_df")
if df is None or df.empty:
    df = st.session_state.get("closed_df")
if df is None or df.empty:
    st.warning("Data nahi mila. Refresh button dabao.")
    st.stop()

work = df.copy()
if "ticket_id" in work.columns:
    work = work.drop_duplicates(subset=["ticket_id"], keep="first")

for a, b in {
    "Problem Classification": "problem_class",
    "Problem Related To": "problem_related",
    "Problem Reported": "problem_reported",
    "Root Cause": "root_cause",
    "Final Action Taken": "final_action",
}.items():
    if a in work.columns and b not in work.columns:
        work[b] = work[a]

if "submitted_time" in work.columns and "resolved_time" in work.columns:
    work = work.dropna(subset=["submitted_time", "resolved_time"])
    work["resolution_hours"] = (work["resolved_time"] - work["submitted_time"]).dt.total_seconds() / 3600.0
    work = work[work["resolution_hours"] >= 0]
    work["month_key"] = work["resolved_time"].dt.to_period("M")
    work["month_label"] = work["resolved_time"].dt.strftime("%b-%y")
else:
    st.error("submitted_time / resolved_time missing")
    st.stop()

refined = work.apply(refine_row, axis=1, result_type="expand")
refined.columns = ["issue_type", "related_to"]
work["issue_type"] = refined["issue_type"]
work["related_to"] = refined["related_to"]
work["sla_band"] = work["resolution_hours"].apply(sla_bucket)


if "isp" not in work.columns:
    work["isp"] = work.get("owner", "").apply(classify_isp)
else:
    work["isp"] = work["isp"].fillna("").astype(str)
    mask = work["isp"].isin(["", "OTHER", "nan", "UNKNOWN"])
    if mask.any() and "owner" in work.columns:
        work.loc[mask, "isp"] = work.loc[mask, "owner"].apply(classify_isp)

if "status" in work.columns:
    sl = work["status"].astype(str).str.lower()
    closed_mask = sl.str.contains("resolv|close", na=False)
    if closed_mask.any():
        work = work[closed_mask].copy()

partner = isp_label()
work = apply_isp_filter(work)

st.markdown("---")
f1, f2, f3 = st.columns([1, 1, 2])
with f1:
    st.markdown(f"**ISP:** {partner}")
    st.caption("Top / sidebar se multiple ISP select karo")
with f2:
    date_mode = st.radio("Date", ["Last N months", "From – To"], horizontal=True)
with f3:
    months_n = st.selectbox(
        "Period Filter",
        ["Last 1 Month", "Last 2 Months", "Last 3 Months", "Last 4 Months",
         "Last 5 Months", "Last 6 Months", "Last 7 Months", "Overall"],
        index=2,
        disabled=(date_mode == "From – To"),
    )

max_dt = work["resolved_time"].max()
min_dt = work["resolved_time"].min()
if pd.isna(max_dt):
    st.info("No resolved tickets for this selection.")
    st.stop()

if date_mode == "From – To":
    rng = st.date_input(
        "Report From → To (resolved date)",
        value=(min_dt.date(), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        d0, d1 = rng[0], rng[1]
    else:
        d0 = d1 = rng
    selected = work[
        (work["resolved_time"].dt.date >= d0) & (work["resolved_time"].dt.date <= d1)
    ].copy()
    period_label = f"{d0} to {d1}"
else:
    if months_n == "Overall":
        selected = work.copy()
        period_label = "Overall"
    else:
        n = int(months_n.split()[1])
        start = (max_dt.to_period("M") - (n - 1)).to_timestamp()
        selected = work[work["resolved_time"] >= start].copy()
        period_label = months_n

if selected.empty:
    st.warning("Is period / partner pe resolved data nahi hai.")
    st.stop()

st.caption(f"Showing **{partner}** • **{period_label}** • {len(selected)} tickets")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric("Total Tickets", len(selected))
with kpi2:
    st.metric("> 24 Hrs", int((selected["resolution_hours"] > 24).sum()))
with kpi3:
    st.metric("Vendor Change", int((selected["issue_type"] == "Vendor Change").sum()))
with kpi4:
    st.metric("NOT Feasible", int((selected["issue_type"] == "NOT Feasible for service").sum()))
with kpi5:
    st.metric("Others (left)", int((selected["issue_type"] == "Others").sum()))

st.markdown("---")

month_periods = sorted(selected["month_key"].dropna().unique().tolist())
month_labels = [pd.Period(p, freq="M").strftime("%b-%y") for p in month_periods]
extra_cls = [c for c in selected["issue_type"].dropna().unique() if c not in CLASS_ORDER]
all_cls = CLASS_ORDER + extra_cls

sla_rows = []
for band in SLA_ORDER:
    row = {"SLA Bucket": band}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        cnt = int(((selected["month_key"] == p) & (selected["sla_band"] == band)).sum())
        row[lab] = cnt
        total += cnt
    row["Grand Total"] = total
    sla_rows.append(row)
gt = {"SLA Bucket": "Grand Total"}
for lab in month_labels:
    gt[lab] = int(sum(r[lab] for r in sla_rows))
gt["Grand Total"] = int(sum(r["Grand Total"] for r in sla_rows))
sla_rows.append(gt)
sla_df = pd.DataFrame(sla_rows)

cls_rows = []
for cls in all_cls:
    row = {"Problem Classification": cls}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        part = selected[(selected["month_key"] == p) & (selected["issue_type"] == cls)]
        cnt = int(len(part))
        row[lab] = cnt if cnt else 0
        avg = part["resolution_hours"].mean() if len(part) else np.nan
        row[f"Avg Hrs ({lab})"] = round(avg, 2) if pd.notna(avg) else "-"
        total += cnt
    if total == 0:
        continue
    row["Grand Total"] = total
    cls_rows.append(row)
if cls_rows:
    gt2 = {"Problem Classification": "Grand Total"}
    for lab in month_labels:
        gt2[lab] = int(sum(int(r[lab] or 0) for r in cls_rows))
        gt2[f"Avg Hrs ({lab})"] = "-"
    gt2["Grand Total"] = int(sum(r["Grand Total"] for r in cls_rows))
    cls_rows.append(gt2)
cls_df = pd.DataFrame(cls_rows)

rel_rows = []
for rel in RELATED_ORDER + [x for x in selected["related_to"].dropna().unique() if x not in RELATED_ORDER]:
    row = {"Problem Related To": rel}
    total = 0
    for p, lab in zip(month_periods, month_labels):
        cnt = int(((selected["month_key"] == p) & (selected["related_to"] == rel)).sum())
        row[lab] = cnt if cnt else 0
        total += cnt
    if total == 0:
        continue
    row["Grand Total"] = total
    rel_rows.append(row)
if rel_rows:
    gtr = {"Problem Related To": "Grand Total"}
    for lab in month_labels:
        gtr[lab] = int(sum(int(r[lab] or 0) for r in rel_rows))
    gtr["Grand Total"] = int(sum(r["Grand Total"] for r in rel_rows))
    rel_rows.append(gtr)
rel_df = pd.DataFrame(rel_rows) if rel_rows else pd.DataFrame()

repeat_idx = ["SINGLE TIME CALL LOG", "2 TIMES CALL LOG", "3 TIME CALL LOG", "4 Time Repeat", "5+ Time Repeat"]
rep = {"REPEAT TIME": repeat_idx}
for p, lab in zip(month_periods, month_labels):
    mdf = selected[selected["month_key"] == p]
    vc = mdf.groupby("site_code").size() if "site_code" in mdf.columns else pd.Series(dtype=int)
    tt_vals, sc_vals = [], []
    for nrep in [1, 2, 3, 4]:
        sites = vc[vc == nrep]
        sc_vals.append(int(len(sites)))
        tt_vals.append(int(sites.sum()) if len(sites) else 0)
    sites5 = vc[vc >= 5]
    sc_vals.append(int(len(sites5)))
    tt_vals.append(int(sites5.sum()) if len(sites5) else 0)
    rep[f"{lab}-TT"] = tt_vals
    rep[f"{lab}-SITES"] = sc_vals
rep_df = pd.DataFrame(rep)

st.subheader("1. Resolution Time Buckets (SLA)")
st.dataframe(style_blue(sla_df), use_container_width=True, hide_index=True)
st.caption("Har SLA option ke tickets — Vendor Change jaisa detail.")
show_ticket_groups(
    [(band, selected[selected["sla_band"] == band]) for band in SLA_ORDER],
    prefix="SLA · ",
    empty_msg="Is period mein SLA tickets nahi.",
)

st.subheader("2. Problem Classification & Avg Resolution Time")
st.dataframe(style_navy(cls_df), use_container_width=True, hide_index=True)

st.subheader("2b. Others / Force Majeure / Housekeeping — remark mapping")
st.caption(
    "Third Party Others: ONU reboot → Device Rebooted • alternate SP / vendor / ISP / migration → Vendor Change • payment → Payment updation. "
    "Force Majeure: landslide/rain/flood → Natural Calamity • rolled back / not feasible → NOT Feasible. "
    "Housekeeping Others: speedtest OK • firewall/ping."
)
split_names = [
    "Vendor Change", "NOT Feasible for service", "ONU/Media converter/ZTE modem Rebooted",
    "Natural Calamity", "Payment updation issue", "Link OK — Speedtest",
    "Firewall / Ping (Housekeeping)", "Others",
]
split_rows = []
for name in split_names:
    part = selected[selected["issue_type"] == name]
    if part.empty:
        continue
    split_rows.append({
        "Mapped class": name,
        "Tickets": len(part),
        "Avg Hrs": round(part["resolution_hours"].mean(), 2) if len(part) else 0,
    })
st.dataframe(pd.DataFrame(split_rows), use_container_width=True, hide_index=True)

st.caption("Har classification ke tickets.")
show_ticket_groups(
    [(cls, selected[selected["issue_type"] == cls]) for cls in all_cls],
    prefix="Class · ",
    empty_msg="Is period mein classification tickets nahi.",
)

if "problem_reported" in selected.columns:
    pr = selected["problem_reported"].fillna("").astype(str).str.strip()
    pr = pr.replace({"nan": "", "None": "", "--": "", "none": ""})
    tmp = selected.copy()
    tmp["_pr"] = pr
    tmp = tmp[tmp["_pr"] != ""]
    counts = tmp["_pr"].value_counts()
    if not counts.empty:
        st.subheader("2c. Problem Reported — har option ke tickets")
        top_n = 30
        names = list(counts.index[:top_n])
        groups = [(name, tmp[tmp["_pr"] == name]) for name in names]
        rest = tmp[~tmp["_pr"].isin(names)]
        if not rest.empty:
            groups.append((f"Other Problem Reported ({len(rest)})", rest))
        show_ticket_groups(groups, prefix="Reported · ")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("3. Problem Related To")
    if not rel_df.empty:
        st.dataframe(style_blue(rel_df), use_container_width=True, hide_index=True)
    else:
        st.info("No Problem Related data available.")
with col_b:
    st.subheader("4. Repeat Call Analysis")
    st.dataframe(style_blue(rep_df), use_container_width=True, hide_index=True)

rel_opts = RELATED_ORDER + [
    x for x in selected["related_to"].dropna().unique() if x not in RELATED_ORDER
]
st.markdown("#### 3. Problem Related To — tickets")
st.caption("Third Party, House keeping, Force Majeure, Vendor Change… har option ke tickets.")
show_ticket_groups(
    [(rel, selected[selected["related_to"] == rel]) for rel in rel_opts],
    prefix="Related · ",
    empty_msg="Problem Related tickets nahi.",
)

st.markdown("#### 4. Repeat Call Analysis — sites + tickets")
st.caption(
    "Jo number table mein dikha (1 time / 2 times / … / 5+) uske **kaun se site** aur **kaun se tickets** "
    "yahan expand karke poori detail ke saath dikhenge."
)
rb = repeat_buckets(selected)
repeat_site_frames = []
repeat_ticket_frames = []
for lab, sites, part in rb:
    n_sites = int(len(sites))
    n_tt = int(len(part))
    if n_sites == 0:
        continue
    is_hot = lab.startswith("5+")
    with st.expander(
        f"{lab}   ·   {n_sites} site{'s' if n_sites != 1 else ''}   ·   {n_tt} ticket{'s' if n_tt != 1 else ''}",
        expanded=is_hot,
    ):
        st.markdown("**Sites in this bucket**")
        site_tab = site_repeat_summary(part)
        if not site_tab.empty:
            st.dataframe(site_tab, use_container_width=True, height=min(320, 48 + 32 * min(len(site_tab), 8)))
            tagged = site_tab.copy()
            tagged.insert(0, "repeat_bucket", lab)
            repeat_site_frames.append(tagged)
        st.markdown("**Tickets of these sites**")
        st.dataframe(
            ticket_view(part),
            use_container_width=True,
            height=min(420, 48 + 32 * min(n_tt, 11)),
        )
        tagged_t = ticket_view(part).copy()
        tagged_t.insert(0, "repeat_bucket", lab)
        repeat_ticket_frames.append(tagged_t)

vc = selected[selected["issue_type"] == "Vendor Change"]
if not vc.empty:
    st.subheader("Vendor Change tickets (this period)")
    st.dataframe(ticket_view(vc), use_container_width=True, height=280)


def report_sheets():
    sheets = {
        "SLA_Buckets": sla_df,
        "Classification": cls_df,
    }
    if not rel_df.empty:
        sheets["Related_To"] = rel_df
    sheets["Repeat"] = rep_df
    tv = ticket_view(selected)
    if not tv.empty:
        sheets["Ticket_Detail"] = tv
    if repeat_site_frames:
        sheets["Repeat_Sites"] = pd.concat(repeat_site_frames, ignore_index=True)
    if repeat_ticket_frames:
        sheets["Repeat_Tickets"] = pd.concat(repeat_ticket_frames, ignore_index=True)
    return sheets


st.markdown("---")
try:
    download_pack(
        f"{partner} Full Performance Report",
        report_sheets(),
        file_stem=f"XTRNATE_{partner}_{str(period_label).replace(' ', '_')}_Report",
        title=f"Partner Performance Report  ·  {partner}",
        subtitle=f"{partner}  •  {period_label}  •  {len(selected)} tickets",
        key="partner_report_dl",
    )
except Exception:
    st.caption("Download prepare skip — page data upar same hai.")

