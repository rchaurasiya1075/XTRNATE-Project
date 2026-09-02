"""Firestore helper. Prefers one-shot FIREBASE_SA_JSON secret."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ID = "xtranet-d7dca"
_app = None

PEM_BLOCK = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----([^-]*)-----END \1-----",
    re.DOTALL,
)


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
    key = str(raw or "")
    key = key.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    key = key.replace("BEGIN_PRIVATE_KEY", "BEGIN PRIVATE KEY").replace("END_PRIVATE_KEY", "END PRIVATE KEY")
    m = PEM_BLOCK.search(key)
    if not m:
        m2 = re.search(
            r"BEGIN ([A-Z ]*PRIVATE KEY)-----(.*?)-----END",
            key,
            re.DOTALL,
        )
        if m2:
            label = m2.group(1).strip() or "PRIVATE KEY"
            body = m2.group(2)
        else:
            label = "PRIVATE KEY"
            body = key
    else:
        label = (m.group(1) or "PRIVATE KEY").strip()
        body = m.group(2)
    body = re.sub(r"[^A-Za-z0-9+/=]", "", body)
    if len(body) < 80:
        raise ValueError(
            "private_key toot gayi (PEM body short). Secrets mein JSON file ka "
            "private_key field poora paste karo."
        )
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN {label}-----\n{wrapped}\n-----END {label}-----\n"


def _escape_ctrl_in_strings(text):
    out = []
    in_str = False
    esc = False
    for ch in text:
        if not in_str:
            if ch == '"':
                in_str = True
            out.append(ch)
            continue
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = False
            out.append(ch)
            continue
        if ch == "\n":
            out.append("\\n")
            continue
        if ch == "\r":
            continue
        if ch == "\t":
            out.append("\\t")
            continue
        if ord(ch) < 32:
            continue
        out.append(ch)
    return "".join(out)


def _parse_sa_json(raw):
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if text.startswith('"') and text.endswith('"') and text.count('"') == 2:
        text = text[1:-1]
    for candidate in (text, _escape_ctrl_in_strings(text)):
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
    raise ValueError(
        "JSON parse fail. FIREBASE_SA_JSON mein poori JSON file paste karo."
    )


def _load_sa_info():
    import streamlit as st

    raw = None
    for name in ("FIREBASE_SA_JSON", "firebase_sa_json"):
        if name in st.secrets:
            raw = st.secrets[name]
            break
    if raw is not None:
        info = _parse_sa_json(raw)
    else:
        info = dict(st.secrets["google_service_account"])
    if not isinstance(info, dict):
        raise ValueError("Service account JSON object nahi bana.")
    info = {str(k): info[k] for k in info}
    if "private_key" not in info:
        raise ValueError("JSON mein private_key field nahi hai.")
    info["private_key"] = _fix_private_key(info["private_key"])
    info["type"] = info.get("type") or "service_account"
    return info


def get_db():
    global _app
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_ready():
        raise RuntimeError("Firebase secrets missing.")
    if not firebase_admin._apps:
        info = _load_sa_info()
        try:
            cred = credentials.Certificate(info)
        except ValueError as e:
            pk = str(info.get("private_key", ""))
            raise ValueError(
                "Firebase key load fail. PEM starts_with_BEGIN="
                f"{pk.strip().startswith('-----BEGIN')} len={len(pk)}. "
                "Secrets box poora saaf karke sirf FIREBASE_SA_JSON = \"\"\" {json} \"\"\" paste karo. "
                f"Detail: {e}"
            ) from e
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
