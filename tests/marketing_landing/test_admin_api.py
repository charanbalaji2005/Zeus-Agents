"""The /admin control plane: nothing is reachable without ADMIN_SECRET, guessing gets locked out,
account actions drive the same approval/token gate ``zeus login`` enforces, and the console only
runs allowlisted commands.

Driven over real HTTP against the real ``server.py`` handler; only MongoDB and Google are stand-ins."""

import json
import threading
import types
import urllib.error
import urllib.request

import pytest

from marketing_landing import admin_api, cli_api

from .test_cli_api import CLIENT_ID, GOOGLE_PROFILE, _Collection

SECRET = "correct horse battery staple"


class _Cursor(list):
    def sort(self, key, direction):
        return _Cursor(sorted(self, key=lambda d: d.get(key) or "", reverse=direction < 0))

    def limit(self, n):
        return _Cursor(self[:n])


class _AdminCollection(_Collection):
    def find(self, query=None, projection=None):
        return _Cursor(dict(d) for d in self.docs if self._match(d, query or {}))

    def count_documents(self, query):
        return len(self.find(query))

    def update_many(self, query, update):
        hits = self.find(query)
        for doc in self.docs:
            if self._match(doc, query):
                doc.update(update.get("$set", {}))
        return types.SimpleNamespace(modified_count=len(hits))

    def delete_one(self, query):
        doc = self.find_one(query)
        if doc is not None:
            self.docs.remove(doc)


class _FakeMongo:
    def __init__(self):
        for name in ("users", "cli_tokens", "usage", "conversations"):
            setattr(self, name, _AdminCollection())

    def command(self, name):
        return {"ok": 1}


@pytest.fixture
def site(monkeypatch):
    import server

    db = _FakeMongo()
    monkeypatch.setattr(server, "mongo_db", db)
    monkeypatch.setattr(server, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(cli_api, "_fetch_google", lambda url, headers=None: dict(GOOGLE_PROFILE))
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    monkeypatch.setattr(admin_api, "_failures", {})
    httpd = server.ThreadingTCPServer(("127.0.0.1", 0), server.ZeusHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", db
    httpd.shutdown()
    httpd.server_close()


def _call(url, payload=None, secret=SECRET, token=""):
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Admin-Secret"] = secret
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _login(base):
    return _call(f"{base}/api/cli/login", {"kind": "access_token", "token": "google-token"}, secret="")


def test_admin_api_is_closed_without_a_configured_secret(site, monkeypatch):
    base, _ = site
    _login(base)
    monkeypatch.delenv("ADMIN_SECRET")
    for path in ("/api/admin/users", "/api/admin/overview", "/api/admin/logs"):
        assert _call(base + path, secret="anything")[0] == 503
    assert _call(f"{base}/api/admin/auth", {"secret": ""}, secret="")[0] == 503


def test_wrong_secret_is_refused_and_repeated_guessing_locks_the_client_out(site):
    base, _ = site
    _login(base)
    status, body = _call(f"{base}/api/admin/users", secret="guess")
    assert status == 401 and "users" not in body
    for _ in range(admin_api._MAX_FAILURES):
        _call(f"{base}/api/admin/auth", {"secret": "guess"}, secret="")
    assert _call(f"{base}/api/admin/users")[0] == 429
    assert any(e["level"] == "AUTH" for e in admin_api.logs()["entries"])


def test_approving_from_the_panel_lets_zeus_login_succeed(site):
    base, _ = site
    assert _login(base)[0] == 403  # new account waits for approval

    status, listing = _call(f"{base}/api/admin/users")
    assert status == 200 and [u["email"] for u in listing["users"]] == ["ada@example.com"]
    assert listing["users"][0]["approved"] is False

    assert _call(f"{base}/api/admin/users/action", {"action": "approve", "email": "ada@example.com",
                                                    "approved": True})[0] == 200
    status, body = _login(base)
    assert status == 200 and body["token"].startswith("zat_")
    assert _call(f"{base}/api/admin/users")[1]["users"][0]["active_tokens"] == 1


@pytest.mark.parametrize("action", ["revoke_tokens", "delete"])
def test_revoking_or_deleting_signs_the_terminal_out(site, action):
    base, db = site
    _login(base)
    _call(f"{base}/api/admin/users/action", {"action": "approve", "email": "ada@example.com", "approved": True})
    token = _login(base)[1]["token"]
    upload = {"records": [{"model": "m"}]}
    assert _call(f"{base}/api/cli/usage", upload, secret="", token=token)[0] == 200

    status, body = _call(f"{base}/api/admin/users/action", {"action": action, "email": "ada@example.com"})
    assert status == 200 and body["revoked"] == 1
    assert _call(f"{base}/api/cli/usage", upload, secret="", token=token)[0] == 401
    assert (db.users.find_one({"email": "ada@example.com"}) is None) == (action == "delete")


def test_console_runs_only_allowlisted_commands(site, monkeypatch):
    base, _ = site
    ran = []
    monkeypatch.setattr(admin_api, "run_cli", lambda args, timeout=30: ran.append(args) or
                        {"exit_code": 0, "timed_out": False, "stdout": "ok", "stderr": "", "duration_ms": 1})
    for command in ("zeus chat -q hi", "zeus doctor; env", "rm -rf /", "zeus config set model x"):
        assert _call(f"{base}/api/admin/exec", {"command": command})[0] == 400
    assert ran == []
    assert _call(f"{base}/api/admin/exec", {"command": "  zeus   doctor "}, secret="wrong")[0] == 401
    status, body = _call(f"{base}/api/admin/exec", {"command": "  zeus   doctor "})
    assert status == 200 and body["command"] == "zeus doctor" and ran == [["doctor"]]


def test_console_child_does_not_inherit_site_secrets(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pw@cluster")
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs["env"])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(admin_api.subprocess, "run", fake_run)
    admin_api.run_cli(["--version"])
    assert "MONGODB_URI" not in seen and "ADMIN_SECRET" not in seen


def test_tools_list_output_is_parsed_into_toolsets():
    text = ("Built-in toolsets (cli):\n"
            "  ✓ enabled  web  🔍 Web Search & Scraping\n"
            "  ✗ disabled  video  🎬 Video Analysis\n"
            "\n"
            "Plugin toolsets (cli):\n"
            "  ✗ disabled  a2a  🔌 A2A\n")
    assert admin_api.parse_tools(text) == [
        {"section": "Built-in toolsets (cli)", "name": "web", "label": "🔍 Web Search & Scraping", "enabled": True},
        {"section": "Built-in toolsets (cli)", "name": "video", "label": "🎬 Video Analysis", "enabled": False},
        {"section": "Plugin toolsets (cli)", "name": "a2a", "label": "🔌 A2A", "enabled": False},
    ]


def test_admin_page_is_served_unframeable(site):
    base, _ = site
    with urllib.request.urlopen(f"{base}/admin", timeout=10) as r:
        assert r.status == 200 and b"Control plane locked" in r.read()
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
