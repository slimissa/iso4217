"""
Tests for the strict JSON loader of tools/validate.py (v1.8.5, F12).

json.loads keeps the last of two equal keys and accepts NaN, Infinity and -Infinity. The loader now rejects both,
and numbers that overflow to infinity, with exit 2 and a message that names the file. Each case runs the tool as a
subprocess against the real registry with one edit.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = PROJECT_ROOT / "tools" / "validate.py"
REAL = (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")


def _run(registry: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VALIDATE), "--registry", str(registry), *extra],
                          capture_output=True, text=True, timeout=120)


def _stage(tmp_path: Path, text: str, name: str = "iso4217.json") -> Path:
    shutil.copy(PROJECT_ROOT / "schema.json", tmp_path / "schema.json")
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _edit(pattern: str, replacement: str) -> str:
    text, n = re.subn(pattern, replacement, REAL, count=1)
    assert n == 1, f"the test fixture no longer finds {pattern!r} in iso4217.json"
    return text


def _assert_clean_fatal(r: subprocess.CompletedProcess, path: Path, reason: str) -> None:
    assert r.returncode == 2, f"exit {r.returncode}\n{r.stdout[-300:]}\n{r.stderr[-400:]}"
    assert "Traceback" not in r.stderr, r.stderr[-400:]
    assert path.name in r.stderr and reason in r.stderr, r.stderr


def test_control_the_unedited_registry_passes(tmp_path):
    r = _run(_stage(tmp_path, REAL))
    assert r.returncode == 0, r.stdout[-400:] + r.stderr


def test_a_duplicate_key_whose_last_value_is_valid_no_longer_passes(tmp_path):
    # json.loads keeps the last "version", so the bad first value used to be invisible and the file passed.
    text = _edit(r'"version": "(\d+\.\d+\.\d+)"', r'"version": "not-a-version", "version": "\1"')
    p = _stage(tmp_path, text)
    _assert_clean_fatal(_run(p), p, "duplicate key 'version'")


def test_a_duplicate_key_is_found_at_any_depth(tmp_path):
    p = _stage(tmp_path, '{"meta": {"x": 1, "x": 2}}')
    _assert_clean_fatal(_run(p), p, "duplicate key 'x'")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_constants_exit_2(tmp_path, constant):
    p = _stage(tmp_path, _edit(r'"minor_units": 2\b', f'"minor_units": {constant}'))
    _assert_clean_fatal(_run(p), p, constant)


@pytest.mark.parametrize("literal", ["1e999", "-1e999", "1" + "0" * 400 + ".5"])
def test_a_float_that_overflows_to_infinity_exits_2(tmp_path, literal):
    p = _stage(tmp_path, _edit(r'"minor_units": 2\b', f'"minor_units": {literal}'))
    _assert_clean_fatal(_run(p), p, "overflows to infinity")


def test_the_schema_file_is_loaded_strictly_too(tmp_path):
    reg = _stage(tmp_path, REAL)
    schema = tmp_path / "dup-schema.json"
    schema.write_text('{"type": "object", "type": "array"}', encoding="utf-8")
    _assert_clean_fatal(_run(reg, "--schema", str(schema)), schema, "duplicate key 'type'")
