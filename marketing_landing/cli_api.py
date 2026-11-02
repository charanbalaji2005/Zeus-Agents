"""Zeus Agents account API for the terminal: approval-gated ``zeus login``, then usage and
conversation uploads from terminals whose owner opted in.

Everything is stored in MongoDB (database ``Zeus``) and nowhere else: when the database is not
connected these endpoints answer 503 instead of falling back to a local file.

Collections (the site owner administers them in MongoDB Atlas):
  users          one document per Google account. ``approved: true`` lets ``zeus login`` succeed;
                 new accounts start unapproved unless their email is in ADMIN_EMAILS.
  cli_tokens     one per signed-in terminal: sha256 of its token -> email. ``revoked: true`` cuts
                 that terminal off; un-approving the user cuts off all of them.
  usage          one per model API call: model, provider, token counts, timing.
  conversations  one per turn: the user's message and Zeus's reply.

Every Google token is verified with Google (issued to OUR client id, verified email, unexpired)
before an account is created or a terminal token minted; nothing the browser claims is trusted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
_TOKEN_KINDS = ("credential", "access_token")
_MAX_BATCH = 200
_MAX_TEXT_CHARS = 200_000
logger = logging.getLogger("zeus.cli_api")


def admin_emails() -> frozenset[str]:
    """``ADMIN_EMAILS`` (comma-separated): approved automatically, so the owner never locks themselves out."""
    return frozenset(e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip())

_USAGE_FIELDS = ("session_id", "turn_id", "api_request_id", "model", "provider", "platform",
                 "api_duration", "started_at", "finish_reason", "at")
_CONVERSATION_FIELDS = ("session_id", "turn_id", "model", "platform", "user_message",
                        "assistant_response", "at")


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fetch_google(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiError(401, f"Google rejected the sign-in token (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ApiError(502, f"Could not reach Google to verify the sign-in: {exc}") from exc
    if not isinstance(data, dict):
        raise ApiError(502, "Google returned an unexpected verification response.")
    return data


def verify_google_token(kind: str, token: str, client_id: str, *,
                        fetch: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """The verified Google profile for *token*, or ApiError."""
    fetch = fetch or _fetch_google
    if kind not in _TOKEN_KINDS or not token:
        raise ApiError(400, "Send a Google 'credential' or 'access_token'.")
    param = "id_token" if kind == "credential" else "access_token"
    info = fetch(f"{TOKENINFO_URL}?{urllib.parse.urlencode({param: token})}")
    if not client_id or (info.get("aud") or info.get("azp")) != client_id:
        raise ApiError(401, "This Google token was not issued for Zeus Agents.")
    if kind == "credential" and info.get("iss") not in _GOOGLE_ISSUERS:
        raise ApiError(401, "This ID token was not issued by Google.")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        raise ApiError(401, "This Google account has no verified email address.")
    if int(info.get("exp") or 0) <= time.time():
        raise ApiError(401, "The Google sign-in expired; run `zeus login` again.")
    profile = info if kind == "credential" else fetch(USERINFO_URL, {"Authorization": f"Bearer {token}"})
    if profile.get("sub") != info.get("sub"):
        raise ApiError(401, "Google returned a profile for a different account.")
    return {"email": info["email"].lower(), "sub": info.get("sub"),
            "name": profile.get("name") or info["email"], "picture": profile.get("picture")}


def _ensure_indexes(db) -> None:
    if getattr(db, "_zeus_cli_indexes", False):
        return
    db.cli_tokens.create_index("token_sha256", unique=True)
    db.users.create_index("email")
    db.usage.create_index([("email", 1), ("received_at", -1)])
    db.conversations.create_index([("email", 1), ("session_id", 1)])
    db._zeus_cli_indexes = True


def cli_login(db, client_id: str, payload: dict[str, Any], *, verify=verify_google_token) -> dict[str, Any]:
    """Register the Google account; mint a terminal token only when the account is approved."""
    profile = verify(str(payload.get("kind") or ""), str(payload.get("token") or ""), client_id)
    email, now, is_admin = profile["email"], _now(), profile["email"] in admin_emails()
    fields = {"email": email, "name": profile["name"], "picture": profile["picture"],
              "provider": "google", "provider_id": profile["sub"], "last_cli_login": now}
    if is_admin:
        fields["approved"] = True
    on_insert = {"created_at": now} if is_admin else {"created_at": now, "approved": False}
    db.users.update_one({"email": email}, {"$set": fields, "$setOnInsert": on_insert}, upsert=True)
    user = db.users.find_one({"email": email}) or {}
    if user.get("approved") is not True:
        raise ApiError(403, "Your Zeus Agents account is waiting for approval.", approved=False, email=email)
    token = "zat_" + secrets.token_urlsafe(32)
    db.cli_tokens.insert_one({"token_sha256": _sha256(token), "email": email, "created_at": now,
                              "last_used": now, "revoked": False})
    return {"approved": True, "token": token, "email": email, "name": profile["name"]}


def authenticate(db, authorization: str) -> str:
    """The approved email behind a ``Bearer zat_...`` terminal token, or ApiError."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith("zat_"):
        raise ApiError(401, "Missing terminal token; run `zeus login`.")
    grant = db.cli_tokens.find_one({"token_sha256": _sha256(token.strip())})
    if not grant or grant.get("revoked"):
        raise ApiError(401, "This terminal was signed out; run `zeus login` again.")
    user = db.users.find_one({"email": grant["email"]}) or {}
    if user.get("approved") is not True:
        raise ApiError(403, "Your Zeus Agents account is not approved.")
    db.cli_tokens.update_one({"_id": grant["_id"]}, {"$set": {"last_used": _now()}})
    return grant["email"]


def _clip(value: Any) -> Any:
    return value[:_MAX_TEXT_CHARS] if isinstance(value, str) else value


def _usage_doc(record: dict[str, Any]) -> dict[str, Any]:
    doc = {k: _clip(record.get(k)) for k in _USAGE_FIELDS if record.get(k) is not None}
    usage = record.get("usage")
    if isinstance(usage, dict):
        doc["usage"] = {k: v for k, v in usage.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    return doc


def _conversation_doc(record: dict[str, Any]) -> dict[str, Any]:
    return {k: _clip(record.get(k)) for k in _CONVERSATION_FIELDS if record.get(k) is not None}


_COLLECTIONS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "/api/cli/usage": ("usage", _usage_doc),
    "/api/cli/conversations": ("conversations", _conversation_doc),
}


def ingest(db, email: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ApiError(400, "Send a non-empty 'records' list.")
    if len(records) > _MAX_BATCH:
        raise ApiError(413, f"At most {_MAX_BATCH} records per request.")
    collection, shape = _COLLECTIONS[path]
    received = _now()
    docs = [{**shape(r), "email": email, "received_at": received} for r in records if isinstance(r, dict)]
    if docs:
        getattr(db, collection).insert_many(docs)
    return {"stored": len(docs)}


def cli_logout(db, authorization: str) -> dict[str, Any]:
    _, _, token = (authorization or "").partition(" ")
    if token.startswith("zat_"):
        db.cli_tokens.update_one({"token_sha256": _sha256(token.strip())},
                                 {"$set": {"revoked": True, "revoked_at": _now()}})
    return {"signed_out": True}


def _dispatch(path: str, db, client_id: str, payload: dict[str, Any], authorization: str) -> dict[str, Any]:
    if path == "/api/cli/login":
        return cli_login(db, client_id, payload)
    if path == "/api/cli/logout":
        return cli_logout(db, authorization)
    return ingest(db, authenticate(db, authorization), path, payload)


ROUTES = frozenset({"/api/cli/login", "/api/cli/logout", *_COLLECTIONS})


def handle_post(handler, path: str, body: str, db, client_id: str) -> bool:
    """Serve *path* on *handler* when it is a CLI route; False leaves it to the caller."""
    if path not in ROUTES:
        return False
    try:
        if db is None:
            raise ApiError(503, "The Zeus Agents database is not connected.")
        _ensure_indexes(db)
        try:
            payload = json.loads(body or "{}")
        except ValueError as exc:
            raise ApiError(400, "Request body must be JSON.") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "Request body must be a JSON object.")
        status, result = 200, _dispatch(path, db, client_id, payload, handler.headers.get("Authorization", ""))
    except ApiError as exc:
        status, result = exc.status, {"error": exc.message, **exc.extra}
    except Exception:  # a database failure must still answer the terminal, not drop it
        logger.exception("cli_api %s failed", path)
        status, result = 500, {"error": "The Zeus Agents server hit an error; try again shortly."}
    data = json.dumps(result).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
    return True
