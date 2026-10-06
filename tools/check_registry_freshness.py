#!/usr/bin/env python3
"""
Snapshot freshness check for the ISO 4217 Currency Registry.

Reads iso4217.json's meta.updated field and fails if it is older than
a configurable threshold (default: 180 days).

Rationale for the 180-day default: ISO 4217 amendments are published
irregularly, and this registry detects new amendments but does not
ingest them automatically — a human applies each change. A single
missed cycle, roughly two quarterly windows, is a signal that the
review loop has stalled, not that the source is late. 180 days is one
clearly-missed cycle without being noisy on a healthy schedule.

The threshold is a suggestion, not a fact. Override it with
--threshold when a stricter or looser policy is warranted.

Exit codes:
    0  meta.updated is within threshold
    1  meta.updated is older than threshold
    2  fatal (missing file, invalid JSON, unparseable or future date)

Usage:
    python3 tools/check_snapshot_freshness.py
    python3 tools/check_snapshot_freshness.py --threshold 365
    python3 tools/check_snapshot_freshness.py --json
    python3 tools/check_snapshot_freshness.py --root /path/to/checkout
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_STALE = 1
EXIT_FATAL = 2

DEFAULT_THRESHOLD_DAYS = 180
# A date one day ahead of the runner's clock is a timezone artifact,
# not a data error. CI runs on UTC; a maintainer whose local time is
# ahead of UTC can set meta.updated to what is, from the runner's
# perspective, tomorrow. Allow up to this many days of skew before
# treating a future date as a real error.
FUTURE_TOLERANCE_DAYS = 1


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def read_meta_updated(root: Path) -> str:
    """
    Read iso4217.json's meta.updated field. Exits with EXIT_FATAL on any
    structural problem.
    """
    p = root / "iso4217.json"
    if not p.is_file():
        print(f"FATAL: registry not found: {p}", file=sys.stderr)
        sys.exit(EXIT_FATAL)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FATAL: invalid JSON in {p}: {e}", file=sys.stderr)
        sys.exit(EXIT_FATAL)

    updated = data.get("meta", {}).get("updated")
    if not isinstance(updated, str) or not updated:
        print(
            f"FATAL: meta.updated is missing or not a string in {p}",
            file=sys.stderr,
        )
        sys.exit(EXIT_FATAL)

    return updated


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD into a date object. Exits with EXIT_FATAL on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        print(
            f"FATAL: meta.updated is not a valid ISO 8601 date: {value!r}",
            file=sys.stderr,
        )
        sys.exit(EXIT_FATAL)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_text(
    updated: str,
    age_days: int,
    threshold: int,
    stale: bool,
    future: bool,
) -> str:
    lines = []
    rule = "=" * 78
    lines.append(rule)
    lines.append("  Snapshot Freshness Check - ISO 4217 Currency Registry")
    lines.append(rule)
    lines.append(f"  meta.updated:   {updated}")
    lines.append(f"  Age:            {age_days} day(s)")
    lines.append(f"  Threshold:      {threshold} day(s)")
    lines.append(rule)

    if future:
        lines.append(f"  ! meta.updated is in the future by {abs(age_days)} day(s)")
        lines.append("  ! This is a data error, not a freshness problem")
    elif stale:
        lines.append(
            f"  \u2717 STALE - {age_days} days since the last update "
            f"(threshold {threshold})"
        )
        lines.append("")
        lines.append("  Check for pending ISO amendments:")
        lines.append("    python3 tools/check_amendments.py")
        lines.append("")
        lines.append("  If no amendment is pending, update meta.updated")
        lines.append("  and document the reason in CHANGELOG.md.")
    else:
        lines.append(
            f"  \u2713 OK - {age_days} day(s) old "
            f"(threshold {threshold})"
        )

    lines.append(rule)
    return "\n".join(lines)


def report_json(
    updated: str,
    age_days: int,
    threshold: int,
    stale: bool,
    future: bool,
) -> str:
    return json.dumps(
        {
            "meta_updated": updated,
            "age_days": age_days,
            "threshold_days": threshold,
            "stale": stale,
            "future": future,
            "pass": (not stale) and (not future),
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_snapshot_freshness.py",
        description=(
            "Check that iso4217.json's meta.updated field is within "
            "the freshness threshold."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  within threshold\n"
            "  1  older than threshold\n"
            "  2  fatal (missing file, invalid JSON, unparseable date)\n"
        ),
    )
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD_DAYS,
        metavar="DAYS",
        help=(
            f"maximum allowed age in days "
            f"(default: {DEFAULT_THRESHOLD_DAYS})"
        ),
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="emit machine-readable JSON instead of the text report",
    )
    parser.add_argument(
        "--root", type=Path, default=PROJECT_ROOT,
        help=f"project root to check (default: {PROJECT_ROOT})",
    )
    parser.add_argument(
        "--today", metavar="YYYY-MM-DD", default=None,
        help="Override today's date, for testing.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.threshold < 1:
        print(
            f"FATAL: --threshold must be >= 1, got {args.threshold}",
            file=sys.stderr,
        )
        return EXIT_FATAL

    updated = read_meta_updated(args.root)
    snapshot_date = parse_iso_date(updated)
    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print(
                f"FATAL: --today is not a valid ISO 8601 date: {args.today!r}",
                file=sys.stderr,
            )
            return EXIT_FATAL
    else:
        today = date.today()
    delta = (today - snapshot_date).days

    # A future meta.updated is a data error, not a freshness issue.
    # Report it and fail — a snapshot dated in the future cannot be
    # trusted as "as of" any real moment.
    future = delta < -FUTURE_TOLERANCE_DAYS
    stale = delta > args.threshold

    if args.json:
        print(report_json(updated, delta, args.threshold, stale, future))
    else:
        print(report_text(updated, delta, args.threshold, stale, future))

    if future or stale:
        return EXIT_STALE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())