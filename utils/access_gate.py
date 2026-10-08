"""Public site lock. A user ID opens only that person's projects."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path

import streamlit as st

PRODUCT = "Opsora"
TAGLINE = "Reports for any project — paste your sheet, keep your data private."

_PATH = Path(__file__).with_name("access_codes.json")
_SESSION_DAYS = 30


def _hash(pin: str) -> str:
    return hashlib.sha256(str(pin or "").strip().encode()).hexdigest()


def _load() -> dict:
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("users", [])
                data.setdefault("sessions", {})
                return data
    except Exception:
        pass
    return {"users": [], "sessions": {}}


def _save(data: dict) -> None:
    _PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def list_users() -> list[dict]:
    out = []
    for row in _load().get("users") or []:
        if not isinstance(row, dict):
            continue
        out.append({
            "name": str(row.get("name") or "").strip(),
            "projects": [str(p).strip() for p in (row.get("projects") or []) if str(p).strip()],
        })
    return [r for r in out if r["name"]]


def save_user(name: str, pin: str, projects: list[str]) -> None:
    name = str(name or "").strip()
    pin = str(pin or "").strip()
    projects = [str(p).strip() for p in projects if str(p).strip()]
    if not name or len(pin) < 4 or not projects:
        raise ValueError("Name, a passcode of at least 4 characters, and one project are required.")
    data = _load()
    users = [u for u in (data.get("users") or []) if str(u.get("name") or "").strip().lower() != name.lower()]
    users.append({"name": name, "hash": _hash(pin), "projects": projects})
    data["users"] = users
    _save(data)


def delete_user(name: str) -> None:
    data = _load()
    data["users"] = [
        u for u in (data.get("users") or [])
        if str(u.get("name") or "").strip().lower() != str(name or "").strip().lower()
    ]
    _save(data)


def _admin_pin_ok(pin: str) -> bool:
    try:
        from utils.custom_projects import check_admin_pin, admin_pin_set
        if admin_pin_set() and check_admin_pin(pin):
            return True
    except Exception:
        pass
    try:
        secret = str(st.secrets.get("access", {}).get("admin") or "").strip()
        if secret and secret == str(pin or "").strip():
            return True
    except Exception:
        pass
    return False


def admin_configured() -> bool:
    try:
        from utils.custom_projects import admin_pin_set
        if admin_pin_set():
            return True
    except Exception:
        pass
    try:
        if str(st.secrets.get("access", {}).get("admin") or "").strip():
            return True
    except Exception:
        pass
    return False


def register_user(user_id: str, password: str) -> None:
    user_id = str(user_id or "").strip()
    password = str(password or "").strip()
    if len(user_id) < 3 or len(password) < 4:
        raise ValueError("User ID at least 3 characters and password at least 4.")
    if user_id.lower() in ("admin", "xtranet", "shell", "backhaul", "link", "dgll"):
        raise ValueError("This user ID is reserved.")
    data = _load()
    for row in data.get("users") or []:
        if str(row.get("name") or "").strip().lower() == user_id.lower():
            raise ValueError("This user ID already exists. Sign in instead.")
    data.setdefault("users", []).append({"name": user_id, "hash": _hash(password), "projects": []})
    _save(data)


def add_user_project(user_id: str, project_name: str) -> str:
    """Empty project for this user only. Does not touch Xtranet / Shell data."""
    from utils.custom_projects import is_builtin
    user_id = str(user_id or "").strip()
    project_name = str(project_name or "").strip()
    if not user_id or not project_name:
        raise ValueError("Project name is required.")
    if is_builtin(project_name) or project_name.lower() in ("xtranet", "shell", "backhaul", "link", "dgll"):
        raise ValueError("That project name is already in use. Pick another name.")
    key = project_name if project_name.lower().startswith(user_id.lower() + " — ") else f"{user_id} — {project_name}"
    data = _load()
    found = False
    for row in data.get("users") or []:
        if str(row.get("name") or "").strip().lower() != user_id.lower():
            continue
        found = True
        projects = [str(p).strip() for p in (row.get("projects") or []) if str(p).strip()]
        if key not in projects:
            projects.append(key)
        row["projects"] = projects
    if not found:
        raise ValueError("User not found.")
    _save(data)
    return key


def match_login(user_id: str, password: str) -> dict | None:
    user_id = str(user_id or "").strip()
    password = str(password or "").strip()
    if not user_id or not password:
        return None
    if user_id.lower() == "admin" and _admin_pin_ok(password):
        return {"name": "Admin", "projects": None, "admin": True}
    digest = _hash(password)
    for row in _load().get("users") or []:
        if str(row.get("name") or "").strip().lower() != user_id.lower():
            continue
        if str(row.get("hash") or "") != digest:
            return None
        projects = [str(p).strip() for p in (row.get("projects") or []) if str(p).strip()]
        return {"name": str(row.get("name") or user_id), "projects": projects, "admin": False}
    return None


def _prune_sessions(data: dict) -> None:
    now = time.time()
    sessions = data.get("sessions") or {}
    data["sessions"] = {
        k: v for k, v in sessions.items()
        if isinstance(v, dict) and float(v.get("exp") or 0) > now
    }


def start_session(hit: dict) -> str:
    data = _load()
    _prune_sessions(data)
    token = secrets.token_urlsafe(24)
    data.setdefault("sessions", {})[token] = {
        "name": hit.get("name") or "User",
        "admin": bool(hit.get("admin")),
        "projects": list(hit.get("projects") or []),
        "exp": time.time() + _SESSION_DAYS * 86400,
        "guide_seen": bool(hit.get("guide_seen")),
    }
    _save(data)
    return token


def read_session(token: str) -> dict | None:
    token = str(token or "").strip()
    if not token:
        return None
    data = _load()
    row = (data.get("sessions") or {}).get(token)
    if not isinstance(row, dict):
        return None
    if float(row.get("exp") or 0) < time.time():
        data["sessions"].pop(token, None)
        _save(data)
        return None
    return row


def end_session(token: str) -> None:
    token = str(token or "").strip()
    if not token:
        return
    data = _load()
    if token in (data.get("sessions") or {}):
        data["sessions"].pop(token, None)
        _save(data)


def _user_saw_guide(name, admin) -> bool:
    data = _load()
    if admin:
        return bool(data.get("guide_admin"))
    name = str(name or "").strip().lower()
    for row in data.get("users") or []:
        if str(row.get("name") or "").strip().lower() == name:
            return bool(row.get("guide_seen"))
    return False


def guide_seen() -> bool:
    if st.session_state.get("guide_seen"):
        return True
    if st.session_state.get("access_admin"):
        return bool(_load().get("guide_admin"))
    name = str(st.session_state.get("access_name") or "").strip().lower()
    for row in _load().get("users") or []:
        if str(row.get("name") or "").strip().lower() == name:
            return bool(row.get("guide_seen"))
    return False


def mark_guide_seen() -> None:
    st.session_state.guide_seen = True
    st.session_state.show_guide = False
    data = _load()
    if st.session_state.get("access_admin"):
        data["guide_admin"] = True
    else:
        name = str(st.session_state.get("access_name") or "").strip().lower()
        for row in data.get("users") or []:
            if str(row.get("name") or "").strip().lower() == name:
                row["guide_seen"] = True
    token = str(st.session_state.get("access_token") or "")
    if token and isinstance((data.get("sessions") or {}).get(token), dict):
        data["sessions"][token]["guide_seen"] = True
    _save(data)


def _apply_login(hit: dict, token: str) -> None:
    st.session_state.access_ok = True
    st.session_state.access_admin = bool(hit.get("admin"))
    st.session_state.access_name = hit.get("name")
    st.session_state.access_projects = hit.get("projects") or []
    st.session_state.access_token = token
    st.session_state.guide_seen = bool(hit.get("guide_seen"))
    try:
        st.query_params["sid"] = token
    except Exception:
        pass


def _restore_session() -> bool:
    if st.session_state.get("access_ok"):
        return True
    try:
        token = str(st.query_params.get("sid") or "")
    except Exception:
        token = ""
    row = read_session(token)
    if not row:
        return False
    _apply_login(row, token)
    return True


def is_admin() -> bool:
    return bool(st.session_state.get("access_ok") and st.session_state.get("access_admin"))


def apply_access_scope() -> None:
    """Drop every project this passcode is not allowed to open."""
    if not st.session_state.get("access_ok"):
        return
    if st.session_state.get("access_admin"):
        return
    allowed = [p for p in (st.session_state.get("access_projects") or []) if p]
    if not allowed:
        st.session_state.projects = []
        st.session_state.active_project = ""
        st.session_state.closed_df = None
        st.session_state.open_df = None
        st.session_state.raw_tickets_df = None
        return
    st.session_state.projects = list(allowed)
    if st.session_state.get("active_project") not in allowed:
        st.session_state.active_project = allowed[0]
        st.session_state._view_project = None
        st.session_state.closed_df = None
        st.session_state.open_df = None
        st.session_state.raw_tickets_df = None


def logout() -> None:
    end_session(str(st.session_state.get("access_token") or ""))
    for key in (
        "access_ok", "access_admin", "access_name", "access_projects", "access_token",
        "closed_df", "open_df", "raw_tickets_df", "_view_project", "project_store",
    ):
        st.session_state.pop(key, None)
    try:
        if "sid" in st.query_params:
            del st.query_params["sid"]
    except Exception:
        pass
    st.rerun()


def ensure_logged_in() -> bool:
    if not st.session_state.get("access_ok"):
        _restore_session()
    if st.session_state.get("access_ok"):
        apply_access_scope()
        with st.sidebar:
            who = st.session_state.get("access_name") or "User"
            st.caption(f"Signed in: **{who}**")
            if st.button("Guide", key="open_guide_btn"):
                st.session_state.show_guide = True
                st.rerun()
            if st.button("Log out", key="access_logout"):
                logout()
        if st.session_state.get("show_guide") or not guide_seen():
            render_guide()
        return True

    st.markdown(
        """
        <div style="max-width:460px;margin:8vh auto 0;padding:28px 26px;border-radius:16px;
                    background:#0f172a;color:#f8fafc;border:1px solid #334155;">
          <div style="font-size:1.4rem;font-weight:800;">Opsora</div>
          <div style="opacity:.8;margin-top:6px;">Reports for any project. Sign in once — a refresh stays signed in.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    box = st.columns([1, 1.2, 1])[1]
    with box:
        if not admin_configured() and not list_users():
            st.info("First time only: set the admin passcode. After that, add a passcode for each project.")
            pin1 = st.text_input("Admin passcode", type="password", key="boot_admin_1")
            pin2 = st.text_input("Confirm passcode", type="password", key="boot_admin_2")
            if st.button("Save admin passcode", type="primary"):
                if pin1 != pin2 or len(str(pin1 or "").strip()) < 4:
                    st.error("Passcodes must match and be at least 4 characters.")
                else:
                    from utils.custom_projects import set_admin_pin
                    set_admin_pin(pin1.strip())
                    hit = {"name": "Admin", "admin": True, "projects": None, "guide_seen": False}
                    _apply_login(hit, start_session(hit))
                    st.rerun()
            return False

        user_id = st.text_input("User ID", key="access_user")
        password = st.text_input("Password", type="password", key="access_pin")
        c1, c2 = st.columns(2)
        if c1.button("Sign in", type="primary", use_container_width=True):
            hit = match_login(user_id, password)
            if not hit:
                st.error("Wrong user ID or password.")
            else:
                hit["guide_seen"] = _user_saw_guide(hit.get("name"), hit.get("admin"))
                _apply_login(hit, start_session(hit))
                st.session_state.closed_df = None
                st.session_state.open_df = None
                st.session_state.raw_tickets_df = None
                st.session_state._view_project = None
                st.session_state.project_store = {}
                st.rerun()
        if c2.button("Create account", use_container_width=True):
            try:
                register_user(user_id, password)
                hit = {"name": user_id.strip(), "admin": False, "projects": [], "guide_seen": False}
                _apply_login(hit, start_session(hit))
                st.session_state.closed_df = None
                st.session_state.open_df = None
                st.session_state.raw_tickets_df = None
                st.session_state._view_project = None
                st.session_state.project_store = {}
                st.rerun()
            except Exception as e:
                st.error(str(e))
        st.caption("Admin sign in: user ID **admin** and the admin password. New users do not see that Excel.")
    return False


def render_passcode_admin() -> None:
    if not is_admin():
        return
    with st.expander("Passcodes — one code, one project", expanded=False):
        st.caption("Anyone can open the site. A passcode shows only the projects you tick. Admin passcode sees everything.")
        from utils.data_source import init_data_source
        init_data_source()
        # Admin must see every project while assigning codes, not a filtered list.
        names = list(st.session_state.projects)
        who = st.text_input("Person / team name", key="acc_name")
        code = st.text_input("Their passcode", type="password", key="acc_pin")
        picks = st.multiselect("Projects they can open", names, key="acc_projects")
        if st.button("Save passcode", key="acc_save"):
            try:
                save_user(who, code, picks)
                st.success(f"Passcode saved for {who.strip()}. They cannot open any other project.")
            except Exception as e:
                st.error(str(e))
        rows = list_users()
        if rows:
            st.dataframe(
                [{"Name": r["name"], "Projects": ", ".join(r["projects"])} for r in rows],
                hide_index=True,
                use_container_width=True,
            )
            victim = st.selectbox("Remove passcode", [r["name"] for r in rows], key="acc_del_name")
            if st.button("Delete this passcode", key="acc_del_btn"):
                delete_user(victim)
                st.rerun()


def render_guide() -> None:
    """First login: what the app is, with a sample row. Not loaded into reports."""
    import pandas as pd

    show = st.session_state.get("show_guide") or not guide_seen()
    if not show:
        return
    st.markdown("### Welcome to Opsora")
    st.caption("This is a short guide. Your reports are unchanged. Close it when you know the pages.")
    st.markdown(
        """
**What this is**  
Opsora turns one Google Sheet into ticket, SLA and site reports. Each user sees only their own project.

**Start**  
1. On Home, write a **project name**.  
2. Paste the Google Sheet link, including `gid=`.  
3. Click **Load this sheet**.  
4. Open Dashboard, Site Search, Closed Analysis or Partner Report. They all use that sheet.

**Pages**  
- **Tickets** — site search, dashboard, open calls, closed and repeat sites.  
- **ISP & Partner** — compare partners, vendor performance, vendor change.  
- **SLA & Reports** — monthly SLA, penalty, holiday downtime, conclusion slides.  
- **Daily Ops** — VPN update and the pending-call mail.  
- **Tools** — Excel to PowerPoint, and upload a file if you are not using a Google link.

**Sample row** (example only — this is not your data)
"""
    )
    sample = pd.DataFrame([
        {
            "Incident ID": "IN071026-0003354",
            "Site code": "XTNPIT355",
            "Status": "Assign to FE",
            "Owner": "HCIN",
            "State": "Uttarakhand",
            "Submitted": "2026-10-07 16:31",
        },
        {
            "Incident ID": "IN071026-0002407",
            "Site code": "XTNUDN388",
            "Status": "Resolved",
            "Owner": "ONEOTT",
            "State": "Punjab",
            "Submitted": "2026-10-07 12:59",
        },
    ])
    st.dataframe(sample, hide_index=True, use_container_width=True)
    st.caption("Your sheet should have the same kind of columns: Incident ID, site code, status, owner, time, state. If the names differ, map them once under the link box.")
    if st.button("Got it — hide this guide", type="primary", key="guide_done"):
        mark_guide_seen()
        st.rerun()
    st.divider()
