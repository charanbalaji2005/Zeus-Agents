"""Termux's interactive fast launch keeps main's deferred-startup hints (main's ZeusCLI runs again)."""
import sys


def test_termux_fast_launch_defers_agent_startup_like_main(monkeypatch):
    from zeus_cli import main

    monkeypatch.setenv("TERMUX_VERSION", "fixture")
    monkeypatch.delenv("ZEUS_TERMUX_DISABLE_FAST_CLI", raising=False)
    monkeypatch.delenv("ZEUS_DEFER_AGENT_STARTUP", raising=False)
    monkeypatch.delenv("ZEUS_FAST_STARTUP_BANNER", raising=False)
    monkeypatch.setattr(sys, "argv", ["zeus", "--cli"])
    launches = []
    monkeypatch.setattr(main, "cmd_chat", launches.append)
    assert main._try_termux_fast_cli_launch()
    assert len(launches) == 1
    assert launches[0].compact is True
    import os
    assert os.environ["ZEUS_DEFER_AGENT_STARTUP"] == "1"
    assert os.environ["ZEUS_FAST_STARTUP_BANNER"] == "1"
