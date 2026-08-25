import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.data_processing import filter_by_period

st.set_page_config(page_title="Repeat Analysis | XTRNATE", page_icon="🔁", layout="wide")

st.title("🔁 Repeat Site & Area Analysis")
st.markdown("State → City → Site Code → Full Ticket Details (Incident ID, Submitted, Resolved, Reason)")

isp = st.session_state.get('selected_isp')
if not isp:
    st.warning("Please select an ISP from the Home page first.")
    st.stop()

closed_df = st.session_state.get('closed_df')
open_df = st.session_state.get('open_df')

if closed_df is None or closed_df.empty:
    st.warning("No closed tickets data found. Please upload Closed Tickets Excel from **Upload Data** page.")
    st.stop()

# Filter by ISP
if isp != "ALL" and 'isp' in closed_df.columns:
    closed_df = closed_df[closed_df['isp'] == isp].copy()
if open_df is not None and not open_df.empty and isp != "ALL" and 'isp' in open_df.columns:
    open_df = open_df[open_df['isp'] == isp].copy()

st.markdown(f"**Active ISP:** `{isp}` | Closed Records: **{len(closed_df)}** | Open Records: **{len(open_df) if open_df is not None else 0}**")

# Period selector
period = st.radio(
    "Select Period (for Closed / Repeat analysis)",
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
st.success(f"Closed tickets in selected period: **{len(df)}**")

if df.empty:
    st.info("No closed data in selected period.")
    st.stop()

# ===================== TABS =====================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ State → City → Ticket Drill-down",
    "📊 Top Repeated Sites",
    "🔍 Site Detail (Reasons + Days)",
    "📈 Category & Ageing",
    "🚨 Current Open Tickets"
])

# -------------------- TAB 1: State → City → Ticket Drill-down --------------------
with tab1:
    st.subheader("State → City → Full Ticket Details")
    st.caption("Pehle State select karo → phir City → uske baad us city ke saare tickets (Site Code, Incident ID, Submitted, Resolved, Reason) dikhenge.")

    if 'state' not in df.columns:
        st.warning("State column nahi mila. Excel mein State column hona chahiye.")
    else:
        # State counts
        state_counts = df['state'].value_counts().reset_index()
        state_counts.columns = ['State', 'Ticket Count']

        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.markdown("#### State-wise Count")
            st.dataframe(state_counts, use_container_width=True, height=300)

        with col_b:
            fig = px.bar(state_counts, x='State', y='Ticket Count', color='Ticket Count',
                         color_continuous_scale='Blues', text='Ticket Count')
            fig.update_layout(template='plotly_dark', height=300)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔽 Drill-down")

        # State selector
        states_list = ['All States'] + sorted(df['state'].dropna().unique().tolist())
        selected_state = st.selectbox("1. Select State", states_list, key="drill_state")

        if selected_state == 'All States':
            state_df = df.copy()
        else:
            state_df = df[df['state'] == selected_state].copy()

        st.info(f"Selected State: **{selected_state}** → Total Tickets: **{len(state_df)}**")

        # City selector
        if 'city' in state_df.columns and state_df['city'].notna().any():
            city_counts = state_df['city'].value_counts().reset_index()
            city_counts.columns = ['City', 'Ticket Count']

            st.markdown("#### Cities in this State")
            st.dataframe(city_counts, use_container_width=True, height=250)

            cities_list = ['All Cities'] + sorted(state_df['city'].dropna().unique().tolist())
            selected_city = st.selectbox("2. Select City", cities_list, key="drill_city")

            if selected_city == 'All Cities':
                city_df = state_df.copy()
            else:
                city_df = state_df[state_df['city'] == selected_city].copy()

            st.success(f"City: **{selected_city}** → Tickets: **{len(city_df)}**")
        else:
            st.warning("City column missing or empty. Showing all tickets of selected state.")
            city_df = state_df.copy()
            selected_city = "All"

        # Full ticket detail table
        st.markdown("### 📋 Ticket Details")
        st.caption("Site Code | Incident ID | Submitted Time | Resolved Time | Resolution Days | Reason (Last Enclosure)")

        detail_cols = [
            'ticket_id', 'site_code', 'submitted_time', 'resolved_time',
            'resolution_days', 'reason_clean', 'category', 'state', 'city',
            'down_time_min', 'owner'
        ]
        detail_cols = [c for c in detail_cols if c in city_df.columns]

        if detail_cols:
            show_df = city_df[detail_cols].sort_values(
                'submitted_time' if 'submitted_time' in city_df.columns else detail_cols[0],
                ascending=False
            )
            st.dataframe(show_df, use_container_width=True, height=450)

            # Download this view
            def to_excel(dataframe):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='Drilldown')
                return output.getvalue()

            st.download_button(
                "📥 Download this State/City tickets Excel",
                data=to_excel(show_df),
                file_name=f"XTRNATE_{isp}_{selected_state}_{selected_city}_tickets.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Required columns not found.")

# -------------------- TAB 2: Top Repeated Sites --------------------
with tab2:
    st.subheader("Most Repeated Site Codes")
    min_count = st.slider("Minimum repeat count to show", 2, 20, 3, key="min_repeat")

    if 'site_code' in df.columns:
        agg_dict = {'ticket_id': 'count'}
        if 'down_time_min' in df.columns:
            agg_dict['down_time_min'] = 'sum'
        if 'resolution_days' in df.columns:
            agg_dict['resolution_days'] = 'mean'

        site_counts = df.groupby('site_code').agg(agg_dict).reset_index()
        site_counts = site_counts.rename(columns={
            'ticket_id': 'repeat_count',
            'down_time_min': 'total_downtime_min',
            'resolution_days': 'avg_resolution_days'
        })

        if 'state' in df.columns:
            state_map = df.groupby('site_code')['state'].first()
            site_counts['state'] = site_counts['site_code'].map(state_map)
        if 'city' in df.columns:
            city_map = df.groupby('site_code')['city'].first()
            site_counts['city'] = site_counts['site_code'].map(city_map)

        site_counts = site_counts[site_counts['repeat_count'] >= min_count].sort_values('repeat_count', ascending=False)
        st.dataframe(site_counts, use_container_width=True, height=400)

        top15 = site_counts.head(15)
        if not top15.empty:
            fig = px.bar(top15, x='site_code', y='repeat_count', color='repeat_count',
                         color_continuous_scale='Reds', text='repeat_count',
                         title="Top 15 Repeated Sites")
            fig.update_layout(template='plotly_dark', height=400, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("site_code column not found.")

# -------------------- TAB 3: Site Detail --------------------
with tab3:
    st.subheader("Detailed View for High-Repeat Sites")
    st.caption("Select a site → har occurrence ka reason + resolution days")

    if 'site_code' not in df.columns:
        st.warning("site_code not available")
    else:
        site_counts = df['site_code'].value_counts()
        high_sites = site_counts[site_counts >= 2].index.tolist()

        if not high_sites:
            st.info("No site has repeated 2 or more times in this period.")
        else:
            selected_site = st.selectbox("Select Site Code", high_sites, key="site_detail_select")
            site_data = df[df['site_code'] == selected_site].copy()
            site_data = site_data.sort_values('submitted_time', ascending=False) if 'submitted_time' in site_data.columns else site_data

            st.markdown(f"### Site: **{selected_site}** — Total Downs: **{len(site_data)}**")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Occurrences", len(site_data))
            if 'resolution_days' in site_data.columns:
                m2.metric("Avg Resolution Days", round(site_data['resolution_days'].mean(), 1))
                m3.metric("Max Resolution Days", round(site_data['resolution_days'].max(), 1))
            if 'state' in site_data.columns:
                m4.metric("State", str(site_data['state'].iloc[0]) if len(site_data) > 0 else "-")

            detail_cols = ['ticket_id', 'submitted_time', 'resolved_time', 'resolution_days',
                           'category', 'reason_clean', 'state', 'city', 'down_time_min']
            detail_cols = [c for c in detail_cols if c in site_data.columns]
            st.dataframe(site_data[detail_cols], use_container_width=True, height=400)

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

            df_temp = df.copy()
            df_temp['ageing'] = df_temp['resolution_days'].apply(ageing_bucket)
            age_order = ['0-24 Hrs', '24-48 Hrs', '48-72 Hrs', '3-5 Days', 'Above 5 Days', 'Unknown']
            age_counts = df_temp['ageing'].value_counts().reindex(age_order, fill_value=0).reset_index()
            age_counts.columns = ['Ageing Bucket', 'Count']

            fig = px.bar(age_counts, x='Ageing Bucket', y='Count', color='Count',
                         color_continuous_scale='OrRd', text='Count',
                         title="Resolution Ageing Distribution")
            fig.update_layout(template='plotly_dark', height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(age_counts, use_container_width=True)
        else:
            st.info("Resolution days not calculated (need Submitted + Resolved Time-Active)")

# -------------------- TAB 5: Current Open Tickets --------------------
with tab5:
    st.subheader("🚨 Current Open Tickets (Live)")
    st.caption("Yeh Open tickets hain jo abhi resolve nahi hue. HCIN / ONEOTT / ALL ke hisaab se filter hota hai.")

    if open_df is None or open_df.empty:
        st.info("No open tickets loaded. Upload Open Tickets Excel from Upload Data page.")
    else:
        st.metric("Total Open Tickets", len(open_df))

        # State wise open
        if 'state' in open_df.columns:
            st.markdown("#### Open Tickets by State")
            open_state = open_df['state'].value_counts().reset_index()
            open_state.columns = ['State', 'Open Count']
            fig = px.bar(open_state, x='State', y='Open Count', color='Open Count',
                         color_continuous_scale='Oranges', text='Open Count')
            fig.update_layout(template='plotly_dark', height=350)
            st.plotly_chart(fig, use_container_width=True)

        # Full open list
        open_cols = ['ticket_id', 'site_code', 'submitted_time', 'open_hours',
                     'status', 'state', 'city', 'reason', 'owner']
        open_cols = [c for c in open_cols if c in open_df.columns]

        st.markdown("#### All Open Tickets Detail")
        st.dataframe(
            open_df[open_cols].sort_values('open_hours', ascending=False) if 'open_hours' in open_df.columns else open_df[open_cols],
            use_container_width=True,
            height=450
        )

        def to_excel_open(dataframe):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                dataframe.to_excel(writer, index=False, sheet_name='Open_Tickets')
            return output.getvalue()

        st.download_button(
            "📥 Download Open Tickets Excel",
            data=to_excel_open(open_df[open_cols]),
            file_name=f"XTRNATE_Open_{isp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ===================== DOWNLOAD SUMMARY =====================
st.markdown("---")
st.subheader("Download Summary")

def to_excel(dataframe):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='Summary')
    return output.getvalue()

if 'site_code' in df.columns:
    summary = df.groupby('site_code').size().reset_index(name='repeat_count')
    summary = summary.sort_values('repeat_count', ascending=False)
    st.download_button(
        "📥 Download Site Repeat Summary",
        data=to_excel(summary),
        file_name=f"XTRNATE_Repeat_Summary_{isp}_{period.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
