"""
Tests for tools/check_readme_drift.py.

Each test builds a minimal fake repo in tmp_path, points the tool at it via
README_CHECK_REPO, and asserts the exit code and drift text. The tool is
never run against the real tree here — the gate does that.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_readme_drift.py"


def _init_repo(root: Path) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, env=env)


def _run(root: Path, *args: str):
    env = {**os.environ, "README_CHECK_REPO": str(root)}
    return subprocess.run(
        [sys.executable, str(TOOL), "--quiet", *args],
        capture_output=True, text=True, env=env,
    )


def _minimal_repo(tmp_path: Path, readme_text: str, extra=None) -> Path:
    (tmp_path / "README.md").write_text(readme_text, encoding="utf-8")
    (tmp_path / "iso4217.json").write_text(
        '{"currencies":{"active":[],"withdrawn":[]},"non_iso":{}}', encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "release.sh").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    for rel, content in (extra or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _init_repo(tmp_path)
    return tmp_path


def test_clean_minimal_repo_passes(tmp_path):
    root = _minimal_repo(tmp_path, "# Title\n\nNo claims.\n")
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dangling_link_fails(tmp_path):
    root = _minimal_repo(tmp_path, "[x](./missing.md)\n")
    r = _run(root, "--only", "links")
    assert r.returncode == 1
    assert "dangling link" in r.stdout


def test_link_to_existing_file_passes(tmp_path):
    root = _minimal_repo(tmp_path, "[x](./kept.md)\n", {"kept.md": "hi\n"})
    r = _run(root, "--only", "links")
    assert r.returncode == 0, r.stdout


def test_active_count_mismatch_fails(tmp_path):
    (tmp_path / "iso4217.json").write_text(
        '{"currencies":{"active":[{"code":"USD"}],"withdrawn":[]},"non_iso":{}}',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("167 active currencies\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "release.sh").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "decisions").mkdir(parents=True, exist_ok=True)
    _init_repo(tmp_path)
    r = _run(tmp_path, "--only", "counts")
    assert r.returncode == 1
    assert "active currencies" in r.stdout
    assert "168" not in r.stdout and "167" in r.stdout and "1" in r.stdout


def test_gate_count_word_mismatch_fails(tmp_path):
    (tmp_path / "iso4217.json").write_text(
        '{"currencies":{"active":[],"withdrawn":[]},"non_iso":{}}', encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("Runs a fifteen-check gate.\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "release.sh").write_text(
        '    run_gate_step "a" foo\n    run_gate_step "b" bar\n', encoding="utf-8",
    )
    (tmp_path / "docs" / "decisions").mkdir(parents=True, exist_ok=True)
    _init_repo(tmp_path)
    r = _run(tmp_path, "--only", "counts")
    assert r.returncode == 1
    assert "fifteen" in r.stdout and "2" in r.stdout


def test_duplicate_adr_fails(tmp_path):
    root = _minimal_repo(
        tmp_path, "# Title\n",
        {"docs/decisions/a.md": "# ADR 0005\n", "docs/decisions/b.md": "# ADR 0005\n"},
    )
    r = _run(root, "--only", "adrs")
    assert r.returncode == 1
    assert "ADR 0005 declared twice" in r.stdout


def test_readme_cites_unknown_adr_fails(tmp_path):
    root = _minimal_repo(tmp_path, "See ADR 0042.\n")
    r = _run(root, "--only", "adrs")
    assert r.returncode == 1
    assert "ADR 0042" in r.stdout


def test_readme_missing_exits_fatal(tmp_path):
    root = _minimal_repo(tmp_path, "# Title\n")
    (root / "README.md").unlink()
    r = _run(root)
    assert r.returncode == 3
