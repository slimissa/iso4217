"""
The Python wheel ships a valid registry (v1.9.2, audit finding P5-01, ADR 0011).

v1.9.1 shipped wrappers/python/schema.json inside the wheel: a v1.3.0 schema that rejected the v1.4.0 registry it
sat next to (314 errors). Nothing read it, so nothing failed. These tests build the real wheel, install it into a
clean virtualenv (not a source-tree import), and hold the installed registry to the repository's schema.

Rule 10 (a check that cannot fail is not a check): `check_wheel` is the one function that judges a wheel, and the
`TestTheCheckCanFail` cases feed it a wheel that ships the stale schema and a wheel whose registry is invalid.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PY_WRAPPER = PROJECT_ROOT / "wrappers" / "python"
ROOT_SCHEMA = PROJECT_ROOT / "schema.json"
ROOT_REGISTRY = PROJECT_ROOT / "iso4217.json"

jsonschema = pytest.importorskip("jsonschema")


def build_wheel(source: Path, out: Path) -> Path:
    """Build a wheel from a copy of the wrapper directory, offline, with the interpreter running the tests."""
    work = out / "src"
    shutil.copytree(source, work, ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", "tests"))
    done = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", str(out / "dist")],
        cwd=work, capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    wheels = list((out / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def check_wheel(wheel: Path) -> list[str]:
    """Every way a wheel can fail the consumer. An empty list means a consumer gets a valid registry."""
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        stale = [n for n in names if n.endswith("schema.json")]
        if stale:
            problems.append(f"the wheel ships a schema: {stale} (ADR 0011: the schema is the contract, not the payload)")
        data = [n for n in names if n.endswith("iso4217.json")]
        if len(data) != 1:
            return problems + [f"expected exactly one iso4217.json in the wheel, found {data}"]
        shipped = json.loads(z.read(data[0]).decode("utf-8"))
        raw = z.read(data[0])
    if raw != ROOT_REGISTRY.read_bytes():
        problems.append("the wheel's iso4217.json differs from the repository's iso4217.json")
    schema = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
    cls = jsonschema.validators.validator_for(schema)
    errors = list(cls(schema).iter_errors(shipped))
    if errors:
        problems.append(f"the wheel's registry has {len(errors)} schema error(s); first: {errors[0].message[:120]}")
    return problems


@pytest.fixture(scope="module")
def real_wheel(tmp_path_factory) -> Path:
    return build_wheel(PY_WRAPPER, tmp_path_factory.mktemp("wheel"))


class TestTheWheelAConsumerGets:
    def test_the_built_wheel_passes_every_check(self, real_wheel):
        assert check_wheel(real_wheel) == []

    def test_the_wheel_ships_no_schema(self, real_wheel):
        with zipfile.ZipFile(real_wheel) as z:
            assert not [n for n in z.namelist() if n.endswith("schema.json")]

    def test_a_clean_virtualenv_installs_it_and_loads_a_valid_registry(self, real_wheel, tmp_path):
        venv = tmp_path / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, timeout=300)
        bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        python = bindir / ("python.exe" if sys.platform == "win32" else "python")
        done = subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(real_wheel)],
            capture_output=True, text=True, timeout=300,
        )
        assert done.returncode == 0, done.stdout[-1000:] + done.stderr[-1000:]
        # Run from a directory that is not the repository, so a source-tree import cannot satisfy it.
        probe = (
            "import iso4217, json, pathlib; "
            "d = pathlib.Path(iso4217.__file__).parent; "
            "print(d); print((d / 'iso4217.json').is_file()); print((d / 'schema.json').exists())"
        )
        run = subprocess.run([str(python), "-c", probe], cwd=tmp_path, capture_output=True, text=True, timeout=120)
        assert run.returncode == 0, run.stderr[-800:]
        site_dir, has_json, has_schema = run.stdout.strip().splitlines()
        assert PROJECT_ROOT not in Path(site_dir).parents, "the import resolved to the source tree, not the install"
        assert has_json == "True" and has_schema == "False"
        installed = json.loads((Path(site_dir) / "iso4217.json").read_text(encoding="utf-8"))
        schema = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
        errors = list(jsonschema.validators.validator_for(schema)(schema).iter_errors(installed))
        assert errors == [], f"{len(errors)} errors; first: {errors[0].message[:120] if errors else ''}"
        assert installed["meta"]["schema_version"] == schema["$id"].rsplit("/v", 1)[1].split("/")[0]


class TestTheCheckCanFail:
    """Rule 10: break the wheel in the two ways that matter and assert check_wheel says so."""

    def _copy(self, tmp_path) -> Path:
        src = tmp_path / "wrapper"
        shutil.copytree(PY_WRAPPER, src, ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", "tests"))
        return src

    def test_a_wheel_that_ships_the_stale_schema_fails(self, tmp_path):
        src = self._copy(tmp_path)
        stale = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
        stale["$id"] = stale["$id"].replace("/v1.4.0/", "/v1.3.0/")
        (src / "schema.json").write_text(json.dumps(stale, indent=2), encoding="utf-8")
        (src / "setup.py").write_text(
            (src / "setup.py").read_text(encoding="utf-8").replace(
                'DATA_FILES = ("iso4217.json",)', 'DATA_FILES = ("iso4217.json", "schema.json")'),
            encoding="utf-8")
        wheel = build_wheel(src, tmp_path / "out")
        problems = check_wheel(wheel)
        assert any("ships a schema" in p for p in problems), problems

    def test_a_wheel_whose_registry_is_invalid_fails(self, tmp_path):
        src = self._copy(tmp_path)
        data = json.loads((src / "iso4217.json").read_text(encoding="utf-8"))
        data["currencies"]["active"][0]["minor_units"] = "two"
        (src / "iso4217.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        wheel = build_wheel(src, tmp_path / "out")
        problems = check_wheel(wheel)
        assert any("schema error" in p for p in problems), problems
        assert any("differs" in p for p in problems), problems

    def test_a_wheel_with_a_stale_registry_copy_fails(self, tmp_path):
        src = self._copy(tmp_path)
        data = json.loads((src / "iso4217.json").read_text(encoding="utf-8"))
        data["meta"]["updated"] = "1999-01-01"
        (src / "iso4217.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        wheel = build_wheel(src, tmp_path / "out")
        assert any("differs" in p for p in check_wheel(wheel))
