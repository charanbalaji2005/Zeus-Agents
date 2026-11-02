"""MongoDB read models and maintenance behind the admin panel (routing and auth live in ``admin_api``).

Collections (see ``cli_api``): ``users``, ``cli_tokens`` (one per signed-in terminal, keyed by the
sha256 of its token), ``usage`` (one per model call, ``usage`` holds the canonical token buckets),
``conversations`` (one per opted-in turn) and ``admin_audit`` (every admin mutation, written here).

Timestamps written by ``cli_api`` are UTC ISO strings, so range filters compare them as strings.
A token's sha256 doubles as its session id: it cannot be turned back into the token.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

ANALYTICS_MAX_DOCS = 100_000  # bounds one analytics pass on a large ``usage`` collection
TOP_N = 10
COLLECTIONS = ("users", "cli_tokens", "usage", "conversations", "admin_audit")
PRUNABLE = ("usage", "conversations")  # the audit trail is never prunable from the panel
TEXT_CLIP = 8000
_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")
_USAGE_FIELDS = {"_id": 0, "email": 1, "model": 1, "provider": 1, "platform": 1, "usage": 1,
                 "api_duration": 1, "received_at": 1}
_SESSION_FIELDS = {"_id": 0, "token_sha256": 1, "email": 1, "created_at": 1, "last_used": 1,
                   "revoked": 1, "revoked_at": 1}
_CONVERSATION_FIELDS = {"_id": 0, "email": 1, "session_id": 1, "turn_id": 1, "model": 1, "platform": 1,
                        "user_message": 1, "assistant_response": 1, "received_at": 1}


def _now() -> datetime:
    return datetime.now(UTC)


def _since(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


def _tokens(usage: Any) -> dict[str, int]:
    usage = usage if isinstance(usage, dict) else {}
    out = {k: int(usage.get(k) or 0) for k in _TOKEN_KEYS}
    out["total_tokens"] = int(usage.get("total_tokens") or 0) or out["input_tokens"] + out["output_tokens"] \
        + out["cache_read_tokens"] + out["cache_write_tokens"]
    return out


# ── analytics ────────────────────────────────────────────────────────────────

def _top(table: dict[str, Counter], key: str, extra: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = sorted(table.items(), key=lambda kv: (kv[1]["tokens"], kv[1]["requests"]), reverse=True)[:TOP_N]
    return [{key: name, "requests": c["requests"], "tokens": c["tokens"], **(extra or {}).get(name, {})}
            for name, c in rows]


def analytics(db, days: int) -> dict[str, Any]:
    """Usage over the last *days* days: totals, a zero-filled daily series and top models/users."""
    since = _since(days)
    docs = db.usage.find({"received_at": {"$gte": since}}, _USAGE_FIELDS).limit(ANALYTICS_MAX_DOCS)
    totals: Counter = Counter()
    daily: dict[str, Counter] = defaultdict(Counter)
    models: dict[str, Counter] = defaultdict(Counter)
    users: dict[str, Counter] = defaultdict(Counter)
    platforms: Counter = Counter()
    providers: dict[str, dict[str, Any]] = {}
    last_seen: dict[str, dict[str, Any]] = {}
    latency_total, latency_n, seen = 0.0, 0, 0
    for doc in docs:
        seen += 1
        tok = _tokens(doc.get("usage"))
        totals.update(tok)
        model, email = str(doc.get("model") or "unknown"), str(doc.get("email") or "unknown")
        when = str(doc.get("received_at") or "")
        for bucket in (daily[when[:10]], models[model], users[email]):
            bucket["requests"] += 1
            bucket["tokens"] += tok["total_tokens"]
        providers.setdefault(model, {"provider": doc.get("provider") or ""})
        if when > last_seen.get(email, {}).get("last_active", ""):
            last_seen[email] = {"last_active": when}
        platforms[str(doc.get("platform") or "unknown")] += 1
        if isinstance(doc.get("api_duration"), (int, float)):
            latency_total += float(doc["api_duration"])
            latency_n += 1
    signups = Counter(str(u.get("created_at") or "")[:10]
                      for u in db.users.find({"created_at": {"$gte": since[:10]}}, {"_id": 0, "created_at": 1}))
    today = _now().date()
    series = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        series.append({"date": day, "requests": daily[day]["requests"], "tokens": daily[day]["tokens"],
                       "signups": signups[day]})
    prompt = totals["input_tokens"] + totals["cache_read_tokens"] + totals["cache_write_tokens"]
    return {
        "days": days,
        "truncated": seen >= ANALYTICS_MAX_DOCS,
        "totals": {
            "requests": seen, **{k: totals[k] for k in (*_TOKEN_KEYS, "total_tokens")},
            "active_users": len(users),
            "avg_latency_ms": round(latency_total / latency_n * 1000) if latency_n else None,
            "cache_hit_rate": round(totals["cache_read_tokens"] / prompt, 4) if prompt else None,
            "conversations": db.conversations.count_documents({"received_at": {"$gte": since}}),
            "signups": sum(signups.values()),
        },
        "series": series,
        "models": _top(models, "model", providers),
        "users": _top(users, "email", last_seen),
        "platforms": [{"platform": p, "requests": n} for p, n in platforms.most_common(TOP_N)],
    }


# ── terminal sessions ────────────────────────────────────────────────────────

SESSION_FILTERS = {"active": {"revoked": False}, "revoked": {"revoked": True}, "all": {}}


def _session(doc: dict[str, Any]) -> dict[str, Any]:
    digest = str(doc.get("token_sha256") or "")
    return {"id": digest, "fingerprint": digest[:12], "email": doc.get("email"),
            "created_at": doc.get("created_at"), "last_used": doc.get("last_used"),
            "revoked": bool(doc.get("revoked")), "revoked_at": doc.get("revoked_at")}


def sessions(db, status: str, email: str, limit: int) -> list[dict[str, Any]]:
    query = dict(SESSION_FILTERS[status])
    if email:
        query["email"] = email
    return [_session(d) for d in db.cli_tokens.find(query, _SESSION_FIELDS).sort("last_used", -1).limit(limit)]


def revoke_session(db, session_id: str) -> str | None:
    """The owning email when an active session was revoked, else None."""
    grant = db.cli_tokens.find_one({"token_sha256": session_id, "revoked": False})
    if grant is None:
        return None
    db.cli_tokens.update_one({"token_sha256": session_id},
                             {"$set": {"revoked": True, "revoked_at": _now().isoformat()}})
    return grant.get("email")


# ── conversations ────────────────────────────────────────────────────────────

def _clip(value: Any) -> tuple[str, bool]:
    text = value if isinstance(value, str) else ""
    return text[:TEXT_CLIP], len(text) > TEXT_CLIP


def _conversation(doc: dict[str, Any]) -> dict[str, Any]:
    user, user_cut = _clip(doc.get("user_message"))
    reply, reply_cut = _clip(doc.get("assistant_response"))
    return {k: doc.get(k) for k in ("email", "session_id", "turn_id", "model", "platform", "received_at")} | {
        "user_message": user, "assistant_response": reply, "truncated": user_cut or reply_cut}


def conversations(db, email: str, text: str, before: str, limit: int) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if email:
        query["email"] = email
    if text:
        pattern = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"user_message": pattern}, {"assistant_response": pattern}]
    if before:
        query["received_at"] = {"$lt": before}
    docs = list(db.conversations.find(query, _CONVERSATION_FIELDS).sort("received_at", -1).limit(limit + 1))
    items = [_conversation(d) for d in docs[:limit]]
    return {"items": items, "next_before": items[-1]["received_at"] if len(docs) > limit else None}


# ── one user ─────────────────────────────────────────────────────────────────

def user_detail(db, email: str) -> dict[str, Any] | None:
    user = db.users.find_one({"email": email}, {"_id": 0})
    if user is None:
        return None
    totals: Counter = Counter()
    models: Counter = Counter()
    last_active = ""
    requests = 0
    for doc in db.usage.find({"email": email}, _USAGE_FIELDS).limit(ANALYTICS_MAX_DOCS):
        requests += 1
        tok = _tokens(doc.get("usage"))
        totals.update(tok)
        models[str(doc.get("model") or "unknown")] += 1
        last_active = max(last_active, str(doc.get("received_at") or ""))
    return {
        "user": user,
        "sessions": sessions(db, "all", email, 200),
        "usage": {"requests": requests, "total_tokens": totals["total_tokens"],
                  "input_tokens": totals["input_tokens"], "output_tokens": totals["output_tokens"],
                  "last_active": last_active or None,
                  "models": [{"model": m, "requests": n} for m, n in models.most_common(TOP_N)]},
        "conversation_count": db.conversations.count_documents({"email": email}),
        "recent_conversations": conversations(db, email, "", "", 10)["items"],
    }


def purge_user_data(db, email: str) -> dict[str, int]:
    return {"usage": db.usage.delete_many({"email": email}).deleted_count,
            "conversations": db.conversations.delete_many({"email": email}).deleted_count}


# ── database & audit ─────────────────────────────────────────────────────────

def database_stats(db) -> dict[str, Any]:
    from pymongo.errors import PyMongoError

    counts = {name: getattr(db, name).count_documents({}) for name in COLLECTIONS}
    try:
        raw = db.command("dbStats")
        size = {"data_bytes": raw.get("dataSize"), "storage_bytes": raw.get("storageSize"),
                "index_bytes": raw.get("indexSize")}
    except PyMongoError as exc:  # shared Atlas tiers may refuse dbStats; the counts still stand
        size = {"error": str(exc)}
    oldest = {name: next(iter(getattr(db, name).find({}, {"_id": 0, "received_at": 1})
                              .sort("received_at", 1).limit(1)), {}).get("received_at")
              for name in PRUNABLE}
    return {"collections": counts, "size": size, "oldest": oldest, "prunable": list(PRUNABLE)}


def prune(db, collection: str, older_than_days: int) -> int:
    cutoff = _since(older_than_days)
    return getattr(db, collection).delete_many({"received_at": {"$lt": cutoff}}).deleted_count


def write_audit(db, entry: dict[str, Any]) -> None:
    db.admin_audit.insert_one(dict(entry))


def audit_log(db, action: str, limit: int) -> list[dict[str, Any]]:
    query = {"action": action} if action else {}
    return list(db.admin_audit.find(query, {"_id": 0}).sort("at", -1).limit(limit))
