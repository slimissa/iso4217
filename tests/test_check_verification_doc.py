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

# ---------------------------------------------------------------------------
# v1.9.5, audit finding P5-11 (ADR 0017): precision, an OK line that names what it checked, a self-checking
# grandfather list, and exact fence handling. Classes (ADR 0014, D1): R = red-first, C = characterization.
# ---------------------------------------------------------------------------

import re  # noqa: E402

import json  # noqa: E402

GRANDFATHER_FILE = "docs/verification-grandfathered.json"
ENTRIES = {
    "docs/v1.5.0-verification.md": "79 lines; one short of the minimum; a real record",
    "docs/v1.5.4-verification.md": "the stub shipped uncompleted; the check did not exist until v1.7.11",
}


def _grandfather(tmp_path: Path, entries: dict | None = None) -> None:
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / GRANDFATHER_FILE).write_text(json.dumps(ENTRIES if entries is None else entries, indent=2), encoding="utf-8")


def _write_named(tmp_path: Path, version: str, body: str) -> Path:
    (tmp_path / "docs").mkdir(exist_ok=True)
    p = tmp_path / "docs" / f"{version}-verification.md"
    p.write_text(body, encoding="utf-8")
    return p


def _complete(version: str, extra: str = "") -> str:
    return f"# {version}\n\n" + "\n".join(f"Evidence line {i} for {version}." for i in range(90)) + "\n" + extra


def _run_args(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), str(tmp_path), *args], capture_output=True, text=True, timeout=30)


class TestPlaceholderIsCaseSensitive:
    def test_R_a_lower_case_placeholder_in_prose_is_not_a_marker(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "The registry uses a placeholder for the symbol when none exists.\n"))
        assert _run(tmp_path).returncode == 0

    def test_C_an_upper_case_PLACEHOLDER_is_still_a_marker(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "PLACEHOLDER: fill in the proof.\n"))
        r = _run(tmp_path)
        assert r.returncode == 1 and "PLACEHOLDER marker" in r.stdout


class TestTheOkLineNamesWhatItChecked:
    def test_R_default_mode_names_the_path_and_the_line_count(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9"))
        r = _run(tmp_path)
        assert r.returncode == 0
        assert re.search(r"^OK: docs/v9\.9\.9-verification\.md clean \(\d+ lines\)$", r.stdout, re.M), r.stdout

    def test_R_all_mode_names_the_count_and_the_grandfathered_paths(self, tmp_path):
        _write_named(tmp_path, "v1.5.0", "# v1.5.0\n" + "\n".join(f"line {i}" for i in range(78)) + "\n")
        _write_named(tmp_path, "v1.5.4", "# v1.5.4\n\n| 8.1 | CI | TODO |\n")
        _write_named(tmp_path, "v9.9.9", _complete("v9.9.9"))
        _grandfather(tmp_path)
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "3 verification doc(s) clean, 2 grandfathered" in r.stdout
        assert "docs/v1.5.0-verification.md" in r.stdout and "docs/v1.5.4-verification.md" in r.stdout


class TestTheGrandfatherListChecksItself:
    def _both_listed(self, tmp_path):
        _write_named(tmp_path, "v1.5.0", "# v1.5.0\n" + "\n".join(f"line {i}" for i in range(78)) + "\n")
        _write_named(tmp_path, "v1.5.4", "# v1.5.4\n\n| 8.1 | CI | TODO |\n")
        _write_named(tmp_path, "v9.9.9", _complete("v9.9.9"))
        _grandfather(tmp_path)

    def test_R_a_listed_stub_is_accepted_by_all_and_still_refused_by_default_mode(self, tmp_path):
        self._both_listed(tmp_path)
        assert _run_args(tmp_path, "--all").returncode == 0
        _write_named(tmp_path, "v9.9.10", "# v9.9.10\n\n| 8.1 | CI | TODO |\n")  # the latest doc is a new stub
        assert _run(tmp_path).returncode == 1, "grandfathering never applies to the latest doc"

    def test_R_a_listed_doc_that_became_clean_is_a_stale_entry(self, tmp_path):
        self._both_listed(tmp_path)
        _write_named(tmp_path, "v1.5.0", _complete("v1.5.0"))
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 1
        assert "STALE" in r.stdout and "docs/v1.5.0-verification.md" in r.stdout

    def test_R_a_listed_path_that_does_not_exist_is_an_error(self, tmp_path):
        _write_named(tmp_path, "v1.5.0", "# v1.5.0\n" + "\n".join(f"line {i}" for i in range(78)) + "\n")
        _write_named(tmp_path, "v9.9.9", _complete("v9.9.9"))
        _grandfather(tmp_path)
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 1 and "docs/v1.5.4-verification.md" in r.stdout and "does not exist" in r.stdout

    def test_R_without_a_grandfather_file_nothing_is_grandfathered_and_nothing_is_missing(self, tmp_path):
        _write_named(tmp_path, "v9.9.9", _complete("v9.9.9"))
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 0 and "0 grandfathered" in r.stdout

    def test_R_a_grandfather_entry_must_carry_a_reason(self, tmp_path):
        _write_named(tmp_path, "v9.9.9", _complete("v9.9.9"))
        _grandfather(tmp_path, {"docs/v1.5.0-verification.md": ""})
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 2 and "reason" in r.stderr

    def test_R_the_latest_doc_can_never_be_grandfathered(self, tmp_path):
        self._both_listed(tmp_path)
        _write_named(tmp_path, "v9.9.10", "# v9.9.10\n\n| 8.1 | CI | TODO |\n")
        _grandfather(tmp_path, {**ENTRIES, "docs/v9.9.10-verification.md": "listed on purpose; the latest doc is exempt from this"})
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 1 and "v9.9.10-verification.md" in r.stdout

    def test_C_an_unlisted_dirty_doc_fails_all(self, tmp_path):
        self._both_listed(tmp_path)
        _write_named(tmp_path, "v1.6.0", "# v1.6.0\n\n| 8.1 | CI | TODO |\n")
        r = _run_args(tmp_path, "--all")
        assert r.returncode == 1 and "v1.6.0-verification.md" in r.stdout


class TestFenceHandlingIsExact:
    def test_C_a_todo_in_a_fence_passes_and_the_same_todo_outside_fails(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "```\nTODO quoted evidence\n```\n"))
        assert _run(tmp_path).returncode == 0
        _write(tmp_path, _complete("v9.9.9", "TODO quoted evidence\n"))
        assert _run(tmp_path).returncode == 1

    def test_R_an_unclosed_fence_is_an_error_not_a_hiding_place(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "```\nsome output\n\nTODO the rest of the document is hidden\n"))
        r = _run(tmp_path)
        assert r.returncode == 1
        assert "unclosed code fence opened at line" in r.stdout

    def test_R_a_tilde_line_inside_a_backtick_fence_does_not_close_it(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "```\n~~~\nTODO still evidence\n```\n"))
        assert _run(tmp_path).returncode == 0

    def test_R_a_shorter_fence_inside_a_longer_one_does_not_close_it(self, tmp_path):
        _write(tmp_path, _complete("v9.9.9", "````\n```\nTODO still evidence\n```\n````\n"))
        assert _run(tmp_path).returncode == 0


class TestTheRealTree:
    def test_R_all_is_clean_on_the_repositorys_own_history(self):
        r = subprocess.run([sys.executable, str(TOOL), str(PROJECT_ROOT), "--all"], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout[-1500:]
        assert "grandfathered" in r.stdout

    def test_R_the_two_grandfathered_docs_are_the_ones_the_audit_measured_and_each_has_a_reason(self):
        entries = json.loads((PROJECT_ROOT / GRANDFATHER_FILE).read_text(encoding="utf-8"))
        assert set(entries) == {"docs/v1.5.0-verification.md", "docs/v1.5.4-verification.md"}
        assert all(len(reason) > 20 for reason in entries.values())
