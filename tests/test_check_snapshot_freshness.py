"""
Tests for tools/check_snapshot_freshness.py.

The tool globs tools/*_snapshot.json under its module-level
PROJECT_ROOT. These tests monkeypatch PROJECT_ROOT to point at a
temp directory so every case is isolated.

The --today flag is already present on this tool; the tests here
exercise it in the same way as the registry-freshness tests do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_snapshot_freshness as csf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_root(tmp_path: Path) -> Path:
    """
    Create tmp_path/tools/ so the tool's glob finds what we place
    there. Returns the root (the parent of tools/).
    """
    (tmp_path / "tools").mkdir()
    return tmp_path


def _write_snapshot(root: Path, stem: str, *, review_by,
                    sibling: bool = False) -> None:
    """
    Write tools/<stem>.json with meta.review_by. If sibling is True,
    also write tools/<stem>.meta.json with the same review_by — the
    tool then reads the sibling, not the snapshot.
    """
    snap = root / "tools" / f"{stem}.json"
    snap.write_text(
        json.dumps({"meta": {"review_by": review_by}}),
        encoding="utf-8",
    )
    if sibling:
        meta = root / "tools" / f"{stem}.meta.json"
        meta.write_text(
            json.dumps({"meta": {"review_by": review_by}}),
            encoding="utf-8",
        )


def _run(monkeypatch, root: Path, argv: list[str]) -> int:
    monkeypatch.setattr(csf, "PROJECT_ROOT", root)
    try:
        return csf.main(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return exc.code if isinstance(exc.code, int) else 1


# ---------------------------------------------------------------------------
# --today against a single snapshot
# ---------------------------------------------------------------------------

class TestTodayFlag:

    def test_future_review_by_is_ok(self, tmp_path, monkeypatch):
        root = _build_root(tmp_path)
        _write_snapshot(root, "foo_snapshot", review_by="2027-01-01")
        assert _run(monkeypatch, root, ["--today", "2026-10-07"]) == 0

    def test_review_by_equals_today_is_ok(self, tmp_path, monkeypatch):
        root = _build_root(tmp_path)
        _write_snapshot(root, "foo_snapshot", review_by="2026-10-07")
        assert _run(monkeypatch, root, ["--today", "2026-10-07"]) == 0

    def test_review_by_yesterday_is_stale(self, tmp_path, monkeypatch):
        root = _build_root(tmp_path)
        _write_snapshot(root, "foo_snapshot", review_by="2026-10-06")
        assert _run(monkeypatch, root, ["--today", "2026-10-07"]) == 1


# ---------------------------------------------------------------------------
# closed and unset states
# ---------------------------------------------------------------------------

class TestThreeStateDesign:

    def test_closed_is_never_stale(self, tmp_path, monkeypatch):
        root = _build_root(tmp_path)
        _write_snapshot(root, "static_snapshot", review_by="closed")
        # Even far in the future, closed never fails
        assert _run(monkeypatch, root, ["--today", "2099-01-01"]) == 0

    def test_unset_is_a_warning_not_a_failure(self, tmp_path, monkeypatch, capsys):
        root = _build_root(tmp_path)
        _write_snapshot(root, "no_date_snapshot", review_by=None)
        code = _run(monkeypatch, root, ["--today", "2026-10-07"])
        assert code == 0
        out = capsys.readouterr().out
        assert "unset" in out.lower() or "WARN" in out

    def test_missing_snapshot_directory_is_fatal(self, tmp_path, monkeypatch):
        # No tools/ directory at all
        monkeypatch.setattr(csf, "PROJECT_ROOT", tmp_path)
        code = _run(monkeypatch, tmp_path, ["--today", "2026-10-07"])
        assert code == 2


# ---------------------------------------------------------------------------
# sibling metadata
# ---------------------------------------------------------------------------

class TestSiblingMetadata:

    def test_sibling_is_preferred(self, tmp_path, monkeypatch, capsys):
        root = _build_root(tmp_path)
        # Snapshot carries a stale date; the sibling carries a future one.
        _write_snapshot(root, "vendored_snapshot", review_by="2020-01-01")
        (root / "tools" / "vendored_snapshot.meta.json").write_text(
            json.dumps({"meta": {"review_by": "2027-01-01"}}),
            encoding="utf-8",
        )
        code = _run(monkeypatch, root, ["--today", "2026-10-07"])
        # Sibling's future date wins -> pass
        assert code == 0
        out = capsys.readouterr().out
        assert "sibling" in out.lower()

    def test_snapshot_used_when_no_sibling(self, tmp_path, monkeypatch):
        root = _build_root(tmp_path)
        _write_snapshot(root, "self_dated_snapshot", review_by="2027-01-01")
        assert _run(monkeypatch, root, ["--today", "2026-10-07"]) == 0