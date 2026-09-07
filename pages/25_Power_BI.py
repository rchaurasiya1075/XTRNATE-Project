import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.bootstrap import ensure_ready, apply_isp_filter
from utils.data_source import source_status, init_data_source
from utils.powerbi_pack import (
    build_model,
    csv_zip,
    excel_model,
    google_sheet_m,
    power_query_m,
)
from utils.auto_load import DEFAULT_SHEET_URL

st.set_page_config(page_title="Power BI | Xtranet", page_icon="📊", layout="wide")
init_data_source()
ensure_ready()

st.title("📊 Power BI integration")
st.caption(
    "Push the active Xtranet dataset (Google Sheet or Manual Excel) into Power BI. "
    "Existing report pages are unchanged."
)
st.info(source_status())

project = st.session_state.get("active_project") or "Xtranet"
source = "Manual Excel" if st.session_state.get("data_source") == "upload" else "Google Sheet"

closed = apply_isp_filter(st.session_state.get("closed_df"))
opened = apply_isp_filter(st.session_state.get("open_df"))
if closed is None or closed.empty:
    st.warning("No ticket data in the active source. Load Google Sheet or upload Excel on Upload Data.")
    st.stop()

sheets = build_model(closed, opened, project=project, source=source)
stem = f"Xtranet_{project}_PowerBI".replace(" ", "_")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Project", project)
k2.metric("Fact tickets", 0 if "Fact_Tickets" not in sheets else len(sheets["Fact_Tickets"]))
k3.metric("Sites", 0 if "Dim_Site" not in sheets else len(sheets["Dim_Site"]))
k4.metric("Tables", len(sheets))

tabs = st.tabs(["1. Dataset for Power BI", "2. Embed a published report", "3. How to connect"])

with tabs[0]:
    st.markdown("##### Star schema for Power BI Desktop")
    st.caption("Fact_Tickets + Dim_Site + Daily + SLA + Classification. Same forest-green Excel as other downloads.")
    for name, df in sheets.items():
        with st.expander(f"{name}  ({0 if df is None else len(df)} rows)", expanded=(name == "KPI")):
            st.dataframe(df.head(30), use_container_width=True, hide_index=True)

    xls = excel_model(sheets, project=project, source=source)
    zipped = csv_zip(sheets, stem=stem)
    mscript = power_query_m(project)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "📥 Excel model (.xlsx)",
            data=xls,
            file_name=f"{stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="pbi_xlsx",
        )
    with c2:
        st.download_button(
            "📥 CSV zip (Get Data → Folder)",
            data=zipped,
            file_name=f"{stem}.zip",
            mime="application/zip",
            use_container_width=True,
            key="pbi_zip",
        )
    with c3:
        st.download_button(
            "📥 Power Query M",
            data=mscript.encode("utf-8"),
            file_name=f"{stem}.pq",
            mime="text/plain",
            use_container_width=True,
            key="pbi_m",
        )
    st.code(mscript, language="text")

with tabs[1]:
    st.markdown("##### Embed a report already published in Power BI")
    st.caption(
        "In Power BI Service: File → Embed report → Publish to web (public) **or** "
        "Website / portal. Paste the `https://app.powerbi.com/view?r=...` link."
    )
    if "pbi_embeds" not in st.session_state:
        st.session_state.pbi_embeds = {}
    stored = st.session_state.pbi_embeds.get(project, "")
    url = st.text_input("Power BI view URL", value=stored, placeholder="https://app.powerbi.com/view?r=...", key="pbi_url")
    h = st.slider("Embed height", 480, 1200, 720, 20)
    if st.button("Save & show report", type="primary"):
        u = (url or "").strip()
        if "app.powerbi.com" not in u and "powerbi.com" not in u:
            st.error("Paste a Power BI view / embed URL.")
        else:
            st.session_state.pbi_embeds[project] = u
            st.success(f"Saved for {project}.")
            st.rerun()
    show = st.session_state.pbi_embeds.get(project, "")
    if show:
        components.iframe(show, height=h, scrolling=True)
    else:
        st.info("No embed saved for this project yet. Dataset download in tab 1 still works without an embed.")

with tabs[2]:
    st.markdown("""
**Path A — Excel / CSV (recommended)**  
1. Tab 1 → download Excel model.  
2. Power BI Desktop → **Get data → Excel** → pick the file.  
3. Load `Fact_Tickets`, `Dim_Site`, `Daily`.  
4. Model view: relate `Fact_Tickets[site_code]` to `Dim_Site[site_code]`.  
5. Build visuals, then **Publish** to Power BI Service.  
6. Copy the view URL into tab 2 to see it inside Xtranet.

**Path B — live Google Sheet**  
Power BI Desktop → Get data → Web. Use the sheet CSV export if sharing is on.
    """)
    st.code(google_sheet_m(DEFAULT_SHEET_URL), language="text")
    st.caption("Service account / tenant embed (app-owns-data) needs Azure client secrets — not stored here. Use Publish-to-web or a view URL.")
