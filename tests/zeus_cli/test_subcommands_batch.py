"""Smoke tests for the batch-extracted subcommand parser builders.

Each ``build_<group>_parser`` should attach its subcommand to a subparsers
group and wire ``func`` to the injected handler. These are intentionally
light — the byte-identical ``--help`` verification done at extraction time is
the real behavioral guarantee; this just guards against a module failing to
import or a builder raising.
"""

from __future__ import annotations

import argparse


from zeus_cli.subcommands.config import build_config_parser
from zeus_cli.subcommands.login import build_login_parser



def _h(name):
    def handler(args):  # pragma: no cover - identity only
        return name
    handler.__name__ = f"cmd_{name}"
    return handler






def test_config_get_unset_subcommands_parse():
    """`zeus config get/unset` parse key args (and --json for get)."""
    parser = argparse.ArgumentParser(prog="zeus")
    sub = parser.add_subparsers(dest="command")
    handler = _h("config")
    build_config_parser(sub, cmd_config=handler)

    ns = parser.parse_args(["config", "get", "terminal.backend", "--json"])
    assert ns.func is handler
    assert ns.config_command == "get"
    assert ns.key == "terminal.backend"
    assert ns.json is True

    ns = parser.parse_args(["config", "unset", "terminal.backend"])
    assert ns.func is handler
    assert ns.config_command == "unset"
    assert ns.key == "terminal.backend"




def test_login_subcommand_is_listed_and_parses_flags():
    """`zeus login` (Google account sign-in) is advertised and parses its flags."""
    parser = argparse.ArgumentParser(prog="zeus")
    sub = parser.add_subparsers(dest="command")
    handler = _h("login")
    build_login_parser(sub, cmd_login=handler)
    assert "login" in parser.format_help()

    ns = parser.parse_args(["login", "--portal-url", "http://localhost:8080", "--no-browser"])
    assert ns.func is handler
    assert ns.portal_url == "http://localhost:8080"
    assert ns.no_browser is True
    assert parser.parse_args(["login", "--status"]).status is True
    assert parser.parse_args(["login", "--sign-out"]).sign_out is True
