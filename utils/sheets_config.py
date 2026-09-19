"""Single place for every Google Sheet workbook ID and tab GID.

Change utils/sheets.json (or the Sheet Links page) — all pages read from here.
"""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).with_name("sheets.json")

_DEFAULT = {
    "workbooks": {
        "xtranet": {
            "id": "1ELusYn2el4_rvHJYFD1_c92FN4SVQ1Cgwp-BwFADi8I",
            "label": "Xtranet main (tickets, SIM, LC, circuit, site master)",
        },
        "ops": {
            "id": "1bkXg9iqJMY4jw_fAsMa6XQDHiA3qOln7d8f_0RqHc6I",
            "label": "Ops (daily open tickets, pending mail, last mile master)",
        },
    },
    "tabs": {
        "tickets_xtranet": {"book": "xtranet", "gid": 1980854633, "label": "Xtranet ticket history"},
        "tickets_shell": {"book": "xtranet", "gid": 1861519338, "label": "Shell ticket history"},
        "tickets_other": {"book": "xtranet", "gid": 1643784953, "label": "Other project tickets"},
        "daily_open": {"book": "ops", "gid": 407315218, "label": "Daily open tickets"},
        "pending_mail": {"book": "ops", "gid": 762980214, "label": "OPEN CALLS / pending mail"},
        "sim_inventory": {"book": "xtranet", "gid": 1240520075, "label": "SIM inventory"},
        "sim_usage": {"book": "xtranet", "gid": 710549453, "label": "SIM month-wise usage"},
        "circuit": {"book": "xtranet", "gid": 886642043, "label": "Circuit ID"},
        "lc_master": {"book": "xtranet", "gid": 401145054, "label": "LC master"},
        "site_primary": {"book": "xtranet", "gid": 2129640700, "label": "Site master primary"},
        "site_fallback": {"book": "xtranet", "gid": 658119379, "label": "Site master fallback"},
        "last_mile_master": {"book": "ops", "gid": 1181450647, "label": "Last mile master (ops)"},
        "site_updated": {"book": "xtranet", "gid": 0, "label": "Updated_Master (bulk site updates)"},
    },
}


def _load() -> dict:
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("workbooks") and data.get("tabs"):
                return data
    except Exception:
        pass
    return json.loads(json.dumps(_DEFAULT))


def save_config(data: dict) -> None:
    _PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def all_config() -> dict:
    return _load()


def workbook_id(name: str = "xtranet") -> str:
    books = _load().get("workbooks") or {}
    item = books.get(name) or {}
    if isinstance(item, dict):
        return str(item.get("id") or "").strip()
    return str(item or "").strip()


def xtranet_id() -> str:
    return workbook_id("xtranet")


def ops_id() -> str:
    return workbook_id("ops")


def edit_url(sheet_id: str, gid=None) -> str:
    sid = str(sheet_id or "").strip()
    if gid is None or gid == "":
        return f"https://docs.google.com/spreadsheets/d/{sid}/edit?usp=sharing"
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit?gid={gid}#gid={gid}"


def xtranet_url() -> str:
    return edit_url(xtranet_id())


def ops_url() -> str:
    return edit_url(ops_id())


def gid(tab: str):
    tabs = _load().get("tabs") or {}
    item = tabs.get(tab) or {}
    return item.get("gid", 0)


def tab_book(tab: str) -> str:
    tabs = _load().get("tabs") or {}
    item = tabs.get(tab) or {}
    return str(item.get("book") or "xtranet")


def tab_id(tab: str) -> str:
    return workbook_id(tab_book(tab))


def tab_url(tab: str) -> str:
    return edit_url(tab_id(tab), gid(tab))


def csv_url(tab: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{tab_id(tab)}/export?format=csv&gid={gid(tab)}"
