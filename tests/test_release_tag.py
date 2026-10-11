"""
Tests for tag_release() in scripts/release.sh.

The tag message is the first lines of the CHANGELOG section. It used to be
passed with `git tag -a -m`, which (like -F) runs git's default cleanup and
silently removes every line that begins with `#`. That dropped the Markdown
section headings (`### Fixed`, `### Added`) from every tag message. The
message is now written to a file, tagged with `-F <file> --cleanup=whitespace`,
read back from the tag object and compared; on a mismatch the local tag is
deleted and the release stops before the push (invariant 7).

release.sh has no source guard, so tag_release() is cut out of the script
text and run in a bash subshell in a temporary git repository with a local
bare origin.
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

SECTION = """# Changelog

## [9.9.9] \u2014 2026-01-01

Intro paragraph.

### Fixed

- first thing  
- second thing \u2014 with a dash

# a line that starts with a hash

### Added

- third thing

## [9.9.8] \u2014 2025-12-31

older
"""


def _function() -> str:
    match = re.search(r"^tag_release\(\) \{\n.*?^\}\n", TEXT, re.S | re.M)
    assert match, "tag_release() not found in scripts/release.sh; the harness cannot test it"
    return match.group(0)


@pytest.fixture
def repo(tmp_path: Path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work.mkdir()
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    def git(*a):
        return subprocess.run(["git", *a], cwd=work, check=True, capture_output=True, text=True, env=env).stdout
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (work / "f").write_text("x\n")
    git("add", "f")
    git("commit", "-q", "-m", "base")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "-u", "origin", "main")
    return work, origin, git


def _run(work: Path, changelog_text: str, *, tamper: bool = False):
    changelog = work.parent / "CHANGELOG.md"
    changelog.write_text(changelog_text, encoding="utf-8")
    wrapper = ""
    if tamper:
        # a git that records something other than what it was given
        wrapper = (
            'git() { if [ "${1:-}" = "for-each-ref" ]; then echo "tampered"; else command git "$@"; fi; }\n'
        )
    harness = work.parent / "harness.sh"
    harness.write_text(
        "set -euo pipefail\nEXIT_PRECOND=1\nVERSION=9.9.9\nTAG=v9.9.9\n"
        f'CHANGELOG="{changelog}"\n' + HELPERS + wrapper + _function() + "\ntag_release\n"
    )
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", TMPDIR=str(work.parent))
    result = subprocess.run([BASH, str(harness)], cwd=work, capture_output=True, text=True, env=env, timeout=60)
    return result.returncode, result.stdout, result.stderr


def _recorded(git) -> str:
    return git("for-each-ref", "refs/tags/v9.9.9", "--format=%(contents)")


class TestMessage:
    def test_section_headings_survive(self, repo):
        work, origin, git = repo
        code, _, _ = _run(work, SECTION)
        assert code == 0
        recorded = _recorded(git)
        assert "### Fixed" in recorded and "### Added" in recorded

    def test_a_line_starting_with_a_hash_survives(self, repo):
        work, origin, git = repo
        _run(work, SECTION)
        assert "# a line that starts with a hash" in _recorded(git)

    def test_trailing_whitespace_is_normalised_so_it_is_not_a_false_mismatch(self, repo):
        work, origin, git = repo
        code, _, err = _run(work, SECTION)       # SECTION has a line ending in two spaces
        assert code == 0, err
        assert "- first thing\n" in _recorded(git) + "\n"

    def test_non_ascii_text_round_trips(self, repo):
        work, origin, git = repo
        _run(work, SECTION)
        assert "second thing \u2014 with a dash" in _recorded(git)

    def test_the_message_stops_at_the_next_version_heading(self, repo):
        work, origin, git = repo
        _run(work, SECTION)
        assert "older" not in _recorded(git) and "9.9.8" not in _recorded(git)

    def test_at_most_fifteen_lines_are_used(self, repo):
        work, origin, git = repo
        long = "## [9.9.9] \u2014 2026-01-01\n" + "".join(f"- line {i}\n" for i in range(30))
        _run(work, long)
        assert len([l for l in _recorded(git).split("\n") if l]) == 15

    def test_an_empty_section_falls_back_to_the_release_name(self, repo):
        work, origin, git = repo
        _run(work, "## [9.9.9] \u2014 2026-01-01\n\n## [9.9.8] \u2014 old\n")
        assert _recorded(git).strip() == "Release v9.9.9"


class TestPush:
    def test_the_tag_reaches_origin(self, repo):
        work, origin, git = repo
        code, out, _ = _run(work, SECTION)
        assert code == 0 and "tagged and pushed: v9.9.9" in out
        remote = subprocess.run(["git", "--git-dir", str(origin), "tag", "-l"], capture_output=True, text=True).stdout
        assert "v9.9.9" in remote


class TestReadBackMismatch:
    def test_a_recorded_message_that_differs_deletes_the_local_tag_and_does_not_push(self, repo):
        work, origin, git = repo
        code, _, err = _run(work, SECTION, tamper=True)
        assert code == 1
        assert "different tag message" in err and "nothing pushed" in err
        assert git("tag", "-l") == ""                                  # local tag removed
        remote = subprocess.run(["git", "--git-dir", str(origin), "tag", "-l"], capture_output=True, text=True).stdout
        assert remote == ""                                            # never left the machine


class TestSource:
    def test_the_message_goes_through_a_file_not_m(self):
        body = _function()
        assert "-F" in body and "--cleanup=whitespace" in body
        assert 'tag -a "$TAG" -m' not in body

    def test_the_read_back_happens_before_the_push(self):
        body = _function()
        assert body.index("%(contents)") < body.index("git push origin")
