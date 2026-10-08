"""Public site lock. A passcode opens only the projects assigned to it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

_PATH = Path(__file__).with_name("access_codes.json")


def _hash(pin: str) -> str:
    return hashlib.sha256(str(pin or "").strip().encode()).hexdigest()


def _load() -> dict:
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("users", [])
                return data
    except Exception:
        pass
    return {"users": []}


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
    for key in (
        "access_ok", "access_admin", "access_name", "access_projects",
        "closed_df", "open_df", "raw_tickets_df", "_view_project", "project_store",
    ):
        st.session_state.pop(key, None)
    st.rerun()


def ensure_logged_in() -> bool:
    if st.session_state.get("access_ok"):
        apply_access_scope()
        with st.sidebar:
            who = st.session_state.get("access_name") or "User"
            st.caption(f"Signed in: **{who}**")
            if st.button("Log out", key="access_logout"):
                logout()
        return True

    st.markdown(
        """
        <div style="max-width:460px;margin:8vh auto 0;padding:28px 26px;border-radius:16px;
                    background:#0f172a;color:#f8fafc;border:1px solid #334155;">
          <div style="font-size:1.4rem;font-weight:800;">Xtranet NOC</div>
          <div style="opacity:.8;margin-top:6px;">Sign in with your user ID. A new account starts empty — add your own Excel link.</div>
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
                    st.session_state.access_ok = True
                    st.session_state.access_admin = True
                    st.session_state.access_name = "Admin"
                    st.session_state.access_projects = None
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
                st.session_state.access_ok = True
                st.session_state.access_admin = bool(hit.get("admin"))
                st.session_state.access_name = hit.get("name")
                st.session_state.access_projects = hit.get("projects") or []
                st.session_state.closed_df = None
                st.session_state.open_df = None
                st.session_state.raw_tickets_df = None
                st.session_state._view_project = None
                st.session_state.project_store = {}
                st.rerun()
        if c2.button("Create account", use_container_width=True):
            try:
                register_user(user_id, password)
                st.session_state.access_ok = True
                st.session_state.access_admin = False
                st.session_state.access_name = user_id.strip()
                st.session_state.access_projects = []
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
