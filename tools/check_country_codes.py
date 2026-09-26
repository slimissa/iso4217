#!/usr/bin/env python3
"""
Check that every country code referenced by the ISO 4217 registry
resolves in a vendored ISO 3166 snapshot.

Every `currencies.{active,withdrawn}[].countries[].code` in
iso4217.json is an ISO 3166-1 alpha-2 country code. This tool
verifies that each one exists in the snapshot's
`countries.active[].alpha_2` set.

The snapshot is a byte-for-byte copy of ISO 3166's `iso3166.json`,
checked into `tools/iso3166_snapshot.json`. Refresh it with
`--refresh-from <path>` when ISO 3166 publishes a new release.

Exit codes:
    0  every country code resolves
    1  one or more unknown codes
    2  fatal (missing files, malformed JSON)

Usage:
    python3 tools/check_country_codes.py
    python3 tools/check_country_codes.py --json
    python3 tools/check_country_codes.py --verbose
    python3 tools/check_country_codes.py --snapshot /path/to/snapshot.json
    python3 tools/check_country_codes.py --refresh-from /path/to/iso3166.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = PROJECT_ROOT / "iso4217.json"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "tools" / "iso3166_snapshot.json"

EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_FATAL = 2


def _load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        print(f"FATAL: {label} not found at {path}", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FATAL: {label} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(EXIT_FATAL)


def _snapshot_codes(snapshot: dict) -> set[str]:
    """
    Extract the set of alpha-2 codes from the snapshot's active
    countries. The snapshot is ISO 3166's `iso3166.json`, whose shape
    is `{"countries": {"active": [{"alpha_2": "US", ...}, ...]}}`.
    """
    codes: set[str] = set()
    for c in snapshot.get("countries", {}).get("active", []):
        a2 = c.get("alpha_2")
        if isinstance(a2, str):
            codes.add(a2)
    return codes


def _registry_references(registry: dict) -> list[tuple[str, str]]:
    """
    Return every (currency_code, country_code) pair referenced by the
    registry. Covers active and withdrawn currencies.
    """
    refs: list[tuple[str, str]] = []
    for section in ("active", "withdrawn"):
        for currency in registry.get("currencies", {}).get(section, []):
            currency_code = currency.get("code", "?")
            for country in currency.get("countries", []):
                cc = country.get("code")
                if isinstance(cc, str):
                    refs.append((currency_code, cc))
    return refs


def report_text(
    snapshot_version: str,
    unique_codes: int,
    total_refs: int,
    unknown: list[tuple[str, str]],
    verbose: bool,
) -> str:
    rule = "=" * 78
    lines = [
        rule,
        "  Country Code Check - ISO 4217 -> ISO 3166 snapshot",
        rule,
        f"  Snapshot version: {snapshot_version}",
        f"  Unique codes:     {unique_codes}",
        f"  Total references: {total_refs}",
        rule,
        "",
    ]

    if not unknown:
        lines.append(
            f"  OK: every referenced code resolves in the snapshot"
        )
        lines.append(rule)
        return "\n".join(lines)

    lines.append(f"  FAIL: {len(unknown)} unknown code reference(s)")
    lines.append("")
    for currency_code, country_code in unknown[:50]:
        lines.append(f"    {currency_code}: country code {country_code!r} not in snapshot")
    if len(unknown) > 50:
        lines.append(f"    ... and {len(unknown) - 50} more")
    lines.append("")
    lines.append(rule)
    return "\n".join(lines)


def report_json(
    snapshot_version: str,
    unique_codes: int,
    total_refs: int,
    unknown: list[tuple[str, str]],
) -> str:
    return json.dumps(
        {
            "snapshot_version": snapshot_version,
            "unique_codes": unique_codes,
            "total_references": total_refs,
            "unknown_count": len(unknown),
            "unknown": [{"currency": c, "country": cc} for c, cc in unknown],
            "pass": len(unknown) == 0,
        },
        indent=2,
        ensure_ascii=False,
    )


def refresh_snapshot(source: Path, dest: Path) -> None:
    if not source.is_file():
        print(f"FATAL: --refresh-from source not found: {source}", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    shutil.copyfile(source, dest)
    print(f"Refreshed {dest} from {source}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="check_country_codes.py",
        description=(
            "Verify every countries[].code in iso4217.json resolves "
            "in the vendored ISO 3166 snapshot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  every code resolves\n"
            "  1  one or more unknown codes\n"
            "  2  fatal\n"
        ),
    )
    ap.add_argument(
        "--registry", type=Path, default=DEFAULT_REGISTRY,
        help=f"path to iso4217.json (default: {DEFAULT_REGISTRY})",
    )
    ap.add_argument(
        "--snapshot", type=Path, default=DEFAULT_SNAPSHOT,
        help=f"path to the ISO 3166 snapshot (default: {DEFAULT_SNAPSHOT})",
    )
    ap.add_argument(
        "--refresh-from", type=Path, default=None, metavar="PATH",
        help="replace the snapshot with a fresh ISO 3166 iso3166.json, then check",
    )
    ap.add_argument("--json", "-j", action="store_true", help="JSON output")
    ap.add_argument("--verbose", "-v", action="store_true", help="extra detail")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.refresh_from is not None:
        refresh_snapshot(args.refresh_from, args.snapshot)

    snapshot = _load_json(args.snapshot, "ISO 3166 snapshot")
    registry = _load_json(args.registry, "ISO 4217 registry")

    snapshot_version = snapshot.get("meta", {}).get("version", "unknown")
    valid = _snapshot_codes(snapshot)
    refs = _registry_references(registry)

    unique_referenced = {cc for _, cc in refs}
    unknown = [(cur, cc) for cur, cc in refs if cc not in valid]

    # Deduplicate unknown pairs
    seen: set[tuple[str, str]] = set()
    unique_unknown: list[tuple[str, str]] = []
    for pair in unknown:
        if pair not in seen:
            seen.add(pair)
            unique_unknown.append(pair)

    if args.json:
        print(report_json(snapshot_version, len(unique_referenced),
                          len(refs), unique_unknown))
    else:
        print(report_text(snapshot_version, len(unique_referenced),
                          len(refs), unique_unknown, args.verbose))

    return EXIT_UNKNOWN if unique_unknown else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())