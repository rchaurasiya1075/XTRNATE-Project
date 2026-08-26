import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

def clean_column_names(df):
    """Standardize column names safely + remove duplicates"""
    try:
        df.columns = [str(c).strip() for c in df.columns]
        cols = pd.Series(df.columns)
        for dup in cols[cols.duplicated()].unique():
            idxs = cols[cols == dup].index.tolist()
            for i, idx in enumerate(idxs[1:], 1):
                cols.iloc[idx] = f"{dup}_{i}"
        df.columns = cols
    except Exception:
        pass
    return df

def parse_datetime(series):
    try:
        if not isinstance(series, (pd.Series, list, tuple, np.ndarray)):
            return pd.Series([pd.NaT] * (len(series) if hasattr(series, '__len__') else 1))
        return pd.to_datetime(series, errors='coerce', dayfirst=False)
    except Exception:
        try:
            return pd.Series([pd.NaT] * len(series))
        except:
            return pd.Series(dtype='datetime64[ns]')

def detect_category(reason_text):
    """Fallback only when Problem Classification is empty."""
    try:
        if pd.isna(reason_text):
            return 'Others'
        text = str(reason_text).lower()
        if 'fibre cut' in text or 'fiber cut' in text:
            return 'Fibre Cut'
        if 'backend' in text or 'upstream' in text or 'node isolation' in text:
            return 'Backend /Upstream issue/Node isolation at ISP end'
        if 'house keep' in text or 'housekeep' in text:
            return 'House keeping'
        if 'third party' in text:
            return 'Third Party'
        if 'force maj' in text or 'natural calamity' in text or 'landslide' in text:
            return 'Natural Calamity'
        if 'rebooted' in text or ('reboot' in text and ('onu' in text or 'modem' in text)):
            return 'ONU/Media converter/ZTE modem Rebooted'
        if 'onu' in text or 'modem' in text or 'media converter' in text:
            return 'ONU/Media converter/ZTE modem is faulty'
        if 'power outage' in text:
            return 'Power outage at ISP Node'
        if 'lan' in text:
            return 'Problem in LAN connectivity.'
        if 'sdwan' in text or 'cable disconnect' in text:
            return 'Interface down/ Cable disconnected from SDWAN'
        if 'no changes' in text or 'nff' in text:
            return 'No changes done'
        return 'Others'
    except Exception:
        return 'Others'

def safe_series(df, col):
    try:
        data = df[col]
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]
        return data
    except Exception:
        return pd.Series(dtype=object)

def process_closed_tickets(df):
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
        'Last Enclosure Comment': 'reason',
        'State': 'state',
        'City': 'city',
        'Resolved Time-Active': 'resolved_time',
        'Resolved Time': 'resolved_time',
        'Close Time(Active)': 'close_time',
        'Down Time': 'down_time_min',
        'Down time-Archive': 'down_time_archive',
        'Resolution time': 'resolution_time_raw',
        'Assign to FE Time-Active': 'assign_fe_time',
        'Last Modified Time': 'last_modified',
        'SubmittedBy': 'submitted_by',
        'Root Cause': 'root_cause',
        'Problem Classification': 'problem_class',
        'Problem Related To': 'problem_related',
        'Problem Reported': 'problem_reported',
        'Classification': 'mfc_class',
        'Site': 'site_alt',
    }

    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)
    df = clean_column_names(df)

    for col in ['submitted_time', 'resolved_time', 'assign_fe_time', 'last_modified', 'close_time']:
        if col in df.columns:
            df[col] = parse_datetime(safe_series(df, col))

    if 'down_time_min' in df.columns:
        try:
            df['down_time_min'] = pd.to_numeric(safe_series(df, 'down_time_min'), errors='coerce')
        except Exception:
            df['down_time_min'] = np.nan

    try:
        if 'submitted_time' in df.columns and 'resolved_time' in df.columns:
            delta = safe_series(df, 'resolved_time') - safe_series(df, 'submitted_time')
            df['resolution_days'] = pd.to_numeric(delta.dt.total_seconds() / 86400, errors='coerce').round(1)
        elif 'down_time_min' in df.columns:
            df['resolution_days'] = (pd.to_numeric(safe_series(df, 'down_time_min'), errors='coerce') / 1440).round(1)
        else:
            df['resolution_days'] = np.nan
    except Exception:
        df['resolution_days'] = np.nan

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
        try:
            df['isp'] = safe_series(df, 'owner').apply(get_isp)
        except Exception:
            df['isp'] = 'OTHER'

    # Category = exact Problem Classification from sheet
    if 'problem_class' in df.columns:
        pc = safe_series(df, 'problem_class').astype(str).str.strip()
        blank = pc.isin(['', '--', 'nan', 'None', 'NaN'])
        df['category'] = pc
        if 'reason' in df.columns:
            df.loc[blank, 'category'] = safe_series(df, 'reason').apply(detect_category)
        else:
            df.loc[blank, 'category'] = 'Others'
    elif 'reason' in df.columns:
        df['category'] = safe_series(df, 'reason').apply(detect_category)
    else:
        df['category'] = 'Others'

    if 'reason' in df.columns:
        try:
            df['reason_clean'] = safe_series(df, 'reason').astype(str).str.slice(0, 120)
        except Exception:
            df['reason_clean'] = ''
    else:
        df['reason_clean'] = ''

    if 'site_code' in df.columns:
        try:
            df['site_code'] = safe_series(df, 'site_code').astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = safe_series(df, 'site_code').astype(str)

    return df

def process_open_tickets(df):
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
        'Caller Name': 'caller_name',
        'Problem Classification': 'problem_class',
        'Problem Related To': 'problem_related',
        'Problem Reported': 'problem_reported',
        'Root Cause': 'root_cause',
    }
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)
    df = clean_column_names(df)

    for col in ['submitted_time', 'assign_fe_time', 'last_modified']:
        if col in df.columns:
            df[col] = parse_datetime(safe_series(df, col))

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
        try:
            df['isp'] = safe_series(df, 'owner').apply(get_isp)
        except Exception:
            df['isp'] = 'OTHER'

    if 'submitted_time' in df.columns:
        try:
            now = datetime.now()
            delta = now - safe_series(df, 'submitted_time')
            df['open_hours'] = pd.to_numeric(delta.dt.total_seconds() / 3600, errors='coerce').round(1)
        except Exception:
            df['open_hours'] = np.nan

    if 'site_code' in df.columns:
        try:
            df['site_code'] = safe_series(df, 'site_code').astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = safe_series(df, 'site_code').astype(str)

    return df

def process_site_master(df):
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
    df = clean_column_names(df)
    if 'site_code' in df.columns:
        try:
            df['site_code'] = safe_series(df, 'site_code').astype(str).str.strip().str.upper()
        except Exception:
            df['site_code'] = safe_series(df, 'site_code').astype(str)
    return df

def merge_with_site_master(tickets_df, site_df):
    if site_df is None or site_df.empty or tickets_df is None or tickets_df.empty:
        return tickets_df
    try:
        site_df = site_df.copy()
        tickets_df = tickets_df.copy()
        if 'site_code' in site_df.columns:
            site_df['site_code'] = safe_series(site_df, 'site_code').astype(str).str.strip().str.upper()
        if 'site_code' in tickets_df.columns:
            tickets_df['site_code'] = safe_series(tickets_df, 'site_code').astype(str).str.strip().str.upper()
        cols_to_merge = [c for c in ['site_code', 'bank_name', 'branch_name', 'state', 'media', 'isp_name', 'partner', 'phase'] if c in site_df.columns]
        if 'site_code' not in cols_to_merge:
            return tickets_df
        merged = tickets_df.merge(site_df[cols_to_merge], on='site_code', how='left', suffixes=('', '_master'))
        if 'state_master' in merged.columns:
            merged['state'] = merged['state_master'].fillna(merged.get('state'))
            merged = merged.drop(columns=['state_master'], errors='ignore')
        return merged
    except Exception:
        return tickets_df

def filter_by_period(df, period='1M'):
    if df is None or df.empty or 'submitted_time' not in df.columns:
        return df if df is not None else pd.DataFrame()
    try:
        now = datetime.now()
        days = {'1M': 30, '2M': 60, '3M': 90, '6M': 180}.get(period)
        if not days:
            return df
        return df[df['submitted_time'] >= now - timedelta(days=days)].copy()
    except Exception:
        return df

def get_summary_stats(df):
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
            s = safe_series(df, 'down_time_min')
            stats['total_downtime_min'] = s.sum(skipna=True)
            stats['avg_downtime_min'] = s.mean(skipna=True)
            stats['max_downtime_min'] = s.max(skipna=True)
            stats['avg_downtime_hrs'] = round(stats['avg_downtime_min'] / 60, 2) if stats['avg_downtime_min'] else 0
            stats['total_downtime_hrs'] = round(stats['total_downtime_min'] / 60, 2) if stats['total_downtime_min'] else 0
    except Exception:
        pass
    return stats
