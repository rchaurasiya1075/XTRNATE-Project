"""Forest-green PDF tables. Never uses pandas .map — Arrow/NA safe."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
from fpdf import FPDF

IST = ZoneInfo("Asia/Kolkata")
NAVY = (31, 81, 63)
GOLD = (45, 106, 79)
INK = (26, 26, 26)
ALT = (240, 244, 242)
MUTED = (107, 114, 128)
WHITE = (255, 255, 255)
SUB = (216, 237, 228)


def _cell(val) -> str:
    if val is None:
        return ""
    try:
        name = type(val).__name__
        if name in ("NAType", "NaTType"):
            return ""
    except Exception:
        pass
    try:
        if isinstance(val, float) and val != val:
            return ""
    except Exception:
        pass
    if isinstance(val, pd.Timestamp):
        try:
            if pd.isna(val):
                return ""
            return val.strftime("%d-%b-%Y %H:%M")
        except Exception:
            return ""
    if isinstance(val, datetime):
        try:
            return val.strftime("%d-%b-%Y %H:%M")
        except Exception:
            return ""
    if isinstance(val, date) and not isinstance(val, datetime):
        try:
            return val.strftime("%d-%b-%Y")
        except Exception:
            return ""
    if isinstance(val, (int,)) and not isinstance(val, bool):
        return f"{val:,}"
    if isinstance(val, float):
        try:
            if val == int(val):
                return f"{int(val):,}"
            return f"{val:,.2f}"
        except Exception:
            return str(val)
    try:
        s = str(val).replace("\n", " ").strip()
    except Exception:
        return ""
    if s.lower() in ("nan", "none", "nat", "<na>", "<nat>", "null"):
        return ""
    try:
        return s.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return s[:80]


def _table(df):
    """Return (col_names, list[list[str]]) with zero pandas map()."""
    if df is None:
        return ["Info"], [["No rows"]]
    if isinstance(df, pd.Series):
        df = df.to_frame()
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:
            return ["Info"], [["No rows"]]
    cols = [str(c) for c in list(df.columns)[:12]]
    if not cols:
        return ["Info"], [["No columns"]]
    n = min(len(df), 500)
    rows = []
    use_cols = list(df.columns)[:12]
    matrix = None
    try:
        matrix = df[use_cols].to_numpy(dtype=object)
    except Exception:
        matrix = None
    if matrix is not None:
        for i in range(min(len(matrix), n)):
            rec = []
            for v in matrix[i]:
                rec.append(_cell(v))
            rows.append(rec)
    else:
        for i in range(n):
            rec = []
            for c in use_cols:
                try:
                    rec.append(_cell(df[c].iloc[i]))
                except Exception:
                    rec.append("")
            rows.append(rec)
    return cols, rows


class ReportPDF(FPDF):
    def __init__(self, title: str, subtitle: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.report_title = _cell(title)[:90]
        self.report_sub = _cell(subtitle)[:110]
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(10, 20, 10)
        try:
            self.alias_nb_pages()
        except Exception:
            pass

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
        self.set_text_color(*SUB)
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


def _draw_table(pdf: FPDF, df, section: str):
    cols, rows = _table(df)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _cell(section))
    pdf.ln(8)

    usable = pdf.w - pdf.l_margin - pdf.r_margin
    n = max(len(cols), 1)
    weights = []
    for j, name in enumerate(cols):
        w = len(name)
        for rec in rows[:40]:
            if j < len(rec):
                w = max(w, len(rec[j]))
        weights.append(min(max(w, 6), 40))
    total = sum(weights) or 1
    widths = [usable * w / total for w in weights]
    widths = [max(w, 12 if n > 10 else 14) for w in widths]
    scale = usable / (sum(widths) or 1)
    widths = [w * scale for w in widths]
    row_h, header_h = 6.2, 7.2

    def header_row():
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 7.5)
        x, y = pdf.l_margin, pdf.get_y()
        for w, name in zip(widths, cols):
            pdf.set_xy(x, y)
            pdf.cell(w, header_h, _cell(name)[:40], border=0, fill=True, align="C")
            x += w
        pdf.set_y(y + header_h)

    header_row()
    if not rows:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 8, "No rows")
        return

    for i, rec in enumerate(rows):
        if pdf.get_y() > pdf.h - 20:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*NAVY)
            pdf.cell(0, 7, _cell(section) + "  (contd.)")
            pdf.ln(8)
            header_row()
        first = (rec[0] if rec else "").strip().lower()
        is_tot = first in ("grand total", "total", "total / average")
        if is_tot:
            pdf.set_fill_color(*NAVY)
            pdf.set_text_color(*WHITE)
            pdf.set_font("Helvetica", "B", 7)
        else:
            pdf.set_fill_color(*(ALT if i % 2 else WHITE))
            pdf.set_text_color(*INK)
            pdf.set_font("Helvetica", "", 7)
        x, y = pdf.l_margin, pdf.get_y()
        for j, w in enumerate(widths):
            val = rec[j] if j < len(rec) else ""
            if len(val) > 48:
                val = val[:47] + "..."
            pdf.set_xy(x, y)
            pdf.cell(w, row_h, val, border=0, fill=True, align="L" if j == 0 else "C")
            x += w
        pdf.set_y(y + row_h)


def pdf_bytes(sheets, *, title="XTRNATE Report", subtitle="", sheet_name="Report"):
    try:
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
            clean.append((str(name), df))
        if not clean:
            clean = [("Report", pd.DataFrame({"Info": ["No rows"]}))]

        stamp = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST")
        sub = f"{subtitle}  •  {stamp}" if subtitle else f"XTRNATE NOC  •  {stamp}"
        pdf = ReportPDF(title, sub)
        for name, df in clean:
            pdf.add_page()
            try:
                _draw_table(pdf, df, name)
            except Exception:
                pdf.set_font("Helvetica", "I", 10)
                pdf.set_text_color(*MUTED)
                pdf.cell(0, 8, "This sheet could not be drawn.")
        raw = pdf.output()
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        out = BytesIO()
        pdf.output(out)
        return out.getvalue()
    except Exception:
        return b""
