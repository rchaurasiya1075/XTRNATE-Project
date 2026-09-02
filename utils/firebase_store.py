"""Firestore helper. Uses Streamlit secrets google_service_account."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ID = "xtranet-d7dca"
_app = None


def _now():
    return datetime.now(IST).strftime("%d-%b-%Y %I:%M:%S %p IST")


def firebase_ready():
    try:
        import streamlit as st
        return "google_service_account" in st.secrets
    except Exception:
        return False


def _fix_private_key(raw):
    key = str(raw or "").strip()
    if key.startswith("\"") and key.endswith("\""):
        key = key[1:-1]
    key = key.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    key = key.replace("BEGIN_PRIVATE_KEY", "BEGIN PRIVATE KEY")
    key = key.replace("END_PRIVATE_KEY", "END PRIVATE KEY")
    key = key.replace("BEGIN_RSA_PRIVATE_KEY", "BEGIN RSA PRIVATE KEY")
    if "BEGIN PRIVATE KEY" not in key and key.startswith("{"):
        try:
            parsed = json.loads(key)
            if isinstance(parsed, dict) and parsed.get("private_key"):
                return _fix_private_key(parsed["private_key"])
        except Exception:
            pass
    if "BEGIN PRIVATE KEY" in key and "-----BEGIN PRIVATE KEY-----" not in key:
        key = key.replace("BEGIN PRIVATE KEY", "-----BEGIN PRIVATE KEY-----")
        key = key.replace("END PRIVATE KEY", "-----END PRIVATE KEY-----")
    key = re.sub(r"-+BEGIN PRIVATE KEY-+", "-----BEGIN PRIVATE KEY-----", key)
    key = re.sub(r"-+END PRIVATE KEY-+", "-----END PRIVATE KEY-----", key)
    if not key.endswith("\n"):
        key += "\n"
    return key


def _sa_info():
    import streamlit as st
    info = dict(st.secrets["google_service_account"])
    # Sometimes whole JSON dumped in one field
    if "private_key" not in info and len(info) == 1:
        only = next(iter(info.values()))
        if isinstance(only, str) and only.strip().startswith("{"):
            info = json.loads(only)
    if "private_key" in info:
        info["private_key"] = _fix_private_key(info["private_key"])
    info["type"] = info.get("type") or "service_account"
    return info


def get_db():
    global _app
    import streamlit as st
    import firebase_admin
    from firebase_admin import credentials, firestore

    if "google_service_account" not in st.secrets:
        raise RuntimeError(
            "Firebase service account missing. Streamlit Secrets mein [google_service_account] paste karo."
        )
    if not firebase_admin._apps:
        info = _sa_info()
        cred = credentials.Certificate(info)
        pid = (
            st.secrets.get("firebase", {}).get("projectId")
            or info.get("project_id")
            or PROJECT_ID
        )
        _app = firebase_admin.initialize_app(cred, {"projectId": pid})
    return firestore.client()


def upsert(collection, doc_id, data):
    db = get_db()
    payload = dict(data)
    payload["updated_at"] = _now()
    if "created_at" not in payload:
        existing = db.collection(collection).document(str(doc_id)).get()
        if existing.exists:
            prev = existing.to_dict() or {}
            payload["created_at"] = prev.get("created_at", _now())
        else:
            payload["created_at"] = _now()
    db.collection(collection).document(str(doc_id)).set(payload, merge=True)
    return payload


def get_one(collection, doc_id):
    db = get_db()
    snap = db.collection(collection).document(str(doc_id)).get()
    return snap.to_dict() if snap.exists else None


def list_all(collection, limit=2000):
    db = get_db()
    rows = []
    for snap in db.collection(collection).limit(limit).stream():
        row = snap.to_dict() or {}
        row["_id"] = snap.id
        rows.append(row)
    return rows


def delete_one(collection, doc_id):
    get_db().collection(collection).document(str(doc_id)).delete()
