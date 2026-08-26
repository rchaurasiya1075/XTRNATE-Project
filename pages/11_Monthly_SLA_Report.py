import calendar
from datetime import date, datetime
from io import BytesIO
import os
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.auto_load import auto_load_tickets

st.set_page_config(
    page_title="Monthly SLA Report | XTRNATE", page_icon="📅", layout="wide"
)

st.title("📅 Monthly SLA Report")
st.caption(
    "Daily resolve counts by time bucket • HCIN / OTT split • Weekend & holiday logic"
)

if st.session_state.get("closed_df") is None:
    with st.spinner("Google Sheet se data load ho raha hai..."):
        auto_load_tickets()

closed_df = st.session_state.get("closed_df")
if closed_df is None or closed_df.empty:
    st.warning(
        "Closed data nahi mila. Sheet share check karo ya Home se Refresh dabao."
    )
    st.stop()

df = closed_df.copy()

if "ticket_id" in df.columns:
    df = df.drop_duplicates(subset=["ticket_id"], keep="first")

if "submitted_time" not in df.columns or "resolved_time" not in df.columns:
    st.error("submitted_time / resolved_time missing")
    st.stop()

df = df.dropna(subset=["submitted_time", "resolved_time"])
df["resolution_hours"] = (
    df["resolved_time"] - df["submitted_time"]
).dt.total_seconds() / 3600.0
df = df[df["resolution_hours"] >= 0].copy()
df["resolved_date"] = df["resolved_time"].dt.normalize().dt.date
df["resolved_month"] = df["resolved_time"].dt.strftime("%Y-%m")


def sla_bucket(hrs):
    if hrs < 2:
        return "<2"
    if hrs < 4:
        return "<4"
    if hrs < 8:
        return "<8"
    if hrs < 24:
        return "<24"
    if hrs < 48:
        return ">24"
    if hrs < 72:
        return ">48"
    return ">72"


df["bucket"] = df["resolution_hours"].apply(sla_bucket)


def partner_type(row):
    owner = str(row.get("owner", "") or "").upper()
    isp = str(row.get("isp", "") or "").upper()
    text = f"{owner} {isp}"
    if "HCIN" in text:
        return "HCIN"
    if any(x in text for x in ["ONEOTT", "OTT", "CELERITY"]):
        return "OTT"
    return "OTHER"


df["partner"] = df.apply(partner_type, axis=1)


def is_holiday(d: date) -> bool:
    wd = d.weekday()
    if wd == 6:
        return True
    if wd == 5:
        day = d.day
        if 8 <= day <= 14 or 22 <= day <= 28:
            return True
    return False


months = sorted(df["resolved_month"].dropna().unique().tolist(), reverse=True)
if not months:
    st.info("Koi valid resolved date nahi mili.")
    st.stop()

selected_month = st.selectbox("Select Month (separate monthly sheet)", months)

try:
    y, m = map(int, selected_month.split("-"))
except Exception:
    y, m = datetime.now().year, datetime.now().month

month_df = df[df["resolved_month"] == selected_month].copy()
days_in_month = calendar.monthrange(y, m)[1]
all_dates = [date(y, m, d) for d in range(1, days_in_month + 1)]

num_cols = [
    "< 2 HRS",
    "< 4 HRS",
    "< 8 HRS",
    "< 24 HRS",
    "> 24 HRS",
    "> 48 HRS",
    "> 72 HRS",
    "TOTAL RESOLVED",
    "HCIN (<24H)",
    "HCIN (>24H)",
    "OTT (<24H)",
    "OTT (>24H)",
]

rows = []
for d in all_dates:
    date_str = d.strftime("%d-%b-%Y")
    if is_holiday(d):
        row = {"DATE": date_str, "_holiday": True}
        row["< 2 HRS"] = "HOLIDAY"
        for c in num_cols[1:]:
            row[c] = ""
        rows.append(row)
        continue

    day = month_df[month_df["resolved_date"] == d]
    b = day["bucket"].value_counts()
    hcin = day[day["partner"] == "HCIN"]
    ott = day[day["partner"] == "OTT"]

    rows.append({
        "DATE": date_str,
        "< 2 HRS": int(b.get("<2", 0)),
        "< 4 HRS": int(b.get("<4", 0)),
        "< 8 HRS": int(b.get("<8", 0)),
        "< 24 HRS": int(b.get("<24", 0)),
        "> 24 HRS": int(b.get(">24", 0)),
        "> 48 HRS": int(b.get(">48", 0)),
        "> 72 HRS": int(b.get(">72", 0)),
        "TOTAL RESOLVED": int(len(day)),
        "HCIN (<24H)": (
            int((hcin["resolution_hours"] < 24).sum()) if len(hcin) else 0
        ),
        "HCIN (>24H)": (
            int((hcin["resolution_hours"] >= 24).sum()) if len(hcin) else 0
        ),
        "OTT (<24H)": (
            int((ott["resolution_hours"] < 24).sum()) if len(ott) else 0
        ),
        "OTT (>24H)": (
            int((ott["resolution_hours"] >= 24).sum()) if len(ott) else 0
        ),
        "_holiday": False,
    })

daily = pd.DataFrame(rows)


def to_num(val):
    try:
        return int(val)
    except Exception:
        return 0


work = daily[~daily["_holiday"]].copy()
totals = {c: int(work[c].map(to_num).sum()) for c in num_cols}

# KPI calculations
hcin_kpi = totals["HCIN (<24H)"] + totals["HCIN (>24H)"]
ott_kpi = totals["OTT (<24H)"] + totals["OTT (>24H)"]

# KPI cards UI
st.markdown("### KPI Summary")
k1, k2, k3 = st.columns(3)

with k1:
    st.markdown(
        f"""
    <div style="background:linear-gradient(135deg,#EFF6FF,#DBEAFE);border:2px solid #3B82F6;border-radius:14px;padding:1.3rem;text-align:center;box-shadow:0 4px 14px rgba(59,130,246,0.25);">
        <div style="color:#1E40AF;font-weight:700;letter-spacing:0.5px;">📊 TOTAL RESOLVED</div>
        <div style="color:#1E3A8A;font-weight:800;font-size:2.2rem;margin-top:4px;">{totals['TOTAL RESOLVED']}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with k2:
    st.markdown(
        f"""
    <div style="background:linear-gradient(135deg,#ECFDF5,#D1FAE5);border:2px solid #10B981;border-radius:14px;padding:1.3rem;text-align:center;box-shadow:0 4px 14px rgba(16,185,129,0.25);">
        <div style="color:#047857;font-weight:700;letter-spacing:0.5px;">🏢 HCIN TOTAL</div>
        <div style="color:#065F46;font-weight:800;font-size:2.2rem;margin-top:4px;">{hcin_kpi}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        f"""
    <div style="background:linear-gradient(135deg,#F3E8FF,#E9D5FF);border:2px solid #A855F7;border-radius:14px;padding:1.3rem;text-align:center;box-shadow:0 4px 14px rgba(168,85,247,0.25);">
        <div style="color:#6B21A8;font-weight:700;letter-spacing:0.5px;">🌐 OTT / CELERITY TOTAL</div>
        <div style="color:#581C87;font-weight:800;font-size:2.2rem;margin-top:4px;">{ott_kpi}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("---")
st.subheader(f"Daily Sheet — {selected_month}")

display_cols = ["DATE"] + num_cols
show = daily[display_cols].copy()

for c in num_cols:
    show[c] = show[c].apply(
        lambda x: x if str(x) == "HOLIDAY" or str(x) == "" else to_num(x)
    )

total_row = {"DATE": "TOTAL"}
for c in num_cols:
    total_row[c] = totals[c]
show = pd.concat([show, pd.DataFrame([total_row])], ignore_index=True)


def style_sla_table(df_table):
    green_cols = ["< 2 HRS", "< 4 HRS", "< 8 HRS"]
    yellow_cols = ["< 24 HRS"]
    red_cols = ["> 24 HRS", "> 48 HRS", "> 72 HRS"]

    def apply_style(row):
        styles = [""] * len(row)
        is_total = str(row["DATE"]).upper() == "TOTAL"
        is_hol = any(str(row.get(c, "")) == "HOLIDAY" for c in green_cols)

        if is_total:
            return [
                "background-color: #334155; color: #FFFFFF; font-weight: 800;"
                " border: 1px solid #0F172A; text-align: center;"
            ] * len(row)

        if is_hol:
            return [
                "background-color: #FEE2E2; color: #991B1B; font-weight: 700;"
                " border: 1px solid #FECACA; text-align: center;"
            ] * len(row)

        styles[0] = (
            "background-color: #F1F5F9; color: #0F172A; font-weight: 700;"
            " border: 1px solid #CBD5E1; text-align: center;"
        )

        for i, col in enumerate(df_table.columns):
            if col == "DATE":
                continue
            val = row[col]
            try:
                num = int(val)
            except Exception:
                num = 0

            base = (
                "border: 1px solid #E2E8F0; text-align: center; font-weight:"
                " 600;"
            )

            if col in green_cols:
                if num == 0:
                    styles[i] = (
                        base + " background-color: #F8FAFC; color: #94A3B8;"
                    )
                else:
                    styles[i] = (
                        base
                        + " background-color: #ECFDF5; color: #047857;"
                        " font-weight: 800;"
                    )
            elif col in yellow_cols:
                if num == 0:
                    styles[i] = (
                        base + " background-color: #F8FAFC; color: #94A3B8;"
                    )
                else:
                    styles[i] = (
                        base
                        + " background-color: #FFFBEB; color: #B45309;"
                        " font-weight: 800;"
                    )
            elif col in red_cols:
                if num == 0:
                    styles[i] = (
                        base + " background-color: #F8FAFC; color: #94A3B8;"
                    )
                else:
                    styles[i] = (
                        base
                        + " background-color: #FFF1F2; color: #BE123C;"
                        " font-weight: 800;"
                    )
            elif col == "TOTAL RESOLVED":
                styles[i] = (
                    base
                    + " background-color: #E0F2FE; color: #0369A1; font-weight:"
                    " 800;"
                )
            elif col == "HCIN (<24H)":
                styles[i] = base + (
                    " background-color: #ECFDF5; color: #047857; font-weight:"
                    " 800;"
                    if num
                    else " background-color: #F8FAFC; color: #94A3B8;"
                )
            elif col == "HCIN (>24H)":
                styles[i] = base + (
                    " background-color: #FFF1F2; color: #BE123C; font-weight:"
                    " 800;"
                    if num
                    else " background-color: #F8FAFC; color: #94A3B8;"
                )
            elif col == "OTT (<24H)":
                styles[i] = base + (
                    " background-color: #F3E8FF; color: #6B21A8; font-weight:"
                    " 800;"
                    if num
                    else " background-color: #F8FAFC; color: #94A3B8;"
                )
            elif col == "OTT (>24H)":
                styles[i] = base + (
                    " background-color: #FFF1F2; color: #BE123C; font-weight:"
                    " 800;"
                    if num
                    else " background-color: #F8FAFC; color: #94A3B8;"
                )
            else:
                styles[i] = base

        return styles

    styled = df_table.style.apply(apply_style, axis=1)
    styled = styled.set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#0F172A"),
                ("color", "#FFFFFF"),
                ("font-weight", "800"),
                ("text-align", "center"),
                ("border", "1px solid #475569"),
                ("padding", "10px 6px"),
                ("font-size", "12px"),
            ],
        },
        {
            "selector": "td",
            "props": [("padding", "8px 6px"), ("font-size", "13px")],
        },
        {
            "selector": "table",
            "props": [
                ("border-collapse", "collapse"),
                ("width", "100%"),
                ("border", "2px solid #334155"),
            ],
        },
    ])
    return styled


st.dataframe(
    style_sla_table(show), use_container_width=True, height=560, hide_index=True
)

st.caption(
    "🟢 Green = fast (<8h)  |  🟡 Yellow = <24h  |  🔴 Red = late (>24h)  | "
    " HOLIDAY = Sun + 2nd/4th Sat  |  Dark row = TOTAL"
)

# Charts Section
st.markdown("---")
col1, col2 = st.columns(2)

chart_src = work.copy()
for c in num_cols:
    chart_src[c] = chart_src[c].map(to_num)

with col1:
    if not chart_src.empty:
        fig = px.bar(
            chart_src,
            x="DATE",
            y="TOTAL RESOLVED",
            text="TOTAL RESOLVED",
            color="TOTAL RESOLVED",
            color_continuous_scale="Blues",
            title="Daily Total Resolved",
        )
        fig.update_layout(
            template="plotly_dark", height=360, xaxis_tickangle=-45
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    bucket_order = [
        "< 2 HRS",
        "< 4 HRS",
        "< 8 HRS",
        "< 24 HRS",
        "> 24 HRS",
        "> 48 HRS",
        "> 72 HRS",
    ]
    bdf = pd.DataFrame(
        {"Bucket": bucket_order, "Count": [totals[b] for b in bucket_order]}
    )
    fig = px.bar(
        bdf,
        x="Bucket",
        y="Count",
        text="Count",
        color="Count",
        color_continuous_scale="Teal",
        title="Month SLA Bucket Totals",
    )
    fig.update_layout(template="plotly_dark", height=360)
    st.plotly_chart(fig, use_container_width=True)

comp = pd.DataFrame({
    "Segment": ["HCIN (<24H)", "HCIN (>24H)", "OTT (<24H)", "OTT (>24H)"],
    "Count": [
        totals["HCIN (<24H)"],
        totals["HCIN (>24H)"],
        totals["OTT (<24H)"],
        totals["OTT (>24H)"],
    ],
})
fig = px.bar(
    comp,
    x="Segment",
    y="Count",
    text="Count",
    color="Count",
    color_continuous_scale="Purples",
    title="HCIN vs OTT (<24h / >24h)",
)
fig.update_layout(template="plotly_dark", height=360)
st.plotly_chart(fig, use_container_width=True)


def to_excel():
    out = BytesIO()
    export = show.copy()

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        sheet_name = selected_month[:31]
        export.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        worksheet.hide_gridlines(2)

        # Excel Dark/Modern Formats
        header_fmt = workbook.add_format({
            "bg_color": "#0F172A",
            "font_color": "#F8FAFC",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#334155",
            "font_name": "Segoe UI",
            "font_size": 10,
        })

        date_col_fmt = workbook.add_format({
            "bg_color": "#F1F5F9",
            "font_color": "#0F172A",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#CBD5E1",
            "font_name": "Segoe UI",
            "font_size": 10,
        })

        total_row_fmt = workbook.add_format({
            "bg_color": "#1E293B",
            "font_color": "#38BDF8",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#0F172A",
            "font_name": "Segoe UI",
            "font_size": 10,
        })

        holiday_fmt = workbook.add_format({
            "bg_color": "#FEE2E2",
            "font_color": "#991B1B",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#FECACA",
            "font_name": "Segoe UI",
            "font_size": 10,
        })

        green_fmt = workbook.add_format({
            "bg_color": "#DCFCE7",
            "font_color": "#15803D",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        yellow_fmt = workbook.add_format({
            "bg_color": "#FEF3C7",
            "font_color": "#B45309",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        red_fmt = workbook.add_format({
            "bg_color": "#FFE4E6",
            "font_color": "#BE123C",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        blue_total_fmt = workbook.add_format({
            "bg_color": "#E0F2FE",
            "font_color": "#0369A1",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        purple_fmt = workbook.add_format({
            "bg_color": "#F3E8FF",
            "font_color": "#6B21A8",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        zero_fmt = workbook.add_format({
            "bg_color": "#F8FAFC",
            "font_color": "#94A3B8",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
        })

        # Apply Headers
        worksheet.set_row(0, 24)
        for col_num, col_name in enumerate(export.columns):
            worksheet.write(0, col_num, col_name, header_fmt)

        green_cols = ["< 2 HRS", "< 4 HRS", "< 8 HRS"]
        yellow_cols = ["< 24 HRS"]
        red_cols = [
            "> 24 HRS",
            "> 48 HRS",
            "> 72 HRS",
            "HCIN (>24H)",
            "OTT (>24H)",
        ]

        for row_idx, row in export.iterrows():
            excel_row = row_idx + 1
            worksheet.set_row(excel_row, 20)
            is_total = str(row["DATE"]).upper() == "TOTAL"
            is_holiday_row = str(row.get("< 2 HRS", "")) == "HOLIDAY"

            for col_idx, col_name in enumerate(export.columns):
                val = row[col_name]

                if is_total:
                    worksheet.write(excel_row, col_idx, val, total_row_fmt)
                    continue

                if is_holiday_row:
                    worksheet.write(excel_row, col_idx, val, holiday_fmt)
                    continue

                if col_name == "DATE":
                    worksheet.write(excel_row, col_idx, val, date_col_fmt)
                    continue

                try:
                    num_val = int(val)
                except Exception:
                    num_val = 0

                if num_val == 0 and val != "HOLIDAY":
                    worksheet.write(excel_row, col_idx, num_val, zero_fmt)
                elif col_name in green_cols or col_name == "HCIN (<24H)":
                    worksheet.write(excel_row, col_idx, num_val, green_fmt)
                elif col_name in yellow_cols:
                    worksheet.write(excel_row, col_idx, num_val, yellow_fmt)
                elif col_name in red_cols:
                    worksheet.write(excel_row, col_idx, num_val, red_fmt)
                elif col_name == "TOTAL RESOLVED":
                    worksheet.write(excel_row, col_idx, num_val, blue_total_fmt)
                elif col_name == "OTT (<24H)":
                    worksheet.write(excel_row, col_idx, num_val, purple_fmt)
                else:
                    worksheet.write(excel_row, col_idx, val, zero_fmt)

        # Auto-fit Column Widths
        for col_idx, col_name in enumerate(export.columns):
            max_len = (
                max(export[col_name].astype(str).map(len).max(), len(col_name))
                + 4
            )
            worksheet.set_column(col_idx, col_idx, max(max_len, 13))

        # Executive Summary KPI Sheet
        summary = pd.DataFrame({
            "KPI Metric": [
                "TOTAL RESOLVED",
                "HCIN TOTAL",
                "OTT / CELERITY TOTAL",
            ],
            "Count": [totals["TOTAL RESOLVED"], hcin_kpi, ott_kpi],
        })
        summary.to_excel(writer, index=False, sheet_name="Executive Summary")

        kpi_ws = writer.sheets["Executive Summary"]
        kpi_ws.hide_gridlines(2)
        kpi_ws.set_row(0, 24)

        kpi_val_fmt = workbook.add_format({
            "bg_color": "#F0F9FF",
            "font_color": "#0284C7",
            "bold": True,
            "align": "center",
            "border": 1,
            "border_color": "#BAE6FD",
            "font_name": "Segoe UI",
            "font_size": 11,
        })
        kpi_lbl_fmt = workbook.add_format({
            "bg_color": "#F8FAFC",
            "font_color": "#334155",
            "bold": True,
            "align": "left",
            "border": 1,
            "border_color": "#E2E8F0",
            "font_name": "Segoe UI",
            "font_size": 10,
        })

        for col_num, col_name in enumerate(summary.columns):
            kpi_ws.write(0, col_num, col_name, header_fmt)

        for r_idx, r in summary.iterrows():
            kpi_ws.set_row(r_idx + 1, 22)
            kpi_ws.write(r_idx + 1, 0, r["KPI Metric"], kpi_lbl_fmt)
            kpi_ws.write(r_idx + 1, 1, r["Count"], kpi_val_fmt)

        kpi_ws.set_column(0, 0, 28)
        kpi_ws.set_column(1, 1, 16)

    return out.getvalue()


st.download_button(
    f"📥 Download {selected_month} Monthly Sheet (Excel)",
    data=to_excel(),
    file_name=f"XTRNATE_SLA_{selected_month}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
