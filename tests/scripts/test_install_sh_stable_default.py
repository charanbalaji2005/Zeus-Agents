"""The installer's channel choice decides where an install of the official repository lands.

No GitHub release is published yet, so a plain install follows main (as `zeus update` does
for an unconfigured checkout). The stable path stays reachable with an empty `--channel`,
which lets a release decide: a new or rerun install then lands on the latest stable release.
The official URL is redirected to a local origin and `curl` answers the release lookup.
"""
from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL = "https://github.com/charanbalaji2005/Zeus-Agents.git"

pytestmark = pytest.mark.platforms("posix")

# An empty channel: the release decides (stable for the official repository's main line).
RELEASE = ["--channel", ""]


def _git(cwd, *args, env=None):
    return subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env,
    ).stdout.strip()


@pytest.mark.parametrize("side,start,args,tagged,lands", [
    (False, None, [], True, "tip"),                     # default: main, no release lookup
    (False, None, RELEASE, True, "release"),            # fresh install: the release, not main's tip
    (False, None, ["--channel", "main"], True, "tip"),  # explicit opt-out: main's tip
    (False, "before", RELEASE, True, "release"),             # rerun behind the release: moves forward to it
    (False, "tip", RELEASE, True, "tip"),                    # rerun already containing it: never moves back
    (False, None, RELEASE, False, None),                     # release tag unreachable: fail, publish nothing
    (False, "before", RELEASE, False, "before"),             # ... a rerun keeps its checkout instead
    # The release cut on a release branch, main past the fork point (v0.22.2's shape): main moves
    # back only through `zeus update`, whose downgrade guard the installer cannot run.
    (True, "tip", RELEASE, True, "tip"),
    (True, "tip", ["--channel", "stable"], True, "tip"),
    (True, "before", RELEASE, True, "release"),
])
def test_install_lands_on_the_latest_stable_release(tmp_path, side, start, args, tagged, lands):
    origin, home, bin_dir = tmp_path / "origin", tmp_path / "home", tmp_path / "bin"
    install = home / ".zeus" / "zeus-agents"
    for d in (origin, home, bin_dir):
        d.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "before")
    if side:
        _git(origin, "checkout", "-q", "-b", "release/1.2")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "release")
    commits = {"before": _git(origin, "rev-parse", "HEAD~1"), "release": _git(origin, "rev-parse", "HEAD")}
    if tagged:
        _git(origin, "tag", "-a", "v1.2.3", "-m", "release")
    _git(origin, "checkout", "-q", "main")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "newer")
    commits["tip"] = _git(origin, "rev-parse", "HEAD")
    (home / ".gitconfig").write_text(f'[url "file://{origin}"]\n  insteadOf = {OFFICIAL}\n', encoding="utf-8")
    (bin_dir / "curl").write_text(
        '#!/bin/sh\ncase "$*" in *api.github.com*) printf \'{\\n  "tag_name": "v1.2.3",\\n}\\n\';; *) exit 22;; esac\n',
        encoding="utf-8")
    (bin_dir / "curl").chmod(0o755)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HOME": str(home), "NO_COLOR": "1",
           "GIT_CONFIG_NOSYSTEM": "1"}
    if start:
        install.parent.mkdir(parents=True)
        _git(tmp_path, "clone", "-q", OFFICIAL, str(install), env=env)
        _git(install, "checkout", "-q", "--detach", commits[start])

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "install.sh"), "--stage", "repository", "--dir", str(install),
         "--zeus-home", str(home / ".zeus"), "--non-interactive", *args],
        check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120, env=env,
    )

    if lands is None:
        assert result.returncode != 0 and not install.exists(), result.stdout + result.stderr
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(install, "rev-parse", "HEAD") == commits[lands], result.stdout + result.stderr
    assert _git(install, "status", "--porcelain") == "", result.stdout + result.stderr
