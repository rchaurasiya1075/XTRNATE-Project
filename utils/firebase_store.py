"""Firestore helper. Prefers one-shot FIREBASE_SA_JSON secret."""
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
        if "FIREBASE_SA_JSON" in st.secrets:
            return True
        if "firebase_sa_json" in st.secrets:
            return True
        return "google_service_account" in st.secrets
    except Exception:
        return False


def _fix_private_key(raw):
    key = str(raw or "").strip().strip('"').strip("'")
    key = key.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    key = key.replace("BEGIN_PRIVATE_KEY", "BEGIN PRIVATE KEY")
    key = key.replace("END_PRIVATE_KEY", "END PRIVATE KEY")
    key = re.sub(r"-+BEGIN PRIVATE KEY-+", "-----BEGIN PRIVATE KEY-----", key)
    key = re.sub(r"-+END PRIVATE KEY-+", "-----END PRIVATE KEY-----", key)
    if not key.endswith("\n"):
        key += "\n"
    return key


def _load_sa_info():
    import streamlit as st

    raw = None
    for name in ("FIREBASE_SA_JSON", "firebase_sa_json"):
        if name in st.secrets:
            raw = st.secrets[name]
            break
    if raw is not None:
        text = str(raw).strip()
        if text.startswith("\"") and text.endswith("\""):
            text = text[1:-1]
        info = json.loads(text)
    else:
        info = dict(st.secrets["google_service_account"])
        if "private_key" not in info:
            raise ValueError(
                "Secrets galat hain. Sabse aasan: FIREBASE_SA_JSON mein poori JSON file paste karo."
            )
    if not isinstance(info, dict):
        raise ValueError("Service account JSON object nahi bana.")
    if "private_key" not in info:
        raise ValueError("JSON mein private_key field nahi hai.")
    info["private_key"] = _fix_private_key(info["private_key"])
    info["type"] = info.get("type") or "service_account"
    if "BEGIN PRIVATE KEY" not in info["private_key"]:
        raise ValueError(
            "private_key PEM nahi hai. JSON file ka poora content FIREBASE_SA_JSON mein paste karo."
        )
    return info


def get_db():
    global _app
    import streamlit as st
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_ready():
        raise RuntimeError("Firebase secrets missing.")
    if not firebase_admin._apps:
        info = _load_sa_info()
        cred = credentials.Certificate(info)
        pid = info.get("project_id") or PROJECT_ID
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
