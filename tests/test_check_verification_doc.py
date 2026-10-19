"""
tools/check_verification_doc.py: exit codes under the convention in RELEASE_PATTERN.md.

0 clean, 1 placeholder found, 2 usage or nothing to check. (Until v1.8.3 "nothing to check" exited 3, the code
the convention keeps for "could not run".) The tool had no tests before this file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_verification_doc.py"
CLEAN = "# Verification\n" + "".join(f"line {i} of real content\n" for i in range(100))


def _run(*args: str):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=60)


def _root(tmp_path: Path, docs: dict[str, str]) -> Path:
    d = tmp_path / "docs"
    d.mkdir()
    for name, text in docs.items():
        (d / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_clean_doc_exits_0(tmp_path):
    r = _run(str(_root(tmp_path, {"v1.0.0-verification.md": CLEAN})))
    assert r.returncode == 0 and "clean" in r.stdout


@pytest.mark.parametrize("marker", ["TODO", "FIXME", "<paste the log>", "<the real line>"])
def test_a_placeholder_exits_1(tmp_path, marker):
    r = _run(str(_root(tmp_path, {"v1.0.0-verification.md": CLEAN + marker + "\n"})))
    assert r.returncode == 1 and "DIRTY" in r.stdout


def test_a_stub_that_is_too_short_exits_1(tmp_path):
    assert _run(str(_root(tmp_path, {"v1.0.0-verification.md": "# short\n"}))).returncode == 1


def test_a_root_without_a_docs_directory_exits_2(tmp_path):
    r = _run(str(tmp_path))
    assert r.returncode == 2 and "not found" in r.stderr


def test_a_docs_directory_without_verification_docs_exits_2(tmp_path):
    r = _run(str(_root(tmp_path, {"README.md": "x\n"})))
    assert r.returncode == 2 and "no docs/v*-verification.md" in r.stderr


def test_a_usage_error_exits_2():
    assert _run("--bogus").returncode == 2


def test_only_the_latest_doc_is_checked_unless_all_is_given(tmp_path):
    root = _root(tmp_path, {"v1.0.0-verification.md": CLEAN + "TODO\n", "v1.1.0-verification.md": CLEAN})
    assert _run(str(root)).returncode == 0
    assert _run(str(root), "--all").returncode == 1
