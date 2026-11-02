"""Admin control plane for the Zeus Agents site: ``/admin`` and every ``/api/admin/*`` route.

Access is a single shared secret, ``ADMIN_SECRET`` (Render dashboard / environment). There is no
default: without it the admin API answers 503, because a default would be published with the
repository and hand anyone user deletion and server-side command execution. Every API call sends
the secret in ``X-Admin-Secret``; repeated wrong guesses from one client lock that client out.

Account actions map onto the model ``cli_api`` enforces: "approve" flips ``users.approved`` (the
gate ``zeus login`` checks), "revoke_tokens" revokes every terminal token of the account (they are
stored hashed, so the next ``zeus login`` mints a fresh one), "delete" removes the user document
and revokes its terminals.

The command console runs only the argv vectors in ``COMMANDS`` (no shell, 30s timeout) with the
site's own secrets stripped from the child environment.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import platform
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("zeus.admin_api")

PAGE = Path(__file__).resolve().parent / "admin.html"
REPO_ROOT = Path(__file__).resolve().parent.parent
STARTED_AT = time.time()

COMMANDS: dict[str, list[str]] = {
    "zeus status --full": ["status", "--full"],
    "zeus doctor": ["doctor"],
    "zeus tools list": ["tools", "list"],
    "zeus auth list": ["auth", "list"],
    "zeus cron list": ["cron", "list"],
    "zeus --version": ["--version"],
}
COMMAND_TIMEOUT = 30
# The child is a diagnostic `zeus` run: it never needs the site's database or OAuth credentials.
_SCRUBBED_ENV = ("MONGODB_URI", "ADMIN_SECRET", "GITHUB_CLIENT_SECRET")

_MAX_FAILURES = 10
_LOCKOUT_SECONDS = 15 * 60
_failures: dict[str, deque[float]] = {}
_failures_lock = threading.Lock()

_LOG: deque[dict[str, Any]] = deque(maxlen=200)
_log_lock = threading.Lock()
_log_seq = 0
_QUIET_PATHS = ("/api/admin/logs",)  # the log tab polls this; recording it would drown the feed

_INTEGRITY_MAX_BYTES = 256 * 1024 * 1024
_TOOL_LINE = re.compile(r"^\s*[✓✗]\s+(enabled|disabled)\s+(\S+)\s*(.*)$")
_USER_FIELDS = ("email", "name", "picture", "provider", "created_at", "last_login",
                "last_cli_login", "approved")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Site:
    """What the hosting server knows, read at request time so tests can swap it."""
    db: Any
    mongo_status: str
    fallback_users: dict[str, Any]
    port: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── event log ────────────────────────────────────────────────────────────────

def record(level: str, message: str) -> None:
    global _log_seq
    with _log_lock:
        _log_seq += 1
        _LOG.append({"seq": _log_seq, "at": _now(), "level": level, "message": message})


def record_request(path: str, fmt: str, args: tuple[Any, ...]) -> None:
    """Mirror ``BaseHTTPRequestHandler.log_message`` into the ring buffer."""
    if urllib.parse.urlparse(path).path in _QUIET_PATHS:
        return
    message = fmt % args
    if fmt.startswith('"%s"') and len(args) >= 2:  # log_request: requestline, code, size
        code = str(args[1])
        level = "ERROR" if code.startswith("5") else "WARN" if code.startswith("4") else "INFO"
    else:  # log_error
        level = "ERROR"
    record(level, message)


def logs() -> dict[str, Any]:
    with _log_lock:
        return {"entries": list(_LOG)}


# ── authentication ───────────────────────────────────────────────────────────

def _client_key(handler) -> str:
    # Render's proxy appends the real peer last; earlier entries are client-controlled.
    forwarded = handler.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[-1].strip() if forwarded else handler.client_address[0]


def _locked_out(client: str) -> bool:
    cutoff = time.time() - _LOCKOUT_SECONDS
    with _failures_lock:
        attempts = _failures.get(client)
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return bool(attempts) and len(attempts) >= _MAX_FAILURES


def _note_failure(client: str) -> None:
    with _failures_lock:
        _failures.setdefault(client, deque()).append(time.time())


def require_admin(handler, given: str) -> None:
    expected = os.environ.get("ADMIN_SECRET", "")
    if not expected:
        raise ApiError(503, "The admin panel is disabled: set ADMIN_SECRET on the server.")
    client = _client_key(handler)
    if _locked_out(client):
        raise ApiError(429, "Too many wrong admin secrets; try again in 15 minutes.")
    if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        _note_failure(client)
        record("AUTH", f"Rejected admin secret from {client}")
        raise ApiError(401, "Wrong admin secret.")


# ── telemetry ────────────────────────────────────────────────────────────────

def _mongo_health(site: Site) -> dict[str, Any]:
    if site.db is None:
        return {"status": site.mongo_status, "ping_ms": None, "database": "Zeus"}
    started = time.perf_counter()
    try:
        site.db.command("ping")
    except Exception as exc:  # network/auth failure is exactly what this card reports
        return {"status": f"error: {exc}", "ping_ms": None, "database": "Zeus"}
    return {"status": "connected", "ping_ms": round((time.perf_counter() - started) * 1000, 1),
            "database": "Zeus"}


def _user_counts(site: Site) -> dict[str, Any]:
    if site.db is None:
        users = list(site.fallback_users.values())
        providers = Counter(u.get("provider") for u in users)
        return {"source": "local_fallback", "total": len(users), "google": providers["google"],
                "github": providers["github"], "approved": sum(u.get("approved") is True for u in users),
                "active_tokens": 0}
    db = site.db
    return {"source": "mongodb", "total": db.users.count_documents({}),
            "google": db.users.count_documents({"provider": "google"}),
            "github": db.users.count_documents({"provider": "github"}),
            "approved": db.users.count_documents({"approved": True}),
            "active_tokens": db.cli_tokens.count_documents({"revoked": False})}


def _engine() -> dict[str, Any]:
    """Model and gateway of the Zeus install this server runs from (absent on a landing-only deploy)."""
    try:
        from zeus_cli.config import load_config_readonly
        from gateway.status import get_running_pid
        model = load_config_readonly().get("model") or ""
        pid = get_running_pid(cleanup_stale=False)
    except ImportError as exc:
        return {"available": False, "reason": f"Zeus is not installed on this server ({exc.name})."}
    except Exception as exc:  # a broken config is a finding to show, not a reason to fail the page
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    if isinstance(model, dict):
        name, provider = model.get("default") or model.get("model") or "", model.get("provider") or ""
    else:
        name, provider = str(model), ""
    return {"available": True, "model": name or "(not set)", "provider": provider or "auto",
            "gateway": {"running": pid is not None, "pid": pid}}


def _integrity(path: Path) -> str:
    if path.stat().st_size > _INTEGRITY_MAX_BYTES:
        return "skipped (large)"
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2)
        try:
            return str(conn.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"error: {exc}"


def _storage() -> dict[str, Any]:
    try:
        from zeus_constants import display_zeus_home, get_zeus_home
    except ImportError:
        return {"available": False, "reason": "Zeus is not installed on this server.", "files": []}
    home = get_zeus_home()
    files = sorted({*home.glob("*.db"), *home.glob("*/*.db")})
    return {"available": True, "home": display_zeus_home(), "files": [
        {"name": p.relative_to(home).as_posix(), "bytes": p.stat().st_size,
         "modified": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(),
         "integrity": _integrity(p)} for p in files]}


def overview(site: Site) -> dict[str, Any]:
    return {
        "server": {"uptime_seconds": int(time.time() - STARTED_AT), "port": site.port,
                   "python": platform.python_version(), "platform": platform.platform(terse=True),
                   "environment": "render" if os.environ.get("RENDER") else "local",
                   "cli_only": os.environ.get("CLI_ONLY", "").lower() in ("true", "1", "yes")},
        "mongodb": _mongo_health(site),
        "users": _user_counts(site),
        "engine": _engine(),
        "storage": _storage(),
    }


# ── users ────────────────────────────────────────────────────────────────────

def list_users(site: Site, query: dict[str, list[str]]) -> dict[str, Any]:
    raw_limit = (query.get("limit") or [""])[0]
    limit = max(1, min(int(raw_limit) if raw_limit.isdigit() else 1000, 5000))
    if site.db is None:
        users = sorted(site.fallback_users.values(), key=lambda u: u.get("created_at") or "", reverse=True)
        return {"source": "local_fallback",
                "users": [{**{k: u.get(k) for k in _USER_FIELDS}, "active_tokens": 0} for u in users[:limit]]}
    projection = {"_id": 0, **{k: 1 for k in _USER_FIELDS}}
    docs = site.db.users.find({}, projection).sort("created_at", -1).limit(limit)
    tokens = Counter(t.get("email") for t in site.db.cli_tokens.find({"revoked": False}, {"email": 1}))
    return {"source": "mongodb",
            "users": [{**{k: d.get(k) for k in _USER_FIELDS}, "active_tokens": tokens[d.get("email")]}
                      for d in docs]}


def _revoke(db, email: str) -> int:
    return db.cli_tokens.update_many({"email": email, "revoked": False},
                                     {"$set": {"revoked": True, "revoked_at": _now()}}).modified_count


def _approve(db, email: str, payload: dict[str, Any]) -> dict[str, Any]:
    approved = payload.get("approved") is True
    db.users.update_one({"email": email}, {"$set": {"approved": approved, "approval_changed_at": _now()}})
    return {"approved": approved}


def _revoke_tokens(db, email: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"revoked": _revoke(db, email)}


def _delete(db, email: str, payload: dict[str, Any]) -> dict[str, Any]:
    revoked = _revoke(db, email)
    db.users.delete_one({"email": email})
    return {"deleted": True, "revoked": revoked}


_USER_ACTIONS: dict[str, Callable[[Any, str, dict[str, Any]], dict[str, Any]]] = {
    "approve": _approve, "revoke_tokens": _revoke_tokens, "delete": _delete,
}


def user_action(site: Site, payload: dict[str, Any]) -> dict[str, Any]:
    action, email = str(payload.get("action") or ""), str(payload.get("email") or "").strip().lower()
    if action not in _USER_ACTIONS:
        raise ApiError(400, f"Unknown action; use one of {', '.join(_USER_ACTIONS)}.")
    if site.db is None:
        raise ApiError(503, "Account actions need MongoDB; the database is not connected.")
    if not email or site.db.users.find_one({"email": email}) is None:
        raise ApiError(404, "No such user.")
    result = _USER_ACTIONS[action](site.db, email, payload)
    record("AUTH", f"Admin {action} {email}: {json.dumps(result)}")
    return {"email": email, "action": action, **result}


# ── zeus CLI ─────────────────────────────────────────────────────────────────

def run_cli(args: list[str], timeout: int = COMMAND_TIMEOUT) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED_ENV}
    env.update(PYTHONIOENCODING="utf-8", NO_COLOR="1", TERM="dumb")
    started = time.perf_counter()
    try:
        done = subprocess.run([sys.executable, "-m", "zeus_cli.main", *args], cwd=REPO_ROOT, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": None, "timed_out": True, "stdout": exc.stdout or "", "stderr": exc.stderr or "",
                "duration_ms": int((time.perf_counter() - started) * 1000)}
    return {"exit_code": done.returncode, "timed_out": False, "stdout": done.stdout, "stderr": done.stderr,
            "duration_ms": int((time.perf_counter() - started) * 1000)}


def parse_tools(text: str) -> list[dict[str, Any]]:
    """Rows of ``zeus tools list``: section headers end in ':', rows are '✓ enabled  name  label'."""
    toolsets, section = [], ""
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            section = line.rstrip()[:-1]
        elif m := _TOOL_LINE.match(line):
            toolsets.append({"section": section, "name": m.group(2), "label": m.group(3).strip(),
                             "enabled": m.group(1) == "enabled"})
    return toolsets


def tools() -> dict[str, Any]:
    result = run_cli(COMMANDS["zeus tools list"])
    return {"toolsets": parse_tools(result["stdout"]), **result}


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    command = " ".join(str(payload.get("command") or "").split())
    if command not in COMMANDS:
        raise ApiError(400, "Only these commands are allowed: " + ", ".join(COMMANDS))
    record("AUTH", f"Admin ran `{command}`")
    return {"command": command, **run_cli(COMMANDS[command])}


# ── HTTP routing ─────────────────────────────────────────────────────────────

def _json_body(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body or "{}")
    except ValueError as exc:
        raise ApiError(400, "Request body must be JSON.") from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.")
    return payload


def _auth(handler, site: Site, query, body: str) -> dict[str, Any]:
    require_admin(handler, str(_json_body(body).get("secret") or ""))
    record("AUTH", f"Admin signed in from {_client_key(handler)}")
    return {"ok": True}


_GET: dict[str, Callable[..., dict[str, Any]]] = {
    "/api/admin/overview": lambda h, site, q, b: overview(site),
    "/api/admin/users": lambda h, site, q, b: list_users(site, q),
    "/api/admin/tools": lambda h, site, q, b: tools(),
    "/api/admin/logs": lambda h, site, q, b: logs(),
}
_POST: dict[str, Callable[..., dict[str, Any]]] = {
    "/api/admin/auth": _auth,
    "/api/admin/users/action": lambda h, site, q, b: user_action(site, _json_body(b)),
    "/api/admin/exec": lambda h, site, q, b: execute(_json_body(b)),
}
_ROUTES = {"GET": _GET, "POST": _POST}
_PAGE_PATHS = ("/admin", "/admin/")


def _send(handler, status: int, data: bytes, content_type: str, extra: dict[str, str]) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    for key, value in extra.items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(data)


def _serve_page(handler) -> None:
    _send(handler, 200, PAGE.read_bytes(), "text/html; charset=utf-8", {
        "X-Robots-Tag": "noindex, nofollow",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": ("default-src 'self'; img-src 'self' https: data:; "
                                    "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                                    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"),
    })


def handle(handler, method: str, raw_path: str, body: str, site: Site) -> bool:
    """Serve *raw_path* when it is an admin route; False leaves it to the caller."""
    url = urllib.parse.urlparse(raw_path)
    if method == "GET" and url.path in _PAGE_PATHS:
        _serve_page(handler)
        return True
    if not url.path.startswith("/api/admin/"):
        return False
    try:
        route = _ROUTES.get(method, {}).get(url.path)
        if route is None:
            raise ApiError(404, "No such admin endpoint.")
        if route is not _auth:
            require_admin(handler, handler.headers.get("X-Admin-Secret", ""))
        status, result = 200, route(handler, site, urllib.parse.parse_qs(url.query), body)
    except ApiError as exc:
        status, result = exc.status, {"error": exc.message}
    except Exception as exc:  # a database failure must still answer the panel, not drop the socket
        logger.exception("admin_api %s failed", url.path)
        record("ERROR", f"{url.path}: {type(exc).__name__}: {exc}")
        status, result = 500, {"error": f"{type(exc).__name__}: {exc}"}
    _send(handler, status, json.dumps(result, default=str).encode("utf-8"), "application/json",
          {"Cache-Control": "no-store"})
    return True
