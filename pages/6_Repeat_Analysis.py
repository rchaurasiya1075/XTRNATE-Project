import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period, get_summary_stats

st.set_page_config(page_title="Repeat Analysis | XTRNATE", page_icon="🔁", layout="wide")

st.title("🔁 Repeat Site & Area Analysis")
st.markdown("State → City → Site Code wise repeated downs, reasons aur resolution time")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

closed_df = st.session_state.get('closed_df')

if closed_df is None or closed_df.empty:
    st.warning("No closed tickets data found. Please upload Closed Tickets Excel from **Upload Data** page.")
    st.stop()

# Filter by ISP
if isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()

st.markdown(f"**Active ISP:** `{isp}` | Total Closed Records: **{len(closed_df)}**")

# Period selector
period = st.radio(
    "Select Period",
    ["Last 1 Month", "Last 2 Months", "Last 3 Months", "Last 6 Months", "Overall"],
    horizontal=True
)
period_map = {
    "Last 1 Month": "1M",
    "Last 2 Months": "2M",
    "Last 3 Months": "3M",
    "Last 6 Months": "6M",
    "Overall": "ALL"
}

df = filter_by_period(closed_df, period_map[period]) if period_map[period] != "ALL" else closed_df.copy()

st.success(f"Showing **{len(df)}** tickets for **{period}**")

if df.empty:
    st.info("No data in selected period.")
    st.stop()

# ===================== TABS =====================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Top Repeated Sites",
    "🗺️ State / City Focus",
    "🔍 Site Detail (Reasons + Days)",
    "📈 Category & Ageing"
])

# -------------------- TAB 1: Top Repeated Sites --------------------
with tab1:
    st.subheader("Most Repeated Site Codes")
    
    min_count = st.slider("Minimum repeat count to show", 2, 20, 3)
    
    if 'site_code' in df.columns:
        site_counts = df.groupby('site_code').agg(
            repeat_count=('ticket_id', 'count'),
            total_downtime_min=('down_time_min', 'sum') if 'down_time_min' in df.columns else ('ticket_id', 'count'),
            avg_resolution_days=('resolution_days', 'mean') if 'resolution_days' in df.columns else ('ticket_id', 'count'),
            states=('state', lambda x: ', '.join(x.dropna().unique()[:3])) if 'state' in df.columns else ('ticket_id', 'count'),
            cities=('city', lambda x: ', '.join(x.dropna().unique()[:3])) if 'city' in df.columns else ('ticket_id', 'count')
        ).reset_index()
        
        site_counts = site_counts[site_counts['repeat_count'] >= min_count].sort_values('repeat_count', ascending=False)
        
        st.dataframe(site_counts, use_container_width=True, height=400)
        
        # Chart
        top15 = site_counts.head(15)
        if not top15.empty:
            fig = px.bar(top15, x='site_code', y='repeat_count', color='repeat_count',
                         color_continuous_scale='Reds', text='repeat_count',
                         title="Top 15 Repeated Sites")
            fig.update_layout(template='plotly_dark', height=400, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("site_code column not found in data.")

# -------------------- TAB 2: State / City Focus --------------------
with tab2:
    st.subheader("State-wise & City-wise Repeated Downs")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### State-wise Ticket Count")
        if 'state' in df.columns:
            state_counts = df['state'].value_counts().reset_index()
            state_counts.columns = ['State', 'Ticket Count']
            fig = px.bar(state_counts, x='State', y='Ticket Count', color='Ticket Count',
                         color_continuous_scale='Blues', text='Ticket Count')
            fig.update_layout(template='plotly_dark', height=380)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(state_counts, use_container_width=True)
        else:
            st.info("State column missing")
    
    with col2:
        st.markdown("#### City-wise Ticket Count (Top 20)")
        if 'city' in df.columns:
            city_counts = df['city'].value_counts().head(20).reset_index()
            city_counts.columns = ['City', 'Ticket Count']
            fig = px.bar(city_counts, x='City', y='Ticket Count', color='Ticket Count',
                         color_continuous_scale='Teal', text='Ticket Count')
            fig.update_layout(template='plotly_dark', height=380, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(city_counts, use_container_width=True)
        else:
            st.info("City column missing in uploaded data. Upload Excel with City column for this view.")
    
    # Hierarchical State → Site
    st.markdown("---")
    st.subheader("State → Site Code Hierarchical View")
    if 'state' in df.columns and 'site_code' in df.columns:
        hier = df.groupby(['state', 'site_code']).size().reset_index(name='count')
        hier = hier.sort_values(['state', 'count'], ascending=[True, False])
        st.dataframe(hier, use_container_width=True, height=350)

# -------------------- TAB 3: Site Detail (Reasons + Days) --------------------
with tab3:
    st.subheader("Detailed View for High-Repeat Sites")
    st.caption("Select a site to see every occurrence, reason (Last Enclosure), and how many days it took to resolve.")
    
    if 'site_code' not in df.columns:
        st.warning("site_code not available")
    else:
        site_counts = df['site_code'].value_counts()
        high_sites = site_counts[site_counts >= 2].index.tolist()
        
        if not high_sites:
            st.info("No site has repeated 2 or more times in this period.")
        else:
            selected_site = st.selectbox("Select Site Code", high_sites)
            
            site_data = df[df['site_code'] == selected_site].copy()
            site_data = site_data.sort_values('submitted_time', ascending=False)
            
            st.markdown(f"### Site: **{selected_site}** — Total Downs: **{len(site_data)}**")
            
            # Summary metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Occurrences", len(site_data))
            if 'resolution_days' in site_data.columns:
                m2.metric("Avg Resolution Days", round(site_data['resolution_days'].mean(), 1))
                m3.metric("Max Resolution Days", round(site_data['resolution_days'].max(), 1))
            if 'state' in site_data.columns:
                m4.metric("State", site_data['state'].iloc[0] if not site_data['state'].isna().all() else "-")
            
            # Detail table
            detail_cols = ['ticket_id', 'submitted_time', 'resolved_time', 'resolution_days', 
                           'category', 'reason_clean', 'state', 'city', 'down_time_min']
            detail_cols = [c for c in detail_cols if c in site_data.columns]
            
            st.dataframe(site_data[detail_cols], use_container_width=True, height=400)
            
            # Reasons breakdown for this site
            if 'category' in site_data.columns:
                st.markdown("#### Category Breakdown for this Site")
                cat_counts = site_data['category'].value_counts().reset_index()
                cat_counts.columns = ['Category', 'Count']
                fig = px.pie(cat_counts, names='Category', values='Count', hole=0.4)
                fig.update_layout(template='plotly_dark', height=350)
                st.plotly_chart(fig, use_container_width=True)

# -------------------- TAB 4: Category & Ageing --------------------
with tab4:
    st.subheader("Category Breakdown & Resolution Ageing")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if 'category' in df.columns:
            cat_df = df['category'].value_counts().reset_index()
            cat_df.columns = ['Category', 'Count']
            fig = px.pie(cat_df, names='Category', values='Count', hole=0.35,
                         title="Complaint Category Distribution")
            fig.update_layout(template='plotly_dark', height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(cat_df, use_container_width=True)
        else:
            st.info("Category not available")
    
    with col2:
        if 'resolution_days' in df.columns:
            # Ageing buckets
            def ageing_bucket(days):
                if pd.isna(days):
                    return 'Unknown'
                if days <= 1:
                    return '0-24 Hrs'
                elif days <= 2:
                    return '24-48 Hrs'
                elif days <= 3:
                    return '48-72 Hrs'
                elif days <= 5:
                    return '3-5 Days'
                else:
                    return 'Above 5 Days'
            
            df['ageing'] = df['resolution_days'].apply(ageing_bucket)
            age_order = ['0-24 Hrs', '24-48 Hrs', '48-72 Hrs', '3-5 Days', 'Above 5 Days', 'Unknown']
            age_counts = df['ageing'].value_counts().reindex(age_order, fill_value=0).reset_index()
            age_counts.columns = ['Ageing Bucket', 'Count']
            
            fig = px.bar(age_counts, x='Ageing Bucket', y='Count', color='Count',
                         color_continuous_scale='OrRd', text='Count',
                         title="Resolution Ageing Distribution")
            fig.update_layout(template='plotly_dark', height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(age_counts, use_container_width=True)
        else:
            st.info("Resolution days not calculated (need Submitted + Resolved time)")

# ===================== DOWNLOAD =====================
st.markdown("---")
st.subheader("Download Report Data")

def to_excel(dataframe):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='Repeat_Analysis')
    return output.getvalue()

if 'site_code' in df.columns:
    summary = df.groupby('site_code').agg(
        repeat_count=('ticket_id', 'count'),
        avg_days=('resolution_days', 'mean') if 'resolution_days' in df.columns else ('ticket_id', 'count')
    ).reset_index().sort_values('repeat_count', ascending=False)
    
    st.download_button(
        "📥 Download Site Repeat Summary Excel",
        data=to_excel(summary),
        file_name=f"XTRNATE_Repeat_Sites_{isp}_{period.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
