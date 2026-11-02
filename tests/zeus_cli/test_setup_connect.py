"""First-time "Connect what's on this computer": logins other tools already hold (Claude Code,
Codex CLI) and local model servers are found, offered first, and connected — one as the default,
the rest kept usable from /model."""

import base64
import json
import time
from argparse import Namespace
from unittest.mock import patch

import pytest

from zeus_cli import setup_connect
from zeus_cli.setup_connect import Found


def _jwt(exp: float) -> str:
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(exp)})}.sig"


@pytest.fixture
def codex_login(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    tokens = {"access_token": _jwt(time.time() + 3600), "refresh_token": "rt-demo"}
    (codex_home / "auth.json").write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    return tokens


@pytest.fixture
def claude_code_login(tmp_path, monkeypatch):
    claude_dir = tmp_path / "claude"
    claude_dir.mkdir()
    oauth = {"accessToken": "sk-ant-oat-demo", "refreshToken": "rt-demo",
             "expiresAt": int((time.time() + 3600) * 1000)}
    (claude_dir / ".credentials.json").write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))


def test_existing_claude_code_and_codex_logins_are_detected(claude_code_login, codex_login):
    assert setup_connect._detect_claude_code().key == "claude-code"
    codex = setup_connect._detect_codex()
    assert codex.key == "codex" and codex.tokens["refresh_token"] == "rt-demo"


def test_no_logins_means_nothing_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "none"))
    assert setup_connect._detect_claude_code() is None
    assert setup_connect._detect_codex() is None


def test_a_failing_probe_does_not_hide_the_others(monkeypatch):
    hit = Found("claude-code", "Claude (via Claude Code)", "uses your Claude Code login")

    def broken():
        raise ValueError("malformed auth file")

    monkeypatch.setattr(setup_connect, "_DETECTORS", (broken, lambda: hit, lambda: None))
    assert setup_connect.detect_connections() == [hit]


def _run_first_time_wizard(found, answer):
    from zeus_cli.setup import run_setup_wizard
    with patch("zeus_cli.setup.is_interactive_stdin", return_value=True), \
            patch("zeus_cli.setup.offer_agent_import", return_value=""), \
            patch("zeus_cli.setup_connect.detect_connections", return_value=found), \
            patch("zeus_cli.setup.prompt_choice", side_effect=answer), \
            patch("zeus_cli.setup_connect.run_connect_setup") as connect, \
            patch("zeus_cli.setup_quick._run_first_time_quick_setup") as quick, \
            patch("zeus_cli.setup._record_setup_completed"):
        run_setup_wizard(Namespace(non_interactive=False, section=None, reset=False,
                                   reconfigure=False, quick=False))
    return connect, quick


def test_first_run_offers_connect_first_when_something_is_found():
    found = [Found("claude-code", "Claude (via Claude Code)", "uses your Claude Code login")]
    menus = []

    def answer(question, choices, default=0, description=None):
        menus.append(choices)
        return default

    connect, quick = _run_first_time_wizard(found, answer)

    first_row, *others = menus[0]
    assert first_row.startswith("Connect what's on this computer") and "Claude" in first_row
    assert not any("(recommended)" in row for row in others)
    connect.assert_called_once()
    assert connect.call_args.args[2] == found
    quick.assert_not_called()


def test_first_run_without_anything_found_keeps_quick_setup_default():
    menus = []

    def answer(question, choices, default=0, description=None):
        menus.append(choices)
        return default

    connect, quick = _run_first_time_wizard([], answer)

    assert not any(row.startswith("Connect what's") for row in menus[0])
    connect.assert_not_called()
    quick.assert_called_once()


def test_connect_sets_default_and_keeps_the_others_usable(codex_login):
    """Ollama becomes the default model; the Codex CLI login is imported into Zeus without
    becoming the active provider, so /model can switch to it later."""
    from zeus_cli.auth import get_active_provider, get_codex_auth_status
    from zeus_cli.config import load_config

    ollama = Found("ollama", "Ollama (local)", "2 model(s)", base_url="http://localhost:11434/v1",
                   models=("llama3.2", "qwen3"))
    codex = Found("codex", "OpenAI Codex (via Codex CLI)", "imports your Codex CLI login", tokens=codex_login)
    config = load_config()

    with patch("zeus_cli.setup.prompt_checklist", return_value=[0, 1]), \
            patch("zeus_cli.setup.prompt_choice", return_value=0), \
            patch("zeus_cli.model_setup_flows_custom._pick_detected_model", return_value="qwen3"), \
            patch("zeus_cli.setup_quick.finish_first_time_setup") as finish:
        setup_connect.run_connect_setup(config, None, [ollama, codex])

    saved = load_config()
    assert saved["model"]["provider"] == "custom"
    assert saved["model"]["default"] == "qwen3"
    assert saved["model"]["base_url"] == "http://localhost:11434/v1"
    assert any(p.get("base_url") == "http://localhost:11434/v1" for p in saved.get("custom_providers") or [])
    assert get_codex_auth_status().get("logged_in")
    assert get_active_provider() != "openai-codex"
    assert config["model"]["default"] == "qwen3"  # caller's dict re-synced before the final save
    finish.assert_called_once()


def test_unticking_everything_falls_back_to_the_provider_login_picker():
    found = [Found("claude-code", "Claude (via Claude Code)", "uses your Claude Code login")]
    with patch("zeus_cli.setup.prompt_checklist", return_value=[]), \
            patch("zeus_cli.setup.setup_model_provider") as picker, \
            patch("zeus_cli.model_setup_flows._model_flow_anthropic") as anthropic, \
            patch("zeus_cli.setup_quick.finish_first_time_setup"):
        setup_connect.run_connect_setup({}, None, found)

    picker.assert_called_once()
    anthropic.assert_not_called()
