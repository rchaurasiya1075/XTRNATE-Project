import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

def clean_column_names(df):
    """Standardize column names"""
    df.columns = df.columns.str.strip()
    return df

def parse_datetime(series):
    """Parse various datetime formats"""
    return pd.to_datetime(series, errors='coerce', dayfirst=False)

def detect_category(reason_text):
    """Auto detect complaint category from Last Enclosure / RFO text"""
    if pd.isna(reason_text):
        return 'Other'
    text = str(reason_text).lower()
    
    if any(k in text for k in ['fiber cut', 'fibre cut', 'fiber loss', 'fibre loss', 'link down', 'link was', 'ofc', 'optical', 'device hung', 'reboot', 'hardware', 'signal', 'attenuation', 'modem', 'router hung']):
        return 'Technical Issue'
    if any(k in text for k in ['backend', 'core network', 'noc end', 'from our end', 'server']):
        return 'Backend Issue'
    if any(k in text for k in ['vendor', 'partner', 'isp downtime', 'unplanned isp', 'bsnl', 'airtel', 'sub-vendor']):
        return 'Vendor Issue'
    if any(k in text for k in ['customer', 'customer end', 'internal wiring', 'power issue', 'ups', 'site power', 'no issue observed']):
        return 'Customer End Issue'
    if any(k in text for k in ['commercial', 'billing', 'payment', 'renewal']):
        return 'Commercial Issue'
    return 'Other'

def process_closed_tickets(df):
    """Process closed tickets Excel"""
    df = clean_column_names(df)
    
    # Flexible rename map (handle common variations)
    rename_map = {
        'Incident ID': 'ticket_id',
        'Request Title': 'site_code',
        'Submitted Time': 'submitted_time',
        'CurrentStatus': 'status',
        'Current Status': 'status',
        'Owner': 'owner',
        'Last Enclosure Comment(Active)': 'reason',
        'Last Enclosure Comment': 'reason',
        'State': 'state',
        'City': 'city',
        'Resolved Time-Active': 'resolved_time',
        'Resolved Time': 'resolved_time',
        'Close Time(Active)': 'close_time',
        'Down Time': 'down_time_min',
        'Down time-Archive': 'down_time_min',
        'Resolution time': 'resolution_time_raw',
        'Assign to FE Time-Active': 'assign_fe_time',
        'Last Modified Time': 'last_modified',
        'SubmittedBy': 'submitted_by',
        'Root Cause': 'root_cause'
    }
    
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    for col in ['submitted_time', 'resolved_time', 'assign_fe_time', 'last_modified', 'close_time']:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
    
    if 'down_time_min' in df.columns:
        df['down_time_min'] = pd.to_numeric(df['down_time_min'], errors='coerce')
    
    # Calculate resolution days
    if 'submitted_time' in df.columns and 'resolved_time' in df.columns:
        df['resolution_days'] = (df['resolved_time'] - df['submitted_time']).dt.total_seconds() / 86400
        df['resolution_days'] = df['resolution_days'].round(1)
    elif 'down_time_min' in df.columns:
        df['resolution_days'] = (df['down_time_min'] / 1440).round(1)  # minutes to days
    else:
        df['resolution_days'] = np.nan
    
    if 'owner' in df.columns:
        df['isp'] = df['owner'].astype(str).apply(
            lambda x: 'HCIN' if 'HCIN' in x.upper() else ('ONEOTT' if 'ONEOTT' in x.upper() or 'OTT' in x.upper() else 'OTHER')
        )
    
    if 'reason' in df.columns:
        df['reason_clean'] = df['reason'].astype(str).str[:120]
        df['category'] = df['reason'].apply(detect_category)
    else:
        df['category'] = 'Other'
    
    if 'site_code' in df.columns:
        df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
    
    return df

def process_open_tickets(df):
    """Process open tickets Excel"""
    df = clean_column_names(df)
    
    rename_map = {
        'Incident ID': 'ticket_id',
        'Request Title': 'site_code',
        'Submitted Time': 'submitted_time',
        'CurrentStatus': 'status',
        'Current Status': 'status',
        'Owner': 'owner',
        'Last Enclosure Comment(Active)': 'reason',
        'State': 'state',
        'City': 'city',
        'Assign to FE Time-Active': 'assign_fe_time',
        'Last Modified Time': 'last_modified',
        'SubmittedBy': 'submitted_by',
        'ETA': 'eta',
        'Caller Name': 'caller_name'
    }
    
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    for col in ['submitted_time', 'assign_fe_time', 'last_modified']:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
    
    if 'owner' in df.columns:
        df['isp'] = df['owner'].astype(str).apply(
            lambda x: 'HCIN' if 'HCIN' in x.upper() else ('ONEOTT' if 'ONEOTT' in x.upper() or 'OTT' in x.upper() else 'OTHER')
        )
    
    if 'submitted_time' in df.columns:
        now = datetime.now()
        df['open_hours'] = (now - df['submitted_time']).dt.total_seconds() / 3600
        df['open_hours'] = df['open_hours'].round(1)
    
    if 'site_code' in df.columns:
        df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
    
    return df

def process_site_master(df):
    """Process site master data"""
    df = clean_column_names(df)
    
    rename_map = {
        'HughesSitecode': 'site_code',
        'Bank Name': 'bank_name',
        'Branch Name': 'branch_name',
        'State': 'state',
        'Media': 'media',
        'ISP Name': 'isp_name',
        'Partner': 'partner',
        'Phase Details': 'phase'
    }
    
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    if 'site_code' in df.columns:
        df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
    
    return df

def merge_with_site_master(tickets_df, site_df):
    """Join tickets with site master"""
    if site_df is None or site_df.empty:
        return tickets_df
    
    site_df = site_df.copy()
    site_df['site_code'] = site_df['site_code'].astype(str).str.strip().str.upper()
    
    tickets_df = tickets_df.copy()
    if 'site_code' in tickets_df.columns:
        tickets_df['site_code'] = tickets_df['site_code'].astype(str).str.strip().str.upper()
    
    cols_to_merge = [c for c in ['site_code', 'bank_name', 'branch_name', 'state', 'media', 'isp_name', 'partner', 'phase'] if c in site_df.columns]
    
    merged = tickets_df.merge(
        site_df[cols_to_merge],
        on='site_code',
        how='left',
        suffixes=('', '_master')
    )
    
    if 'state_master' in merged.columns:
        merged['state'] = merged['state_master'].fillna(merged.get('state'))
        merged = merged.drop(columns=['state_master'], errors='ignore')
    
    return merged

def filter_by_period(df, period='1M'):
    """Filter dataframe by period based on submitted_time"""
    if 'submitted_time' not in df.columns or df.empty:
        return df
    
    now = datetime.now()
    if period == '1M':
        start = now - timedelta(days=30)
    elif period == '2M':
        start = now - timedelta(days=60)
    elif period == '3M':
        start = now - timedelta(days=90)
    elif period == '6M':
        start = now - timedelta(days=180)
    else:
        return df
    
    return df[df['submitted_time'] >= start].copy()

def get_summary_stats(df):
    """Get key summary statistics"""
    if df.empty:
        return {}
    
    stats = {
        'total_tickets': len(df),
        'total_downtime_min': df['down_time_min'].sum() if 'down_time_min' in df.columns else 0,
        'avg_downtime_min': df['down_time_min'].mean() if 'down_time_min' in df.columns else 0,
        'max_downtime_min': df['down_time_min'].max() if 'down_time_min' in df.columns else 0,
    }
    
    if 'down_time_min' in df.columns:
        stats['avg_downtime_hrs'] = round(stats['avg_downtime_min'] / 60, 2)
        stats['total_downtime_hrs'] = round(stats['total_downtime_min'] / 60, 2)
    
    return stats
