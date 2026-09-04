"""Excel + PDF download buttons — same data, professional format."""
import re

import streamlit as st

from utils.excel_export import excel_bytes
from utils.pdf_export import pdf_bytes

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"


def _stem(name: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", str(name).strip())
    return s.strip("_") or "XTRNATE_Report"


def download_pack(
    label,
    data,
    file_stem,
    *,
    title="XTRNATE Report",
    subtitle="",
    sheet_name="Report",
    key="dl",
):
    """Two buttons: Excel and PDF. PDF fail ho to page crash nahi."""
    stem = _stem(file_stem)
    xls = excel_bytes(data, title=title, subtitle=subtitle, sheet_name=sheet_name)
    pdf = b""
    try:
        pdf = pdf_bytes(data, title=title, subtitle=subtitle, sheet_name=sheet_name)
        if not pdf or not pdf.startswith(b"%PDF"):
            pdf = b""
    except Exception:
        pdf = b""
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            f"📥 {label} — Excel",
            data=xls,
            file_name=f"{stem}.xlsx",
            mime=XLSX,
            key=f"{key}_xlsx",
            use_container_width=True,
        )
    with c2:
        if pdf:
            st.download_button(
                f"📄 {label} — PDF",
                data=pdf,
                file_name=f"{stem}.pdf",
                mime=PDF,
                key=f"{key}_pdf",
                use_container_width=True,
            )
        else:
            st.caption("PDF is sheet pe skip")
