"""`zeus update` must self-heal the ``zeus-acp`` launcher.

ACP hosts (Zed, JetBrains, Buzz Desktop) resolve the agent by the
``zeus-acp`` command name on the login-shell PATH. Fresh installs get the
launcher from ``scripts/install.sh``; existing installs get it from
``_ensure_acp_launcher()`` during ``zeus update``.
"""

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from zeus_cli.update_cmd import _ensure_acp_launcher


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path / ".zeus"))
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    return bin_dir








@pytest.mark.require_symlinks
def test_does_not_follow_symlink_into_venv(fake_home, tmp_path):
    """#21454 failure mode: never write through a symlinked zeus-acp."""
    (fake_home / "zeus").write_text("#!/bin/sh\n", encoding="utf-8")
    console_script = tmp_path / "venv" / "bin" / "zeus-acp"
    console_script.parent.mkdir(parents=True)
    marker = "#!/usr/bin/env python\n# real console script\n"
    console_script.write_text(marker, encoding="utf-8")
    (fake_home / "zeus-acp").symlink_to(console_script)

    _ensure_acp_launcher()

    assert console_script.read_text(encoding="utf-8") == marker
    assert (fake_home / "zeus-acp").is_symlink()






def test_unwritable_bin_dir_is_skipped(fake_home):
    (fake_home / "zeus").write_text("#!/bin/sh\n", encoding="utf-8")
    if not hasattr(os, "geteuid"):
        # Windows: no geteuid, and chmod can't make a directory unwritable
        # anyway. _ensure_acp_launcher is an explicit no-op there, so the
        # assertion below still holds — vacuously.
        _ensure_acp_launcher()
        assert not (fake_home / "zeus-acp").exists()
        return
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write permissions")
    fake_home.chmod(0o555)
    try:
        _ensure_acp_launcher()  # must not raise
        assert not (fake_home / "zeus-acp").exists()
    finally:
        fake_home.chmod(0o755)
