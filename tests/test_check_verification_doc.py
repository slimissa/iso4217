"""tests/test_check_verification_doc.py — v1.9.4 finding.

The gate's own output contains the string `scripts/release.sh does not contain 'TODO'`
(a claim about the release script). The verification doc's evidence section quotes that
output inside a fenced code block. A `TODO` there is *data*, not a placeholder; the
v1.9.4 release script refused to commit its doc because the pre-fix scanner saw it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_verification_doc.py"


def _run(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )


def _write(tmp_path: Path, body: str) -> None:
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "v9.9.9-verification.md").write_text(body, encoding="utf-8")


def _filler(n: int = 90) -> str:
    return "\n".join(f"Evidence line {i} for v9.9.9." for i in range(n))


def test_a_todo_inside_a_fenced_code_block_is_not_a_placeholder(tmp_path):
    # This is the exact line the v1.9.4 release script generated and rejected.
    _write(tmp_path, "# v9.9.9\n\n" + _filler() + "\n\n## Gate\n\n```\n"
                     "[OK  ] scripts/release.sh does not contain 'TODO'\n```\n")
    r = _run(tmp_path)
    assert r.returncode == 0, f"a quoted TODO inside a fence must not be a marker:\n{r.stdout}\n{r.stderr}"


def test_a_todo_inside_an_inline_code_span_is_not_a_placeholder(tmp_path):
    # Prose that *quotes* a marker in backticks is evidence, not a placeholder.
    _write(tmp_path, "# v9.9.9\n\n" + _filler() + "\n\nThe claim is `does not contain 'TODO'`.\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_todo_in_prose_is_still_a_placeholder(tmp_path):
    # The fix must not weaken the check: a real placeholder in prose still fails.
    _write(tmp_path, "# v9.9.9\n\n" + _filler() + "\n\n## Known gaps\n\nTODO: fill in\n")
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "TODO" in r.stdout


def test_a_paste_placeholder_in_prose_still_fails(tmp_path):
    _write(tmp_path, "# v9.9.9\n\n" + _filler() + "\n\n<paste the CI URL here>\n")
    r = _run(tmp_path)
    assert r.returncode == 1 and "<paste" in r.stdout.lower()


def test_the_v1_9_4_release_s_lines_are_now_accepted(tmp_path):
    # Regression: the exact doc the release script tried to commit.
    _write(tmp_path, (
        "# v1.9.4 Post-Release Verification\n\n"
        "**Tag:** v1.9.4\n**Tag commit:** b387f31\n\n"
        + _filler() + "\n\n"
        "## Gate\n\nEvery step of the release gate ran on the release tree.\n\n"
        "```\n"
        "### \u2713 check_release_claims.py\n\n"
        "[OK  ] scripts/release.sh does not contain 'TODO'\n"
        "[OK  ] tests/test_release_harness_mutations.py contains 'M31-ls-remote-check-removed'\n"
        "```\n"
    ))
    r = _run(tmp_path)
    assert r.returncode == 0, f"the v1.9.4 release doc must be clean after the fix:\n{r.stdout}\n{r.stderr}"