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

def process_closed_tickets(df):
    """Process closed tickets Excel"""
    df = clean_column_names(df)
    
    rename_map = {
        'Incident ID': 'ticket_id',
        'Request Title': 'site_code',
        'Submitted Time': 'submitted_time',
        'CurrentStatus': 'status',
        'Owner': 'owner',
        'Last Enclosure Comment(Active)': 'reason',
        'State': 'state',
        'Resolved Time-Active': 'resolved_time',
        'Down Time': 'down_time_min',
        'Assign to FE Time-Active': 'assign_fe_time',
        'Last Modified Time': 'last_modified',
        'SubmittedBy': 'submitted_by'
    }
    
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    for col in ['submitted_time', 'resolved_time', 'assign_fe_time', 'last_modified']:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
    
    if 'down_time_min' in df.columns:
        df['down_time_min'] = pd.to_numeric(df['down_time_min'], errors='coerce')
    
    if 'owner' in df.columns:
        df['isp'] = df['owner'].astype(str).apply(lambda x: 'HCIN' if 'HCIN' in x.upper() else ('ONEOTT' if 'ONEOTT' in x.upper() or 'OTT' in x.upper() else 'OTHER'))
    
    if 'reason' in df.columns:
        df['reason_clean'] = df['reason'].astype(str).str.extract(r'(RFO:.*|Resolved.*|Call on Hold.*|Assign to FE.*|Comment.*)', expand=False)
        df['reason_clean'] = df['reason_clean'].fillna(df['reason'].astype(str).str[:80])
    
    return df

def process_open_tickets(df):
    """Process open tickets Excel"""
    df = clean_column_names(df)
    
    rename_map = {
        'Incident ID': 'ticket_id',
        'Request Title': 'site_code',
        'Submitted Time': 'submitted_time',
        'CurrentStatus': 'status',
        'Owner': 'owner',
        'Last Enclosure Comment(Active)': 'reason',
        'State': 'state',
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
        df['isp'] = df['owner'].astype(str).apply(lambda x: 'HCIN' if 'HCIN' in x.upper() else ('ONEOTT' if 'ONEOTT' in x.upper() or 'OTT' in x.upper() else 'OTHER'))
    
    if 'submitted_time' in df.columns:
        now = datetime.now()
        df['open_hours'] = (now - df['submitted_time']).dt.total_seconds() / 3600
        df['open_hours'] = df['open_hours'].round(1)
    
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
    tickets_df['site_code'] = tickets_df['site_code'].astype(str).str.strip().str.upper()
    
    merged = tickets_df.merge(
        site_df[['site_code', 'bank_name', 'branch_name', 'state', 'media', 'isp_name', 'partner', 'phase']],
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
