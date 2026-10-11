"""
Tests for commit_and_push() in scripts/release.sh.

A release only modifies tracked files: version bumps and regenerated
artifacts. Anything else in the tree after the gate is something a generator
or test left behind, or a deletion nobody asked for, and `git add -A` used to
sweep it into the release commit without a word. commit_and_push now:

  - aborts if there is an untracked, non-ignored file (before staging);
  - prints `git diff --cached --stat` before committing;
  - aborts if any staged path is not a plain modification (added, deleted,
    renamed, type-changed), unstaging everything first so the tree is left as
    the operator found it.

release.sh has no source guard, so the function is cut out of the script text
and run in a bash subshell inside a real temporary git repository with a
local bare `origin`. Nothing outside the temp directory is touched.
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
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"
TEXT = RELEASE_SH.read_text(encoding="utf-8")
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash and POSIX git paths")

HELPERS = (
    "info()  { printf '  %s\\n' \"$*\"; }\n"
    "step()  { printf '\\n== %s ==\\n' \"$*\"; }\n"
    "fail()  { printf 'FAIL: %s\\n' \"$*\" >&2; exit \"$EXIT_PRECOND\"; }\n"
)


def _function() -> str:
    match = re.search(r"^commit_and_push\(\) \{\n.*?^\}\n", TEXT, re.S | re.M)
    assert match, "commit_and_push() not found in scripts/release.sh; the harness cannot test it"
    return match.group(0)


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=check,
        env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null"),
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / ".gitignore").write_text("*.log\n")
    (work / "a.txt").write_text("one\n")
    (work / "b.txt").write_text("two\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "-u", "origin", "main")
    return work, origin


def _run(work: Path):
    harness = work.parent / "harness.sh"
    harness.write_text(
        "set -euo pipefail\nEXIT_PRECOND=1\nTAG=v9.9.9\n" + HELPERS + _function() + "\ncommit_and_push\n"
    )
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    result = subprocess.run([BASH, str(harness)], cwd=work, capture_output=True, text=True, env=env, timeout=60)
    return result.returncode, result.stdout, result.stderr


def _origin_subjects(origin: Path) -> list:
    out = subprocess.run(
        ["git", "--git-dir", str(origin), "log", "--format=%s", "main"], capture_output=True, text=True, check=True
    ).stdout
    return out.split("\n")[:-1]


class TestCommits:
    def test_a_plain_modification_is_committed_pushed_and_its_stat_printed_first(self, repo):
        work, origin = repo
        (work / "a.txt").write_text("one changed\n")
        code, out, _ = _run(work)
        assert code == 0
        assert "a.txt" in out and "1 file changed" in out
        assert out.index("1 file changed") < out.index("committed: Release v9.9.9")
        assert _origin_subjects(origin)[0] == "Release v9.9.9"

    def test_no_changes_commits_nothing_and_still_succeeds(self, repo):
        work, origin = repo
        code, out, _ = _run(work)
        assert code == 0
        assert "no changes to commit" in out
        assert _origin_subjects(origin) == ["base"]

    def test_ignored_files_are_not_a_reason_to_abort(self, repo):
        work, origin = repo
        (work / "a.txt").write_text("one changed\n")
        (work / "debug.log").write_text("noise\n")
        code, _, _ = _run(work)
        assert code == 0
        assert _origin_subjects(origin)[0] == "Release v9.9.9"


class TestAborts:
    def _assert_untouched(self, work: Path, origin: Path):
        assert _origin_subjects(origin) == ["base"]                  # nothing pushed
        assert _git(work, "rev-parse", "HEAD") == _git(work, "rev-parse", "origin/main")  # nothing committed
        assert _git(work, "diff", "--cached", "--name-only") == ""    # nothing left staged

    def test_an_untracked_file_aborts_before_staging_and_is_named(self, repo):
        work, origin = repo
        (work / "a.txt").write_text("one changed\n")
        (work / "stray.parquet").write_text("left by the gate\n")
        code, _, err = _run(work)
        assert code == 1
        assert "stray.parquet" in err and "untracked" in err
        self._assert_untouched(work, origin)
        assert (work / "stray.parquet").exists()

    def test_a_deleted_tracked_file_aborts_and_is_unstaged(self, repo):
        work, origin = repo
        (work / "b.txt").unlink()
        code, _, err = _run(work)
        assert code == 1
        assert "b.txt" in err and "only modifications are expected" in err
        self._assert_untouched(work, origin)
        assert not (work / "b.txt").exists()                          # the working tree is left as found

    def test_a_staged_new_file_aborts_and_is_unstaged(self, repo):
        work, origin = repo
        (work / "new.txt").write_text("x\n")
        _git(work, "add", "new.txt")
        code, _, err = _run(work)
        assert code == 1 and "new.txt" in err
        self._assert_untouched(work, origin)

    def test_a_rename_aborts(self, repo):
        work, origin = repo
        _git(work, "mv", "a.txt", "renamed.txt")
        code, _, err = _run(work)
        assert code == 1 and "renamed.txt" in err
        self._assert_untouched(work, origin)

    def test_a_modification_alongside_a_deletion_still_aborts_everything(self, repo):
        work, origin = repo
        (work / "a.txt").write_text("one changed\n")
        (work / "b.txt").unlink()
        code, _, _ = _run(work)
        assert code == 1
        self._assert_untouched(work, origin)


class TestSource:
    def test_there_is_no_silent_swallow(self):
        body = _function()
        assert "|| true" not in body
        assert "2>/dev/null" not in body

    def test_the_stat_is_printed_before_the_commit(self):
        body = _function()
        assert body.index("git diff --cached --stat") < body.index('git commit -m "Release $TAG"')
