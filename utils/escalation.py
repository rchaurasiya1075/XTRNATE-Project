import pandas as pd
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def get_escalation_path(isp):
    return os.path.join(DATA_DIR, f"escalation_{isp.lower()}.csv")

def load_escalation_matrix(isp):
    """Load escalation matrix for given ISP"""
    path = get_escalation_path(isp)
    if os.path.exists(path):
        df = pd.read_csv(path)
        return df
    else:
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
        return default

def save_escalation_matrix(isp, df):
    """Save escalation matrix"""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = get_escalation_path(isp)
    df.to_csv(path, index=False)

def calculate_escalation_level(open_hours, matrix_df):
    """Return escalation level based on open hours"""
    if matrix_df is None or matrix_df.empty:
        return 'L1', 'Unknown'
    
    matrix_df = matrix_df.sort_values('Min_Hours')
    
    for _, row in matrix_df.iterrows():
        min_h = float(row['Min_Hours'])
        max_h = float(row['Max_Hours'])
        if min_h <= open_hours < max_h:
            return row['Level'], row['Name']
    
    last = matrix_df.iloc[-1]
    return last['Level'], last['Name']

def get_escalation_color(level):
    """Return color for level"""
    colors = {
        'L1': '#22c55e',
        'L2': '#eab308',
        'L3': '#f97316',
        'L4': '#ef4444',
    }
    return colors.get(str(level).upper(), '#6b7280')

def apply_escalation_to_open(open_df, matrix_df):
    """Add escalation columns to open tickets"""
    if open_df.empty:
        return open_df
    
    df = open_df.copy()
    
    levels = []
    names = []
    colors = []
    
    for hours in df.get('open_hours', [0]*len(df)):
        level, name = calculate_escalation_level(hours if pd.notna(hours) else 0, matrix_df)
        levels.append(level)
        names.append(name)
        colors.append(get_escalation_color(level))
    
    df['escalation_level'] = levels
    df['escalation_person'] = names
    df['escalation_color'] = colors
    
    return df
