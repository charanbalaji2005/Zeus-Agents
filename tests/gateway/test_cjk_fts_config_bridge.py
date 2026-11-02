"""config.yaml sessions.* bridges for the search-index knobs (config-authoritative).

Salvaged from PR #65544 (adapted: agent.fts_v2_read → sessions.cjk_fts).
"""

from __future__ import annotations

import os
from pathlib import Path

import zeus_yaml as yaml

import gateway.run as gateway_run


def _write_home(tmp_path: Path, sessions_cfg: dict, env_text: str = "") -> Path:
    zeus_home = tmp_path / ".zeus"
    zeus_home.mkdir()
    (zeus_home / "config.yaml").write_text(
        yaml.safe_dump({"sessions": sessions_cfg}), encoding="utf-8"
    )
    (zeus_home / ".env").write_text(env_text, encoding="utf-8")
    return zeus_home


def test_cjk_fts_bridged_from_config(tmp_path, monkeypatch):
    home = _write_home(tmp_path, {"cjk_fts": False})
    monkeypatch.setattr(gateway_run, "_zeus_home", home)
    monkeypatch.setenv("ZEUS_CJK_FTS", "1")
    gateway_run._reload_runtime_env_preserving_config_authority()
    assert os.environ["ZEUS_CJK_FTS"] == "False"


