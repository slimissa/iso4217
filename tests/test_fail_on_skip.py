"""
Tests for the --fail-on-skip option in tests/conftest.py (added in v1.7.14).

A skipped test verifies nothing. Before v1.7.14 a suite missing an optional
dependency finished green: without pandas, 8 tests were skipped and
`pytest tests/` still exited 0, so the release gate and CI could pass without
them. CI and the gate now pass --fail-on-skip, and the allowed number of skips
is 0. A plain `pytest tests/` stays lenient so a contributor without every
optional dependency can still run the rest.

The option is exercised in subprocesses: each case copies the real
tests/conftest.py next to a throwaway test file in a temporary directory, so
the repo's own suite is not involved and no pytester plugin is needed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = PROJECT_ROOT / "tests" / "conftest.py"
VALIDATE_YML = PROJECT_ROOT / ".github" / "workflows" / "validate.yml"
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"


def _run(tmp_path: Path, source: str, *flags: str):
    shutil.copyfile(CONFTEST, tmp_path / "conftest.py")
    (tmp_path / "test_case.py").write_text(source)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *flags, "test_case.py"],
        cwd=tmp_path, capture_output=True, text=True, env=env, timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


class TestOption:
    def test_passing_suite_exits_0_with_the_flag(self, tmp_path):
        code, out = _run(tmp_path, "def test_a():\n    assert True\n", "--fail-on-skip")
        assert code == 0
        assert "FAIL-ON-SKIP" not in out

    def test_a_skip_without_the_flag_still_exits_0(self, tmp_path):
        code, out = _run(tmp_path, "import pytest\ndef test_a():\n    pytest.skip('no widget')\n")
        assert code == 0
        assert "1 skipped" in out

    def test_a_skip_with_the_flag_exits_1_and_names_the_test_and_reason(self, tmp_path):
        code, out = _run(
            tmp_path, "import pytest\ndef test_a():\n    pytest.skip('no widget')\n", "--fail-on-skip"
        )
        assert code == 1
        assert "FAIL-ON-SKIP: 1 test(s) were skipped" in out
        assert "test_case.py::test_a" in out and "no widget" in out

    def test_a_module_level_importorskip_counts(self, tmp_path):
        source = "import pytest\npytest.importorskip('no_such_module_v1714')\ndef test_a():\n    pass\n"
        code, out = _run(tmp_path, source, "--fail-on-skip")
        # The module is skipped at collection, so no test runs and pytest's own
        # status is 5; the option must not turn that into success.
        assert code != 0
        assert "FAIL-ON-SKIP" in out and "no_such_module_v1714" in out

    def test_every_skip_is_counted(self, tmp_path):
        source = (
            "import pytest\n"
            "@pytest.mark.parametrize('n', [1, 2, 3])\n"
            "def test_a(n):\n    pytest.skip('nope')\n"
        )
        code, out = _run(tmp_path, source, "--fail-on-skip")
        assert code == 1 and "3 test(s) were skipped" in out

    def test_a_failing_test_is_not_masked(self, tmp_path):
        source = "import pytest\ndef test_a():\n    assert False\ndef test_b():\n    pytest.skip('x')\n"
        code, out = _run(tmp_path, source, "--fail-on-skip")
        assert code == 1
        assert "1 failed" in out

    def test_no_tests_collected_keeps_its_own_status(self, tmp_path):
        code, _ = _run(tmp_path, "x = 1\n", "--fail-on-skip")
        assert code == 5

    def test_skipif_that_does_not_fire_is_not_a_skip(self, tmp_path):
        source = "import pytest\n@pytest.mark.skipif(False, reason='never')\ndef test_a():\n    pass\n"
        code, _ = _run(tmp_path, source, "--fail-on-skip")
        assert code == 0


class TestRealSuite:
    def test_the_pandas_tests_fail_the_run_when_pandas_is_missing(self, tmp_path):
        # A shadow module makes `import pandas` fail exactly as an absent
        # install does. Without the flag this run is green with skips.
        shadow = tmp_path / "shadow" / "pandas"
        shadow.mkdir(parents=True)
        (shadow / "__init__.py").write_text("raise ModuleNotFoundError('pandas', name='pandas')\n")
        env = dict(os.environ, PYTHONPATH=str(shadow.parent))
        base = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "tests/test_export_parquet.py", "-k", "Pandas"]
        lenient = subprocess.run(base, cwd=PROJECT_ROOT, capture_output=True, text=True, env=env, timeout=300)
        strict = subprocess.run(base + ["--fail-on-skip"], cwd=PROJECT_ROOT, capture_output=True, text=True, env=env, timeout=300)
        assert lenient.returncode == 0 and "skipped" in lenient.stdout
        assert strict.returncode == 1
        assert "FAIL-ON-SKIP" in strict.stdout and "pandas" in strict.stdout


class TestCallers:
    """CI and the release gate are the strict callers; both must pass the flag."""

    def test_ci_installs_pandas_and_runs_the_suite_with_the_flag(self):
        text = VALIDATE_YML.read_text(encoding="utf-8")
        assert "pip install -r requirements-ci.txt" in text
        assert re.search(r"(?m)^pandas\b", (PROJECT_ROOT / "requirements-ci.txt").read_text(encoding="utf-8"))
        assert re.search(r"python3 -m pytest tests/ [^\n]*--fail-on-skip", text)

    def test_the_gate_runs_pytest_with_the_flag(self):
        text = RELEASE_SH.read_text(encoding="utf-8")
        gate = re.search(r'^\s*run_gate_step "pytest tests/"\s+(.*)$', text, re.M)
        assert gate and "--fail-on-skip" in gate.group(1)

    def test_the_dry_run_plan_shows_the_flag(self):
        text = RELEASE_SH.read_text(encoding="utf-8")
        assert re.search(r'^\s*echo "  python3 -m pytest tests/ -q --fail-on-skip"$', text, re.M)
