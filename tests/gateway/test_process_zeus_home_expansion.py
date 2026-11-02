"""Gateway identity-file readers expand a literal ``~`` in ZEUS_HOME.

``python -m gateway.run`` never passes through the CLI's ``normalize_zeus_home_env()``, so the
process-level home readers (PID/lock/status, lifecycle ledger, heartbeat) must expand on their own
or a fish-style ``ZEUS_HOME='~/.zeus'`` lands the identity files under ``<cwd>/~/.zeus``.
"""

from pathlib import Path

import pytest

from gateway import lifecycle_ledger, shutdown_watchdog, status


@pytest.mark.parametrize(
    "reader",
    [status._get_process_zeus_home, lifecycle_ledger._process_zeus_home,
     shutdown_watchdog._process_zeus_home],
    ids=["status", "lifecycle_ledger", "shutdown_watchdog"],
)
def test_process_home_readers_expand_literal_tilde(reader, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("ZEUS_HOME", "~/.x")
    assert reader() == tmp_path / ".x"
    assert reader().is_absolute()
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path / ".abs"))
    assert reader() == Path(tmp_path / ".abs")
