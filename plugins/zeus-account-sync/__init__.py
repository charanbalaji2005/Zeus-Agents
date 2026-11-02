"""Upload opted-in activity to the signed-in Zeus Agents account (see ``zeus_cli/auth_google_account``).

``post_api_request`` -> a usage record (``account.sync.usage``); ``post_llm_call`` -> a
conversation turn (``account.sync.conversations``). Both switches are off until the user says yes
during ``zeus login`` (or ``zeus login --sharing``), and nothing is sent without a terminal token
from an approved sign-in.

Hooks fire on the turn thread under the owning profile's scope, so settings, the token and the
outbox path are resolved there and handed to a scope-bound background thread: an upload never
delays a turn. A record the server could not take for a transient reason (offline, 429, 5xx)
waits in ``<zeus_home>/account_sync_outbox.json`` and goes out with the next upload.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

OUTBOX_NAME = "account_sync_outbox.json"
_OUTBOX_MAX_RECORDS = 5000
_BATCH = 200
_MAX_TEXT_CHARS = 200_000
_KINDS = ("usage", "conversations")
_lock = threading.Lock()


def _target(kind: str) -> Optional[tuple[str, str, Path]]:
    """``(portal_url, terminal_token, outbox_path)`` when *kind* is opted in and signed in."""
    from zeus_cli.auth_google_account import load_account
    from zeus_cli.config import load_config_readonly
    from zeus_constants import get_zeus_home

    account_cfg = (load_config_readonly() or {}).get("account") or {}
    if not (account_cfg.get("sync") or {}).get(kind):
        return None
    portal = str(account_cfg.get("portal_url") or "").rstrip("/")
    token = str((load_account() or {}).get("token") or "")
    if not portal or not token.startswith("zat_"):
        return None
    return portal, token, get_zeus_home() / OUTBOX_NAME


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return text[:_MAX_TEXT_CHARS]


def _read_outbox(path: Path) -> list[dict[str, Any]]:
    from utils import read_json_or_empty
    pending = read_json_or_empty(path).get("pending")
    return [p for p in pending if isinstance(p, dict) and p.get("kind") in _KINDS] if isinstance(pending, list) else []


def _write_outbox(path: Path, pending: list[dict[str, Any]]) -> None:
    if not pending:
        path.unlink(missing_ok=True)
        return
    from utils import atomic_json_write
    atomic_json_write(path, {"pending": pending[-_OUTBOX_MAX_RECORDS:]}, mode=0o600)


def _retryable(status: int) -> bool:
    return status == 0 or status == 429 or status >= 500


def deliver(portal: str, token: str, outbox: Path, kind: str, record: dict[str, Any], *, post=None) -> None:
    """Send *record* plus anything waiting in *outbox*; keep only what failed transiently."""
    if post is None:
        from zeus_cli.auth_google_account import post_json as post
    with _lock:
        pending = _read_outbox(outbox) + [{"kind": kind, "record": record}]
        keep: list[dict[str, Any]] = []
        for k in _KINDS:
            records = [p["record"] for p in pending if p["kind"] == k]
            for start in range(0, len(records), _BATCH):
                status, body = post(f"{portal}/api/cli/{k}", {"records": records[start:start + _BATCH]}, token)
                if status == 200:
                    continue
                if _retryable(status):
                    keep += [{"kind": k, "record": r} for r in records[start:]]
                else:  # rejected outright (signed out, unapproved, malformed): retrying cannot help
                    logger.warning("Zeus Agents rejected %d %s record(s): %s", len(records) - start, k,
                                   body.get("error") or f"HTTP {status}")
                break
        _write_outbox(outbox, keep)


def _enqueue(kind: str, record: dict[str, Any]) -> None:
    target = _target(kind)
    if target is None:
        return
    from agent.memory_provider import spawn_context_thread
    portal, token, outbox = target
    spawn_context_thread(deliver, name=f"zeus-account-sync-{kind}",
                         args=(portal, token, outbox, kind, record)).start()


def _on_post_api_request(*, session_id=None, turn_id=None, api_request_id=None, model=None, provider=None,
                         platform=None, usage=None, api_duration=None, started_at=None,
                         finish_reason=None, **_ignored) -> None:
    _enqueue("usage", {
        "session_id": session_id, "turn_id": turn_id, "api_request_id": api_request_id, "model": model,
        "provider": provider, "platform": platform, "usage": usage if isinstance(usage, dict) else None,
        "api_duration": api_duration, "started_at": started_at, "finish_reason": finish_reason,
        "at": time.time(),
    })


def _on_post_llm_call(*, session_id=None, turn_id=None, user_message=None, assistant_response=None,
                      model=None, platform=None, **_ignored) -> None:
    _enqueue("conversations", {
        "session_id": session_id, "turn_id": turn_id, "model": model, "platform": platform,
        "user_message": _text(user_message), "assistant_response": _text(assistant_response),
        "at": time.time(),
    })


def register(ctx) -> None:
    ctx.register_hook("post_api_request", _on_post_api_request)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
