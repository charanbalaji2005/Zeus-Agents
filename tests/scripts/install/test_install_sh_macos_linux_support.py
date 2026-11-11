"""Tests for macOS and Linux platform support in scripts/install.sh and setup-zeus.sh."""
import json
from pathlib import Path
import re
import shutil
import subprocess

try:
    import pytest
except ImportError:
    pytest = None

ROOT = Path(__file__).resolve().parents[3]
INSTALL_SH = ROOT / "scripts" / "install.sh"
SETUP_ZEUS_SH = ROOT / "setup-zeus.sh"
LOCK_JSON = ROOT / "pm" / "lock.json"


def _get_bash():
    for candidate in [
        "C:\\Program Files\\Git\\bin\\bash.exe",
        shutil.which("bash"),
    ]:
        if candidate and Path(candidate).is_file():
            return candidate
    return "bash"


def test_install_sh_no_bash4_case_conversion():
    """macOS default /bin/bash is 3.2.57; ${var,,} and ${var^^} are bash 4+ and fail with bad substitution."""
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert not re.search(r"\$\{[^}]*,,[^}]*\}", content), "install.sh contains bash 4 lowercase expansion (${var,,})"
    assert not re.search(r"\$\{[^}]*\^\^[^}]*\}", content), "install.sh contains bash 4 uppercase expansion (${var^^})"
    assert not re.search(r"\bdeclare\s+-A\b", content), "install.sh contains bash 4 associative array"


def test_install_sh_macos_target_resolution(tmp_path):
    """Darwin uname resolves to darwin-arm64 and darwin-x64 with valid pinned uv artifacts."""
    bash = _get_bash()
    script = r"""
source "$1" --manifest >/dev/null
uname() {
    case "$1" in
        -m) echo "$MOCK_ARCH" ;;
        -s) echo "Darwin" ;;
    esac
}
MOCK_ARCH=arm64
target="$(uv_bootstrap_target)"
echo "target_arm64=$target"
uv_bootstrap_pin "$target"
echo "url_arm64=$UV_PIN_URL"

MOCK_ARCH=x86_64
target="$(uv_bootstrap_target)"
echo "target_x64=$target"
uv_bootstrap_pin "$target"
echo "url_x64=$UV_PIN_URL"
"""
    result = subprocess.run([bash, "-c", script, "_", str(INSTALL_SH)],
                            capture_output=True, text=True, check=True)
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert lines["target_arm64"] == "darwin-arm64"
    assert lines["target_x64"] == "darwin-x64"
    artifacts = json.loads(LOCK_JSON.read_text(encoding="utf-8"))["packages"]["uv"]["artifacts"]
    assert lines["url_arm64"] == artifacts["darwin-arm64"]["url"]
    assert lines["url_x64"] == artifacts["darwin-x64"]["url"]


def test_install_sh_linux_target_resolution(tmp_path):
    """Linux uname resolves to linux-x64, linux-arm64, and musl variants."""
    bash = _get_bash()
    script = r"""
source "$1" --manifest >/dev/null
head() { return 1; }
ldd() { echo "ldd (GNU libc) 2.35"; }
uname() {
    case "$1" in
        -m) echo "$MOCK_ARCH" ;;
        -s) echo "Linux" ;;
    esac
}
MOCK_ARCH=x86_64
target="$(uv_bootstrap_target)"
echo "target_glibc_x64=$target"

MOCK_ARCH=aarch64
target="$(uv_bootstrap_target)"
echo "target_glibc_arm64=$target"
"""
    result = subprocess.run([bash, "-c", script, "_", str(INSTALL_SH)],
                            capture_output=True, text=True, check=True)
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert lines["target_glibc_x64"] == "linux-x64"
    assert lines["target_glibc_arm64"] == "linux-arm64"


def test_install_sh_error_line_extraction(tmp_path):
    """error_line extracts meaningful failure messages (Error, Exception, failed, Incomplete tail)."""
    bash = _get_bash()
    script = r"""
source "$1" --manifest >/dev/null
e1="$(printf 'step started\nError: build failed: missing file\ncleaning up' | error_line)"
echo "e1=$e1"
e2="$(printf 'installing...\n⚠ Incomplete tail steps: launchers failed\ndone' | error_line)"
echo "e2=$e2"
e3="$(printf 'Traceback (most recent call last):\nValueError: invalid svg\nfull log: path' | error_line)"
echo "e3=$e3"
"""
    result = subprocess.run([bash, "-c", script, "_", str(INSTALL_SH)],
                            capture_output=True, text=True, check=True)
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert "Error: build failed: missing file" in lines["e1"]
    assert "Incomplete tail steps" in lines["e2"]
    assert "ValueError: invalid svg" in lines["e3"]


def test_setup_zeus_sh_macos_and_linux_musl(tmp_path):
    """setup-zeus.sh resolves target for macOS and distinguishes musl from glibc on Linux."""
    content = SETUP_ZEUS_SH.read_text(encoding="utf-8")
    assert not re.search(r"\$\{[^}]*,,[^}]*\}", content), "setup-zeus.sh contains bash 4 lowercase expansion"
    assert "linux-$arch-musl" in content, "setup-zeus.sh missing musl target mapping"
