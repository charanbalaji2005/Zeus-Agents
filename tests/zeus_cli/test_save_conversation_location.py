"""Tests for /save — the conversation snapshot slash command.

Regression: the old implementation wrote ``zeus_conversation_<ts>.json``
to the current working directory (CWD). Users who ran /save expected the
file to be discoverable via ``zeus sessions browse``, but CWD-resident
snapshots are not indexed in the state DB and are generally invisible.
The fix writes snapshots under ``~/.zeus/sessions/saved/`` and prints
the absolute path plus the resume hint for the live session.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def zeus_home(tmp_path, monkeypatch):
    home = tmp_path / ".zeus"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("ZEUS_HOME", str(home))
    # Clear any cached zeus_home computation
    import zeus_constants
    if hasattr(zeus_constants, "_zeus_home_cache"):
        zeus_constants._zeus_home_cache = None
    return home


def _make_stub_cli(history):
    """Build a minimal object exposing just what save_conversation uses."""
    return SimpleNamespace(
        conversation_history=history,
        model="test-model",
        session_id="20260101_120000_abc123",
        session_start=datetime(2026, 1, 1, 12, 0, 0),
    )


def test_save_conversation_writes_under_zeus_home(zeus_home, tmp_path, monkeypatch, capsys):
    """Snapshot must land under ~/.zeus/sessions/saved/, not CWD."""
    # Change CWD to a different directory to prove the file does NOT go there.
    work = tmp_path / "somewhere-else"
    work.mkdir()
    monkeypatch.chdir(work)

    # Import fresh to pick up the ZEUS_HOME fixture
    for mod in [m for m in sys.modules if m.startswith("cli") or m == "zeus_constants"]:
        sys.modules.pop(mod, None)

    import cli

    stub = _make_stub_cli([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])

    # Call the unbound method against our stub.
    cli.ZeusCLI.save_conversation(stub, "/save json")

    # File must NOT be in CWD
    cwd_leak = list(work.glob("zeus_conversation_*.json"))
    assert not cwd_leak, f"snapshot leaked to CWD: {cwd_leak}"

    # File MUST be under ~/.zeus/sessions/saved/
    saved_dir = zeus_home / "sessions" / "saved"
    assert saved_dir.is_dir(), "expected saved/ subdirectory to be created"
    files = list(saved_dir.glob("zeus_conversation_*.json"))
    assert len(files) == 1, files

    payload = json.loads(files[0].read_text())
    assert payload["model"] == "test-model"
    # /save now emits the canonical export_session shape: the session id
    # lives under "id" (was "session_id" in the legacy snapshot format).
    assert payload["id"] == "20260101_120000_abc123"
    assert payload["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    # User-facing message must include the absolute path AND the resume hint.
    out = capsys.readouterr().out
    assert str(files[0]) in out, out
    assert "zeus --resume 20260101_120000_abc123" in out, out


def test_save_conversation_empty_history_does_nothing(zeus_home, capsys):
    for mod in [m for m in sys.modules if m.startswith("cli") or m == "zeus_constants"]:
        sys.modules.pop(mod, None)
    import cli

    stub = _make_stub_cli([])
    cli.ZeusCLI.save_conversation(stub, "/save json")

    saved_dir = zeus_home / "sessions" / "saved"
    assert not saved_dir.exists() or not list(saved_dir.iterdir())
    out = capsys.readouterr().out
    assert "No conversation to save" in out




def test_save_conversation_bad_format_shows_usage(zeus_home, capsys):
    for mod in [m for m in sys.modules if m.startswith("cli") or m == "zeus_constants"]:
        sys.modules.pop(mod, None)
    import cli

    stub = _make_stub_cli([{"role": "user", "content": "hi"}])
    cli.ZeusCLI.save_conversation(stub, "/save pdf")

    saved_dir = zeus_home / "sessions" / "saved"
    assert not saved_dir.exists() or not list(saved_dir.iterdir())
    out = capsys.readouterr().out
    assert "Usage:" in out
