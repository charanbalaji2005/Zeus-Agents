"""Resolve ZEUS_HOME for standalone skill scripts.

Skill scripts may run outside the Zeus process (system Python, nix env,
CI) where ``zeus_constants`` is not importable.  This module provides the
same ``get_zeus_home()`` contract without requiring it on ``sys.path``.

When ``zeus_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from zeus_constants import get_zeus_home
except (ModuleNotFoundError, ImportError):

    def get_zeus_home() -> Path:
        """Return the Zeus home directory (default: ``~/.zeus``)."""
        val = os.environ.get("ZEUS_HOME", "").strip()
        return Path(val) if val else Path.home() / ".zeus"
