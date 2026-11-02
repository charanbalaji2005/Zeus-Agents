from types import SimpleNamespace
from unittest.mock import patch

import pytest

from zeus_cli.config import get_managed_system, is_managed, recommended_update_command
from zeus_cli.main import cmd_update
from tools.skills_hub_official import OptionalSkillSource


def test_recommended_update_command_defaults_to_zeus_update(monkeypatch):
    monkeypatch.delenv("ZEUS_MANAGED", raising=False)

    # Also short-circuit the .managed marker path — CI runners may have an
    # ambient ~/.zeus/.managed if a prior test left ZEUS_HOME pointing
    # somewhere with that marker, which would make get_managed_update_command()
    # return "Update your Nix flake input ..." instead of falling through to
    # detect_install_method().
    with patch("zeus_cli.config.get_managed_update_command", return_value=None), \
         patch("zeus_cli.config.detect_install_method", return_value="git"):
        assert recommended_update_command() == "zeus update"


@pytest.mark.parametrize("false_value", ["false", "0", "no", "off", "FALSE"])
def test_get_managed_system_false_values(monkeypatch, false_value):
    """An explicit opt-out is not a package manager named "false" (#12864)."""
    monkeypatch.setenv("ZEUS_MANAGED", false_value)

    assert get_managed_system() is None
    assert not is_managed()
    with patch("zeus_cli.config.detect_install_method", return_value="git"):
        assert recommended_update_command() == "zeus update"


def test_optional_skill_source_honors_env_override(monkeypatch, tmp_path):
    optional_dir = tmp_path / "optional-skills"
    optional_dir.mkdir()
    monkeypatch.setenv("ZEUS_OPTIONAL_SKILLS", str(optional_dir))

    source = OptionalSkillSource()

    assert source._optional_dir == optional_dir
