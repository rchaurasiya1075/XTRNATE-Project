"""Professional PDF export — navy / gold, print-ready tables."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
from fpdf import FPDF

IST = ZoneInfo("Asia/Kolkata")
NAVY = (11, 31, 58)
GOLD = (184, 134, 11)
INK = (28, 25, 23)
ALT = (246, 243, 238)
MUTED = (120, 113, 108)
WHITE = (255, 255, 255)


def _txt(val) -> str:
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return ""
        return val.strftime("%d-%b-%Y %H:%M")
    if isinstance(val, datetime):
        return val.strftime("%d-%b-%Y %H:%M")
    if isinstance(val, date) and not isinstance(val, datetime):
        return val.strftime("%d-%b-%Y")
    if isinstance(val, float):
        if val == int(val):
            return f"{int(val):,}"
        return f"{val:,.2f}"
    s = str(val).replace("\n", " ").strip()
    if s.lower() in ("nan", "none", "nat", "<na>"):
        return ""
    return s.encode("latin-1", "replace").decode("latin-1")


def _prep(df) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if isinstance(df, pd.Series):
        df = df.to_frame()
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    return out.loc[:, ~out.columns.duplicated()].reset_index(drop=True)


class ReportPDF(FPDF):
    def __init__(self, title: str, subtitle: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.report_title = _txt(title)[:90]
        self.report_sub = _txt(subtitle)[:110]
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(10, 20, 10)
        self.alias_nb_pages()

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 16, "F")
        self.set_fill_color(*GOLD)
        self.rect(0, 16, self.w, 1.4, "F")
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 13)
        self.set_xy(10, 3.2)
        self.cell(self.w - 20, 6, self.report_title, align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(232, 213, 163)
        self.set_xy(10, 9.5)
        self.cell(self.w - 20, 5, self.report_sub, align="L")
        self.set_y(22)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*GOLD)
        self.set_line_width(0.35)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"XTRNATE NOC  |  Confidential  |  Page {self.page_no()}/{{nb}}", align="C")


def _col_widths(pdf: FPDF, cols, data: pd.DataFrame):
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    n = max(len(cols), 1)
    weights = []
    for c in cols:
        sample = data[c].astype(str).head(40).map(len) if c in data.columns and not data.empty else pd.Series([0])
        w = max(len(str(c)), int(sample.max() if len(sample) else 0), 6)
        if any(k in str(c).lower() for k in ("reason", "remark", "address", "comment")):
            w = max(w, 28)
        weights.append(min(w, 40))
    total = sum(weights) or 1
    widths = [usable * w / total for w in weights]
    # floor so tiny cols stay readable
    widths = [max(w, 14) if n <= 10 else max(w, 11) for w in widths]
    scale = usable / sum(widths)
    return [w * scale for w in widths]


def _draw_table(pdf: FPDF, df: pd.DataFrame, section: str):
    data = _prep(df)
    cols = list(data.columns)
    if not cols:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 8, "No columns")
        return
    # too many columns → keep first 12
    if len(cols) > 12:
        cols = cols[:12]
        data = data[cols]
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _txt(section))
    pdf.ln(8)

    widths = _col_widths(pdf, cols, data)
    row_h = 6.2
    header_h = 7.2

    def header_row():
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 7.5)
        x = pdf.l_margin
        y = pdf.get_y()
        for w, name in zip(widths, cols):
            pdf.set_xy(x, y)
            pdf.cell(w, header_h, _txt(name)[:40], border=0, fill=True, align="C")
            x += w
        pdf.set_y(y + header_h)

    header_row()
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*INK)
    if data.empty:
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 8, "No rows")
        return

    for i, row in data.iterrows():
        if pdf.get_y() > pdf.h - 20:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*NAVY)
            pdf.cell(0, 7, _txt(section) + "  (contd.)")
            pdf.ln(8)
            header_row()
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*INK)
        fill = i % 2 == 1
        if fill:
            pdf.set_fill_color(*ALT)
        else:
            pdf.set_fill_color(*WHITE)
        first = _txt(row.iloc[0]).strip().lower()
        is_tot = first in ("grand total", "total")
        if is_tot:
            pdf.set_fill_color(*NAVY)
            pdf.set_text_color(*WHITE)
            pdf.set_font("Helvetica", "B", 7)
        x = pdf.l_margin
        y = pdf.get_y()
        # compute row height from longest wrap — keep single line for speed
        for w, name in zip(widths, cols):
            val = _txt(row[name])
            if len(val) > 48:
                val = val[:47] + "..."
            align = "L" if name == cols[0] else "C"
            pdf.set_xy(x, y)
            pdf.cell(w, row_h, val, border=0, fill=True, align=align)
            x += w
        pdf.set_y(y + row_h)
        if is_tot:
            pdf.set_text_color(*INK)
            pdf.set_font("Helvetica", "", 7)


def pdf_bytes(sheets, *, title="XTRNATE Report", subtitle="", sheet_name="Report"):
    if isinstance(sheets, (pd.DataFrame, pd.Series)):
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

    stamp = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST")
    sub = f"{subtitle}  •  {stamp}" if subtitle else f"XTRNATE NOC  •  {stamp}"
    pdf = ReportPDF(title, sub)
    for i, (name, df) in enumerate(clean):
        pdf.add_page()
        _draw_table(pdf, df, name)
    out = BytesIO()
    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        out.write(bytes(raw))
    else:
        pdf.output(out)
    return out.getvalue()
