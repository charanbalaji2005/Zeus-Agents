"""Resolve ZEUS_HOME for standalone skill scripts.

Skill scripts may run outside the Zeus process (e.g. system Python,
nix env, CI) where ``zeus_constants`` is not importable.  This module
provides the same ``get_zeus_home()`` and ``display_zeus_home()``
contracts as ``zeus_constants`` without requiring it on ``sys.path``.

When ``zeus_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``zeus_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``ZEUS_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from zeus_constants import display_zeus_home
    from zeus_constants import get_zeus_home
except (ModuleNotFoundError, ImportError):

    def get_zeus_home() -> Path:
        """Return the Zeus home directory (default: ~/.zeus).

        Mirrors ``zeus_constants.get_zeus_home()``."""
        val = os.environ.get("ZEUS_HOME", "").strip()
        return Path(val) if val else Path.home() / ".zeus"

    def display_zeus_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``zeus_constants.display_zeus_home()``."""
        home = get_zeus_home()
        try:
            return "~/" + home.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(home)
