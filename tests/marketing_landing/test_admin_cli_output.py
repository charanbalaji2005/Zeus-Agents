"""The admin console shows CLI output as text, including the partial output of a command that
ran past its time limit (Python hands that back as bytes even under text=True)."""

import subprocess

from marketing_landing import admin_api


def test_timed_out_command_returns_readable_partial_output(monkeypatch):
    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"], output="┌ Zeus Doctor\n✓ Python".encode(), stderr=None)

    monkeypatch.setattr(admin_api.subprocess, "run", slow_run)
    result = admin_api.run_cli(["doctor"], timeout=7)

    assert result["timed_out"] is True and result["exit_code"] is None
    assert result["stdout"] == "┌ Zeus Doctor\n✓ Python"
    assert "no result within 7s" in result["stderr"]
    assert "b'" not in result["stdout"] + result["stderr"]


def test_slow_diagnostics_get_more_time_than_quick_commands():
    assert admin_api.COMMAND_TIMEOUTS["zeus doctor"] > admin_api.COMMAND_TIMEOUT
    assert set(admin_api.COMMAND_TIMEOUTS) <= set(admin_api.COMMANDS)


def test_real_cli_run_returns_text():
    result = admin_api.run_cli(admin_api.COMMANDS["zeus --version"], timeout=120)
    assert result["exit_code"] == 0, result["stderr"]
    assert isinstance(result["stdout"], str) and "Zeus Agents" in result["stdout"]
