"""Regression for #68523 — one systemctl timeout must not abort fleet restarts.

On hosts with many profile-backed ``zeus-gateway*.service`` units,
``zeus update`` used to wrap the entire per-scope unit loop in a single
``except subprocess.TimeoutExpired``. A timeout on unit N skipped units
N+1…, leaving later gateways on pre-update in-memory modules while the
checkout on disk was already new (mixed-generation crashes).
"""

from __future__ import annotations

import subprocess

import pytest

from zeus_cli.update_cmd import _for_each_systemd_gateway_unit, _service_unit_supports_graceful_sigusr1_restart, _warn_incomplete_gateway_fleet_restart


def _list_units_stdout(names: list[str]) -> str:
    return "\n".join(f"{name}.service loaded active running" for name in names)


class TestFleetRestartTimeoutIsolation:
    def test_timeout_on_middle_unit_continues_remaining_units(self):
        units = [
            "zeus-gateway-xiaomo1",
            "zeus-gateway-xiaomo2",
            "zeus-gateway-xiaomo3",
            "zeus-gateway-xiaomo4",
            "zeus-gateway-xiaomo5",
            "zeus-gateway-xiaomo6",
            "zeus-gateway-xiaomo7",
            "zeus-gateway",
        ]
        restarted: list[str] = []
        failed: list[str] = []
        timeout_cmds: list = []

        def process_unit(svc_name: str) -> None:
            if svc_name == "zeus-gateway-xiaomo5":
                raise subprocess.TimeoutExpired(
                    cmd=["systemctl", "--user", "--no-ask-password", "restart", svc_name],
                    timeout=15,
                )
            restarted.append(svc_name)

        def on_unit_timeout(svc_name: str, exc: subprocess.TimeoutExpired) -> None:
            failed.append(svc_name)
            timeout_cmds.append(exc.cmd)

        _for_each_systemd_gateway_unit(
            _list_units_stdout(units),
            process_unit=process_unit,
            on_unit_timeout=on_unit_timeout,
        )

        assert failed == ["zeus-gateway-xiaomo5"]
        assert restarted == [
            "zeus-gateway-xiaomo1",
            "zeus-gateway-xiaomo2",
            "zeus-gateway-xiaomo3",
            "zeus-gateway-xiaomo4",
            "zeus-gateway-xiaomo6",
            "zeus-gateway-xiaomo7",
            "zeus-gateway",
        ]
        assert set(restarted) | set(failed) == set(units)
        assert timeout_cmds == [
            ["systemctl", "--user", "--no-ask-password", "restart", "zeus-gateway-xiaomo5"]
        ]

    def test_non_gateway_units_in_list_output_are_ignored(self):
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "zeus-gateway-coder.service loaded active running",
                    "not-a-service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["zeus-gateway-coder"]

    def test_zeus_serve_units_are_included(self):
        # #83438 — zeus update restarted zeus-gateway* units but left
        # zeus-serve* (the Desktop app's backend) on stale pre-update code.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "zeus-serve.service loaded active running",
                    "zeus-serve-work.service loaded active running",
                    "zeus-gateway.service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["zeus-serve", "zeus-serve-work", "zeus-gateway"]

    def test_zeus_dashboard_units_are_included(self):
        # #125297 — the same blind spot for the systemd-supervised dashboard: the
        # unit pass skipped zeus-dashboard*, so a successful update left the
        # dashboard on pre-update code with outcome "deferred" and nothing
        # restarted it. Reconciliation already credits zeus-dashboard{,-<profile>}
        # unit restarts; the pass must produce one.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "zeus-dashboard.service loaded active running",
                    "zeus-dashboard-work.service loaded active running",
                    "zeus-serve.service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["zeus-dashboard", "zeus-dashboard-work", "zeus-serve"]

    def test_zeus_dashboard_near_prefix_is_rejected(self):
        # Same strict shape on the dashboard side: a bare
        # ``startswith("zeus-dashboard")`` gate would also accept the
        # unrelated ``zeus-dashboardd.service``.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["zeus-dashboardd", "zeus-dashboard-work"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["zeus-dashboard-work"]

    def test_zeus_server_near_prefix_is_rejected(self):
        # Review on #83595: a bare ``startswith("zeus-serve")`` gate also
        # accepts the unrelated ``zeus-server.service``. Only the exact
        # base unit or the hyphenated profile family should pass.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["zeus-server"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == []

    def test_zeus_gateway_near_prefix_is_rejected(self):
        # Same strict shape on the gateway side: profile units are
        # ``zeus-gateway-<profile>``, so a hypothetical
        # ``zeus-gatewayd.service`` must not enter the restart path.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["zeus-gatewayd", "zeus-gateway-coder"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["zeus-gateway-coder"]


class TestGracefulSigusr1Eligibility:
    def test_gateway_units_are_eligible(self):
        assert _service_unit_supports_graceful_sigusr1_restart("zeus-gateway")
        assert _service_unit_supports_graceful_sigusr1_restart(
            "zeus-gateway-work"
        )

    def test_serve_units_are_not_eligible(self):
        # zeus-serve doesn't run gateway/run.py, so it never installs the
        # SIGUSR1 handler — sending it the signal would just terminate the
        # process (the default action) instead of draining gracefully.
        assert not _service_unit_supports_graceful_sigusr1_restart("zeus-serve")
        assert not _service_unit_supports_graceful_sigusr1_restart(
            "zeus-serve-work"
        )

    def test_process_errors_other_than_timeout_still_propagate(self):
        def process_unit(_svc_name: str) -> None:
            raise RuntimeError("not a timeout")

        with pytest.raises(RuntimeError, match="not a timeout"):
            _for_each_systemd_gateway_unit(
                _list_units_stdout(["zeus-gateway"]),
                process_unit=process_unit,
                on_unit_timeout=lambda *_: pytest.fail("timeout handler must not run"),
            )


class TestIncompleteFleetRestartWarning:
    def test_warns_with_exact_unrestarted_units(self, capsys):
        _warn_incomplete_gateway_fleet_restart(
            ["zeus-gateway-xiaomo5", "zeus-gateway-xiaomo6", "zeus-gateway-xiaomo5"]
        )
        out = capsys.readouterr().out
        assert "Update incomplete" in out
        assert out.count("zeus-gateway-xiaomo5") == 1
        assert "zeus-gateway-xiaomo6" in out
        assert "pre-update code" in out

