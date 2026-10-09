"""Extra client projects: their own Google Sheet + the column names in that file.

Built-in projects (Xtranet, Shell, Backhaul, Link, DGLL) are never read from here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_PATH = Path(__file__).with_name("custom_projects.json")

# internal key → header that process_closed_tickets already understands
CANON = {
    "site_code": "Request Title",
    "ticket_id": "Incident ID",
    "submitted_time": "Submitted Time",
    "status": "CurrentStatus",
    "owner": "Owner",
    "reason": "Last Enclosure Comment(Active)",
    "resolved_time": "Resolved Time",
    "state": "State",
    "city": "City",
    "down_time_min": "Down Time",
}

FIELDS = [
    ("site_code", "Site code", True),
    ("ticket_id", "Incident / TT number", True),
    ("submitted_time", "Submitted time", True),
    ("status", "Current status", True),
    ("owner", "ISP / Owner", False),
    ("reason", "Remarks", False),
    ("resolved_time", "Resolved time", False),
    ("state", "State", False),
    ("city", "City", False),
    ("down_time_min", "Down time (minutes)", False),
]

ALIASES = {
    "site_code": ["request title", "site code", "sitecode", "site id", "unique id", "hughes sitecode", "hughessitecode"],
    "ticket_id": ["incident id", "ticket id", "tt number", "tt no", "incident no", "incident"],
    "submitted_time": ["submitted time", "open date", "created time", "log time", "open time"],
    "status": ["currentstatus", "current status", "status"],
    "owner": ["owner", "isp", "partner", "isp name"],
    "reason": ["last enclosure comment(active)", "last enclosure comment", "remarks", "remark", "rfo"],
    "resolved_time": ["resolved time-active", "resolved time", "close time(active)", "close time"],
    "state": ["state"],
    "city": ["city", "location"],
    "down_time_min": ["down time", "downtime", "down time (minutes)", "outage minutes"],
}


def guess_columns(headers) -> dict:
    """Match this file's headers to the fields reports already understand."""
    lower = {}
    for h in headers or []:
        key = str(h or "").strip().lower()
        if key and key not in lower:
            lower[key] = str(h).strip()
    out = {}
    for field, names in ALIASES.items():
        for name in names:
            if name in lower:
                out[field] = lower[name]
                break
    return out


BUILTIN = {"xtranet", "shell", "backhaul", "link", "dgll"}


def is_builtin(name: str) -> bool:
    return str(name or "").strip().lower() in BUILTIN


def _load() -> dict:
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    _PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def all_projects() -> dict:
    return _load()


def get_project(name: str) -> dict | None:
    if is_builtin(name):
        return None
    key = str(name or "").strip()
    item = _load().get(key)
    if isinstance(item, dict) and item.get("sheet_url"):
        return item
    try:
        import streamlit as st
        cached = (st.session_state.get("_custom_cfg") or {}).get(key)
        if isinstance(cached, dict) and cached.get("sheet_url"):
            return cached
    except Exception:
        pass
    return item if isinstance(item, dict) else None


def save_project(name: str, sheet_url: str, columns: dict, gid: int | None = None, extra: list | None = None) -> None:
    name = str(name or "").strip()
    if not name or is_builtin(name) or name.startswith("_"):
        return
    data = _load()
    url = str(sheet_url or "").strip()
    if gid is None:
        gid = parse_gid(url)
    clean = {}
    for key, _label, _req in FIELDS:
        val = str((columns or {}).get(key) or "").strip()
        if val and val != "—":
            clean[key] = val
    extras = []
    for item in extra or []:
        if not isinstance(item, dict):
            continue
        lab = str(item.get("label") or "").strip()
        col = str(item.get("column") or "").strip()
        if lab and col and col != "—":
            extras.append({"label": lab, "column": col})
    prev = data.get(name) if isinstance(data.get(name), dict) else {}
    data[name] = {
        "sheet_url": url,
        "gid": int(gid or 0),
        "columns": clean,
        "extra": extras if extra is not None else list(prev.get("extra") or []),
        "pages": dict(prev.get("pages") or {}),
    }
    _save(data)
    try:
        import streamlit as st
        bag = dict(st.session_state.get("_custom_cfg") or {})
        bag[name] = data[name]
        st.session_state._custom_cfg = bag
    except Exception:
        pass


def set_page_sheet(name: str, page_key: str, url: str) -> None:
    """Remember one extra tab (SIM, circuit, LC) for this project."""
    name = str(name or "").strip()
    page_key = str(page_key or "").strip()
    if not name or not page_key or is_builtin(name) or name.startswith("_"):
        return
    data = _load()
    item = data.get(name) if isinstance(data.get(name), dict) else {}
    pages = dict(item.get("pages") or {})
    pages[page_key] = str(url or "").strip()
    item["pages"] = pages
    data[name] = item
    _save(data)
    try:
        import streamlit as st
        bag = dict(st.session_state.get("_custom_cfg") or {})
        bag[name] = item
        st.session_state._custom_cfg = bag
    except Exception:
        pass


def delete_project(name: str) -> bool:
    name = str(name or "").strip()
    if not name or is_builtin(name) or name.startswith("_"):
        return False
    data = _load()
    if name not in data:
        return False
    data.pop(name, None)
    _save(data)
    return True


def admin_pin_set() -> bool:
    return bool(_load().get("_admin"))


def set_admin_pin(pin: str) -> None:
    pin = str(pin or "").strip()
    if len(pin) < 4:
        raise ValueError("PIN must be at least 4 characters.")
    data = _load()
    data["_admin"] = hashlib.sha256(pin.encode()).hexdigest()
    _save(data)


def check_admin_pin(pin: str) -> bool:
    saved = _load().get("_admin")
    if not saved:
        return False
    return hashlib.sha256(str(pin or "").strip().encode()).hexdigest() == saved


def parse_gid(url: str) -> int:
    m = re.search(r"[?&#]gid=(\d+)", str(url or ""))
    return int(m.group(1)) if m else 0


def apply_user_columns(df, columns: dict | None, extra: list | None = None):
    """Rename this file's headers to the standard names. No-op if mapping is empty."""
    if df is None or getattr(df, "empty", True):
        return df
    if not columns and not extra:
        return df
    work = df.copy()
    work.columns = [str(c).strip() for c in work.columns]
    lower = {}
    for c in work.columns:
        lower.setdefault(c.lower(), c)
    rename = {}
    for key, user_name in (columns or {}).items():
        dest = CANON.get(key)
        src = lower.get(str(user_name or "").strip().lower())
        if not dest or not src or src == dest or src in rename:
            continue
        rename[src] = dest
    for item in extra or []:
        if not isinstance(item, dict):
            continue
        lab = str(item.get("label") or "").strip()
        col = str(item.get("column") or "").strip()
        src = lower.get(col.lower())
        if not lab or not src or src in rename or src == lab:
            continue
        rename[src] = lab
    if not rename:
        return work
    return work.rename(columns=rename)
