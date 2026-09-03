import streamlit as st
import pandas as pd
import sys
import os
import io

# Project root add kar rahe hain taaki utils module read ho sake
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv
from utils.data_processing import classify_isp
from utils.bootstrap import ensure_ready
from utils.excel_export import excel_bytes

st.set_page_config(page_title="Circuit ID | XTRNATE", page_icon="🔌", layout="wide")
ensure_ready()

CKT_URL = "https://docs.google.com/spreadsheets/d/1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I/edit?usp=sharing"
CKT_GID = 886642043

st.markdown("""
<style>
.ckt-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 70%);
  border: 1px solid #38bdf8;
  border-radius: 18px;
  padding: 1.4rem 1.6rem 1.1rem 1.6rem;
  margin-bottom: 1.2rem;
  box-shadow: 0 10px 30px rgba(15,23,42,0.35);
}
.ckt-hero h1 { color: #fff; margin: 0 0 0.25rem 0; font-size: 1.7rem; }
.ckt-hero p { color: #cbd5e1; margin: 0; }
.ckt-card {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 1.2rem 1.4rem;
  margin-top: 0.8rem;
  margin-bottom: 1rem;
}
.ckt-label { color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.2rem; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def load_ckt_master():
    sid = extract_sheet_id(CKT_URL)
    df = load_sheet_as_csv(sid, gid=CKT_GID)
    df.columns = [str(c).strip() for c in df.columns]
    rename = {
        'Site Code': 'site_code',
        'Ckt ID': 'ckt_id',
        'CKT ID': 'ckt_id',
        'ISP': 'isp',
        'Bank Name': 'bank_name',
        'Branch Name': 'branch_name',
        'Branch Address': 'address',
        'State': 'state',
        'Phase Details': 'phase',
        'BB Delivery Status': 'delivery',
        'I&C Date': 'ic_date',
        'Acceptance status': 'acceptance',
        'Site': 'site_alt',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if 'site_code' in df.columns:
        df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
    if 'ckt_id' in df.columns:
        df['ckt_id'] = df['ckt_id'].astype(str).str.strip()
    return df

def isp_display(val):
    name = classify_isp(val)
    if name == 'UNKNOWN':
        s = str(val or '').strip()
        return s if s and s.lower() not in ('nan', '--') else '—'
    return name

# Helper function to generate Excel binary buffer
def get_excel_download(dataframe: pd.DataFrame, sheet_name="Circuit_Data", title="Circuit ID"):
    return excel_bytes(dataframe, title=title, sheet_name=sheet_name)

st.markdown("""
<div class="ckt-hero">
  <h1>🔌 Circuit ID Lookup</h1>
  <p>Site Code search → CKT ID + ISP + Area &nbsp;•&nbsp; Copy button se Site Code / CKT ID 1-click copy</p>
</div>
""", unsafe_allow_html=True)

try:
    master = load_ckt_master()
except Exception as e:
    st.error(f"CKT master load fail: {e}")
    st.stop()

st.caption(f"Master loaded: **{len(master)}** sites")

q = st.text_input(
    "Search Site Code or CKT ID",
    placeholder="e.g. XTNSLN354    ya    ENT-BBXX-BWXX-HP-SOL-XX-XXX-HUGHES-0057081",
)

matches = pd.DataFrame()
if q and q.strip():
    key = q.strip()
    key_u = key.upper()
    m1 = master['site_code'].astype(str).str.upper() == key_u if 'site_code' in master.columns else pd.Series(False, index=master.index)
    m2 = master['site_code'].astype(str).str.upper().str.contains(key_u, na=False) if 'site_code' in master.columns else m1
    m3 = master['ckt_id'].astype(str).str.upper().str.contains(key_u, na=False) if 'ckt_id' in master.columns else m1
    matches = master[m1 | m2 | m3].copy()
    if 'site_code' in matches.columns:
        exact = matches[matches['site_code'] == key_u]
        rest = matches[matches['site_code'] != key_u]
        matches = pd.concat([exact, rest], ignore_index=True)

if not q or not q.strip():
    st.info("Upar box mein Site Code likho. Example: `XTNSLN354`")
elif matches.empty:
    st.warning(f"`{q}` ka Circuit ID nahi mila. Code check karo.")
else:
    for i, row in matches.head(15).iterrows():
        site = str(row.get('site_code', '—') or '—')
        ckt = str(row.get('ckt_id', '—') or '—')
        isp = isp_display(row.get('isp', ''))
        state = str(row.get('state', '—') or '—')
        branch = str(row.get('branch_name', '—') or '—')
        bank = str(row.get('bank_name', '—') or '—')
        addr = str(row.get('address', '—') or '—')
        phase = str(row.get('phase', '—') or '—')

        with st.container(border=True):
            st.markdown(f"**Result #{i+1 if isinstance(i, int) else ''}**")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="ckt-label">Site Code — copy</div>', unsafe_allow_html=True)
                st.code(site, language=None)
            with c2:
                st.markdown('<div class="ckt-label">Circuit ID — copy</div>', unsafe_allow_html=True)
                st.code(ckt, language=None)

            a, b = st.columns(2)
            with a:
                st.markdown(f"**ISP:** {isp}")
                st.markdown(f"**Area / Location:** {branch} • {state}")
            with b:
                st.markdown(f"**Bank:** {bank}")
                st.markdown(f"**Phase:** {phase}")
            st.caption(addr)

            # Quick download txt actions
            bc1, bc2, _ = st.columns([1, 1, 2])
            with bc1:
                st.download_button(
                    "📋 Site Code txt",
                    data=site,
                    file_name=f"{site}_site.txt",
                    mime="text/plain",
                    key=f"dl_site_{i}_{site}",
                    use_container_width=True,
                )
            with bc2:
                st.download_button(
                    "📋 CKT ID txt",
                    data=ckt,
                    file_name=f"{site}_ckt.txt",
                    mime="text/plain",
                    key=f"dl_ckt_{i}_{site}",
                    use_container_width=True,
                )

    show_cols = [c for c in ['site_code', 'ckt_id', 'isp', 'state', 'branch_name', 'bank_name', 'address', 'phase', 'delivery', 'acceptance'] if c in matches.columns]
    
    st.markdown("#### Result table")
    st.dataframe(matches[show_cols], use_container_width=True, hide_index=True)
    st.caption("Table se bhi select karke Ctrl+C / long-press copy kar sakte ho.")
    
    # Export options for filtered results
    exp_col1, exp_col2, _ = st.columns([1.5, 1.5, 3])
    with exp_col1:
        st.download_button(
            label="📥 Download Results (CSV)",
            data=matches[show_cols].to_csv(index=False).encode('utf-8'),
            file_name=f"Circuit_SearchResults_{q}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with exp_col2:
        st.download_button(
            label="📊 Download Results (Excel)",
            data=get_excel_download(matches[show_cols], sheet_name="Filtered_Circuits", title="Circuit Search Results"),
            file_name=f"Circuit_SearchResults_{q}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

with st.expander("All sites (master)", expanded=False):
    cols = [c for c in ['site_code', 'ckt_id', 'isp', 'state', 'branch_name', 'bank_name', 'address'] if c in master.columns]
    st.dataframe(master[cols], use_container_width=True, height=360, hide_index=True)
    
    # Export options for master dataset
    m_col1, m_col2, _ = st.columns([1.5, 1.5, 3])
    with m_col1:
        st.download_button(
            label="📥 Export Master (CSV)",
            data=master[cols].to_csv(index=False).encode('utf-8'),
            file_name="Master_Circuit_List.csv",
            mime="text/csv",
            key="master_csv_download",
            use_container_width=True
        )
    with m_col2:
        st.download_button(
            label="📊 Export Master (Excel)",
            data=get_excel_download(master[cols], sheet_name="Master_Circuits", title="Master Circuit List"),
            file_name="Master_Circuit_List.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="master_excel_download",
            use_container_width=True
        )
