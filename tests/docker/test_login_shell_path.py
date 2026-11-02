"""Login shells in the image keep Zeus' own dirs on PATH.

Debian's ``/etc/profile`` resets PATH for every login shell, so without
``/etc/profile.d/zeus.sh`` a ``bash -l`` (``docker exec <c> bash -l``, ssh, the
terminal tool's background ``bash -lic``) lost ``/opt/zeus/bin`` and bare
``zeus`` exited 127 (#56634).
"""
from __future__ import annotations

import subprocess


def test_login_shell_resolves_zeus_to_the_image_shim(built_image: str) -> None:
    r = subprocess.run(
        ["docker", "run", "--rm", "-u", "zeus", "--entrypoint", "bash", built_image,
         "-lc", 'echo "zeus=$(command -v zeus)"; echo "path=$PATH"'],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert r.returncode == 0, r.stderr
    lines = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    assert lines["zeus"] == "/opt/zeus/bin/zeus"
    entries = lines["path"].split(":")
    assert entries.index("/opt/zeus/bin") < entries.index("/opt/zeus/.venv/bin")
    assert entries.count("/opt/zeus/bin") == 1
