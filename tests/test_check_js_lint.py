"""
Tests for tools/check_js_lint.sh (v1.9.1, P5-05). The script is driven with a stub `npm` first on PATH,
so the exit codes are tested without the network and without eslint.

0 clean, 1 lint problems, 2 no package.json, 3 npm missing or `npm install` failed.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "tools" / "check_js_lint.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required")

STUB = """#!/bin/sh
case "$1" in
  install) echo "stub: install"; exit ${STUB_INSTALL:-0} ;;
  run)     echo "stub: lint output"; exit ${STUB_LINT:-0} ;;
esac
exit 99
"""


def build(tmp_path: Path, with_package: bool = True) -> Path:
    root = tmp_path / "proj"
    (root / "tools").mkdir(parents=True)
    (root / "wrappers" / "javascript").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools" / "check_js_lint.sh")
    if with_package:
        (root / "wrappers" / "javascript" / "package.json").write_text("{}", encoding="utf-8")
    return root


def tool_path(tmp_path: Path, with_npm: bool) -> str:
    """A PATH holding only what the script needs, plus a stub npm when asked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("dirname", "tail", "cat"):
        found = shutil.which(name)
        if found and not (bin_dir / name).exists():
            (bin_dir / name).symlink_to(found)
    if with_npm:
        npm = bin_dir / "npm"
        npm.write_text(STUB, encoding="utf-8")
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
    return str(bin_dir)


def run(root: Path, path: str, **env) -> tuple[int, str]:
    full = {"PATH": path, **env}
    done = subprocess.run(
        [BASH, str(root / "tools" / "check_js_lint.sh")], capture_output=True, text=True, env=full, timeout=60
    )
    return done.returncode, done.stdout + done.stderr


def test_clean_lint_exits_0(tmp_path):
    code, out = run(build(tmp_path), tool_path(tmp_path, True))
    assert code == 0 and "OK: eslint clean" in out and "checked under" in out


def test_lint_problems_exit_1(tmp_path):
    code, out = run(build(tmp_path), tool_path(tmp_path, True), STUB_LINT="1")
    assert code == 1 and "FAIL: eslint reported problems" in out and "stub: lint output" in out


def test_a_failed_install_is_could_not_run_not_clean(tmp_path):
    code, out = run(build(tmp_path), tool_path(tmp_path, True), STUB_INSTALL="1")
    assert code == 3 and "NOT RUN" in out


def test_a_missing_npm_is_could_not_run_not_clean(tmp_path):
    code, out = run(build(tmp_path), tool_path(tmp_path, False))
    assert code == 3 and "npm is not installed" in out


def test_a_missing_package_json_exits_2(tmp_path):
    code, out = run(build(tmp_path, with_package=False), tool_path(tmp_path, True))
    assert code == 2 and "FATAL" in out
