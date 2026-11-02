"""A CLI ``restart`` must stamp the planned-restart marker itself.

The gateway writes ``.restart_pending.json`` only on an in-band restart (SIGUSR1 / pause-for-update).
``zeus gateway restart`` on Windows is ``stop()`` + ``start()`` — Windows has no SIGUSR1 — so
without a CLI writer the next boot reads a plain stop and never sends the "Gateway online" notice to
the configured home channels.
"""

from __future__ import annotations

import pytest

from gateway import run as gateway_run

MARKER = ".restart_pending.json"


@pytest.fixture
def zeus_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setattr(gateway_run, "_zeus_home", tmp_path)
    return tmp_path


def test_writer_stamps_the_marker_the_boot_pass_reads(zeus_home):
    """Writer and reader must agree on path and payload; a rename on either side fails here."""
    from gateway.restart_notice import write_planned_restart_marker

    assert gateway_run._planned_restart_notification_pending() is False

    write_planned_restart_marker(via_service=True, detached=False)

    assert (zeus_home / MARKER).exists()
    assert gateway_run._planned_restart_notification_pending() is True
