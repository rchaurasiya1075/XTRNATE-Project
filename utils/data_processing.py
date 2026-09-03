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

def _norm_remark(reason_text):
    t = str(reason_text or '').lower()
    t = t.replace('close_enclosure', ' ')
    t = t.replace('/', ' ').replace('\\', ' ').replace('::', ' ').replace('.', ' ').replace('_', ' ')
    t = re.sub(r'\s+', ' ', t)
    return t

def detect_category(reason_text):
    """One ticket = one category. Specific last-remark overrides first."""
    try:
        if pd.isna(reason_text):
            return 'Others'
        text = _norm_remark(reason_text)

        if (
            'alternate service provider' in text
            or 'provisioned on alternate' in text
            or 'link provisioned on alternate' in text
            or ('existing operator' in text and ('not stable' in text or 'link not stable' in text))
            or ('link not stable' in text and 'alternate' in text)
        ):
            return 'Vendor Change'

        if (
            'not feasible' in text
            or 'technically not feasible' in text
            or 'rolled back by isp' in text
            or 'has become technically not' in text
        ):
            return 'NOT Feasible for service'

        if (
            'post rebooting onu' in text
            or 'rebooting onu' in text
            or 'post reboot' in text
            or ('reboot' in text and 'onu' in text and 'customer intervention' in text)
        ):
            return 'ONU/Media converter/ZTE modem Rebooted'

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

def classify_isp(x):
    """Owner column → ISP. HCIN / ONEOTT aliases; any other owner name is also an ISP."""
    try:
        s = str(x or '').strip()
        if not s or s.lower() in ('nan', 'none', '-', '--', 'nat', 'null', ''):
            return 'UNKNOWN'
        u = s.upper()
        if 'HCIN' in u or 'HICOM' in u:
            return 'HCIN'
        if 'ONEOTT' in u or 'ONE OTT' in u or 'CELERITY' in u:
            return 'ONEOTT'
        if re.search(r'(^|[^A-Z0-9])OTT([^A-Z0-9]|$)', u):
            return 'ONEOTT'
        name = re.split(r'\s*[-–|]\s*', s, maxsplit=1)[0].strip()
        name = re.sub(r'(?i)\s*(fe\s*)?rollout\s*partner.*', '', name).strip()
        return name if name else s
    except Exception:
        return 'UNKNOWN'

def isp_options(*frames, add_all=True):
    """Unique ISP names from loaded tickets (Owner). New ISP auto-appears."""
    names = []
    seen = set()
    for df in frames:
        if df is None or getattr(df, 'empty', True):
            continue
        series = None
        if 'isp' in df.columns:
            series = df['isp']
        elif 'owner' in df.columns:
            series = df['owner'].map(classify_isp)
        if series is None:
            continue
        for v in series.dropna().astype(str).unique():
            v = str(v).strip()
            if not v or v.upper() in ('UNKNOWN', 'NAN', 'NONE', 'OTHER', 'NAT'):
                continue
            if v not in seen:
                seen.add(v)
                names.append(v)
    head = [x for x in ('HCIN', 'ONEOTT') if x in seen]
    rest = sorted(x for x in names if x not in head)
    opts = head + rest
    return (['ALL'] + opts) if add_all else opts


def isp_aliases(name):
    """Expand one ISP pick to matching labels (ONEOTT ↔ OTT ↔ CELERITY)."""
    u = str(name or "").strip().upper()
    if not u:
        return set()
    aliases = {u, str(name).strip()}
    if u in ("ONEOTT", "OTT", "CELERITY", "ONE OTT"):
        aliases.update({"ONEOTT", "OTT", "CELERITY", "ONE OTT"})
    if u in ("HCIN", "HICOM", "HCIL"):
        aliases.update({"HCIN", "HICOM", "HCIL"})
    return {a for a in aliases if a}


def filter_by_isps(df, selected=None):
    """Keep rows for selected ISP names. None or ['ALL'] → no filter. [] → empty."""
    if df is None:
        return pd.DataFrame()
    if getattr(df, "empty", True):
        return df
    if selected is None:
        return df
    if isinstance(selected, str):
        selected = [selected]
    names = [str(x).strip() for x in selected if x and str(x).strip()]
    if not names:
        return df.iloc[0:0].copy()
    if any(str(x).upper() == "ALL" for x in names):
        return df
    aliases = set()
    for n in names:
        aliases |= isp_aliases(n)
        aliases.add(n)
    aliases_u = {str(a).upper() for a in aliases}

    mask = pd.Series(False, index=df.index)
    if "isp" in df.columns:
        mask = mask | df["isp"].astype(str).str.strip().str.upper().isin(aliases_u)
    if "owner" in df.columns:
        classified = df["owner"].map(classify_isp).astype(str).str.upper()
        mask = mask | classified.isin(aliases_u)
        mask = mask | df["owner"].astype(str).str.strip().str.upper().isin(aliases_u)
    if "partner" in df.columns:
        mask = mask | df["partner"].astype(str).str.strip().str.upper().isin(aliases_u)
    if not mask.any() and "isp" not in df.columns and "owner" not in df.columns:
        return df
    return df[mask].copy()


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
        try:
            df['isp'] = safe_series(df, 'owner').apply(classify_isp)
        except Exception:
            df['isp'] = 'UNKNOWN'

    if 'reason' in df.columns:
        remark_cat = safe_series(df, 'reason').apply(detect_category)
        override_names = {
            'NOT Feasible for service',
            'Vendor Change',
            'ONU/Media converter/ZTE modem Rebooted',
        }
        use_override = remark_cat.isin(list(override_names))
    else:
        remark_cat = None
        use_override = None

    if 'problem_class' in df.columns:
        pc = safe_series(df, 'problem_class').astype(str).str.strip()
        blank = pc.isin(['', '--', 'nan', 'None', 'NaN'])
        df['category'] = pc
        if remark_cat is not None:
            df.loc[blank, 'category'] = remark_cat[blank]
            df.loc[use_override, 'category'] = remark_cat[use_override]
    elif remark_cat is not None:
        df['category'] = remark_cat
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
        try:
            df['isp'] = safe_series(df, 'owner').apply(classify_isp)
        except Exception:
            df['isp'] = 'UNKNOWN'

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
    if 'isp_name' in df.columns:
        try:
            df['isp'] = safe_series(df, 'isp_name').apply(classify_isp)
        except Exception:
            pass
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
