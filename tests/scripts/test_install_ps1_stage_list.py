"""install.ps1's single authoritative stage list.

The $Stages table is the ONE list: -Manifest prints it and the no-flag ladder
runs it. Every dispatchable stage is a listed stage; anything else is refused.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.platforms("windows")

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_PS1 = REPO_ROOT / "scripts" / "install.ps1"


def _powershell() -> str:
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell is required")
    return powershell


def _run(tmp_path: Path, args: list[str]):
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALL_PS1), *args,
         "-ZeusHome", str(tmp_path / "zeus-home"),
         "-InstallDir", str(tmp_path / "install")],
        cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=180,
    )


def test_manifest_lists_the_ladder(tmp_path: Path) -> None:
    run = _run(tmp_path, ["-Manifest"])
    assert run.returncode == 0, run.stdout + run.stderr
    names = [s["name"] for s in json.loads(run.stdout)["stages"]]
    assert names.index("products") < names.index("complete") and names[-1] == "complete"


@pytest.mark.parametrize("stage", ["bogus", "desktop"])
def test_unlisted_stage_is_rejected(tmp_path: Path, stage: str) -> None:
    run = _run(tmp_path, ["-Stage", stage, "-Json"])
    assert run.returncode == 2
    frame = json.loads(run.stdout.splitlines()[-1])
    assert frame["ok"] is False and frame["stage"] == stage


def test_complete_stage_writes_pinned_install_marker(tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    commit = "a" * 40
    run = _run(tmp_path, ["-Stage", "complete", "-Commit", commit, "-Json"])
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout.splitlines()[-1])["ok"] is True
    marker = json.loads((install / ".zeus-bootstrap-complete").read_text(encoding="utf-8-sig"))
    assert marker["pinnedCommit"] == commit
    assert marker["pinnedBranch"] == "main"
