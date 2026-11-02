"""First-run "Connect what's on this computer": find logins and local model servers Zeus can
already use (Claude Code, Codex CLI, Ollama, LM Studio), let the user tick which to connect, make
one the default and keep the rest one `/model` away.

Every connector reuses the provider's own setup flow, so the credential rules (borrowed-login
opt-out, Codex token rotation, Claude Code refresh) stay in one place. Names from setup.py are
imported lazily per function so test patches on ``zeus_cli.setup`` take effect."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("zeus_cli.setup")

# Loopback probes: a closed port refuses at once, so a short timeout only bounds a hung server.
_LOCAL_PROBE_TIMEOUT = 1.0
_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"


@dataclass(frozen=True)
class Found:
    """One connectable source: ``key`` selects its connector, ``note`` is the checklist detail."""
    key: str
    label: str
    note: str
    base_url: str = ""
    models: tuple[str, ...] = ()
    tokens: dict = field(default_factory=dict, compare=False, hash=False)


def _detect_claude_code() -> Optional[Found]:
    # read_claude_code_credentials enforces auth.adopt_external_logins itself.
    from agent.anthropic_credentials import read_claude_code_credentials
    creds = read_claude_code_credentials()
    if not creds or not (creds.get("accessToken") or creds.get("refreshToken")):
        return None
    return Found("claude-code", "Claude (via Claude Code)", "uses your Claude Code login")


def _detect_codex() -> Optional[Found]:
    from agent.credential_sources import adopt_external_logins_enabled
    from zeus_cli.auth import _import_codex_cli_tokens
    if not adopt_external_logins_enabled():
        return None
    tokens = _import_codex_cli_tokens()
    if not (tokens and tokens.get("access_token") and tokens.get("refresh_token")):
        return None
    return Found("codex", "OpenAI Codex (via Codex CLI)", "imports your Codex CLI login", tokens=dict(tokens))


def _detect_ollama() -> Optional[Found]:
    from zeus_cli.models_local import _get_ollama_base_url, probe_ollama_local_models
    root = _get_ollama_base_url().rstrip("/").removesuffix("/v1")
    models = probe_ollama_local_models(root, timeout=_LOCAL_PROBE_TIMEOUT)
    if not models:  # unreachable, or running with nothing pulled yet
        return None
    return Found("ollama", "Ollama (local)", f"{len(models)} model(s) on this computer",
                 base_url=f"{root}/v1", models=tuple(models))


def _detect_lmstudio() -> Optional[Found]:
    from zeus_cli.models_local import probe_lmstudio_models
    models = probe_lmstudio_models(base_url=_LMSTUDIO_BASE_URL, timeout=_LOCAL_PROBE_TIMEOUT)
    if not models:
        return None
    return Found("lmstudio", "LM Studio (local)", f"{len(models)} model(s) loaded",
                 base_url=_LMSTUDIO_BASE_URL, models=tuple(models))


_DETECTORS: tuple[Callable[[], Optional[Found]], ...] = (
    _detect_claude_code, _detect_codex, _detect_ollama, _detect_lmstudio)


def detect_connections() -> list[Found]:
    """Everything connectable on this computer, in menu order."""
    found = []
    for detect in _DETECTORS:
        # Each probe reads another program's files or a local port; one malformed file or
        # rejecting server must not hide the others or abort setup.
        try:
            hit = detect()
        except Exception:
            logger.debug("connect detection %s failed", detect.__name__, exc_info=True)
            continue
        if hit:
            found.append(hit)
    return found


# ── Connectors: ``store`` keeps a non-default source usable from /model; ``activate`` makes it
# the default by running the provider's own model flow. ──────────────────────────────────────────

def _store_nothing(_found: Found) -> None:
    """Claude Code's login is read live every turn; nothing to persist."""


def _store_codex(found: Found) -> None:
    from zeus_cli.auth import _save_codex_tokens, get_codex_auth_status
    if not get_codex_auth_status().get("logged_in"):
        _save_codex_tokens(found.tokens, set_active=False)


def _store_ollama(found: Found) -> None:
    from zeus_cli.main_provider_setup import _save_custom_provider
    _save_custom_provider(found.base_url, model=found.models[0], name=found.label)


def _store_lmstudio(_found: Found) -> None:
    from zeus_cli.setup import print_info
    print_info("  LM Studio: choose it any time with `zeus model` → LM Studio.")


def _activate_claude_code(config: dict, _found: Found) -> None:
    from zeus_cli.model_setup_flows import _model_flow_anthropic
    _model_flow_anthropic(config)


def _activate_codex(config: dict, found: Found) -> None:
    from zeus_cli.model_setup_flows import _model_flow_openai_codex
    _store_codex(found)
    _model_flow_openai_codex(config)


def _activate_ollama(config: dict, found: Found) -> None:
    from zeus_cli.main_provider_setup import _save_custom_provider
    from zeus_cli.model_setup_flows_common import _persist_model
    from zeus_cli.model_setup_flows_custom import _pick_detected_model
    try:
        model = _pick_detected_model(list(found.models))
    except (KeyboardInterrupt, EOFError):
        model = ""
    if not model:
        print("No model chosen. Pick one later with `zeus model`.")
        return
    _persist_model(model, "custom", base_url=found.base_url)
    _save_custom_provider(found.base_url, model=model, name=found.label)
    print(f"Default model set to: {model} (via {found.label})")


def _activate_lmstudio(config: dict, _found: Found) -> None:
    from zeus_cli.model_setup_flows import _model_flow_api_key_provider
    _model_flow_api_key_provider(config, "lmstudio")


_CONNECTORS: dict[str, tuple[Callable[[Found], None], Callable[[dict, Found], None]]] = {
    "claude-code": (_store_nothing, _activate_claude_code),
    "codex": (_store_codex, _activate_codex),
    "ollama": (_store_ollama, _activate_ollama),
    "lmstudio": (_store_lmstudio, _activate_lmstudio),
}


def connect_mode_label(found: list[Found]) -> str:
    """The first-time menu row offered when something was detected."""
    names = ", ".join(f.label.split(" (")[0] for f in found)
    return f"Connect what's on this computer — found {names} (recommended)"


def _choose_default(picked: list[Found]) -> Found:
    from zeus_cli.setup import prompt_choice
    if len(picked) == 1:
        return picked[0]
    return picked[prompt_choice("Which one should Zeus use by default?", [f.label for f in picked], 0)]


def run_connect_setup(config: dict, zeus_home, found: list[Found]) -> None:
    """Connect the ticked sources, set the default model, then finish like Quick Setup. Nothing
    ticked falls back to the full provider picker, where the user logs in to any provider."""
    from zeus_cli.setup import _info, print_header, prompt_checklist, setup_model_provider
    from zeus_cli.setup_quick import _reload_config_into, finish_first_time_setup
    print_header("Connect what's on this computer", gap=True)
    rows = [f"{f.label} — {f.note}" for f in found]
    picked = [found[i] for i in prompt_checklist(
        "Connect these to Zeus (Space toggles, Enter confirms):", rows, list(range(len(found))))]
    if not picked:
        _info("Nothing selected — choose a provider and log in instead.", None)
        setup_model_provider(config)
    else:
        default = _choose_default(picked)
        for f in picked:
            if f is not default:
                _CONNECTORS[f.key][0](f)
        _CONNECTORS[default.key][1](config, default)
        # The flows saved through their own load/save cycle; don't clobber it below.
        _reload_config_into(config)
        if len(picked) > 1:
            _info(None, "Switch between them any time with /model in chat or `zeus model`.")
    finish_first_time_setup(config, zeus_home)
