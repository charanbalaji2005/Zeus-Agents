"""The terminal account API on the Zeus Agents site: only approved Google accounts get a terminal
token, uploads need that token, and everything lands in MongoDB (never a local fallback).

Driven over real HTTP against the real ``server.py`` handler; only MongoDB and Google's tokeninfo
are stand-ins."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from marketing_landing import cli_api


class _Collection:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _match(doc, query):
        return all(doc.get(k) == v for k, v in query.items())

    def find_one(self, query):
        return next((d for d in self.docs if self._match(d, query)), None)

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if doc is None:
            if not upsert:
                return
            doc = dict(query, **update.get("$setOnInsert", {}))
            doc["_id"] = len(self.docs) + 1
            self.docs.append(doc)
        doc.update(update.get("$set", {}))

    def insert_one(self, doc):
        self.docs.append(dict(doc, _id=len(self.docs) + 1))

    def insert_many(self, docs):
        for doc in docs:
            self.insert_one(doc)

    def create_index(self, *args, **kwargs):
        pass


class _FakeMongo:
    def __init__(self):
        for name in ("users", "cli_tokens", "usage", "conversations"):
            setattr(self, name, _Collection())


CLIENT_ID = "test-client.apps.googleusercontent.com"
GOOGLE_PROFILE = {"aud": CLIENT_ID, "email": "Ada@Example.com", "email_verified": "true",
                  "sub": "g-123", "exp": "9999999999", "name": "Ada", "picture": None}


@pytest.fixture
def site(monkeypatch):
    """The real landing server on a free port, backed by a fake MongoDB and a fake Google."""
    import server

    db = _FakeMongo()
    monkeypatch.setattr(server, "mongo_db", db)
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(cli_api, "_fetch_google", lambda url, headers=None: dict(GOOGLE_PROFILE))
    httpd = server.ThreadingTCPServer(("127.0.0.1", 0), server.ZeusHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", db
    httpd.shutdown()
    httpd.server_close()


def _post(url, payload, token=""):
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _login(base):
    return _post(f"{base}/api/cli/login", {"kind": "access_token", "token": "google-token"})


def test_new_account_is_recorded_but_waits_for_approval(site):
    base, db = site
    status, body = _login(base)
    assert status == 403 and body["approved"] is False
    user = db.users.find_one({"email": "ada@example.com"})
    assert user["approved"] is False and user["provider"] == "google"
    assert db.cli_tokens.docs == []


def test_approved_account_gets_a_token_and_its_uploads_land_in_mongodb(site):
    base, db = site
    _login(base)
    db.users.find_one({"email": "ada@example.com"})["approved"] = True

    status, body = _login(base)
    assert status == 200 and body["token"].startswith("zat_")
    assert all(body["token"] not in json.dumps(d, default=str) for d in db.cli_tokens.docs)  # hash only

    usage = {"session_id": "s1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "note": "x"}}
    turn = {"session_id": "s1", "user_message": "hi", "assistant_response": "hello"}
    assert _post(f"{base}/api/cli/usage", {"records": [usage]}, body["token"]) == (200, {"stored": 1})
    assert _post(f"{base}/api/cli/conversations", {"records": [turn]}, body["token"]) == (200, {"stored": 1})
    assert db.usage.docs[0]["email"] == "ada@example.com"
    assert db.usage.docs[0]["usage"] == {"input_tokens": 10}
    assert db.conversations.docs[0]["user_message"] == "hi"


def test_unapproving_or_revoking_cuts_the_terminal_off(site):
    base, db = site
    _login(base)
    user = db.users.find_one({"email": "ada@example.com"})
    user["approved"] = True
    token = _login(base)[1]["token"]

    user["approved"] = False
    assert _post(f"{base}/api/cli/usage", {"records": [{"model": "m"}]}, token)[0] == 403
    user["approved"] = True
    assert _post(f"{base}/api/cli/logout", {}, token)[0] == 200
    assert _post(f"{base}/api/cli/usage", {"records": [{"model": "m"}]}, token)[0] == 401
    assert _post(f"{base}/api/cli/usage", {"records": [{"model": "m"}]})[0] == 401
    assert db.usage.docs == []


def test_token_for_another_app_is_refused(site, monkeypatch):
    base, db = site
    monkeypatch.setattr(cli_api, "_fetch_google", lambda url, headers=None: {**GOOGLE_PROFILE, "aud": "other"})
    assert _login(base)[0] == 401
    assert db.users.docs == []


def test_owner_email_is_approved_automatically(site, monkeypatch):
    base, _db = site
    monkeypatch.setenv("ADMIN_EMAILS", "Ada@Example.com")
    status, body = _login(base)
    assert status == 200 and body["approved"] is True


def test_without_mongodb_nothing_is_accepted(site, monkeypatch):
    import server

    base, _db = site
    monkeypatch.setattr(server, "mongo_db", None)
    assert _login(base)[0] == 503
