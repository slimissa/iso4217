"""
Tests for the schema-layer guard of tools/validate.py (v1.8.5, F11).

A check that cannot run must fail, not pass (RELEASE_PATTERN.md, operator-hygiene rule 7). validate.py used to
append a warning and exit 0 when schema.json was missing or the jsonschema package was absent. It now exits 2 or 3,
unless --no-schema asks for the layer to be skipped. Every case runs the tool as a subprocess: the exit code and
the absence of a traceback are the contract.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = PROJECT_ROOT / "tools" / "validate.py"

# Runs validate.py with `import jsonschema` made to fail, without touching the environment.
_BLOCK_JSONSCHEMA = (
    "import runpy, sys; sys.modules['jsonschema'] = None; sys.argv = sys.argv[1:]; "
    "runpy.run_path(sys.argv[0], run_name='__main__')"
)


def _stage(tmp_path: Path, *, schema: str | None = "real") -> Path:
    """A temp directory holding the real registry, and optionally a schema.json beside it."""
    shutil.copy(PROJECT_ROOT / "iso4217.json", tmp_path / "iso4217.json")
    if schema == "real":
        shutil.copy(PROJECT_ROOT / "schema.json", tmp_path / "schema.json")
    elif schema is not None:
        (tmp_path / "schema.json").write_text(schema, encoding="utf-8")
    return tmp_path / "iso4217.json"


def _run(*args: str, block_jsonschema: bool = False) -> subprocess.CompletedProcess:
    if block_jsonschema:
        cmd = [sys.executable, "-c", _BLOCK_JSONSCHEMA, str(VALIDATE), *args]
    else:
        cmd = [sys.executable, str(VALIDATE), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_control_the_real_registry_with_its_schema_still_passes(tmp_path):
    r = _run("--registry", str(_stage(tmp_path)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VALIDATION PASSED" in r.stdout and "SCHEMA_SKIPPED" not in r.stdout


def test_a_missing_default_schema_exits_2_and_does_not_pass(tmp_path):
    r = _run("--registry", str(_stage(tmp_path, schema=None)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "schema.json" in r.stderr and "--no-schema" in r.stderr
    assert "VALIDATION PASSED" not in r.stdout and "Traceback" not in r.stderr


def test_a_missing_explicit_schema_exits_2(tmp_path):
    r = _run("--registry", str(_stage(tmp_path)), "--schema", str(tmp_path / "nope.json"))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "nope.json" in r.stderr and "Traceback" not in r.stderr


def test_no_schema_skips_the_layer_on_purpose_and_says_so(tmp_path):
    r = _run("--registry", str(_stage(tmp_path, schema=None)), "--no-schema")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SCHEMA_SKIPPED" in r.stdout and "VALIDATION PASSED" in r.stdout


def test_no_schema_and_schema_together_are_a_usage_error(tmp_path):
    r = _run("--registry", str(_stage(tmp_path)), "--no-schema", "--schema", str(tmp_path / "schema.json"))
    assert r.returncode == 2
    assert "not allowed with" in r.stderr


def test_a_missing_jsonschema_package_exits_3_and_does_not_pass(tmp_path):
    r = _run("--registry", str(_stage(tmp_path)), block_jsonschema=True)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "jsonschema" in r.stderr and "--no-schema" in r.stderr
    assert "VALIDATION PASSED" not in r.stdout and "Traceback" not in r.stderr


def test_no_schema_does_not_need_the_jsonschema_package(tmp_path):
    r = _run("--registry", str(_stage(tmp_path)), "--no-schema", block_jsonschema=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_an_empty_schema_object_is_a_schema_not_a_missing_one(tmp_path):
    # `{}` is falsy in Python. The old `if schema:` reported it as "not found".
    r = _run("--registry", str(_stage(tmp_path, schema="{}")))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SCHEMA_SKIPPED" not in r.stdout
