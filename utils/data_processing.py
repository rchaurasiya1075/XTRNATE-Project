import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

def clean_column_names(df):
    """Standardize column names safely"""
    try:
        df.columns = [str(c).strip() for c in df.columns]
    except Exception:
        pass
    return df

def parse_datetime(series):
    """Parse various datetime formats"""
    try:
        return pd.to_datetime(series, errors='coerce', dayfirst=False)
    except Exception:
        return pd.Series([pd.NaT] * len(series))

def detect_category(reason_text):
    """Auto detect complaint category from Last Enclosure / RFO text"""
    try:
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
    except Exception:
        return 'Other'

def process_closed_tickets(df):
    """Process closed tickets Excel - robust version"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    df = df.copy()
    df = clean_column_names(df)
    
    # Flexible rename map
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
    
    # Only rename existing columns
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)
    
    # Parse dates safely
    for col in ['submitted_time', 'resolved_time', 'assign_fe_time', 'last_modified', 'close_time']:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
    
    # Numeric downtime
    if 'down_time_min' in df.columns:
        df['down_time_min'] = pd.to_numeric(df['down_time_min'], errors='coerce')
    
    # Resolution days
    try:
        if 'submitted_time' in df.columns and 'resolved_time' in df.columns:
            delta = df['resolved_time'] - df['submitted_time']
            df['resolution_days'] = delta.dt.total_seconds() / 86400
            df['resolution_days'] = pd.to_numeric(df['resolution_days'], errors='coerce').round(1)
        elif 'down_time_min' in df.columns:
            df['resolution_days'] = (pd.to_numeric(df['down_time_min'], errors='coerce') / 1440).round(1)
        else:
            df['resolution_days'] = np.nan
    except Exception:
        df['resolution_days'] = np.nan
    
    # ISP detection
    if 'owner' in df.columns:
        def get_isp(x):
            try:
                s = str(x).upper()
                if 'HCIN' in s:
                    return 'HCIN'
                if 'ONEOTT' in s or 'OTT' in s:
                    return 'ONEOTT'
                return 'OTHER'
            except:
                return 'OTHER'
        df['isp'] = df['owner'].apply(get_isp)
    
    # Reason + Category
    if 'reason' in df.columns:
        try:
            df['reason_clean'] = df['reason'].astype(str).str.slice(0, 120)
        except Exception:
            df['reason_clean'] = df['reason'].astype(str)
        try:
            df['category'] = df['reason'].apply(detect_category)
        except Exception:
            df['category'] = 'Other'
    else:
        df['category'] = 'Other'
        df['reason_clean'] = ''
    
    # Site code clean
    if 'site_code' in df.columns:
        try:
            df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = df['site_code'].astype(str)
    
    return df

def process_open_tickets(df):
    """Process open tickets Excel - robust version"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    df = df.copy()
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
    
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)
    
    for col in ['submitted_time', 'assign_fe_time', 'last_modified']:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
    
    if 'owner' in df.columns:
        def get_isp(x):
            try:
                s = str(x).upper()
                if 'HCIN' in s:
                    return 'HCIN'
                if 'ONEOTT' in s or 'OTT' in s:
                    return 'ONEOTT'
                return 'OTHER'
            except:
                return 'OTHER'
        df['isp'] = df['owner'].apply(get_isp)
    
    if 'submitted_time' in df.columns:
        try:
            now = datetime.now()
            df['open_hours'] = (now - df['submitted_time']).dt.total_seconds() / 3600
            df['open_hours'] = pd.to_numeric(df['open_hours'], errors='coerce').round(1)
        except Exception:
            df['open_hours'] = np.nan
    
    if 'site_code' in df.columns:
        try:
            df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = df['site_code'].astype(str)
    
    return df

def process_site_master(df):
    """Process site master data"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    df = df.copy()
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
    
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)
    
    if 'site_code' in df.columns:
        try:
            df['site_code'] = df['site_code'].astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = df['site_code'].astype(str)
    
    return df

def merge_with_site_master(tickets_df, site_df):
    """Join tickets with site master"""
    if site_df is None or site_df.empty or tickets_df is None or tickets_df.empty:
        return tickets_df
    
    try:
        site_df = site_df.copy()
        tickets_df = tickets_df.copy()
        
        if 'site_code' in site_df.columns:
            site_df['site_code'] = site_df['site_code'].astype(str).str.strip().str.upper()
        if 'site_code' in tickets_df.columns:
            tickets_df['site_code'] = tickets_df['site_code'].astype(str).str.strip().str.upper()
        
        cols_to_merge = [c for c in ['site_code', 'bank_name', 'branch_name', 'state', 'media', 'isp_name', 'partner', 'phase'] if c in site_df.columns]
        
        if 'site_code' not in cols_to_merge:
            return tickets_df
        
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
    except Exception:
        return tickets_df

def filter_by_period(df, period='1M'):
    """Filter dataframe by period based on submitted_time"""
    if df is None or df.empty or 'submitted_time' not in df.columns:
        return df if df is not None else pd.DataFrame()
    
    try:
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
    except Exception:
        return df

def get_summary_stats(df):
    """Get key summary statistics"""
    if df is None or df.empty:
        return {}
    
    stats = {
        'total_tickets': len(df),
        'total_downtime_min': 0,
        'avg_downtime_min': 0,
        'max_downtime_min': 0,
        'avg_downtime_hrs': 0,
        'total_downtime_hrs': 0,
    }
    
    try:
        if 'down_time_min' in df.columns:
            stats['total_downtime_min'] = df['down_time_min'].sum(skipna=True)
            stats['avg_downtime_min'] = df['down_time_min'].mean(skipna=True)
            stats['max_downtime_min'] = df['down_time_min'].max(skipna=True)
            stats['avg_downtime_hrs'] = round(stats['avg_downtime_min'] / 60, 2) if stats['avg_downtime_min'] else 0
            stats['total_downtime_hrs'] = round(stats['total_downtime_min'] / 60, 2) if stats['total_downtime_min'] else 0
    except Exception:
        pass
    
    return stats
