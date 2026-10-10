"""
Tests for tools/check_cross_language.sh.

The script runs the Python, JavaScript, Go, and Rust wrapper suites and used
to treat a missing toolchain as a skip that still exited 0. It now treats
every suite as required. These tests run the real script with a PATH that
holds only stub toolchains, so each case (a suite passing, failing, or its
toolchain being absent) is deterministic and needs no Go, Rust, or Node.

The stubs stand in for the toolchains, not for the wrappers' own suites;
the real suites are run by the gate (`check_cross_language.sh` itself, with
no flags) and by CI's wrapper matrix.

What is covered:
  - every exit code (0 pass, 1 suite failed, 2 usage error or nothing ran,
    3 a required suite did not run);
  - the skip path specifically: a missing toolchain is NOT RUN and fails,
    which is the behaviour these tests exist to protect;
  - --allow-skip: repeatable, case-insensitive, `=` form, validated,
    printed in the output, harmless for a suite that ran;
  - a failure outranks a missing suite; nothing running is fatal even when
    every suite was allowed to skip;
  - the removed --strict flag says so;
  - the release gate calls the script unconditionally (a missing file must
    fail the gate by name, not drop the step).

The tests avoid asserting the check-mark glyphs: the script prints them with
printf `\\u` escapes, which render only under a UTF-8 locale.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "tools" / "check_cross_language.sh"
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bash script; POSIX shell stubs"
)

BASH = shutil.which("bash")
LANGS = {"python": "python3", "javascript": "node", "go": "go", "rust": "cargo"}


def _run(tmp_path: Path, *args: str, present=("python", "javascript", "go", "rust"), failing=()):
    """Run the real script with only the named toolchain stubs on PATH."""
    assert BASH, "bash not found"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "dirname", "tr", "tail", "sed", "cat"):
        real = shutil.which(tool)
        assert real, f"{tool} not found"
        (bin_dir / tool).symlink_to(real)
    for lang in present:
        stub = bin_dir / LANGS[lang]
        stub.write_text(f'#!/bin/sh\nexit {1 if lang in failing else 0}\n')
        stub.chmod(0o755)
    result = subprocess.run(
        [BASH, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60, cwd=PROJECT_ROOT,
        env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Suites run
# ---------------------------------------------------------------------------

class TestSuitesRun:
    def test_all_four_pass(self, tmp_path):
        code, out, _ = _run(tmp_path)
        assert code == 0
        assert "OK: all 4 wrapper suites passed" in out

    def test_a_failing_suite_exits_1(self, tmp_path):
        code, out, _ = _run(tmp_path, failing=("go",))
        assert code == 1
        assert "FAIL: 1 of 4 wrapper suite(s) that ran failed" in out

    def test_a_suite_whose_runner_command_fails_is_a_failure_not_a_skip(self, tmp_path):
        # python3 present but its pytest run failing (e.g. pytest not installed).
        code, out, _ = _run(tmp_path, failing=("python",))
        assert code == 1
        assert "NOT RUN" not in out


# ---------------------------------------------------------------------------
# The skip path: a required suite that did not run
# ---------------------------------------------------------------------------

class TestRequiredSuiteDidNotRun:
    def test_missing_toolchain_is_not_run_and_exits_3(self, tmp_path):
        code, out, _ = _run(tmp_path, present=("python", "javascript", "rust"))
        assert code == 3
        assert "NOT RUN (go not found)" in out
        assert "FAIL: 1 required suite(s) did not run: Go" in out

    def test_two_missing_toolchains_are_both_named(self, tmp_path):
        code, out, _ = _run(tmp_path, present=("python", "javascript"))
        assert code == 3
        assert "did not run: Go, Rust" in out

    def test_failure_message_prints_the_exact_rerun_command(self, tmp_path):
        _, out, _ = _run(tmp_path, present=("python", "javascript"))
        assert "bash tools/check_cross_language.sh --allow-skip go --allow-skip rust" in out

    def test_old_message_is_gone(self, tmp_path):
        _, out, _ = _run(tmp_path, present=("python", "javascript", "rust"))
        assert "skipped" not in out and "OK:" not in out

    def test_a_failure_outranks_a_missing_suite(self, tmp_path):
        code, out, _ = _run(tmp_path, present=("python", "javascript", "go"), failing=("go",))
        assert code == 1
        assert "did not run: Rust" in out

    def test_nothing_installed_is_fatal_not_ok(self, tmp_path):
        # Used to print "OK: 0 wrapper suite(s) passed, 4 skipped" and exit 0.
        code, out, _ = _run(tmp_path, present=())
        assert code == 2
        assert "FATAL: no wrapper suite ran" in out


# ---------------------------------------------------------------------------
# --allow-skip
# ---------------------------------------------------------------------------

class TestAllowSkip:
    def test_named_missing_suite_is_excused_and_printed(self, tmp_path):
        code, out, _ = _run(tmp_path, "--allow-skip", "go", present=("python", "javascript", "rust"))
        assert code == 0
        assert "allowed skip (go not found)" in out
        assert "OK: 3 wrapper suite(s) passed; allowed to skip: Go" in out

    def test_repeatable(self, tmp_path):
        code, out, _ = _run(
            tmp_path, "--allow-skip", "go", "--allow-skip", "rust", present=("python", "javascript")
        )
        assert code == 0
        assert "allowed to skip: Go, Rust" in out

    def test_equals_form_and_any_case(self, tmp_path):
        code, _, _ = _run(tmp_path, "--allow-skip=Go", present=("python", "javascript", "rust"))
        assert code == 0

    def test_excusing_one_does_not_excuse_another(self, tmp_path):
        code, out, _ = _run(tmp_path, "--allow-skip", "go", present=("python", "javascript"))
        assert code == 3
        assert "did not run: Rust" in out
        assert "allowed skip (go not found)" in out

    def test_excusing_a_suite_that_ran_is_harmless(self, tmp_path):
        code, out, _ = _run(tmp_path, "--allow-skip", "go")
        assert code == 0
        assert "allowed skip" not in out
        assert "OK: all 4 wrapper suites passed" in out

    def test_excusing_a_failing_suite_that_ran_does_not_hide_the_failure(self, tmp_path):
        code, _, _ = _run(tmp_path, "--allow-skip", "go", failing=("go",))
        assert code == 1

    def test_excusing_every_suite_is_still_fatal(self, tmp_path):
        args = [a for lang in LANGS for a in ("--allow-skip", lang)]
        code, out, _ = _run(tmp_path, *args, present=())
        assert code == 2
        assert "no wrapper suite ran" in out

    def test_unknown_language_is_a_usage_error(self, tmp_path):
        code, out, err = _run(tmp_path, "--allow-skip", "nonexistent")
        assert code == 2
        assert "unknown language 'nonexistent'" in err
        assert "Python" not in out          # rejected before any suite ran

    def test_missing_value_is_a_usage_error(self, tmp_path):
        code, _, err = _run(tmp_path, "--allow-skip")
        assert code == 2
        assert "needs a language" in err


# ---------------------------------------------------------------------------
# Other flags
# ---------------------------------------------------------------------------

class TestFlags:
    def test_strict_was_removed_and_says_so(self, tmp_path):
        code, _, err = _run(tmp_path, "--strict")
        assert code == 2
        assert "--strict was removed" in err and "--allow-skip" in err

    def test_unknown_flag_is_a_usage_error(self, tmp_path):
        code, _, err = _run(tmp_path, "--bogus")
        assert code == 2 and "unknown flag: --bogus" in err

    def test_help_documents_the_flag_and_all_four_exit_codes(self, tmp_path):
        code, out, _ = _run(tmp_path, "--help")
        assert code == 0
        assert "--allow-skip LANG" in out
        for line in ("0  every required suite", "1  at least one suite", "2  usage error", "3  a required suite"):
            assert line in out

    def test_verbose_streams_and_still_classifies(self, tmp_path):
        code, out, _ = _run(tmp_path, "--verbose", present=("python", "javascript", "rust"))
        assert code == 3 and "running:" in out


# ---------------------------------------------------------------------------
# The release gate calls the script unconditionally
# ---------------------------------------------------------------------------

class TestGateCallsItUnconditionally:
    TEXT = RELEASE_SH.read_text(encoding="utf-8")

    def test_no_file_exists_guard_remains(self):
        assert "-f tools/check_cross_language.sh" not in self.TEXT

    def test_gate_step_is_present_and_takes_no_exception_flag(self):
        match = re.search(r'^\s*run_gate_step "check_cross_language.sh"\s+(.*)$', self.TEXT, re.M)
        assert match, "gate step for check_cross_language.sh not found"
        assert match.group(1).strip() == "bash tools/check_cross_language.sh"

    def test_plan_lists_it_without_a_guard(self):
        assert re.search(r'^\s*echo "  bash tools/check_cross_language.sh"$', self.TEXT, re.M)

    def test_a_missing_script_fails_its_gate_step_by_name(self, tmp_path):
        body = re.search(r"^run_gate_step\(\) \{\n.*?^\}\n", self.TEXT, re.S | re.M)
        assert body, "run_gate_step() not found in release.sh"
        harness = tmp_path / "h.sh"
        harness.write_text(
            "GATE_FAILED=0\ninfo() { printf '  %s\\n' \"$*\"; }\n" + body.group(0)
            + 'run_gate_step "check_cross_language.sh"     bash /nonexistent/tools/check_cross_language.sh\n'
            + 'echo "GATE_FAILED=$GATE_FAILED"\n'
        )
        env = {**os.environ, "LC_ALL": "C"}
        result = subprocess.run([BASH, str(harness)], capture_output=True,
                                text=True, timeout=30, env=env)
        assert "check_cross_language.sh" in result.stdout
        assert "No such file" in result.stdout
        assert "GATE_FAILED=1" in result.stdout
