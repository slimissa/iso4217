"""
Tests for hostile input to tools/validate.py (v1.8.5, F10).

Before the fix, each of these ended in a Python traceback with exit 1, the code that means "the check found a
problem": deep nesting (RecursionError), a huge integer (ValueError), invalid UTF-8 (UnicodeDecodeError) and a
non-object root (AttributeError). The contract now: exit 2, a "FATAL: <file>: <reason>" line on stderr naming the
file, and no traceback. Each case runs the tool as a subprocess.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import validate as V  # noqa: E402

VALIDATE = PROJECT_ROOT / "tools" / "validate.py"


def _run(registry: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VALIDATE), "--registry", str(registry), *extra],
                          capture_output=True, text=True, timeout=120)


def _assert_clean_fatal(r: subprocess.CompletedProcess, path: Path, reason: str) -> None:
    assert r.returncode == 2, f"exit {r.returncode}\n{r.stdout}\n{r.stderr[-400:]}"
    assert "Traceback" not in r.stderr, r.stderr[-400:]
    assert r.stderr.startswith("FATAL: "), r.stderr
    assert path.name in r.stderr, "the message must name the file"
    assert reason in r.stderr, f"expected {reason!r} in {r.stderr!r}"


def _write(tmp_path: Path, name: str, content: bytes | str) -> Path:
    p = tmp_path / name
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return p


def test_deep_nesting_exits_2_not_with_a_recursion_traceback(tmp_path):
    p = _write(tmp_path, "deep.json", "[" * 100000 + "]" * 100000)
    _assert_clean_fatal(_run(p), p, "nested too deeply")


def test_a_huge_integer_exits_2_on_every_interpreter(tmp_path):
    p = _write(tmp_path, "bigint.json", '{"a": ' + "9" * 5000 + "}")
    _assert_clean_fatal(_run(p), p, "integer literal with 5000 digits")


def test_a_negative_huge_integer_is_counted_without_its_sign(tmp_path):
    p = _write(tmp_path, "negint.json", '{"a": -' + "9" * 101 + "}")
    _assert_clean_fatal(_run(p), p, "101 digits")


def test_invalid_utf8_exits_2(tmp_path):
    p = _write(tmp_path, "bad8.json", b'{"a": "\xff"}')
    _assert_clean_fatal(_run(p), p, "not valid UTF-8")


@pytest.mark.parametrize("root, kind", [
    ("[]", "an array"), ('"x"', "a string"), ("42", "a number"), ("1.5", "a number"),
    ("null", "null"), ("true", "a boolean"),
])
def test_a_non_object_root_exits_2(tmp_path, root, kind):
    p = _write(tmp_path, "root.json", root)
    _assert_clean_fatal(_run(p), p, f"top-level value is {kind}, not an object")


def test_invalid_json_still_names_the_file_and_the_position(tmp_path):
    p = _write(tmp_path, "broken.json", '{"a": ')
    r = _run(p)
    _assert_clean_fatal(r, p, "invalid JSON at line 1 column")


def test_a_missing_registry_is_still_exit_2(tmp_path):
    r = _run(tmp_path / "absent.json")
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_the_schema_file_gets_the_same_treatment(tmp_path):
    reg = tmp_path / "iso4217.json"
    reg.write_bytes((PROJECT_ROOT / "iso4217.json").read_bytes())
    schema = _write(tmp_path, "schema.json", "[" * 100000 + "]" * 100000)
    _assert_clean_fatal(_run(reg, "--schema", str(schema)), schema, "nested too deeply")


def test_the_integer_limit_is_exactly_the_constant(tmp_path):
    p = _write(tmp_path, "edge.json", '{"a": ' + "9" * V.MAX_INTEGER_DIGITS + "}")
    assert V._parse_file(p) == {"a": int("9" * V.MAX_INTEGER_DIGITS)}
    p2 = _write(tmp_path, "over.json", '{"a": ' + "9" * (V.MAX_INTEGER_DIGITS + 1) + "}")
    with pytest.raises(SystemExit) as exc:
        V._parse_file(p2)
    assert exc.value.code == 2
