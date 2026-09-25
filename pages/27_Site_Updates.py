import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.sheets_config import tab_url, xtranet_url
from utils.site_update import (
    FORMAT_TITLE,
    UPDATE_COLS,
    WS_TITLE,
    apply_format_sheet_to_master,
    apply_updates_to_google,
    combined_master,
    ensure_format_and_master,
    full_excel,
    master_export,
    parse_site_codes,
    template_excel,
)

st.set_page_config(page_title="Site Updates | Xtranet", page_icon="🗂️", layout="wide")
ensure_ready()

st.title("🗂️ Site Updates")
st.caption(
    f"In the Xtranet Google workbook: fill tab **{FORMAT_TITLE}** (site code + changed columns). "
    f"Then apply — those rows update tab **{WS_TITLE}**."
)

tab1, tab2, tab3 = st.tabs([
    "📥 All sites (one Excel)",
    "📝 Google format sheet",
    "☁️ Upload file (optional)",
])

with tab1:
    st.markdown(
        "One row per site from the site master sheet. "
        "Ticket remarks mark **Non Feasible** with the TT date and ISP (HCIN / ONEOTT). "
        "If no feasibility came after that date, billing says stop payment from that day. "
        "Excel has a **Stop_Payment** sheet with only those sites."
    )
    scope = st.radio("Which sites?", ["All sites", "Paste site codes"], horizontal=True)
    codes = None
    if scope == "Paste site codes":
        blob = st.text_area("Site codes", height=100, placeholder="XTNNTL358\nXTNCHG364")
        codes = parse_site_codes(blob or "")
        if blob and not codes:
            st.warning("No site code found.")
    if st.button("Build sheet", type="primary"):
        with st.spinner("Merging site + SIM + last mile + CKT…"):
            df = combined_master(codes if codes else None)
        if df is None or df.empty:
            st.warning("No rows.")
        else:
            view = master_export(df)
            stop = view[view["Billing"].astype(str).str.startswith("Stop")] if "Billing" in view.columns else view.iloc[0:0]
            st.success(f"{len(view)} sites  •  stop payment: {len(stop)}")
            if not stop.empty:
                st.markdown("**Stop payment — non feasible, no feasibility after that date**")
                show = [c for c in [
                    "Sitecode", "ISP", "Non Feasible On", "Non Feasible TT",
                    "Feasibility After", "Billing", "State", "Last Mile",
                ] if c in stop.columns]
                st.dataframe(stop[show], use_container_width=True, height=280)
            st.dataframe(view.head(50), use_container_width=True, height=360)
            st.download_button(
                "Download Excel — all site details",
                data=full_excel(view),
                file_name="Xtranet_All_Sites_Updated.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with tab2:
    st.markdown(
        f"Same Google workbook. New tab **{FORMAT_TITLE}** is the format. "
        "Put **Site Code** and only columns you are changing "
        "(ISP, CKT ID, Last Mile, SIM, MDN, IP, LC). Blank cell = no change. "
        f"Apply copies those rows onto **{WS_TITLE}** by site code."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(f"Create {FORMAT_TITLE} + {WS_TITLE} tabs", type="primary"):
            try:
                with st.spinner("Creating tabs in Google Sheet…"):
                    fmt, master = ensure_format_and_master()
                st.success(f"Ready: `{fmt.title}` and `{master.title}`")
            except Exception as e:
                st.error(str(e))
                st.caption("Share the Xtranet workbook with the service account as **Editor**.")
    with c2:
        if st.button(f"Apply {FORMAT_TITLE} → {WS_TITLE}"):
            try:
                with st.spinner("Reading format tab and updating master…"):
                    result = apply_format_sheet_to_master()
                st.success(
                    f"{result.get('format_rows', 0)} rows from **{FORMAT_TITLE}** → "
                    f"**{WS_TITLE}**: {result['updated']} changed, {result['added']} new, "
                    f"{result['total']} total."
                )
            except Exception as e:
                st.error(str(e))
    st.markdown(
        f"- Open format: [{FORMAT_TITLE}]({tab_url('site_update_format')})  \n"
        f"- Open master: [{WS_TITLE}]({tab_url('site_updated')})  \n"
        f"- Workbook: [Xtranet Excel]({xtranet_url()})"
    )
    st.caption("Columns: " + " · ".join(UPDATE_COLS))
    st.download_button(
        "Also download the same format as Excel",
        data=template_excel(),
        file_name="Xtranet_Site_Update_Format.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with tab3:
    st.markdown(
        f"Optional: upload a filled Excel instead of typing in **{FORMAT_TITLE}**. "
        f"Same columns. Still writes **{WS_TITLE}**."
    )
    up = st.file_uploader("Excel / CSV", type=["xlsx", "xls", "csv"])
    if up is not None:
        if str(up.name).lower().endswith(".csv"):
            incoming = pd.read_csv(up)
        else:
            incoming = pd.read_excel(up)
        st.caption(f"{len(incoming)} rows in file")
        st.dataframe(incoming.head(20), use_container_width=True)
        if st.button("Apply to Updated_Master", type="primary"):
            try:
                with st.spinner("Writing Google Sheet…"):
                    result = apply_updates_to_google(incoming)
                st.success(
                    f"Google tab **{result['title']}** updated — "
                    f"{result['updated']} changed, {result['added']} new, {result['total']} total rows."
                )
                st.markdown(f"[Open Updated_Master]({tab_url('site_updated')})")
            except Exception as e:
                st.error(str(e))
                st.caption("Share the Xtranet workbook with the service account as Editor if write fails.")
