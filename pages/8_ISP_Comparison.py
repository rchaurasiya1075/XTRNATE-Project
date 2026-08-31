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
from utils.isp_deck import build_isp_pptx

st.set_page_config(page_title="ISP Comparison | XTRNATE", page_icon="⚖️", layout="wide")
show_last_update()

st.title("⚖️ ISP Report — HCIN / ONEOTT")
st.caption("Date range • HCIN ya OTT • Last remark se category • Repeat 3M/6M • Excel + PPT")
ensure_ready()


def classify_from_comment(text):
    """Read last enclosure. Others/Third Party tickets split here. One ticket = one bucket."""
    t = str(text or "").lower()
    t = t.replace("close_enclosure", " ").replace("::", " ")
    if "not feasible" in t or "technically not feasible" in t or "rolled back by isp" in t:
        return "NOT Feasible for service"
    if (
        "alternate service provider" in t
        or "provisioned on alternate" in t
        or ("existing operator" in t and "not stable" in t)
        or ("link not stable" in t and "alternate" in t)
    ):
        return "Vendor Change"
    if (
        "post rebooting onu" in t
        or "rebooting onu" in t
        or ("reboot" in t and "onu" in t and ("came live" in t or "working fine" in t))
    ):
        return "ONU/Media converter/ZTE modem Rebooted"
    return detect_category(text)


def unique_cols(cols, available):
    out = []
    for c in cols:
        if c and c in available and c not in out:
            out.append(c)
    return out


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
work = work.loc[:, ~work.columns.duplicated()].copy()
if "submitted_time" in work.columns:
    work["submitted_time"] = pd.to_datetime(work["submitted_time"], errors="coerce")
if "resolved_time" in work.columns:
    work["resolved_time"] = pd.to_datetime(work["resolved_time"], errors="coerce")

remark_col = None
for c in ["reason", "reason_clean", "Last Enclosure Comment(Active)", "Remark"]:
    if c in work.columns:
        remark_col = c
        break
remark_src = work[remark_col] if remark_col else pd.Series("", index=work.index)
if isinstance(remark_src, pd.DataFrame):
    remark_src = remark_src.iloc[:, 0]
work["outage_class"] = remark_src.apply(classify_from_comment)

partner = st.radio("ISP (sirf selected ka report)", ["HCIN", "ONEOTT"], horizontal=True)

min_d = work["submitted_time"].min() if "submitted_time" in work.columns else pd.NaT
max_d = work["submitted_time"].max() if "submitted_time" in work.columns else pd.NaT
today = date.today()
def_start = today - timedelta(days=6)
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

def filter_isp(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if "isp" in df.columns:
        out = df[df["isp"] == partner].copy()
        if not out.empty:
            return out
    if "owner" in df.columns:
        own = df["owner"].astype(str).str.upper()
        key = "HCIN|HICOM" if partner == "HCIN" else "ONEOTT|OTT|CELERITY"
        return df[own.str.contains(key, na=False)].copy()
    return df.copy()

view = filter_isp(period)
hist = filter_isp(work)

open_view = pd.DataFrame()
if open_df is not None and not open_df.empty:
    open_view = filter_isp(open_df)

st.markdown(
    f"### {partner} Report  •  {start_day.strftime('%d-%b-%Y')} se {end_day.strftime('%d-%b-%Y')}  ({date_on})"
)

rep_sum = pd.DataFrame()
rep_detail = pd.DataFrame()
split = pd.DataFrame()
show_s = []

if view.empty:
    st.info("Is date range / ISP pe closed ticket nahi mila.")
    site = pd.DataFrame()
    stt = pd.DataFrame()
    daily = pd.DataFrame()
    cls = pd.DataFrame()
else:
    stats = get_summary_stats(view)
    total = len(view)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Tickets", total)
    k2.metric("Total DT (Hrs)", stats.get("total_downtime_hrs", 0))
    k3.metric("Avg Resolve (Hrs)", stats.get("avg_downtime_hrs", 0))
    k4.metric("Unique Sites", view["site_code"].nunique() if "site_code" in view.columns else 0)
    k5.metric("Open now", len(open_view))

    st.subheader("📊 Classification of Outage (Last Remark se)")
    cls = view["outage_class"].fillna("Others").astype(str).value_counts().reset_index()
    cls.columns = ["Outage Category", "Count"]
    cls["%"] = (cls["Count"] / cls["Count"].sum() * 100).round(1)
    cls.loc[len(cls)] = ["TOTAL", int(cls["Count"].sum()), 100.0]
    st.dataframe(cls, use_container_width=True, hide_index=True)

    specials = ["NOT Feasible for service", "Vendor Change", "ONU/Media converter/ZTE modem Rebooted"]
    s1, s2, s3 = st.columns(3)
    s1.metric("NOT Feasible", int((view["outage_class"] == specials[0]).sum()))
    s2.metric("Vendor Change", int((view["outage_class"] == specials[1]).sum()))
    s3.metric("Device Rebooted", int((view["outage_class"] == specials[2]).sum()))

    st.markdown("#### Others / Third Party se nikaale tickets (comment se)")
    split = view[view["outage_class"].isin(specials)].copy()
    show_s = unique_cols(
        ["ticket_id", "site_code", "state", "outage_class", remark_col or "reason", "submitted_time"],
        split.columns,
    )
    if split.empty:
        st.caption("Is date range mein ye 3 remark nahi mile.")
    else:
        st.dataframe(split[show_s].sort_values("outage_class"), use_container_width=True, height=280)

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

    st.subheader("📅 Daily ticket count")
    daily = view.set_index(time_col).resample("D").size().reset_index()
    daily.columns = ["Date", "Count"]
    fig = px.bar(daily, x="Date", y="Count", text="Count", color="Count")
    fig.update_layout(template="plotly_dark", height=320)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(daily, use_container_width=True, hide_index=True)

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
    else:
        stt = pd.DataFrame()

    st.subheader("📍 Site codes (is period ke)")
    if "site_code" in view.columns:
        site = view.groupby("site_code").agg(
            tickets=("ticket_id", "count") if "ticket_id" in view.columns else ("site_code", "count"),
            state=("state", "first") if "state" in view.columns else ("site_code", "first"),
            last_remark=(remark_col, "last") if remark_col else ("site_code", "first"),
            category=("outage_class", lambda s: ", ".join(sorted(set(s.astype(str))))),
        ).reset_index().sort_values("tickets", ascending=False)
        st.dataframe(site, use_container_width=True, height=360)
    else:
        site = pd.DataFrame()
        st.info("site_code missing")

    st.subheader("🔁 Repeat sites — is period ke sites ka 3 month / 6 month history")
    st.caption("Jo site is selected period mein down gayi, uska 3M aur 6M mein kitni baar down + har ticket ka reason aur downtime")

    if "site_code" not in view.columns or hist.empty:
        st.info("Repeat nikalne ke liye site_code / history nahi mili.")
    else:
        period_sites = view["site_code"].dropna().astype(str).str.upper().unique().tolist()
        look_end = end_ts
        look_3 = look_end - pd.DateOffset(months=3)
        look_6 = look_end - pd.DateOffset(months=6)
        hist2 = hist[hist["site_code"].astype(str).str.upper().isin(period_sites)].copy()
        if time_col in hist2.columns:
            h3 = hist2[(hist2[time_col] >= look_3) & (hist2[time_col] < look_end)]
            h6 = hist2[(hist2[time_col] >= look_6) & (hist2[time_col] < look_end)]
        else:
            h3, h6 = hist2, hist2

        def dt_hrs(row):
            if "down_time_min" in row and pd.notna(row.get("down_time_min")):
                try:
                    return round(float(row["down_time_min"]) / 60.0, 2)
                except Exception:
                    pass
            if pd.notna(row.get("submitted_time")) and pd.notna(row.get("resolved_time")):
                try:
                    return round((row["resolved_time"] - row["submitted_time"]).total_seconds() / 3600.0, 2)
                except Exception:
                    return None
            return None

        rows_sum = []
        rows_det = []
        for sc in period_sites:
            s3 = h3[h3["site_code"].astype(str).str.upper() == sc]
            s6 = h6[h6["site_code"].astype(str).str.upper() == sc]
            s_now = view[view["site_code"].astype(str).str.upper() == sc]

            def pack(sdf):
                reasons = sdf["outage_class"].dropna().astype(str).tolist() if "outage_class" in sdf.columns else []
                remarks = sdf[remark_col].dropna().astype(str).str.slice(0, 80).tolist() if remark_col and remark_col in sdf.columns else []
                hrs = [dt_hrs(r) for _, r in sdf.iterrows()]
                hrs = [x for x in hrs if x is not None]
                return {
                    "count": len(sdf),
                    "reasons": " | ".join(sorted(set(reasons))) if reasons else "",
                    "remarks": " | ".join(remarks[:6]),
                    "total_hrs": round(sum(hrs), 2) if hrs else 0,
                }

            p3, p6, pn = pack(s3), pack(s6), pack(s_now)
            rows_sum.append({
                "Site Code": sc,
                "State": s_now["state"].iloc[0] if "state" in s_now.columns and len(s_now) else "",
                "This period downs": pn["count"],
                "This period DT hrs": pn["total_hrs"],
                "3M downs": p3["count"],
                "3M total DT hrs": p3["total_hrs"],
                "3M reasons": p3["reasons"],
                "6M downs": p6["count"],
                "6M total DT hrs": p6["total_hrs"],
                "6M reasons": p6["reasons"],
            })
            src = s6 if not s6.empty else s3
            for _, r in src.sort_values(time_col if time_col in src.columns else src.columns[0], ascending=False).iterrows():
                rows_det.append({
                    "Site Code": sc,
                    "Incident ID": r.get("ticket_id", ""),
                    "Submitted": r.get("submitted_time", ""),
                    "Resolved": r.get("resolved_time", ""),
                    "Category": r.get("outage_class", ""),
                    "Last Remark": str(r.get(remark_col, r.get("reason", "")) or "")[:160],
                    "Downtime Hrs": dt_hrs(r),
                })

        rep_sum = pd.DataFrame(rows_sum).sort_values("6M downs", ascending=False)
        rep_detail = pd.DataFrame(rows_det)
        m1, m2, m3 = st.columns(3)
        m1.metric("Sites in period", len(period_sites))
        m2.metric("Sites with 2+ in 3M", int((rep_sum["3M downs"] >= 2).sum()) if not rep_sum.empty else 0)
        m3.metric("Sites with 3+ in 6M", int((rep_sum["6M downs"] >= 3).sum()) if not rep_sum.empty else 0)
        st.dataframe(rep_sum, use_container_width=True, height=380)

        pick = st.selectbox("Site ka ticket-wise downtime / reason", ["—"] + list(rep_sum["Site Code"]))
        if pick and pick != "—" and not rep_detail.empty:
            one = rep_detail[rep_detail["Site Code"] == pick]
            st.markdown(f"**{pick}** — har ticket ka downtime + reason")
            st.dataframe(one, use_container_width=True, height=280)
            if one["Downtime Hrs"].notna().any():
                st.caption(f"Total downtime (listed tickets): **{round(one['Downtime Hrs'].fillna(0).sum(), 2)} hrs**")

    st.subheader("📋 Ticket-wise detail (selected period)")
    show_cols = unique_cols(
        [
            "ticket_id", "site_code", "state", "city", "submitted_time", "resolved_time",
            "status", "owner", "isp", "outage_class", remark_col, "reason", "down_time_min",
        ],
        view.columns,
    )
    detail = view.loc[:, show_cols].copy()
    detail = detail.loc[:, ~detail.columns.duplicated()]
    st.dataframe(detail, use_container_width=True, height=420)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        pd.DataFrame({
            "Field": ["ISP", "From", "To", "Date on", "Tickets", "Open now"],
            "Value": [partner, str(start_day), str(end_day), date_on, total, len(open_view)],
        }).to_excel(w, index=False, sheet_name="Cover")
        cls.to_excel(w, index=False, sheet_name="Outage_Class")
        if not split.empty and show_s:
            split[show_s].to_excel(w, index=False, sheet_name="Others_Split")
        daily.to_excel(w, index=False, sheet_name="Daily")
        if not stt.empty:
            stt.to_excel(w, index=False, sheet_name="State")
        if not site.empty:
            site.to_excel(w, index=False, sheet_name="Sites")
        if not rep_sum.empty:
            rep_sum.to_excel(w, index=False, sheet_name="Repeat_3M_6M")
        if not rep_detail.empty:
            rep_detail.to_excel(w, index=False, sheet_name="Repeat_Tickets")
        detail.to_excel(w, index=False, sheet_name="Tickets")

    meta = {
        "isp": partner,
        "from": start_day.strftime("%d %b %Y"),
        "to": end_day.strftime("%d %b %Y"),
        "date_on": date_on,
        "tickets": total,
        "dt_hrs": stats.get("total_downtime_hrs", 0),
        "avg_hrs": stats.get("avg_downtime_hrs", 0),
        "sites": int(view["site_code"].nunique()) if "site_code" in view.columns else 0,
        "open": len(open_view),
    }
    try:
        ppt_bytes = build_isp_pptx(meta, cls, daily, stt, site)
    except Exception as e:
        ppt_bytes = None
        st.warning(f"PPT build issue: {e}")

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            f"📥 Excel — {partner} full data",
            data=buf.getvalue(),
            file_name=f"XTRNATE_{partner}_{start_day}_to_{end_day}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d2:
        if ppt_bytes:
            st.download_button(
                f"📊 PPT — {partner} review deck",
                data=ppt_bytes,
                file_name=f"XTRNATE_{partner}_{start_day}_to_{end_day}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )

st.markdown("---")
st.subheader("Current open (selected ISP)")
if open_view is None or open_view.empty:
    st.info("Is ISP pe current open nahi.")
else:
    oc = unique_cols(
        ["ticket_id", "site_code", "status", "state", "submitted_time", "open_hours", "reason"],
        open_view.columns,
    )
    st.dataframe(open_view[oc], use_container_width=True, height=280)
