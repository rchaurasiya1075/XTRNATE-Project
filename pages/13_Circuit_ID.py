import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.google_sheets import extract_sheet_id, load_sheet_as_csv

st.set_page_config(page_title="Circuit ID | XTRNATE", page_icon="🔌", layout="wide")

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
}
.ckt-label { color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; }
.ckt-value { color: #f8fafc; font-size: 1.15rem; font-weight: 700; margin: 0.15rem 0 0.7rem 0; word-break: break-all; }
.ckt-id { color: #38bdf8; font-size: 1.35rem; font-weight: 800; font-family: ui-monospace, monospace; }
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
    s = str(val or '').strip()
    u = s.upper()
    if 'HCIN' in u:
        return 'HCIN'
    if 'ONEOTT' in u or 'OTT' in u:
        return 'ONEOTT'
    if 'CELERITY' in u:
        return 'ONEOTT / Celerity'
    return s if s and s.lower() not in ('nan', '--') else '—'

st.markdown("""
<div class="ckt-hero">
  <h1>🔌 Circuit ID Lookup</h1>
  <p>Site Code search → CKT ID + ISP + Area / Location &nbsp;•&nbsp; Master sheet alag (gid 886642043)</p>
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
    placeholder="e.g. XTNSLN354   ya   ENT-BBXX-BWXX-HP-SOL-XX-XXX-HUGHES-0057081",
    label_visibility="visible",
)

matches = pd.DataFrame()
if q and q.strip():
    key = q.strip()
    key_u = key.upper()
    m1 = master['site_code'].astype(str).str.upper() == key_u if 'site_code' in master.columns else pd.Series(False, index=master.index)
    m2 = master['site_code'].astype(str).str.upper().str.contains(key_u, na=False) if 'site_code' in master.columns else m1
    m3 = master['ckt_id'].astype(str).str.upper().str.contains(key_u, na=False) if 'ckt_id' in master.columns else m1
    matches = master[m1 | m2 | m3].copy()
    # exact site first
    if 'site_code' in matches.columns:
        exact = matches[matches['site_code'] == key_u]
        rest = matches[matches['site_code'] != key_u]
        matches = pd.concat([exact, rest], ignore_index=True)

if not q or not q.strip():
    st.info("Upar bade box mein Site Code likho. Example: `XTNSLN354`")
elif matches.empty:
    st.warning(f"`{q}` ka Circuit ID nahi mila. Code check karo.")
else:
    for _, row in matches.head(15).iterrows():
        site = row.get('site_code', '—')
        ckt = row.get('ckt_id', '—')
        isp = isp_display(row.get('isp', ''))
        state = row.get('state', '—')
        branch = row.get('branch_name', '—')
        bank = row.get('bank_name', '—')
        addr = row.get('address', '—')
        phase = row.get('phase', '—')
        st.markdown(f"""
        <div class="ckt-card">
          <div class="ckt-label">Site Code</div>
          <div class="ckt-value">{site}</div>
          <div class="ckt-label">Circuit ID</div>
          <div class="ckt-id">{ckt}</div>
          <div class="ckt-label">ISP</div>
          <div class="ckt-value">{isp}</div>
          <div class="ckt-label">Area / Location</div>
          <div class="ckt-value">{branch} &nbsp;•&nbsp; {state}</div>
          <div class="ckt-label">Bank / Address</div>
          <div class="ckt-value" style="font-weight:500;font-size:0.98rem">{bank}<br/>{addr}</div>
          <div class="ckt-label">Phase</div>
          <div class="ckt-value" style="font-weight:500">{phase}</div>
        </div>
        """, unsafe_allow_html=True)

    show_cols = [c for c in ['site_code', 'ckt_id', 'isp', 'state', 'branch_name', 'bank_name', 'address', 'phase', 'delivery', 'acceptance'] if c in matches.columns]
    st.markdown("#### Result table")
    st.dataframe(matches[show_cols], use_container_width=True, hide_index=True)

with st.expander("All sites (master)", expanded=False):
    cols = [c for c in ['site_code', 'ckt_id', 'isp', 'state', 'branch_name', 'bank_name', 'address'] if c in master.columns]
    st.dataframe(master[cols], use_container_width=True, height=360, hide_index=True)
