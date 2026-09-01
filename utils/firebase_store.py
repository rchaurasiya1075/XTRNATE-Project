"""Firestore helper. Uses Streamlit secrets google_service_account."""
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
        info = dict(st.secrets["google_service_account"])
        if "private_key" in info:
            info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
        cred = credentials.Certificate(info)
        pid = st.secrets.get("firebase", {}).get("projectId", PROJECT_ID)
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
