# 📡 XTRNATE Project – NOC Command Center

Premium Ticket Analytics & Escalation System for NOC Engineers.

## Features

- **Separate Dashboards** for HCIN and ONEOTT
- Excel Upload (Closed + Open Tickets)
- Site Master integration (Bank, Branch, State, etc.)
- 1 / 3 / 6 Month Analysis
- Beautiful interactive charts (Plotly)
- **Editable Escalation Matrix** (per ISP)
- Live Open Tickets with color-coded Escalation Levels
- Filters + Excel Download
- Modern dark premium UI

## How to Run (Local)

```bash
# 1. Go to project folder
cd XTRNATE_Project

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

Browser automatically open hoga → `http://localhost:8501`

## How to Deploy Free (Streamlit Cloud)

1. Go to https://share.streamlit.io
2. Connect your GitHub repo: rchaurasiya1075/XTRNATE-Project
3. Select `app.py` as main file
4. Deploy

## Usage Flow

1. Home page pe **HCIN** ya **ONEOTT** select karo
2. **Upload Data** page pe:
   - Closed Tickets Excel
   - Open Tickets Excel
   - Site Master Excel
3. **Dashboard** pe overview dekho
4. **Closed Analysis** pe deep reports
5. **Open Escalation** pe live escalation status
6. **Escalation Matrix** pe Name / Email / Time rules edit karo

## Notes

- Escalation Matrix har ISP ke liye alag save hota hai (`data/escalation_hcin.csv` etc.)
- Data session mein rehta hai. Browser band kiya to dobara upload karna padega (future mein database add kiya ja sakta hai)
- Down Time column minutes mein expected hai

## Built for

Xtranet NOC Team | FE Rollout Partners (HCIN / ONEOTT)
