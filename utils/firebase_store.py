"""Firestore helper module for Streamlit & Firebase Admin SDK."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ID = "xtranet-d7dca"
_app = None

# Standard PEM Block Regex
PEM_BLOCK = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----([^-]*)-----END \1-----",
    re.DOTALL,
)


def _now():
    """Returns current date time string in IST format."""
    return datetime.now(IST).strftime("%d-%b-%Y %I:%M:%S %p IST")


def firebase_ready():
    """Check if Firebase secret keys are present in Streamlit secrets."""
    try:
        import streamlit as st
        if "FIREBASE_SA_JSON" in st.secrets or "firebase_sa_json" in st.secrets:
            return True
        return "google_service_account" in st.secrets
    except Exception:
        return False


def _fix_private_key(raw):
    """Normalizes and reconstructs standard PEM RSA private key string."""
    key = str(raw or "").strip()
    
    # Strip quotes & clean escaped newlines
    key = key.strip('"').strip("'")
    key = key.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    key = key.replace("BEGIN_PRIVATE_KEY", "BEGIN PRIVATE KEY").replace("END_PRIVATE_KEY", "END PRIVATE KEY")
    
    # Extract inner base64 body
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

    # Clean non-Base64 characters
    clean_base64 = re.sub(r"[^A-Za-z0-9+/=]", "", body)
    
    if len(clean_base64) < 500:
        raise ValueError(
            "Private key corrupt ya truncated hai. Please check secrets configuration."
        )

    # Wrap Base64 body to standard 64-character PEM lines
    wrapped_lines = [clean_base64[i : i + 64] for i in range(0, len(clean_base64), 64)]
    pem_body = "\n".join(wrapped_lines)
    
    return f"-----BEGIN {label}-----\n{pem_body}\n-----END {label}-----\n"


def _escape_ctrl_in_strings(text):
    """Escapes control characters in JSON strings to prevent JSONDecodeError."""
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
    """Parses raw JSON payload into Python dictionary."""
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
    """Loads service account credentials safely from Streamlit secrets."""
    import streamlit as st

    raw = None
    for name in ("FIREBASE_SA_JSON", "firebase_sa_json"):
        if name in st.secrets:
            raw = st.secrets[name]
            break
            
    if raw is not None:
        info = _parse_sa_json(raw)
    elif "google_service_account" in st.secrets:
        info = dict(st.secrets["google_service_account"])
    else:
        raise KeyError("Secrets me Firebase service account credentials nahi mile.")

    if not isinstance(info, dict):
        raise ValueError("Service account object dict format mein match nahi hua.")

    info = {str(k): info[k] for k in info}
    
    if "private_key" not in info:
        raise ValueError("JSON mein private_key field missing hai.")

    info["private_key"] = _fix_private_key(info["private_key"])
    info["type"] = info.get("type") or "service_account"
    return info


def get_db():
    """Initializes Firebase Admin App and returns Firestore DB Client instance."""
    global _app
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_ready():
        raise RuntimeError("Firebase secrets missing in Streamlit.")
        
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
    """Inserts or updates a document in a Firestore collection."""
    db = get_db()
    payload = dict(data)
    payload["updated_at"] = _now()
    
    doc_ref = db.collection(collection).document(str(doc_id))
    existing = doc_ref.get()
    
    if existing.exists:
        prev = existing.to_dict() or {}
        payload["created_at"] = prev.get("created_at", _now())
    else:
        payload["created_at"] = _now()
        
    doc_ref.set(payload, merge=True)
    return payload


def get_one(collection, doc_id):
    """Fetches a single document by ID from a Firestore collection."""
    db = get_db()
    snap = db.collection(collection).document(str(doc_id)).get()
    return snap.to_dict() if snap.exists else None


def list_all(collection, limit=2000):
    """Lists all documents from a specified Firestore collection."""
    db = get_db()
    rows = []
    for snap in db.collection(collection).limit(limit).stream():
        row = snap.to_dict() or {}
        row["_id"] = snap.id
        rows.append(row)
    return rows


def delete_one(collection, doc_id):
    """Deletes a document by ID from a Firestore collection."""
    get_db().collection(collection).document(str(doc_id)).delete()
