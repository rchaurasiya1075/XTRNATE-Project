"""Build a Power BI-ready star schema from the active Xtranet dataset."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

import pandas as pd

from utils.data_processing import detect_category, get_summary_stats
from utils.excel_export import excel_bytes

IST = ZoneInfo("Asia/Kolkata")

KEEP = [
    "ticket_id", "site_code", "status", "state", "city", "owner", "isp",
    "submitted_time", "resolved_time", "down_time_min", "resolution_hours",
    "resolution_days", "category", "reason", "reason_clean", "open_hours",
]


def _cols(df: pd.DataFrame, names) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    use = [c for c in names if c in df.columns]
    out = df.loc[:, use].copy()
    return out.loc[:, ~out.columns.duplicated()]


def _sla(h):
    try:
        if h is None or (isinstance(h, float) and pd.isna(h)):
            return "Unknown"
        x = float(h)
    except Exception:
        return "Unknown"
    if x < 2:
        return "< 2 Hrs"
    if x < 4:
        return "< 4 Hrs"
    if x < 8:
        return "< 8 Hrs"
    if x < 24:
        return "< 24 Hrs"
    if x < 48:
        return "24-48 Hrs"
    if x < 72:
        return "48-72 Hrs"
    return "> 72 Hrs"


def build_model(closed, opened=None, *, project="Xtranet", source="Google Sheet"):
    closed = closed if closed is not None else pd.DataFrame()
    opened = opened if opened is not None else pd.DataFrame()

    fact_c = _cols(closed, KEEP)
    fact_o = _cols(opened, KEEP)
    if not fact_c.empty:
        fact_c["is_open"] = 0
        fact_c["ticket_set"] = "Closed"
    if not fact_o.empty:
        fact_o["is_open"] = 1
        fact_o["ticket_set"] = "Open"
    fact = pd.concat([d for d in (fact_c, fact_o) if not d.empty], ignore_index=True) if (not fact_c.empty or not fact_o.empty) else pd.DataFrame()

    if not fact.empty:
        if "reason" in fact.columns and "category" not in fact.columns:
            fact["category"] = fact["reason"].map(detect_category)
        elif "reason" in fact.columns:
            blank = fact["category"].isna() | fact["category"].astype(str).isin(["", "nan", "None", "Others"])
            fact.loc[blank, "category"] = fact.loc[blank, "reason"].map(detect_category)
        hrs = None
        if "resolution_hours" in fact.columns:
            hrs = pd.to_numeric(fact["resolution_hours"], errors="coerce")
        elif "down_time_min" in fact.columns:
            hrs = pd.to_numeric(fact["down_time_min"], errors="coerce") / 60.0
        if hrs is not None:
            fact["sla_band"] = hrs.map(_sla)
        fact["project"] = project
        fact["data_source"] = source

    sites = pd.DataFrame()
    if not fact.empty and "site_code" in fact.columns:
        g = fact.copy()
        g["_n"] = 1
        agg = {"_n": "sum"}
        if "down_time_min" in g.columns:
            g["down_time_min"] = pd.to_numeric(g["down_time_min"], errors="coerce")
            agg["down_time_min"] = "sum"
        sites = g.groupby("site_code", dropna=False).agg(agg).reset_index()
        sites = sites.rename(columns={"_n": "tickets", "down_time_min": "down_min"})
        for c in ("state", "city", "isp", "owner"):
            if c in fact.columns:
                first = fact.dropna(subset=[c]).groupby("site_code")[c].agg(
                    lambda s: s.astype(str).value_counts().index[0] if len(s) else ""
                )
                sites = sites.merge(first.reset_index(), on="site_code", how="left")

    daily = pd.DataFrame()
    if not fact.empty and "submitted_time" in fact.columns:
        tmp = fact.copy()
        tmp["Date"] = pd.to_datetime(tmp["submitted_time"], errors="coerce").dt.normalize()
        tmp = tmp.dropna(subset=["Date"])
        daily = tmp.groupby("Date").size().reset_index(name="Tickets")
        if "down_time_min" in tmp.columns:
            hrs = tmp.groupby("Date")["down_time_min"].sum().reset_index()
            hrs["DT_Hrs"] = (pd.to_numeric(hrs["down_time_min"], errors="coerce") / 60).round(2)
            daily = daily.merge(hrs[["Date", "DT_Hrs"]], on="Date", how="left")

    sla = pd.DataFrame()
    cls = pd.DataFrame()
    if not fact.empty and "sla_band" in fact.columns:
        sla = fact["sla_band"].value_counts().rename_axis("SLA").reset_index(name="Tickets")
    if not fact.empty and "category" in fact.columns:
        cls = fact["category"].fillna("Others").astype(str).value_counts().rename_axis("Category").reset_index(name="Tickets")

    stats = get_summary_stats(closed if closed is not None else pd.DataFrame())
    kpi = pd.DataFrame({
        "Metric": ["Project", "Source", "Closed tickets", "Open tickets", "Unique sites", "DT hours", "Avg resolve hrs", "Generated"],
        "Value": [
            project,
            source,
            len(closed) if closed is not None else 0,
            len(opened) if opened is not None else 0,
            int(fact["site_code"].nunique()) if not fact.empty and "site_code" in fact.columns else 0,
            stats.get("total_downtime_hrs", 0),
            stats.get("avg_downtime_hrs", 0),
            datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST"),
        ],
    })

    sheets = {"KPI": kpi}
    if not fact.empty:
        sheets["Fact_Tickets"] = fact
    if not sites.empty:
        sheets["Dim_Site"] = sites
    if not daily.empty:
        sheets["Daily"] = daily
    if not sla.empty:
        sheets["SLA"] = sla
    if not cls.empty:
        sheets["Classification"] = cls
    return sheets


def excel_model(sheets, *, project="Xtranet", source="") -> bytes:
    return excel_bytes(
        sheets,
        title=f"{project}  ·  Power BI model",
        subtitle=f"{source}  •  Fact_Tickets + Dim_Site + Daily + SLA",
        sheet_name="KPI",
    )


def csv_zip(sheets, stem="Xtranet_PowerBI") -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        for name, df in sheets.items():
            if df is None or getattr(df, "empty", True):
                continue
            z.writestr(f"{stem}_{name}.csv", df.to_csv(index=False))
    return buf.getvalue()


def power_query_m(project="Xtranet") -> str:
    return f'''// Xtranet NOC — Power Query for {project}
// 1. Download the Power BI Excel / CSV zip from this app
// 2. Power BI Desktop → Get data → Blank query → Advanced Editor → paste this
// 3. Change FilePath to your saved file

let
    FilePath = "C:\\Xtranet\\{project}_PowerBI.xlsx",
    Source = Excel.Workbook(File.Contents(FilePath), null, true),
    Tickets_Table = Source{{[Item="Fact_Tickets", Kind="Sheet"]}}[Data],
    Promoted = Table.PromoteHeaders(Tickets_Table, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {{
        {{"ticket_id", type text}},
        {{"site_code", type text}},
        {{"is_open", Int64.Type}},
        {{"project", type text}}
    }})
in
    Typed
'''


def google_sheet_m(sheet_url: str) -> str:
    return f'''// Connect Power BI Desktop to the same Google Sheet
let
    Source = Csv.Document(Web.Contents("{sheet_url}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true])
in
    Promoted
'''
