import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.escalation import load_escalation_matrix, save_escalation_matrix
from utils.bootstrap import ensure_ready, get_selected_isps, available_isps

st.set_page_config(page_title="Escalation Matrix | XTRNATE", page_icon="⚙️", layout="wide")

st.title("⚙️ Escalation Matrix Configuration")
st.markdown("Yahan se aap **Name, Email, Time Rules, Level** sab edit kar sakte ho. Har ISP ka alag matrix hai.")

ensure_ready()
picked = get_selected_isps()
opts = picked or available_isps()
if not opts:
    st.warning("Koi ISP nahi mila. Home pe data load karo.")
    st.stop()
isp = opts[0] if len(opts) == 1 else st.selectbox("Matrix kis ISP ka edit karna hai", opts)
if not isp or isp in ("ALL", "NONE"):
    st.warning("Ek specific ISP choose karo — matrix har ISP ke liye alag hai.")
    st.stop()

st.success(f"Editing Escalation Matrix for: **{isp}**")

matrix_df = load_escalation_matrix(isp)

st.subheader("Current Escalation Rules")
st.caption("Aap directly table mein edit kar sakte ho. Changes save karne ke baad Save button dabayein.")

edited_df = st.data_editor(
    matrix_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Level": st.column_config.TextColumn("Level", help="L1, L2, L3, L4...", required=True),
        "Min_Hours": st.column_config.NumberColumn("Min Hours", min_value=0, step=0.5, format="%.1f"),
        "Max_Hours": st.column_config.NumberColumn("Max Hours", min_value=0, step=0.5, format="%.1f"),
        "Name": st.column_config.TextColumn("Responsible Person / Team", width="medium"),
        "Email": st.column_config.TextColumn("Email ID", width="medium"),
        "Phone": st.column_config.TextColumn("Phone", width="small"),
        "Remarks": st.column_config.TextColumn("Remarks / Action", width="large"),
    },
    key=f"escalation_editor_{isp}"
)

col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    if st.button("💾 Save Matrix", type="primary", use_container_width=True):
        if edited_df.empty:
            st.error("Matrix cannot be empty")
        else:
            save_escalation_matrix(isp, edited_df)
            st.success(f"✅ Escalation Matrix for **{isp}** saved successfully!")
            st.balloons()

with col2:
    if st.button("🔄 Reset to Default", use_container_width=True):
        default = pd.DataFrame({
            'Level': ['L1', 'L2', 'L3', 'L4'],
            'Min_Hours': [0, 2, 4, 8],
            'Max_Hours': [2, 4, 8, 999],
            'Name': ['NOC / FE Team', 'Team Lead', 'Manager', 'Higher Management'],
            'Email': ['noc@example.com', 'lead@example.com', 'manager@example.com', 'director@example.com'],
            'Phone': ['', '', '', ''],
            'Remarks': ['First response', 'Escalate to lead', 'Manager intervention', 'Critical escalation']
        })
        save_escalation_matrix(isp, default)
        st.success("Reset to default. Please refresh the page.")
        st.rerun()

st.markdown("---")
st.subheader("How it works")
st.markdown("""
- **Min_Hours** se **Max_Hours** tak ka time range define karta hai.
- Ticket kitne hours se open hai, uske hisaab se Level decide hota hai.
- **Open Escalation** page pe automatically color + person dikhega.
- Aap levels add/delete bhi kar sakte ho (dynamic rows).
- Har ISP ka matrix alag save hota hai (Owner column ke names).
""")
