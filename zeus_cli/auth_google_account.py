"""``zeus login``: sign this terminal in with a Zeus Agents Google account.

The browser half lives on the Zeus Agents landing page, which owns the Google OAuth 2.0 web
client. ``zeus login`` opens that page with a one-time loopback port and ``state``; after Google
sign-in the page POSTs the Google token to ``http://127.0.0.1:<port>/callback``.

The page is never trusted: before anything is saved the CLI asks Google (``tokeninfo``) whether
the token was issued to *our* client id for a verified email. A token minted for another app, an
expired one, or a POST without the one-time ``state`` is rejected. No client secret is involved,
and the Google token itself is not stored — only the verified profile.
"""

from __future__ import annotations

import hmac
import html
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

from zeus_constants import get_zeus_home

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
# GSI "Sign in with Google" yields an ID token (``credential``); the token client used by the
# page's "Continue with Google" button yields an ``access_token``. Both verify via tokeninfo.
TOKEN_KINDS = ("credential", "access_token")
_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
_HTTP_TIMEOUT_SECONDS = 15
_MAX_CALLBACK_BYTES = 64 * 1024

_RESULT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Zeus Agents</title></head>
<body style="margin:0;height:100vh;display:grid;place-items:center;background:#111;color:#eee;
font-family:system-ui,sans-serif"><div style="text-align:center;max-width:28rem;padding:1rem">
<h2>{title}</h2><p>{body}</p></div></body></html>"""


class GoogleSignInError(Exception):
    """Sign-in failed; the message is safe to show the user."""


def account_path() -> Path:
    return get_zeus_home() / "account.json"


def load_account() -> dict[str, Any] | None:
    from utils import read_json_or_empty

    data = read_json_or_empty(account_path())
    return data if data.get("email") else None


def save_account(account: dict[str, Any]) -> None:
    from utils import atomic_json_write

    atomic_json_write(account_path(), account, mode=0o600)


def account_settings() -> tuple[str, str]:
    """``(portal_url, google_client_id)`` from the ``account`` section of config.yaml."""
    from zeus_cli.config import load_config

    section = load_config().get("account") or {}
    return str(section.get("portal_url") or "").rstrip("/"), str(section.get("google_client_id") or "")


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GoogleSignInError(f"Google rejected the sign-in token (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleSignInError(f"Could not reach Google to verify the sign-in: {exc}") from exc
    if not isinstance(data, dict):
        raise GoogleSignInError("Google returned an unexpected verification response.")
    return data


def verify_google_token(
    kind: str, token: str, client_id: str, *,
    fetch: Callable[..., dict[str, Any]] = _fetch_json, now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Ask Google about *token* and return the verified account, or raise GoogleSignInError."""
    if kind not in TOKEN_KINDS:
        raise GoogleSignInError("The sign-in page sent an unsupported token type.")
    param = "id_token" if kind == "credential" else "access_token"
    info = fetch(f"{TOKENINFO_URL}?{urllib.parse.urlencode({param: token})}")
    if not client_id or (info.get("aud") or info.get("azp")) != client_id:
        raise GoogleSignInError("This Google token was not issued for Zeus Agents (client id mismatch).")
    if kind == "credential" and info.get("iss") not in _GOOGLE_ISSUERS:
        raise GoogleSignInError("This ID token was not issued by Google.")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        raise GoogleSignInError("Your Google account has no verified email address.")
    if int(info.get("exp") or 0) <= now():
        raise GoogleSignInError("The Google sign-in already expired; run `zeus login` again.")
    profile = info if kind == "credential" else fetch(USERINFO_URL, {"Authorization": f"Bearer {token}"})
    if profile.get("sub") != info.get("sub"):
        raise GoogleSignInError("Google returned a profile for a different account.")
    return {
        "provider": "google",
        "email": info["email"],
        "name": profile.get("name") or info["email"],
        "picture": profile.get("picture"),
        "sub": info.get("sub"),
        "signed_in_at": int(now()),
    }


class _CallbackServer(HTTPServer):
    """One-shot loopback receiver; ``on_token`` verifies, ``outcome`` holds the result."""

    def __init__(self, expected_state: str, on_token: Callable[[str, str], dict[str, Any]]):
        super().__init__(("127.0.0.1", 0), _CallbackHandler)
        self.expected_state = expected_state
        self.on_token = on_token
        self.outcome: dict[str, Any] | GoogleSignInError | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if urllib.parse.urlsplit(self.path).path != "/callback":
            return self._reply(404, "Not found", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_CALLBACK_BYTES:
            return self._reply(413, "Request too large", "")
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        state = form.get("state", [""])[0]
        if not hmac.compare_digest(state.encode(), self.server.expected_state.encode()):
            return self._reply(400, "Sign-in link expired", "Run <code>zeus login</code> again in your terminal.")
        kind, token = next(((k, form[k][0]) for k in TOKEN_KINDS if form.get(k, [""])[0]), ("", ""))
        try:
            account = self.server.on_token(kind, token)
        except GoogleSignInError as exc:
            self.server.outcome = exc
            return self._reply(400, "Sign-in failed", html.escape(str(exc)))
        self.server.outcome = account
        self._reply(200, "Terminal connected", f"Signed in as {html.escape(account['email'])}. "
                    "You can close this tab and return to your terminal.")

    def _reply(self, status: int, title: str, body: str) -> None:
        page = _RESULT_PAGE.format(title=html.escape(title), body=body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - keep tokens out of stderr
        return


def sign_in_url(portal_url: str, port: int, state: str) -> str:
    return f"{portal_url}/?{urllib.parse.urlencode({'zeus_cli_port': port, 'zeus_cli_state': state})}"


def run_browser_sign_in(
    portal_url: str, client_id: str, *, open_browser: bool = True, timeout: float = 300.0,
    verify: Callable[..., dict[str, Any]] = verify_google_token,
) -> dict[str, Any]:
    """Open the sign-in page and block until it hands back a verified Google account."""
    server = _CallbackServer(secrets.token_urlsafe(32), lambda kind, token: verify(kind, token, client_id))
    try:
        url = sign_in_url(portal_url, server.server_address[1], server.expected_state)
        print("Sign in with Google to connect this terminal:")
        print(f"  {url}")
        if open_browser:
            webbrowser.open(url)
        deadline = time.monotonic() + timeout
        while server.outcome is None and time.monotonic() < deadline:
            server.timeout = max(0.05, min(1.0, deadline - time.monotonic()))
            server.handle_request()
    finally:
        server.server_close()
    if server.outcome is None:
        raise GoogleSignInError(f"No sign-in received within {int(timeout)}s; run `zeus login` again.")
    if isinstance(server.outcome, GoogleSignInError):
        raise server.outcome
    return server.outcome


def _print_status() -> None:
    account = load_account()
    if account:
        print(f"Signed in as {account.get('name')} <{account['email']}> (Google)")
    else:
        print("Not signed in. Run `zeus login` to connect this terminal.")


def _sign_out() -> None:
    path = account_path()
    if path.exists():
        path.unlink()
        print("Signed out of Zeus Agents.")
    else:
        print("Not signed in.")


def login_command(args) -> None:
    """``zeus login`` handler: Google sign-in, ``--status`` or ``--sign-out``."""
    if getattr(args, "status", False):
        return _print_status()
    if getattr(args, "sign_out", False):
        return _sign_out()
    portal_url, client_id = account_settings()
    portal_url = (getattr(args, "portal_url", None) or portal_url).rstrip("/")
    if not portal_url or not client_id:
        print("Set account.portal_url and account.google_client_id in config.yaml first "
              "(`zeus config set account.portal_url https://...`).")
        raise SystemExit(1)
    try:
        account = run_browser_sign_in(portal_url, client_id, open_browser=not getattr(args, "no_browser", False),
                                      timeout=float(getattr(args, "timeout", 300.0)))
    except GoogleSignInError as exc:
        print(f"Sign-in failed: {exc}")
        raise SystemExit(1) from None
    save_account(account)
    print(f"Signed in as {account['name']} <{account['email']}>")
