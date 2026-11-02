"""zeus-account-sync: nothing leaves the machine unless that category was opted in and the
terminal holds a token from an approved `zeus login`; failed uploads wait and retry."""

import importlib.util
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "zeus-account-sync"


@pytest.fixture
def sync():
    spec = importlib.util.spec_from_file_location("zeus_account_sync_under_test", _PLUGIN_DIR / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure(usage: bool, conversations: bool, token: str = "zat_abc"):
    from zeus_cli.auth_google_account import save_account
    from zeus_cli.config import load_config, save_config

    config = load_config()
    config["account"] = {**config.get("account", {}), "portal_url": "https://zeus.example",
                         "sync": {"usage": usage, "conversations": conversations}}
    save_config(config)
    if token:
        save_account({"email": "ada@example.com", "name": "Ada", "token": token})


def test_enabled_plugin_loads_through_discovery_and_registers_both_hooks():
    from zeus_cli.config import load_config, save_config
    from zeus_cli.plugins import PluginManager

    config = load_config()
    config["plugins"] = {**(config.get("plugins") or {}), "enabled": ["zeus-account-sync"]}
    save_config(config)
    manager = PluginManager()
    manager.discover_and_load(force=True)
    plugin = next(p for p in manager._plugins.values() if p.manifest.name == "zeus-account-sync")
    assert plugin.enabled and not plugin.error
    assert set(plugin.hooks_registered) == {"post_api_request", "post_llm_call"}


@pytest.mark.parametrize("usage, conversations, token, expected", [
    (True, False, "zat_abc", {"usage"}),
    (False, True, "zat_abc", {"conversations"}),
    (False, False, "zat_abc", set()),
    (True, True, "", set()),  # opted in but never got an approved token
])
def test_only_opted_in_categories_with_a_token_are_targeted(sync, usage, conversations, token, expected):
    _configure(usage, conversations, token)
    assert {kind for kind in ("usage", "conversations") if sync._target(kind)} == expected


def test_failed_upload_waits_in_the_outbox_and_goes_out_next_time(sync, tmp_path):
    outbox = tmp_path / sync.OUTBOX_NAME
    sent = []
    online = {"up": False}

    def post(url, payload, token):
        if not online["up"]:
            return 0, {"error": "offline"}
        sent.append((url.rsplit("/", 1)[-1], [r["n"] for r in payload["records"]], token))
        return 200, {"stored": len(payload["records"])}

    sync.deliver("https://zeus.example", "zat_abc", outbox, "usage", {"n": 1}, post=post)
    sync.deliver("https://zeus.example", "zat_abc", outbox, "conversations", {"n": 2}, post=post)
    assert outbox.exists() and sent == []

    online["up"] = True
    sync.deliver("https://zeus.example", "zat_abc", outbox, "usage", {"n": 3}, post=post)
    assert sent == [("usage", [1, 3], "zat_abc"), ("conversations", [2], "zat_abc")]
    assert not outbox.exists()


def test_rejected_upload_is_dropped_not_retried_forever(sync, tmp_path):
    outbox = tmp_path / sync.OUTBOX_NAME
    sync.deliver("https://zeus.example", "zat_abc", outbox, "usage", {"n": 1},
                 post=lambda *a: (403, {"error": "not approved"}))
    assert not outbox.exists()
