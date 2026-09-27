#!/usr/bin/env python3
"""
tools/check_snapshot_freshness.py

Reads every tools/*_snapshot.json and verifies that its
meta.review_by field is not in the past.

For each snapshot, the tool first looks for a sibling metadata
file at tools/<stem>.meta.json. If that file exists, review_by
and refresh_cadence are read from it. This is the vendored-
snapshot shape: when a snapshot is a byte-for-byte copy of an
external source, the cadence metadata lives in the sibling file
so the snapshot itself stays unmodified.

If no sibling exists, review_by is read from the snapshot's own
meta block.

Three-state design:

  - ISO date (YYYY-MM-DD)   fail if past, pass if future or today
  - "closed"                never checked; snapshot is static
  - null or missing         warn (not fail); review_by is unset

Usage:
    python3 tools/check_snapshot_freshness.py
    python3 tools/check_snapshot_freshness.py --json
    python3 tools/check_snapshot_freshness.py --today 2027-01-01

Exit codes:
    0  all snapshots fresh
    1  at least one snapshot is past due
    2  fatal (no snapshots found, malformed file)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_GLOB = "tools/*_snapshot.json"


def sibling_meta_path(snapshot_path: Path) -> Path:
    """Return tools/<stem>.meta.json for tools/<stem>.json."""
    return snapshot_path.with_name(snapshot_path.stem + ".meta.json")

EXIT_OK = 0
EXIT_STALE = 1
EXIT_FATAL = 2


class FatalError(SystemExit):
    def __init__(self, message: str, code: int = EXIT_FATAL) -> None:
        print(f"error: {message}", file=sys.stderr)
        super().__init__(code)


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FatalError(f"invalid ISO date: {value!r}") from exc


def evaluate(path: Path, today: date) -> dict[str, Any]:
    """
    Return a dict with keys: file, status, detail, review_by, meta_source.

    meta_source is one of:
      "sibling"   metadata was read from tools/<stem>.meta.json
      "snapshot"  metadata was read from the snapshot's own meta block

    status is one of:
      "fresh"    review_by is in the future or today
      "closed"   snapshot is static; never checked
      "unset"    review_by is missing or null; warning only
      "stale"    review_by is in the past
    """
    rel = str(path.relative_to(PROJECT_ROOT))

    # Prefer the sibling metadata file when it exists.
    sibling = sibling_meta_path(path)
    meta_source = "snapshot"
    if sibling.exists():
        try:
            data = json.loads(sibling.read_text(encoding="utf-8"))
        except OSError as exc:
            raise FatalError(f"{sibling}: cannot read: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FatalError(f"{sibling}: invalid JSON: {exc}") from exc
        meta_source = "sibling"
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise FatalError(f"{path}: cannot read: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FatalError(f"{path}: invalid JSON: {exc}") from exc

    meta = data.get("meta")

    if not isinstance(meta, dict):
        return {
            "file": rel,
            "status": "unset",
            "detail": "meta is missing or not an object",
            "review_by": None,
            "meta_source": meta_source,
        }

    review_by = meta.get("review_by")

    if review_by is None:
        return {
            "file": rel,
            "status": "unset",
            "detail": "review_by is not set",
            "review_by": None,
            "meta_source": meta_source,
        }

    if review_by == "closed":
        return {
            "file": rel,
            "status": "closed",
            "detail": "static snapshot, no review required",
            "review_by": "closed",
            "meta_source": meta_source,
        }

    if not isinstance(review_by, str):
        return {
            "file": rel,
            "status": "unset",
            "detail": f"review_by has unexpected type: {type(review_by).__name__}",
            "review_by": None,
            "meta_source": meta_source,
        }

    d = parse_iso_date(review_by)
    if d < today:
        return {
            "file": rel,
            "status": "stale",
            "detail": f"review_by {review_by} is past due",
            "review_by": review_by,
            "meta_source": meta_source,
        }

    return {
        "file": rel,
        "status": "fresh",
        "detail": f"review_by {review_by}",
        "review_by": review_by,
        "meta_source": meta_source,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_snapshot_freshness",
        description=(
            "Verify meta.review_by on every tools/*_snapshot.json. "
            "Exit 0 if all snapshots are fresh or marked closed."
        ),
    )
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON.")
    p.add_argument("--today", metavar="YYYY-MM-DD", default=None,
                   help="Override today's date, for testing.")
    return p


def report_text(results: list[dict[str, Any]], today: date) -> None:
    rule = "=" * 78
    print(rule)
    print("  Snapshot freshness check")
    print(rule)
    print(f"  Today:     {today.isoformat()}")
    print(f"  Snapshots: {len(results)}")
    print(rule)
    for r in results:
        marker = {
            "fresh":  "OK  ",
            "closed": "SKIP",
            "unset":  "WARN",
            "stale":  "FAIL",
        }[r["status"]]
        source = r.get("meta_source", "snapshot")
        suffix = " (sibling)" if source == "sibling" else ""
        print(f"  [{marker}] {r['file']}: {r['detail']}{suffix}")
    print(rule)

    stale = [r for r in results if r["status"] == "stale"]
    unset = [r for r in results if r["status"] == "unset"]

    if stale:
        print(f"  FAIL: {len(stale)} snapshot(s) past due")
    elif unset:
        print(f"  OK with {len(unset)} warning(s): review_by unset")
    else:
        print("  OK: all snapshots fresh")
    print(rule)


def report_json(results: list[dict[str, Any]], today: date) -> None:
    payload = {
        "today": today.isoformat(),
        "total": len(results),
        "fresh": sum(1 for r in results if r["status"] == "fresh"),
        "closed": sum(1 for r in results if r["status"] == "closed"),
        "unset": sum(1 for r in results if r["status"] == "unset"),
        "stale": sum(1 for r in results if r["status"] == "stale"),
        "results": results,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    today = parse_iso_date(args.today) if args.today else date.today()

    snapshots = sorted(PROJECT_ROOT.glob(SNAPSHOT_GLOB))
    if not snapshots:
        raise FatalError(f"no files matched {SNAPSHOT_GLOB} under {PROJECT_ROOT}")

    results = [evaluate(p, today) for p in snapshots]

    if args.json:
        report_json(results, today)
    else:
        report_text(results, today)

    return EXIT_STALE if any(r["status"] == "stale" for r in results) else EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FatalError as exc:
        sys.exit(exc.code)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
