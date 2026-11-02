"""`zeus login` only succeeds for accounts the Zeus Agents owner approved, and activity sharing is
opt-in per category."""

import json
from unittest.mock import patch

import pytest

from zeus_cli import auth_google_account as ga


def test_approved_account_returns_the_terminal_token():
    calls = []

    def post(url, payload, token=""):
        calls.append((url, payload))
        return 200, {"approved": True, "token": "zat_abc"}

    assert ga.register_with_portal("https://zeus.example", "credential", "gtok", post=post) == "zat_abc"
    assert calls == [("https://zeus.example/api/cli/login", {"kind": "credential", "token": "gtok"})]


@pytest.mark.parametrize("status, body, message", [
    (403, {"approved": False}, "waiting for approval"),
    (0, {"error": "connection refused"}, "Could not reach"),
    (503, {"error": "The Zeus Agents database is not connected."}, "database is not connected"),
    (200, {"approved": False}, "refused"),
])
def test_anything_but_an_approved_grant_fails_the_sign_in(status, body, message):
    with pytest.raises(ga.GoogleSignInError, match=message):
        ga.register_with_portal("https://zeus.example", "credential", "gtok",
                                post=lambda *a, **k: (status, body))


def test_unapproved_account_is_not_saved(monkeypatch):
    def fake_sign_in(portal_url, client_id, *, verify, **kwargs):
        return verify("credential", "gtok", client_id)

    monkeypatch.setattr(ga, "run_browser_sign_in", fake_sign_in)
    monkeypatch.setattr(ga, "verify_google_token", lambda *a, **k: {"email": "ada@example.com", "name": "Ada"})
    monkeypatch.setattr(ga, "post_json", lambda *a, **k: (403, {"approved": False}))
    monkeypatch.setattr(ga, "account_settings", lambda: ("https://zeus.example", "cid"))

    with pytest.raises(SystemExit):
        ga.login_command(type("Args", (), {"status": False, "sign_out": False, "sharing": False})())
    assert ga.load_account() is None


@pytest.mark.parametrize("answers, plugin_enabled", [((True, False), True), ((False, False), False)])
def test_sharing_choice_is_saved_per_category(answers, plugin_enabled):
    from zeus_cli.config import load_config

    replies = iter(answers)
    with patch("sys.stdin.isatty", return_value=True), \
            patch("zeus_cli.plugins_cmd.cmd_enable") as enable:
        choice = ga.offer_data_sharing(ask=lambda question: next(replies))

    assert choice == {"usage": answers[0], "conversations": answers[1]}
    assert load_config()["account"]["sync"] == choice
    assert enable.called is plugin_enabled


def test_without_a_terminal_nothing_is_shared():
    from zeus_cli.config import load_config

    with patch("sys.stdin.isatty", return_value=False), patch("zeus_cli.plugins_cmd.cmd_enable") as enable:
        assert ga.offer_data_sharing(ask=lambda q: True) == {"usage": False, "conversations": False}
    assert load_config()["account"]["sync"] == {"usage": False, "conversations": False}
    enable.assert_not_called()


def test_sign_out_revokes_the_terminal_token_on_the_server(monkeypatch):
    ga.save_account({"email": "ada@example.com", "name": "Ada", "token": "zat_abc"})
    calls = []
    monkeypatch.setattr(ga, "account_settings", lambda: ("https://zeus.example", "cid"))
    monkeypatch.setattr(ga, "post_json", lambda url, payload, token="": calls.append((url, token)) or (200, {}))

    ga._sign_out()

    assert calls == [("https://zeus.example/api/cli/logout", "zat_abc")]
    assert ga.load_account() is None
    assert not ga.account_path().exists()
    assert json.dumps(calls)  # the token went only to the logout call
