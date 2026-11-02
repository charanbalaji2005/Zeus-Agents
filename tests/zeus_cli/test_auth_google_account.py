"""`zeus login`: Google sign-in handed back from the Zeus Agents website over loopback.

Contracts: only a token Google confirms was issued to our client id, for a verified email, is
accepted; the loopback callback ignores posts without the one-time state; the verified account
(never the token) lands in ``$ZEUS_HOME/account.json``; ``account.*`` config reaches the reader.
"""

from __future__ import annotations

import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace

import pytest

from zeus_cli import auth_google_account as acct

CLIENT_ID = "test-client.apps.googleusercontent.com"
FUTURE = 4_102_444_800  # 2100-01-01


def _tokeninfo(**overrides):
    info = {"aud": CLIENT_ID, "sub": "123", "email": "zeus@example.com", "email_verified": "true",
            "exp": str(FUTURE), "iss": "https://accounts.google.com", "name": "Zeus User"}
    info.update(overrides)
    return info


def _fetcher(tokeninfo, userinfo=None):
    def fetch(url, headers=None):
        return userinfo if url.startswith(acct.USERINFO_URL) else tokeninfo
    return fetch


def test_id_token_for_our_client_is_accepted():
    account = acct.verify_google_token("credential", "jwt", CLIENT_ID, fetch=_fetcher(_tokeninfo()))
    assert (account["email"], account["sub"], account["provider"]) == ("zeus@example.com", "123", "google")
    assert "jwt" not in account.values()


def test_access_token_uses_userinfo_profile():
    info = _tokeninfo(aud=None, azp=CLIENT_ID, iss=None)
    profile = {"sub": "123", "name": "From Userinfo", "picture": "https://example.com/p.png"}
    account = acct.verify_google_token("access_token", "ya29", CLIENT_ID, fetch=_fetcher(info, profile))
    assert account["name"] == "From Userinfo"


@pytest.mark.parametrize("kind, info, userinfo", [
    ("credential", _tokeninfo(aud="someone-elses-app"), None),
    ("credential", _tokeninfo(email_verified="false"), None),
    ("credential", _tokeninfo(exp="1"), None),
    ("credential", _tokeninfo(iss="https://evil.example"), None),
    ("access_token", _tokeninfo(), {"sub": "999"}),
    ("password", _tokeninfo(), None),
])
def test_untrustworthy_tokens_are_rejected(kind, info, userinfo):
    with pytest.raises(acct.GoogleSignInError):
        acct.verify_google_token(kind, "tok", CLIENT_ID, fetch=_fetcher(info, userinfo))


def _post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_loopback_round_trip_requires_state(monkeypatch):
    opened: queue.Queue[str] = queue.Queue()
    monkeypatch.setattr(acct.webbrowser, "open", opened.put)
    seen = []

    def verify(kind, token, client_id):
        seen.append((kind, token, client_id))
        return {"email": "zeus@example.com", "name": "Zeus User"}

    result = {}
    worker = threading.Thread(target=lambda: result.update(account=acct.run_browser_sign_in(
        "https://portal.example", CLIENT_ID, timeout=30, verify=verify)))
    worker.start()
    url = urllib.parse.urlsplit(opened.get(timeout=10))
    query = dict(urllib.parse.parse_qsl(url.query))
    callback = f"http://127.0.0.1:{query['zeus_cli_port']}/callback"

    assert _post(callback, {"state": "forged", "credential": "jwt"}) == 400
    assert _post(callback, {"state": query["zeus_cli_state"], "credential": "jwt"}) == 200
    worker.join(timeout=10)

    assert result["account"]["email"] == "zeus@example.com"
    assert seen == [("credential", "jwt", CLIENT_ID)]


def test_login_status_and_sign_out_use_zeus_home(monkeypatch, capsys):
    monkeypatch.setattr(acct, "account_settings", lambda: ("https://portal.example", CLIENT_ID))
    monkeypatch.setattr(acct, "run_browser_sign_in", lambda *a, **k: {"email": "zeus@example.com", "name": "Zeus"})
    args = SimpleNamespace(status=False, sign_out=False, portal_url=None, no_browser=True, timeout=5)

    acct.login_command(args)
    assert acct.load_account()["email"] == "zeus@example.com"
    acct.login_command(SimpleNamespace(status=True))
    assert "zeus@example.com" in capsys.readouterr().out
    acct.login_command(SimpleNamespace(status=False, sign_out=True))
    assert acct.load_account() is None


def test_account_config_reaches_the_reader():
    from zeus_cli.config import get_config_path

    get_config_path().write_text(
        "account:\n  portal_url: https://zeus.example/\n  google_client_id: my-client\n", encoding="utf-8")
    assert acct.account_settings() == ("https://zeus.example", "my-client")
