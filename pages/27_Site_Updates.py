import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready
from utils.sheets_config import tab_url, xtranet_url
from utils.site_update import (
    UPDATE_COLS,
    WS_TITLE,
    apply_updates_to_google,
    combined_master,
    ensure_updated_worksheet,
    full_excel,
    parse_site_codes,
    template_excel,
)

st.set_page_config(page_title="Site Updates | Xtranet", page_icon="🗂️", layout="wide")
ensure_ready()

st.title("🗂️ Site Updates")
st.caption(
    "One sheet for every site (SIM, CKT, ISP, last mile, LC). "
    "Download the format → fill only changed fields → app writes Google tab "
    f"**{WS_TITLE}** in the Xtranet workbook."
)

tab1, tab2, tab3 = st.tabs([
    "📥 All sites (one Excel)",
    "📝 Bulk update format",
    "☁️ Write to Google sheet",
])

with tab1:
    st.markdown("Live sheets + anything already on **Updated_Master**. One row per site.")
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
            st.success(f"{len(df)} sites")
            st.dataframe(df.head(50), use_container_width=True, height=360)
            st.download_button(
                "Download Excel — all site details",
                data=full_excel(df),
                file_name="Xtranet_All_Sites_Updated.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with tab2:
    st.markdown(
        "Fill **Site Code** and only the columns that changed "
        "(ISP HCIN→OTT, new CKT ID, last mile, SIM, MDN, IP, LC). Blank = no change."
    )
    st.dataframe(pd.DataFrame(columns=UPDATE_COLS), use_container_width=True)
    st.download_button(
        "Download update format Excel",
        data=template_excel(),
        file_name="Xtranet_Site_Update_Format.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

with tab3:
    st.markdown(
        f"Upload the filled format. Rows are merged into Google tab **{WS_TITLE}** "
        f"in [this workbook]({xtranet_url()})."
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

    st.markdown("---")
    if st.button("Create empty Updated_Master tab (if missing)"):
        try:
            ws = ensure_updated_worksheet()
            st.success(f"Tab ready: {ws.title} (gid {ws.id})")
        except Exception as e:
            st.error(str(e))
