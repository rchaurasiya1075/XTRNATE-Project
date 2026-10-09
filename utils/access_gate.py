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
_SESSION_DAYS = 14
_IDLE_SEC = 3 * 3600
_COOKIE = "opsora_sid"


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


def match_pin(pin: str) -> dict | None:
    """4 digits only. Site PIN opens everything. A saved user PIN opens that user."""
    raw = "".join(ch for ch in str(pin or "") if ch.isdigit())
    if len(raw) != 4:
        return None
    if _admin_pin_ok(raw):
        return {"name": "Admin", "projects": None, "admin": True}
    digest = _hash(raw)
    for row in _load().get("users") or []:
        if str(row.get("hash") or "") != digest:
            continue
        projects = [str(p).strip() for p in (row.get("projects") or []) if str(p).strip()]
        return {"name": str(row.get("name") or "User"), "projects": projects, "admin": False}
    return None


def _open_app(hit: dict) -> None:
    hit["guide_seen"] = True
    _apply_login(hit, start_session(hit))
    st.session_state.closed_df = None
    st.session_state.open_df = None
    st.session_state.raw_tickets_df = None
    st.session_state._view_project = None
    st.session_state.project_store = {}
    st.rerun()


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
        "last_seen": time.time(),
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
    seen = float(row.get("last_seen") or 0)
    if seen and time.time() - seen > _IDLE_SEC:
        data["sessions"].pop(token, None)
        _save(data)
        return None
    return row


def touch_session(token: str) -> None:
    token = str(token or "").strip()
    if not token:
        return
    data = _load()
    row = (data.get("sessions") or {}).get(token)
    if not isinstance(row, dict):
        return
    row["last_seen"] = time.time()
    _save(data)


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


def _cookie_manager():
    try:
        import extra_streamlit_components as stx
    except Exception:
        return None
    cm = st.session_state.get("_opsora_cm")
    if cm is None:
        cm = stx.CookieManager(key="opsora_cookie_mgr")
        st.session_state._opsora_cm = cm
    return cm


def _read_browser_token():
    """(token, ready). ready is False only while the browser cookie has not come back yet."""
    cm = _cookie_manager()
    if cm is None:
        try:
            return str(st.query_params.get("sid") or ""), True
        except Exception:
            return "", True
    try:
        bag = cm.get_all()
    except Exception:
        bag = None
    if bag is None:
        try:
            q = str(st.query_params.get("sid") or "")
        except Exception:
            q = ""
        return (q, True) if q else ("", False)
    token = str((bag or {}).get(_COOKIE) or "")
    if not token:
        try:
            token = str(st.query_params.get("sid") or "")
        except Exception:
            pass
    return token, True


def _save_browser_token(token: str) -> None:
    if not token:
        return
    cm = _cookie_manager()
    if cm is None:
        return
    try:
        from datetime import datetime, timedelta
        cm.set(_COOKIE, token, expires_at=datetime.now() + timedelta(hours=12), key="opsora_set_sid")
    except Exception:
        pass


def _clear_browser_token() -> None:
    cm = _cookie_manager()
    if cm is None:
        return
    try:
        cm.delete(_COOKIE, key="opsora_del_sid")
    except Exception:
        pass


def _apply_login(hit: dict, token: str, remember: bool = True) -> None:
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
    _save_browser_token(token) if remember else None


def _restore_session(token: str | None = None):
    if st.session_state.get("access_ok"):
        return True
    if not token:
        token, ready = _read_browser_token()
        if not ready:
            return None
    row = read_session(token)
    if not row:
        if token:
            _clear_browser_token()
        return False
    touch_session(token)
    row["guide_seen"] = bool(row.get("guide_seen"))
    _apply_login(row, token, remember=False)
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
    _clear_browser_token()
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
        try:
            token, _ready = _read_browser_token()
        except Exception:
            token = ""
        if token:
            try:
                _restore_session(token)
            except Exception:
                pass
    else:
        try:
            touch_session(str(st.session_state.get("access_token") or ""))
        except Exception:
            pass
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
        <style>
        [data-testid="stSidebar"] { display: none; }
        .opsora-login {
          max-width: 380px; margin: 12vh auto 0; padding: 28px 26px 8px;
          border-radius: 18px; background: #0f172a; color: #f8fafc;
          border: 1px solid #334155;
        }
        .opsora-login h1 { margin: 0; font-size: 1.7rem; font-weight: 800; color: #f8fafc; }
        .opsora-login p { margin: 6px 0 0; color: #94a3b8; font-size: 0.92rem; }
        </style>
        <div class="opsora-login">
          <h1>Opsora</h1>
          <p>Enter the 4 digit PIN to open.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    box = st.columns([1, 0.9, 1])[1]
    with box:
        if not admin_configured() and not list_users():
            with st.form("set_pin"):
                a = st.text_input("Set 4 digit PIN", max_chars=4, type="password")
                b = st.text_input("Type it again", max_chars=4, type="password")
                save = st.form_submit_button("Save and open", type="primary", use_container_width=True)
            if save:
                pa = "".join(ch for ch in str(a or "") if ch.isdigit())
                pb = "".join(ch for ch in str(b or "") if ch.isdigit())
                if len(pa) != 4 or pa != pb:
                    st.error("PIN must be 4 numbers, and both boxes must match.")
                else:
                    from utils.custom_projects import set_admin_pin
                    set_admin_pin(pa)
                    _open_app({"name": "Admin", "admin": True, "projects": None})
            return False

        with st.form("pin_login"):
            pin = st.text_input("4 digit PIN", max_chars=4, type="password", placeholder="••••")
            go = st.form_submit_button("Open", type="primary", use_container_width=True)
        if go:
            hit = match_pin(pin)
            if not hit:
                st.error("Wrong PIN. Use 4 numbers only.")
            else:
                _open_app(hit)
        st.caption("Numbers only. Refresh will stay open.")
    return False


def render_passcode_admin() -> None:
    if not is_admin():
        return
    with st.expander("Passcodes — one code, one project", expanded=False):
        st.caption("A 4 digit number opens only the projects you tick. Your own PIN opens everything.")
        from utils.data_source import init_data_source
        init_data_source()
        # Admin must see every project while assigning codes, not a filtered list.
        names = list(st.session_state.projects)
        who = st.text_input("Person / team name", key="acc_name")
        code = st.text_input("Their 4 digit PIN", max_chars=4, type="password", key="acc_pin")
        picks = st.multiselect("Projects they can open", names, key="acc_projects")
        if st.button("Save passcode", key="acc_save"):
            pin = "".join(ch for ch in str(code or "") if ch.isdigit())
            if len(pin) != 4:
                st.error("PIN must be 4 numbers.")
            else:
                try:
                    save_user(who, pin, picks)
                    st.success(f"PIN saved for {who.strip()}.")
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
