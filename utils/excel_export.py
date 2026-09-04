"""XTRNATE branded Excel export — navy headers, borders, zebra, totals, freeze."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")

NAVY = "#0B1F3A"
GOLD = "#B8860B"
SKY = "#0B1F3A"
CYAN = "#E8D5A3"
WHITE = "#FFFFFF"
INK = "#1C1917"
MUTED = "#78716C"
ALT = "#F6F3EE"
ROW = "#FFFFFF"
BORDER = "#D6D3D1"
GREEN_BG, GREEN_FG = "#ECFDF3", "#166534"
YELLOW_BG, YELLOW_FG = "#FFFBEB", "#92400E"
RED_BG, RED_FG = "#FEF2F2", "#9F1239"
TOTAL_BG, TOTAL_FG = "#0B1F3A", "#F5E6C8"
TITLE_SUB_BG = "#132A4A"

TAB_COLORS = ["0B1F3A", "B8860B", "1E3A5F", "3F3F46", "0F766E", "9A3412"]

WRAP_HINTS = (
    "reason", "root_cause", "problem_reported", "final_action", "explanation",
    "remark", "address", "note", "comment", "enclosure", "last_enclosure",
)

GREEN_HINTS = ("<2", "< 2", "<4", "< 4", "<8", "< 8")
YELLOW_HINTS = ("<24", "< 24", "12-24")
RED_HINTS = (">24", "> 24", ">48", "> 48", ">72", "> 72", "more than 72", "24-48", "48-72")


def _safe_sheet(name: str) -> str:
    bad = set(r'[]:*?/\\')
    s = "".join("_" if c in bad else c for c in str(name or "Sheet"))
    s = s.strip()[:31] or "Sheet"
    return s


def _unique_sheet(name: str, used: set) -> str:
    base = _safe_sheet(name)
    n = base
    i = 2
    while n.lower() in used:
        suffix = f"_{i}"
        n = (base[: 31 - len(suffix)] + suffix)
        i += 1
    used.add(n.lower())
    return n


def _prep(df) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if isinstance(df, pd.Series):
        df = df.to_frame()
    if hasattr(df, "data") and not isinstance(df, pd.DataFrame):
        try:
            df = df.data
        except Exception:
            pass
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    out = out.loc[:, ~out.columns.duplicated()].copy()
    for c in out.columns:
        s = out[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            s = pd.to_datetime(s, errors="coerce")
            try:
                if getattr(s.dt, "tz", None) is not None:
                    s = s.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            except Exception:
                try:
                    s = s.dt.tz_localize(None)
                except Exception:
                    pass
            out[c] = s
    return out.reset_index(drop=True)


def _is_total_label(val) -> bool:
    t = str(val or "").strip().lower().replace("_", " ")
    return t in ("grand total", "total", "grand tot")


def _col_tone(col_name: str) -> str | None:
    n = str(col_name).lower()
    if any(h in n for h in GREEN_HINTS):
        return "green"
    if any(h in n for h in YELLOW_HINTS):
        return "yellow"
    if any(h in n for h in RED_HINTS) or "(>24" in n:
        return "red"
    if "(<24" in n:
        return "green"
    if "penalty" in n or "holiday minus" in n:
        return "red"
    if "adjusted dt" in n:
        return "green"
    return None


def _is_wrap_col(name: str) -> bool:
    n = str(name).lower()
    return any(h in n for h in WRAP_HINTS)


def _cell_python(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return None
        ts = val.to_pydatetime()
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.replace(tzinfo=None)
        return ts
    if isinstance(val, datetime):
        return val.replace(tzinfo=None) if val.tzinfo else val
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, (np.bool_, bool)):
        return "Yes" if bool(val) else "No"
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if np.isnan(val):
            return None
        return float(val)
    if isinstance(val, str):
        t = val.strip()
        if t.lower() in ("nan", "none", "nat", "<na>"):
            return None
        return val
    return val


def _formats(wb):
    base = {
        "font_name": "Calibri",
        "font_size": 10,
        "border": 1,
        "border_color": BORDER,
        "valign": "vcenter",
        "text_wrap": True,
    }

    def f(**kw):
        d = dict(base)
        d.update(kw)
        return wb.add_format(d)

    return {
        "title": wb.add_format({
            "font_name": "Calibri", "font_size": 18, "bold": True,
            "font_color": WHITE, "bg_color": NAVY, "align": "left", "valign": "vcenter",
        }),
        "gold": wb.add_format({"bg_color": GOLD}),
        "sub": wb.add_format({
            "font_name": "Calibri", "font_size": 9,
            "font_color": "#E8D5A3", "bg_color": TITLE_SUB_BG, "align": "left", "valign": "vcenter",
        }),
        "header": f(bold=True, font_color=WHITE, bg_color=NAVY, align="center", font_size=10),
        "cell": f(font_color=INK, bg_color=ROW, align="left", font_size=10),
        "cell_alt": f(font_color=INK, bg_color=ALT, align="left", font_size=10),
        "cell_c": f(font_color=INK, bg_color=ROW, align="center", font_size=10),
        "cell_alt_c": f(font_color=INK, bg_color=ALT, align="center", font_size=10),
        "num": f(font_color=INK, bg_color=ROW, align="center", num_format="#,##0"),
        "num_alt": f(font_color=INK, bg_color=ALT, align="center", num_format="#,##0"),
        "num2": f(font_color=INK, bg_color=ROW, align="center", num_format="#,##0.00"),
        "num2_alt": f(font_color=INK, bg_color=ALT, align="center", num_format="#,##0.00"),
        "date": f(font_color=INK, bg_color=ROW, align="center", num_format="dd-mmm-yyyy hh:mm"),
        "date_alt": f(font_color=INK, bg_color=ALT, align="center", num_format="dd-mmm-yyyy hh:mm"),
        "day": f(font_color=INK, bg_color=ROW, align="center", num_format="dd-mmm-yyyy"),
        "day_alt": f(font_color=INK, bg_color=ALT, align="center", num_format="dd-mmm-yyyy"),
        "zero": f(font_color=MUTED, bg_color=ROW, align="center"),
        "zero_alt": f(font_color=MUTED, bg_color=ALT, align="center"),
        "label": f(font_color=INK, bg_color=ROW, align="left", bold=True),
        "label_alt": f(font_color=INK, bg_color=ALT, align="left", bold=True),
        "total": f(bold=True, font_color=TOTAL_FG, bg_color=TOTAL_BG, align="center"),
        "total_l": f(bold=True, font_color=TOTAL_FG, bg_color=TOTAL_BG, align="left"),
        "green": f(bold=True, font_color=GREEN_FG, bg_color=GREEN_BG, align="center"),
        "yellow": f(bold=True, font_color=YELLOW_FG, bg_color=YELLOW_BG, align="center"),
        "red": f(bold=True, font_color=RED_FG, bg_color=RED_BG, align="center"),
        "kpi_l": f(bold=True, font_color="#44403C", bg_color="#F6F3EE", align="left"),
        "kpi_v": f(bold=True, font_color=NAVY, bg_color="#F5E6C8", align="center", font_size=12),
    }


def _pick_fmt(fmt, *, alt, is_total, col_name, val, first_col):
    if is_total:
        return fmt["total_l"] if first_col else fmt["total"]
    tone = _col_tone(col_name)
    numeric = isinstance(val, (int, float)) and not isinstance(val, bool)
    if tone and numeric and val not in (0, 0.0):
        return fmt[tone]
    if first_col and not isinstance(val, (int, float, datetime, date)):
        return fmt["label_alt"] if alt else fmt["label"]
    if val in (0, 0.0) and numeric:
        return fmt["zero_alt"] if alt else fmt["zero"]
    if isinstance(val, datetime):
        return fmt["date_alt"] if alt else fmt["date"]
    if isinstance(val, date):
        return fmt["day_alt"] if alt else fmt["day"]
    if isinstance(val, float):
        return fmt["num2_alt"] if alt else fmt["num2"]
    if isinstance(val, int):
        return fmt["num_alt"] if alt else fmt["num"]
    return (fmt["cell_alt_c"] if alt else fmt["cell_c"]) if not _is_wrap_col(col_name) else (
        fmt["cell_alt"] if alt else fmt["cell"]
    )


def _col_width(name, series) -> float:
    if _is_wrap_col(name):
        return 42
    try:
        sample = series.astype(str).head(120).map(lambda x: len(x) if x not in ("nan", "None", "NaT") else 0)
        m = int(sample.max()) if len(sample) else 0
    except Exception:
        m = 10
    w = max(len(str(name)), m) + 3
    return float(min(max(w, 12), 36))


def write_sheet(writer, df, sheet_name, *, title="", subtitle="", tab_color=None, kpi=False):
    wb = writer.book
    fmt = writer.book._xtrnate_fmt if hasattr(writer.book, "_xtrnate_fmt") else None
    if fmt is None:
        fmt = _formats(wb)
        writer.book._xtrnate_fmt = fmt

    data = _prep(df)
    cols = list(data.columns)
    ncols = max(len(cols), 1)
    ws = wb.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = ws
    if tab_color:
        try:
            ws.set_tab_color("#" + tab_color if not str(tab_color).startswith("#") else tab_color)
        except Exception:
            pass

    ws.hide_gridlines(2)
    ws.set_default_row(18)
    ws.set_row(0, 30)
    ws.set_row(1, 4)
    ws.set_row(2, 18)
    last_col = max(ncols - 1, 0)
    banner = title or sheet_name
    stamp = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST")
    sub = f"{subtitle}  •  Generated {stamp}" if subtitle else f"XTRNATE NOC  •  Confidential  •  {stamp}"

    def _merge_or_write(r, text, style):
        if last_col == 0:
            ws.write(r, 0, text, style)
        else:
            ws.merge_range(r, 0, r, last_col, text, style)

    _merge_or_write(0, banner, fmt["title"])
    for c in range(ncols):
        ws.write_blank(1, c, None, fmt["gold"])
    _merge_or_write(2, sub, fmt["sub"])

    header_row = 3
    ws.set_row(header_row, 24)
    for c, name in enumerate(cols):
        ws.write(header_row, c, str(name), fmt["header"])
        ws.set_column(c, c, _col_width(name, data[name] if name in data.columns else pd.Series(dtype=object)))

    if data.empty:
        ws.freeze_panes(header_row + 1, 0)
        return ws

    for ridx, row in data.iterrows():
        excel_r = header_row + 1 + int(ridx)
        alt = (int(ridx) % 2 == 1)
        first_val = row.iloc[0] if len(row) else ""
        is_total = _is_total_label(first_val)
        if is_total:
            ws.set_row(excel_r, 22)
        for cidx, name in enumerate(cols):
            val = _cell_python(row.iloc[cidx] if cidx < len(row) else None)
            cell_fmt = _pick_fmt(
                fmt, alt=alt, is_total=is_total, col_name=name, val=val, first_col=(cidx == 0)
            )
            if kpi and cidx == 0 and not is_total:
                cell_fmt = fmt["kpi_l"]
            if kpi and cidx == 1 and not is_total:
                cell_fmt = fmt["kpi_v"]
            if val is None:
                ws.write_blank(excel_r, cidx, None, cell_fmt)
            elif isinstance(val, datetime):
                ws.write_datetime(excel_r, cidx, val, cell_fmt)
            elif isinstance(val, date) and not isinstance(val, datetime):
                ws.write_datetime(excel_r, cidx, datetime(val.year, val.month, val.day), cell_fmt)
            else:
                try:
                    ws.write(excel_r, cidx, val, cell_fmt)
                except Exception:
                    ws.write(excel_r, cidx, str(val), cell_fmt)

    last_data = header_row + len(data)
    ws.freeze_panes(header_row + 1, 1 if ncols > 3 else 0)
    ws.autofilter(header_row, 0, last_data, last_col)
    ws.repeat_rows(0, header_row)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.set_paper(9)
    ws.set_margins(0.5, 0.5, 0.7, 0.6)
    ws.set_header("&L&B XTRNATE NOC&R&D")
    ws.set_footer("&C&8XTRNATE NOC  |  Confidential  |  &A  |  Page &P of &N")
    return ws


def excel_bytes(
    sheets,
    *,
    title="XTRNATE Report",
    subtitle="",
    sheet_name="Report",
):
    """Build a branded .xlsx.

    sheets: DataFrame  OR  {name: DataFrame}  OR  list[(name, DataFrame)]
    """
    if isinstance(sheets, pd.DataFrame) or isinstance(sheets, pd.Series):
        items = [(sheet_name, sheets)]
    elif isinstance(sheets, dict):
        items = list(sheets.items())
    else:
        items = list(sheets)

    clean = []
    for name, df in items:
        if df is None:
            continue
        if isinstance(df, pd.DataFrame) and df.empty and len(df.columns) == 0:
            continue
        clean.append((str(name), df))
    if not clean:
        clean = [("Report", pd.DataFrame({"Info": ["No rows for this export"]}))]

    out = BytesIO()
    used = set()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        try:
            writer.book.set_properties({
                "title": title,
                "author": "XTRNATE NOC",
                "company": "XTRNATE",
                "comments": subtitle or "XTRNATE performance report",
            })
        except Exception:
            pass
        for i, (name, df) in enumerate(clean):
            sn = _unique_sheet(name, used)
            kpi = str(name).lower() in ("cover", "snapshot", "kpi", "executive summary") or (
                isinstance(df, pd.DataFrame) and list(df.columns)[:2] in (["Metric", "Count"], ["Field", "Value"], ["KPI Metric", "Count"])
            )
            write_sheet(
                writer,
                df,
                sn,
                title=title if i == 0 else f"{title}  ·  {name}",
                subtitle=subtitle,
                tab_color=TAB_COLORS[i % len(TAB_COLORS)],
                kpi=kpi,
            )
    return out.getvalue()
