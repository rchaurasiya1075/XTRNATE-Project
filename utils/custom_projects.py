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
    item = _load().get(str(name or "").strip())
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
    }
    _save(data)


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
