"""
Tests for `vendor_iso3166.py --check-upstream` (v1.9.1, audit finding F31).

The flag asks whether the vendored release is still the latest tag upstream. These tests point it at a
local git repository with known tags (no network): 0 current, 1 behind or not a tag, 2 no stable tags or
bad flags, 3 the tag list could not be read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import vendor_iso3166 as v  # noqa: E402

TOOL = PROJECT_ROOT / "tools" / "vendor_iso3166.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _upstream(tmp_path: Path, tags: list[str]) -> str:
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "x")
    for tag in tags:
        _git(repo, "tag", tag)
    return repo.as_uri()


def _root(tmp_path: Path, source_version: str | None = "1.8.0") -> Path:
    root = tmp_path / "proj"
    (root / "tools").mkdir(parents=True)
    meta = {} if source_version is None else {"source_version": source_version}
    (root / "tools" / "iso3166_snapshot.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return root


def _main(root: Path, url: str, capsys) -> tuple[int, str]:
    code = v.main(["--check-upstream", "--upstream-url", url], root=root)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_the_vendored_release_being_the_latest_tag_exits_0(tmp_path, capsys):
    code, out = _main(_root(tmp_path), _upstream(tmp_path, ["v1.7.0", "v1.8.0"]), capsys)
    assert code == 0 and "v1.8.0" in out


def test_a_newer_upstream_tag_exits_1(tmp_path, capsys):
    code, out = _main(_root(tmp_path), _upstream(tmp_path, ["v1.8.0", "v1.8.1"]), capsys)
    assert code == 1 and "v1.8.1" in out and "behind" in out.lower()


def test_versions_compare_as_numbers_not_text(tmp_path, capsys):
    code, out = _main(_root(tmp_path, "1.9.0"), _upstream(tmp_path, ["v1.9.0", "v1.10.0"]), capsys)
    assert code == 1 and "v1.10.0" in out


def test_prerelease_and_non_version_tags_are_ignored(tmp_path, capsys):
    url = _upstream(tmp_path, ["v1.8.0", "v1.9.0-rc1", "latest", "release-2"])
    code, _ = _main(_root(tmp_path), url, capsys)
    assert code == 0


def test_a_vendored_version_that_is_not_an_upstream_tag_exits_1(tmp_path, capsys):
    code, out = _main(_root(tmp_path, "1.8.5"), _upstream(tmp_path, ["v1.8.0", "v1.8.9"]), capsys)
    assert code == 1 and "not a tag" in out


def test_an_upstream_with_no_stable_tags_exits_2(tmp_path, capsys):
    code, out = _main(_root(tmp_path), _upstream(tmp_path, ["latest"]), capsys)
    assert code == 2 and "no stable" in out


def test_a_missing_source_version_exits_2(tmp_path, capsys):
    code, _ = _main(_root(tmp_path, None), _upstream(tmp_path, ["v1.8.0"]), capsys)
    assert code == 2


def test_an_unreachable_upstream_exits_3_after_three_attempts(tmp_path, capsys, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(v, "_sleep", sleeps.append)
    code, out = _main(_root(tmp_path), (tmp_path / "no-such-repo").as_uri(), capsys)
    assert code == 3 and "after 3 attempts" in out
    assert len(sleeps) == 2


def test_a_missing_git_is_could_not_run(tmp_path, capsys, monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(v.subprocess, "run", boom)
    code, out = _main(_root(tmp_path), "file:///nowhere", capsys)
    assert code == 3 and "git is not installed" in out


@pytest.mark.parametrize("extra", [["--check"], ["--version", "1.8.0"], ["--source", "x.json"], ["--vendored-at", "2026-01-01"]])
def test_the_flag_does_not_combine_with_the_other_modes(tmp_path, capsys, extra):
    code = v.main(["--check-upstream", *extra], root=_root(tmp_path))
    assert code == 2
    assert "--check-upstream" in capsys.readouterr().err


def test_the_upstream_url_needs_the_flag(tmp_path, capsys):
    code = v.main(["--check", "--upstream-url", "file:///x"], root=_root(tmp_path))
    assert code == 2


def test_the_default_upstream_is_the_iso3166_repository():
    assert v.UPSTREAM_URL == "https://github.com/slimissa/iso3166.git"


def test_the_exit_code_reaches_the_shell(tmp_path):
    url = _upstream(tmp_path, ["v1.8.0", "v1.8.1"])
    root = _root(tmp_path)
    done = subprocess.run(
        [sys.executable, str(TOOL), "--check-upstream", "--upstream-url", url, "--root", str(root)],
        capture_output=True, text=True, timeout=60,
    )
    assert done.returncode == 1, done.stdout + done.stderr
