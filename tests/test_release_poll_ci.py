"""
Tests for the CI-polling and gh-preflight functions of scripts/release.sh.

scripts/release.sh has no source guard: it parses arguments and runs the
release at top level, so it cannot be sourced to reach one function. These
tests cut `poll_ci` and `check_gh_ready` out of the script text, run them in
a bash subshell with the three helpers (info, step, fail) and stub `gh`,
`git`, and `sleep` binaries on a PATH that holds nothing else. No release
is started and nothing is mutated.

The extraction is itself guarded: if a function cannot be found, the test
fails (it never passes vacuously).

What is covered, and why:
  - invariant 7 ("tag only on green") needs poll_ci to return only when every
    workflow in POLLED_WORKFLOWS has a run for the SHA and all are
    completed/success. Each other outcome must exit non-zero;
  - the three paths that used to return success: no gh, no run ever
    appearing, and a timeout;
  - a gh failure must not be read as "no runs yet" (its message is shown);
  - a workflow whose run appears late must be waited for (the early-success
    race);
  - the --poll-timeout flag is validated at parse time, before anything else;
  - check_gh_ready runs before the --dry-run exit, and poll_ci after the push.

The stubs print the already-filtered "id|status|conclusion" lines that the
real `gh ... --jq` prints. They cannot check the jq expression or the gh
flags against a real gh; that is the live smoke test in the release notes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"
TEXT = RELEASE_SH.read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="release.sh is a bash script; no bash subshell harness on Windows"
)

BASH = shutil.which("bash")

HELPERS = (
    "info()  { printf '  %s\\n' \"$*\"; }\n"
    "step()  { printf '\\n== %s ==\\n' \"$*\"; }\n"
    "fail()  { printf 'FAIL: %s\\n' \"$*\" >&2; exit \"$EXIT_PRECOND\"; }\n"
)

GH_STUB = """#!/bin/sh
d="$GH_STUB_DIR"
if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  wf=""
  while [ $# -gt 0 ]; do [ "$1" = "--workflow" ] && wf="$2"; shift; done
  [ -z "$wf" ] && wf=_probe
  n=$(cat "$d/$wf.n" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$d/$wf.n"
  mode=$(cat "$d/$wf.mode" 2>/dev/null || echo success)
  echo "A new release of gh is available: 9.9.9" >&2
  case "$mode" in
    success)       echo "101|completed|success";;
    inprogress)    echo "102|in_progress|pending";;
    queued)        echo "103|queued|pending";;
    failure)       echo "104|completed|failure";;
    cancelled)     echo "105|completed|cancelled";;
    empty)         :;;
    error)         echo "HTTP 401: Bad credentials" >&2; exit 1;;
    appear3)       if [ $n -le 3 ]; then :; else echo "106|completed|success"; fi;;
    oldfail_newok) printf '107|completed|failure\\n108|completed|success\\n';;
  esac
  exit 0
fi
exit 0
"""

GIT_STUB = (
    '#!/bin/sh\n[ "$1" = "rev-parse" ] && echo 0123456789abcdef0123456789abcdef01234567\nexit 0\n'
)


def _extract(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", TEXT, re.S | re.M)
    assert match, f"{name}() not found in scripts/release.sh; the harness cannot test it"
    return match.group(0)


def _run(tmp: Path, function: str, modes: dict, *, timeout=2, grace=1, interval="0.2", with_gh=True):
    """Run one extracted function in a clean-PATH bash subshell."""
    assert BASH, "bash not found"
    bin_dir = tmp / "bin"
    stub_dir = tmp / "stub"
    bin_dir.mkdir()
    stub_dir.mkdir()
    stubs = [("git", GIT_STUB)] + ([("gh", GH_STUB)] if with_gh else [])
    for name, body in stubs:
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)
    for tool in ("sleep", "mktemp", "head", "rm", "cat"):
        real = shutil.which(tool)
        assert real, f"{tool} not found"
        (bin_dir / tool).symlink_to(real)
    for workflow, mode in modes.items():
        (stub_dir / f"{workflow}.mode").write_text(mode)

    harness = tmp / "harness.sh"
    harness.write_text(
        "set -euo pipefail\n"
        "EXIT_PRECOND=1\n"
        "POLLED_WORKFLOWS=(a.yml b.yml)\n"
        f"POLL_TIMEOUT={timeout}\nPOLL_GRACE={grace}\nPOLL_INTERVAL={interval}\n"
        + HELPERS
        + _extract(function)
        + f"\n{function}\n"
    )
    env = {"PATH": str(bin_dir), "GH_STUB_DIR": str(stub_dir), "HOME": str(tmp), "TMPDIR": str(tmp)}
    started = time.time()
    result = subprocess.run([BASH, str(harness)], capture_output=True, text=True, env=env, timeout=60)
    return result.returncode, result.stdout, result.stderr, time.time() - started


# ---------------------------------------------------------------------------
# poll_ci: success
# ---------------------------------------------------------------------------

class TestPollCiSucceeds:
    def test_all_workflows_completed_success(self, tmp_path):
        code, out, err, _ = _run(tmp_path, "poll_ci", {"a.yml": "success", "b.yml": "success"})
        assert code == 0
        assert "completed success" in out

    def test_gh_notices_on_stderr_do_not_break_parsing(self, tmp_path):
        # The stub prints a "new gh release" notice on stderr, as real gh does.
        code, _, _, _ = _run(tmp_path, "poll_ci", {"a.yml": "success", "b.yml": "success"})
        assert code == 0

    def test_a_workflow_whose_run_appears_late_is_waited_for(self, tmp_path):
        # Early-success race: a.yml is done while b.yml has no run yet.
        code, out, _, elapsed = _run(
            tmp_path, "poll_ci", {"a.yml": "success", "b.yml": "appear3"}, grace=5, timeout=10
        )
        assert code == 0
        assert elapsed >= 0.4


# ---------------------------------------------------------------------------
# poll_ci: every other outcome fails
# ---------------------------------------------------------------------------

class TestPollCiFailsClosed:
    def test_a_workflow_with_no_run_fails_after_the_grace_period(self, tmp_path):
        code, _, err, elapsed = _run(
            tmp_path, "poll_ci", {"a.yml": "success", "b.yml": "empty"}, grace=1, timeout=30
        )
        assert code == 1
        assert "b.yml" in err and "did not trigger it" in err
        assert elapsed < 10

    def test_no_run_before_the_grace_period_is_not_yet_a_failure(self, tmp_path):
        code, _, _, _ = _run(
            tmp_path, "poll_ci", {"a.yml": "appear3", "b.yml": "appear3"}, grace=5, timeout=10
        )
        assert code == 0

    def test_a_gh_error_fails_at_once_and_shows_gh_s_message(self, tmp_path):
        code, _, err, elapsed = _run(
            tmp_path, "poll_ci", {"a.yml": "error", "b.yml": "success"}, grace=30, timeout=60
        )
        assert code == 1
        assert "a.yml" in err and "Bad credentials" in err
        assert elapsed < 3

    def test_a_failed_run_fails_at_once_even_while_another_workflow_runs(self, tmp_path):
        code, _, err, elapsed = _run(
            tmp_path, "poll_ci", {"a.yml": "failure", "b.yml": "inprogress"}, grace=30, timeout=60
        )
        assert code == 1
        assert "a.yml" in err and "104" in err and "failure" in err
        assert elapsed < 3

    def test_a_cancelled_run_is_not_green(self, tmp_path):
        code, _, err, _ = _run(tmp_path, "poll_ci", {"a.yml": "cancelled", "b.yml": "success"})
        assert code == 1 and "cancelled" in err

    def test_any_failed_run_for_a_workflow_fails_even_if_a_newer_one_passed(self, tmp_path):
        code, _, err, _ = _run(tmp_path, "poll_ci", {"a.yml": "oldfail_newok", "b.yml": "success"})
        assert code == 1 and "107" in err

    def test_timeout_fails_and_names_the_workflow_still_running(self, tmp_path):
        code, _, err, elapsed = _run(
            tmp_path, "poll_ci", {"a.yml": "inprogress", "b.yml": "success"}, timeout=2, grace=30
        )
        assert code == 1
        assert "timed out after 2s" in err and "a.yml" in err
        # $SECONDS counts whole seconds, so the wait may end up to 1 s early.
        assert 1.0 <= elapsed < 8

    def test_a_queued_run_is_not_green(self, tmp_path):
        code, _, err, _ = _run(tmp_path, "poll_ci", {"a.yml": "queued", "b.yml": "success"}, timeout=1)
        assert code == 1 and "timed out" in err


# ---------------------------------------------------------------------------
# check_gh_ready (runs in the preconditions, before anything is changed)
# ---------------------------------------------------------------------------

class TestCheckGhReady:
    def test_gh_not_installed_fails(self, tmp_path):
        code, _, err, _ = _run(tmp_path, "check_gh_ready", {}, with_gh=False)
        assert code == 1
        assert "gh CLI not found" in err

    def test_gh_that_cannot_list_runs_fails(self, tmp_path):
        code, _, err, _ = _run(tmp_path, "check_gh_ready", {"_probe": "error"})
        assert code == 1
        assert "gh cannot list workflow runs" in err

    def test_working_gh_passes(self, tmp_path):
        code, _, _, _ = _run(tmp_path, "check_gh_ready", {"_probe": "success"})
        assert code == 0


# ---------------------------------------------------------------------------
# --poll-timeout: validated when parsed. `--help` exits 0 inside the parse
# loop, so these invocations never reach preconditions or any mutation.
# ---------------------------------------------------------------------------

def _release(*args: str):
    return subprocess.run(
        [BASH, str(RELEASE_SH), *args], capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=30
    )


class TestPollTimeoutFlag:
    @pytest.mark.parametrize("value", ["", "abc", "0", "-5", "08", "1.5", "5s", "1000000"])
    def test_invalid_value_is_a_usage_error(self, value):
        result = _release("--poll-timeout", value, "--help")
        assert result.returncode == 2
        assert "positive integer" in result.stderr

    def test_missing_value_is_a_usage_error(self):
        result = _release("--poll-timeout")
        assert result.returncode == 2
        assert "needs a value" in result.stderr

    def test_invalid_value_in_equals_form_is_a_usage_error(self):
        result = _release("--poll-timeout=abc", "--help")
        assert result.returncode == 2

    @pytest.mark.parametrize("args", [["--poll-timeout", "120"], ["--poll-timeout=120"], ["--poll-timeout", "999999"]])
    def test_valid_value_is_accepted(self, args):
        result = _release(*args, "--help")
        assert result.returncode == 0
        assert "--poll-timeout" in result.stdout

    def test_usage_documents_the_flag_and_the_prerequisite(self):
        result = _release("--help")
        assert "--poll-timeout N" in result.stdout
        assert "gh CLI" in result.stdout


# ---------------------------------------------------------------------------
# Placement in the release flow
# ---------------------------------------------------------------------------

class TestPlacement:
    def test_gh_is_checked_before_the_dry_run_exit(self):
        main = TEXT[TEXT.index("step \"Preconditions\""):]
        assert main.index("\ncheck_gh_ready\n") < main.index("if $DRY_RUN; then")

    def test_poll_ci_runs_after_the_push_and_before_the_tag(self):
        main = TEXT[TEXT.index("step \"Preconditions\""):]
        assert main.index("\ncommit_and_push\n") < main.index("\npoll_ci\n") < main.index("\ntag_release\n")

    def test_no_bare_return_remains_in_poll_ci(self):
        # The old function ended with a bare `return` after "skipping CI poll".
        body = _extract("poll_ci")
        assert not re.search(r"^\s*return\s*$", body, re.M)
        assert "skipping CI poll" not in body
