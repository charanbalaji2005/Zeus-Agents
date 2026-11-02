"""``zeus login`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_login_parser(subparsers, *, cmd_login: Callable) -> None:
    """Attach ``zeus login``: sign this terminal in with a Zeus Agents Google account.

    Model-provider credentials stay under ``zeus auth`` / ``zeus model``; this is the account
    sign-in that the Zeus Agents website's "Connect your terminal" step points at.
    """
    login_parser = subparsers.add_parser(
        "login", help="Sign this terminal in with your Zeus Agents Google account",
        description="Opens the Zeus Agents sign-in page in your browser. Sign in with Google and "
            "this terminal is connected. Provider API keys are managed with `zeus auth`.")
    login_parser.add_argument("--status", action="store_true", help="Show the signed-in account")
    login_parser.add_argument("--sign-out", action="store_true", help="Forget the signed-in account")
    login_parser.add_argument(
        "--portal-url", default=None,
        help="Sign-in page to use instead of account.portal_url (e.g. http://localhost:8080)")
    login_parser.add_argument(
        "--no-browser", action="store_true", help="Print the sign-in link instead of opening a browser")
    login_parser.add_argument(
        "--timeout", type=float, default=300.0, help="Seconds to wait for the browser sign-in (default: 300)")
    login_parser.set_defaults(func=cmd_login)
