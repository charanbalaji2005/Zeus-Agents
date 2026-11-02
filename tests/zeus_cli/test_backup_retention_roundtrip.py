"""Tests for zeus backup retention (--keep) and the session-store import round trip."""

from argparse import Namespace
from pathlib import Path

import pytest

import zeus_cli.gateway_setup_service as service_setup
from tests.zeus_cli.test_backup import _make_zeus_tree


@pytest.fixture(autouse=True)
def _no_real_gateway_service(monkeypatch):
    """run_import() may start an existing gateway service post-restore; tests must
    never touch the host's systemd/launchd."""
    import zeus_cli.gateway as gateway_mod

    monkeypatch.setattr(service_setup, "ensure_gateway_service", lambda **kw: False)
    monkeypatch.setattr(gateway_mod, "_is_service_running", lambda: False)


def test_run_backup_prunes_older_default_named_zips_but_not_others(tmp_path, monkeypatch):
    """Hourly `zeus backup` callers accumulated 150+ zips; --keep bounds the default-named
    ones and leaves custom-named or foreign zips alone (#81317)."""
    from argparse import Namespace
    from zeus_cli import backup as backup_mod

    home = tmp_path / ".zeus"
    home.mkdir()
    (home / "config.yaml").write_text("model: x\n")
    monkeypatch.setenv("ZEUS_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for i in range(4):
        (tmp_path / f"zeus-backup-2026-01-0{i + 1}-000000.zip").write_bytes(b"old")
    (tmp_path / "my-archive.zip").write_bytes(b"mine")

    backup_mod.run_backup(Namespace(output=None, keep=2))

    kept = sorted(p.name for p in tmp_path.glob("zeus-backup-*.zip"))
    assert len(kept) == 2 and kept[0] == "zeus-backup-2026-01-04-000000.zip"
    assert (tmp_path / "my-archive.zip").exists()


def test_import_restores_the_session_store_with_its_message_uids(tmp_path, monkeypatch):
    """A backup ships state.db as a SQLite snapshot and an import puts it back byte-for-byte: the durable
    message ids come back with the rows."""
    from zeus_state import SessionDB

    zeus_home = tmp_path / ".zeus"
    zeus_home.mkdir()
    _make_zeus_tree(zeus_home)
    db = SessionDB(db_path=zeus_home / "state.db")
    try:
        db.create_session("s", "cli", model="m")
        db.append_message(session_id="s", role="user", content="q")
        db.append_message(session_id="s", role="assistant", content="a")
        uids = [m["message_uid"] for m in db.get_messages_as_conversation("s")]
    finally:
        db.close()
    assert len(uids) == 2 and all(len(u) == 32 for u in uids)

    monkeypatch.setenv("ZEUS_HOME", str(zeus_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from zeus_cli.backup import run_backup, run_import

    out_zip = tmp_path / "backup.zip"
    run_backup(Namespace(output=str(out_zip)))
    for name in ("state.db", "state.db-wal", "state.db-shm"):
        (zeus_home / name).unlink(missing_ok=True)
    assert run_import(Namespace(zipfile=str(out_zip), force=True)) is None

    restored = SessionDB(db_path=zeus_home / "state.db")
    try:
        assert [m["message_uid"] for m in restored.get_messages_as_conversation("s")] == uids
    finally:
        restored.close()
