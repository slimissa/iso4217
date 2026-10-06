"""
Tests for tools/check_registry_freshness.py.

Covers:
  - The --today flag (added in v1.7.6) for exercising timezone
    tolerance without changing the system clock.
  - Timezone tolerance: 0 and -1 day pass; -2 days fail.
  - Threshold behavior: meta.updated within / past the threshold.
  - Fatal paths: missing registry, invalid dates, malformed JSON.
  - --json output mode.

Every test writes a synthetic iso4217.json in a temp directory and
runs the tool against it. Nothing reads the repository's real
registry except the last test class.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.check_registry_freshness import (
    EXIT_FATAL,
    EXIT_OK,
    EXIT_STALE,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_registry(root: Path, updated: str | None = "2026-10-07",
                    version: str = "1.0.0") -> Path:
    """
    Write a minimal iso4217.json. The tool reads only meta.updated;
    the rest is there so the file is a plausible registry and any
    future schema check would not choke.
    """
    meta: dict = {"version": version}
    if updated is not None:
        meta["updated"] = updated
    registry = {
        "meta": meta,
        "source": {"last_amendment_applied": 1},
        "currencies": {"active": [], "withdrawn": []},
    }
    p = root / "iso4217.json"
    p.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return p


def _run(argv: list[str]) -> int:
    """
    Call main() and normalize the exit code. The tool raises SystemExit
    for fatal paths (missing file, unparseable date) and returns an int
    for pass/stale paths.
    """
    try:
        return main(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return exc.code if isinstance(exc.code, int) else 1


# ---------------------------------------------------------------------------
# --today flag
# ---------------------------------------------------------------------------

class TestTodayFlag:
    """
    The --today flag exists so tests can exercise the timezone-tolerance
    behavior without changing the runner's system clock. It was added
    in v1.7.6 as a follow-up to the CI failure of the v1.7.5 release.
    """

    def test_today_equals_meta_updated(self, tmp_path, capsys):
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-07"])
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "0 day(s)" in out

    def test_today_one_day_before_meta_updated_tolerated(self, tmp_path, capsys):
        # CI runs on UTC. A maintainer whose local time is ahead of UTC
        # can write meta.updated to what the runner sees as "tomorrow".
        # One day of skew is a timezone artifact, not a data error.
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-06"])
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "-1 day(s)" in out
        assert "future" not in out.lower()

    def test_today_two_days_before_meta_updated_fails(self, tmp_path, capsys):
        # Two days ahead is beyond timezone skew. The tool reports the
        # meta.updated as a future date and exits stale.
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-05"])
        assert code == EXIT_STALE
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "future" in combined.lower()
        assert "2 day(s)" in combined

    def test_today_old_date_within_threshold(self, tmp_path, capsys):
        _write_registry(tmp_path, updated="2026-06-01")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-01"])
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "122 day(s)" in out

    def test_today_old_date_past_threshold_fails(self, tmp_path):
        _write_registry(tmp_path, updated="2025-01-01")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-01"])
        assert code == EXIT_STALE

    def test_invalid_today_value_fatal(self, tmp_path):
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run(["--root", str(tmp_path), "--today", "not-a-date"])
        assert code == EXIT_FATAL


# ---------------------------------------------------------------------------
# --threshold flag
# ---------------------------------------------------------------------------

class TestThresholdFlag:

    def test_custom_threshold_within(self, tmp_path):
        # 30 days old, custom threshold 60 -> pass
        _write_registry(tmp_path, updated="2026-09-01")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-01",
            "--threshold", "60",
        ])
        assert code == EXIT_OK

    def test_custom_threshold_past(self, tmp_path):
        # 30 days old, custom threshold 10 -> fail
        _write_registry(tmp_path, updated="2026-09-01")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-01",
            "--threshold", "10",
        ])
        assert code == EXIT_STALE

    def test_zero_threshold_rejected(self, tmp_path):
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-07",
            "--threshold", "0",
        ])
        assert code == EXIT_FATAL


# ---------------------------------------------------------------------------
# Fatal paths
# ---------------------------------------------------------------------------

class TestFatalPaths:

    def test_missing_registry(self, tmp_path, capsys):
        # No file written
        code = _run(["--root", str(tmp_path), "--today", "2026-10-07"])
        assert code == EXIT_FATAL
        err = capsys.readouterr().err
        assert "registry not found" in err.lower() or "FATAL" in err

    def test_invalid_json(self, tmp_path):
        (tmp_path / "iso4217.json").write_text("{not json", encoding="utf-8")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-07"])
        assert code == EXIT_FATAL

    def test_missing_meta_updated(self, tmp_path):
        _write_registry(tmp_path, updated=None)
        code = _run(["--root", str(tmp_path), "--today", "2026-10-07"])
        assert code == EXIT_FATAL

    def test_invalid_meta_updated(self, tmp_path):
        _write_registry(tmp_path, updated="not-a-date")
        code = _run(["--root", str(tmp_path), "--today", "2026-10-07"])
        assert code == EXIT_FATAL


# ---------------------------------------------------------------------------
# --json output
# ---------------------------------------------------------------------------

class TestJsonOutput:

    def test_json_shape_on_pass(self, tmp_path, capsys):
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-07",
            "--json",
        ])
        assert code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta_updated"] == "2026-10-07"
        assert payload["threshold_days"] == 180
        assert payload["age_days"] == 0
        assert payload["pass"] is True
        assert payload["stale"] is False
        assert payload["future"] is False

    def test_json_shape_on_stale(self, tmp_path, capsys):
        _write_registry(tmp_path, updated="2024-01-01")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-07",
            "--json",
        ])
        assert code == EXIT_STALE
        payload = json.loads(capsys.readouterr().out)
        assert payload["pass"] is False
        assert payload["stale"] is True
        assert payload["future"] is False

    def test_json_shape_on_future(self, tmp_path, capsys):
        _write_registry(tmp_path, updated="2026-10-07")
        code = _run([
            "--root", str(tmp_path),
            "--today", "2026-10-05",
            "--json",
        ])
        assert code == EXIT_STALE
        payload = json.loads(capsys.readouterr().out)
        assert payload["future"] is True


# ---------------------------------------------------------------------------
# The real registry
# ---------------------------------------------------------------------------

class TestRealRegistry:
    """
    One test against the committed iso4217.json. If this fails, the
    registry on disk is stale relative to the default threshold, or
    the tool's default root is wrong.
    """

    def test_current_registry_is_fresh(self, capsys):
        code = _run([])
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "OK" in out