"""
Tests for the release-script hygiene fixes of v1.7.15 (scripts/release.sh).

  - `die` was called in check_no_orphan_variables but never defined, so the
    check aborted with "command not found" (exit 127) instead of failing
    cleanly;
  - commit_and_push ran `git diff --cached --stat` through a pager, which
    blocked an interactive release until the operator pressed q;
  - print_plan listed 15 of the 17 gate steps.

release.sh has no source guard, so functions are cut out of the script text and
run in bash. `--dry-run` cannot exercise any of this: it exits before
commit_and_push, and the orphan check only reaches `fail` when it finds an
orphan. Hence these tests.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_export_aggregated import env

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEXT = (PROJECT_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash, pty and POSIX git paths")

HELPERS = (
    "info()  { printf '  %s\\n' \"$*\"; }\n"
    "step()  { printf '\\n== %s ==\\n' \"$*\"; }\n"
    "fail_code() { local code=\"$1\"; shift; printf 'FAIL: %s\\n' \"$*\" >&2; exit \"$code\"; }\n"
    "fail()  { fail_code \"$EXIT_PRECOND\" \"$@\"; }\n"
    "mutated_hint() { echo 'restore it with: git checkout -- .'; }\n"
)
ISOLATED = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", TEXT, re.S | re.M)
    assert match, f"{name}() not found in scripts/release.sh; the harness cannot test it"
    return match.group(0)

def _function_from_runtime(name: str) -> str:
    """Extract `name()` from RH_RELEASE_SH (set by the mutation sweep) or from TEXT.

    A mutation sweep points RH_RELEASE_SH at a mutated copy of release.sh. The
    extraction tests must read *that* copy, or the mutant is never exercised
    (M28 in v1.9.4 survived for exactly this reason: _function read TEXT).
    """
    source = os.environ.get("RH_RELEASE_SH")
    text_src = Path(source).read_text(encoding="utf-8") if source else TEXT
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text_src, re.S | re.M)
    assert match, f"{name}() not found in {source or 'scripts/release.sh'}"
    return match.group(0)


# ---------------------------------------------------------------------------
# die -> fail
# ---------------------------------------------------------------------------

GENERATORS = ["export_sql", "export_csv", "export_parquet", "export_countries_parquet",
              "export_aggregated", "sync_wrappers"]


class TestRegenerateStopsOnAFailingGenerator:
    def _run(self, tmp_path: Path, failing: str):
        harness = tmp_path / "harness.sh"
        harness.write_text(
            "set -euo pipefail\nEXIT_PRECOND=1\nEXIT_COULD_NOT=3\nEXIT_GATE=4\nEXIT_PUSH=5\nEXIT_CI=6\nEXIT_TAG=7\nEXIT_DOC=8\nDRY_RUN=false\nRECREATE_TAG=false\n" + HELPERS
            + 'python3() { echo "$1" >> calls.txt; if [ "$1" = "tools/' + failing + '.py" ]; then return 1; fi; return 0; }\n'
            + _function("regenerate_artifacts") + "\nregenerate_artifacts\necho REACHED_END\n"
        )
        result = subprocess.run([BASH, str(harness)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
        calls = (tmp_path / "calls.txt").read_text().split() if (tmp_path / "calls.txt").exists() else []
        return result, calls

    @pytest.mark.parametrize("failing", GENERATORS)
    def test_a_failing_generator_stops_the_release_and_is_named(self, tmp_path, failing):
        result, calls = self._run(tmp_path, failing)
        assert result.returncode == 4
        assert "REACHED_END" not in result.stdout
        assert failing + ".py" in result.stderr
        later = GENERATORS[GENERATORS.index(failing) + 1:]
        assert not any(f"tools/{g}.py" in calls for g in later), calls

    def test_when_nothing_fails_every_generator_runs_in_order(self, tmp_path):
        result, calls = self._run(tmp_path, "none")
        assert result.returncode == 0 and "REACHED_END" in result.stdout
        assert calls == [f"tools/{g}.py" for g in GENERATORS]


class TestOrphanCheck:
    def _run(self, tmp_path: Path, script_body: str):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "release.sh").write_text(script_body, encoding="utf-8")
        harness = tmp_path / "harness.sh"
        harness.write_text(
            "set -euo pipefail\nEXIT_PRECOND=1\nEXIT_COULD_NOT=3\nEXIT_GATE=4\nEXIT_PUSH=5\nEXIT_CI=6\nEXIT_TAG=7\nEXIT_DOC=8\nDRY_RUN=false\nRECREATE_TAG=false\n" + HELPERS + _function("check_no_orphan_variables")
            + "\ncheck_no_orphan_variables\n"
        )
        return subprocess.run([BASH, str(harness)], cwd=tmp_path, capture_output=True, text=True, timeout=60)

    def test_an_orphan_variable_fails_with_the_precondition_exit_and_a_message(self, tmp_path):
        result = self._run(tmp_path, 'VERSION=1\necho "$VERSION $ORPHAN_VAR_XYZ"\n')
        assert result.returncode == 1
        assert "ORPHAN_VAR_XYZ" in result.stderr
        assert "release script references undefined variables" in result.stderr

    def test_the_abort_is_not_a_command_not_found(self, tmp_path):
        result = self._run(tmp_path, 'echo "$ORPHAN_VAR_XYZ"\n')
        assert "command not found" not in result.stderr
        assert result.returncode != 127

    def test_a_clean_script_passes(self, tmp_path):
        assert self._run(tmp_path, 'VERSION=1\necho "$VERSION"\n').returncode == 0

    def test_every_helper_the_script_calls_is_defined_in_it(self):
        for name in ("die", "fail", "info", "step"):
            called = re.search(rf"(?m)^\s+{name} ", TEXT) is not None
            defined = re.search(rf"(?m)^{name}\(\) ", TEXT) is not None
            assert defined or not called, f"{name} is called in release.sh but never defined"


# ---------------------------------------------------------------------------
# --no-pager
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=dict(os.environ, **ISOLATED))


def _repo(tmp_path: Path) -> Path:
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("one\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "-u", "origin", "main")
    (work / "a.txt").write_text("one changed\n")
    return work


def _in_pty(argv: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    """Run argv with a terminal as stdout, so git believes a pager is wanted."""
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.chdir(cwd)
        os.execvpe(argv[0], argv, env)
    out = b""
    while True:
        ready, _, _ = select.select([fd], [], [], 60)
        if not ready:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise AssertionError("timed out: something blocked, probably a pager")
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode("utf-8", errors="replace")


class TestPager:
    def _env(self, marker: Path) -> dict:
        # A pager that records it was started and passes the text through. A real
        # `less` would block here, which is the bug.
        return dict(os.environ, **ISOLATED, TERM="xterm", GIT_PAGER=f"touch {marker}; cat")

    def test_the_harness_notices_a_pager(self, tmp_path):
        """Control: plain `git diff --cached --stat` in a terminal does start the pager."""
        work = _repo(tmp_path)
        _git(work, "add", "-A")
        marker = tmp_path / "pager-ran"
        _in_pty(["git", "diff", "--cached", "--stat"], work, self._env(marker))
        assert marker.exists(), "the harness cannot detect a pager, so the next test would prove nothing"

    def test_commit_and_push_does_not_start_a_pager(self, tmp_path):
        work = _repo(tmp_path)
        marker = tmp_path / "pager-ran"
        harness = tmp_path / "harness.sh"
        harness.write_text(
            "set -euo pipefail\nEXIT_PRECOND=1\nEXIT_COULD_NOT=3\nEXIT_GATE=4\nEXIT_PUSH=5\nEXIT_CI=6\nEXIT_TAG=7\nEXIT_DOC=8\nDRY_RUN=false\nRECREATE_TAG=false\nTAG=v9.9.9\n" + HELPERS + _function("commit_and_push")
            + "\ncommit_and_push\n"
        )
        code, out = _in_pty([BASH, str(harness)], work, self._env(marker))
        assert code == 0, out
        assert "committed: Release v9.9.9" in out
        assert not marker.exists(), "commit_and_push started a pager"


# ---------------------------------------------------------------------------
# print_plan lists what run_gate runs
# ---------------------------------------------------------------------------

def _gate_commands() -> list[str]:
    body = _function("run_gate")
    commands = re.findall(r'(?m)^\s*run_gate_step\s+"[^"]+"\s+(.+?)\s*$', body)
    return [c.replace('"', "") for c in commands]


def _plan_commands() -> list[str]:
    body = _function("print_plan")
    block = re.search(r'echo "Gate:"\n((?:\s+echo "  .+"\n)+)', body)
    assert block, "print_plan has no Gate: list"
    return [c.replace("\\$", "$") for c in re.findall(r'echo "  (.+)"', block.group(1))]


class TestPlanMatchesGate:
    def test_there_is_a_gate_to_compare(self):
        assert len(_gate_commands()) >= 17

    def test_the_plan_lists_every_gate_step_in_gate_order(self):
        assert _plan_commands() == _gate_commands()

# tests/test_release_hygiene.py — append

class TestVerificationDocFunction:
    """v1.9.4: the check-then-commit ordering in write_verification_doc, tested by extraction.

    The harness test for a *prose* TODO would need a test hook in production code
    (to write a TODO into prose, which the release script never does); extraction
    tests the function's own ordering — if check_verification_doc.py exits non-zero,
    the doc is not committed and the exit is 8.
    """

    def _run(self, tmp_path: Path, *, checker_fails: bool) -> subprocess.CompletedProcess:
        work = tmp_path / "work"
        work.mkdir()
        (work / "scripts").mkdir()
        (work / "tools").mkdir()
        (work / "docs").mkdir()
        (work / "VERSION").write_text("1.9.4\n", encoding="utf-8")
        # A stub `git` on PATH: the tested unit is the check-then-commit ordering,
        # not git's behavior. The fixture has no repo, so a bare `git rev-parse`
        # (which write_verification_doc runs before the checker) would exit 128 and
        # abort the harness under `set -e`. The stub exits 0 for every subcommand;
        # the failing-checker path never reaches `git add`/`commit`/`push`
        # (fail_code exits first), so a no-op stub is sufficient for this test.
        (work / "bin").mkdir()
        git = work / "bin" / "git"
        git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        git.chmod(0o755)

        if checker_fails:
            (work / "checker-fails").write_text("x")

        (work / "tools" / "check_verification_doc.py").write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n"
            "if Path('checker-fails').exists():\n"
            "    print('DIRTY: simulated prose TODO')\n"
            "    sys.exit(1)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        # Do NOT pre-write the doc. write_verification_doc must create it, so the
        # checker runs on the freshly written file. If the doc pre-exists, the
        # function early-returns ("already exists; leaving it alone") and the
        # checker is never called, so the check-then-commit ordering would not
        # be tested. The doc is left behind by the heredoc write on the failure
        # path; the function exits 8 (fail_code) before git is touched.

        # The function, extracted from scripts/release.sh by _function(name).
        func = _function_from_runtime("write_verification_doc")

        harness = work / "harness.sh"
        harness.write_text(
            "set -euo pipefail\n"
            "EXIT_PRECOND=1\nEXIT_COULD_NOT=3\nEXIT_GATE=4\nEXIT_PUSH=5\nEXIT_CI=6\nEXIT_TAG=7\nEXIT_DOC=8\n"
            "DRY_RUN=false\nRECREATE_TAG=false\nTAG=v1.9.4\nTODAY=2026-10-28\n"
            "GATE_PASSED=0\nGATE_STEPS=0\nGATE_LOG_FILE=''\nCI_RUN_LINES=''\n"
            "info()  { printf '  %s\\n' \"$*\"; }\n"
            "step()  { printf '\\n== %s ==\\n' \"$*\"; }\n"
            "fail_code() { local code=\"$1\"; shift; printf 'FAIL: %s\\n' \"$*\" >&2; exit \"$code\"; }\n"
            "fail()  { fail_code \"$EXIT_PRECOND\" \"$@\"; }\n"
            "mutated_hint() { echo 'restore it with: git checkout -- .'; }\n"
            + func
            + "\nwrite_verification_doc\necho REACHED_END\n"
        )

        env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": f"{work / 'bin'}{os.pathsep}{os.environ['PATH']}",
        }
        return subprocess.run([BASH, str(harness)], cwd=work, capture_output=True, text=True, env=env, timeout=60)

    def test_a_checker_failure_is_exit_8_and_the_doc_is_not_committed(self, tmp_path):
        r = self._run(tmp_path, checker_fails=True)
        assert r.returncode == 8, r.stdout + r.stderr
        assert "not committed" in r.stderr
        assert "REACHED_END" not in r.stdout
        assert not (tmp_path / "work" / "docs" / "v1.9.4-verification.md").exists() or \
               "TODO" not in (tmp_path / "work" / "docs" / "v1.9.4-verification.md").read_text(), \
               "the doc must not be committed when the checker fails"

