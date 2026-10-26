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

With --membership it also compares currencies (ADR 0010). For each country,
the set of ACTIVE registry currencies listing it is compared with the
snapshot's `currency_codes` (null counts as empty), in both directions. Every
difference must be in docs/COUNTRY_CURRENCY_ALLOWLIST.md with a category and a
reason, and every allow-list entry must still match a difference.

Exit codes:
    0  every country code resolves (or, with --membership, every difference
       is allow-listed and no allow-list entry is stale)
    1  one or more unknown codes (or, with --membership, an unlisted
       difference, a stale entry or an invalid entry)
    2  fatal (missing files, malformed JSON, missing allow-list)

Usage:
    python3 tools/check_country_codes.py
    python3 tools/check_country_codes.py --json
    python3 tools/check_country_codes.py --membership
    python3 tools/check_country_codes.py --verbose
    python3 tools/check_country_codes.py --snapshot /path/to/snapshot.json
    python3 tools/check_country_codes.py --refresh-from /path/to/iso3166.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = PROJECT_ROOT / "iso4217.json"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "tools" / "iso3166_snapshot.json"
DEFAULT_ALLOWLIST = PROJECT_ROOT / "docs" / "COUNTRY_CURRENCY_ALLOWLIST.md"

SIDES = ("4217-only", "3166-only")
CATEGORIES = ("fix-in-3166", "allow-list-with-reason", "out-of-scope-historical")

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



# ---------------------------------------------------------------------------
# Membership: do the two standards name the same currencies? (ADR 0010)
# ---------------------------------------------------------------------------

Atom = tuple  # (country, currency, side)


def _currency_sets(registry: dict, snapshot: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(4217 country -> active currency codes, 3166 country -> currency_codes). Null counts as empty."""
    s4217: dict[str, set[str]] = {}
    for currency in registry.get("currencies", {}).get("active", []):
        for country in currency.get("countries", []):
            cc = country.get("code")
            if isinstance(cc, str):
                s4217.setdefault(cc, set()).add(currency.get("code", "?"))
    s3166: dict[str, set[str]] = {}
    for c in snapshot.get("countries", {}).get("active", []):
        a2 = c.get("alpha_2")
        if isinstance(a2, str):
            s3166[a2] = set(c.get("currency_codes") or [])
    return s4217, s3166


def disagreement_atoms(registry: dict, snapshot: dict) -> set:
    s4217, s3166 = _currency_sets(registry, snapshot)
    atoms: set = set()
    for country in set(s4217) | set(s3166):
        a, b = s4217.get(country, set()), s3166.get(country, set())
        atoms.update((country, cur, "4217-only") for cur in a - b)
        atoms.update((country, cur, "3166-only") for cur in b - a)
    return atoms


def load_allowlist(path: Path) -> list[dict]:
    """The entries of the first fenced json block in the allow-list file."""
    if not path.is_file():
        print(f"FATAL: allow-list not found at {path}", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    found = re.search(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    if not found:
        print(f"FATAL: {path} has no fenced json block", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    try:
        entries = json.loads(found.group(1)).get("entries")
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"FATAL: the json block in {path} is not valid: {e}", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    if not isinstance(entries, list):
        print(f"FATAL: {path} json block has no `entries` list", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    return entries


def check_membership(registry: dict, snapshot: dict, entries: list[dict]) -> dict[str, list[str]]:
    """Return the four kinds of failure. Every list empty means the check passes."""
    codes = _snapshot_codes(snapshot)
    invalid: list[str] = []
    listed: dict = {}
    for i, e in enumerate(entries):
        where = f"entry {i} ({e.get('country')}/{e.get('currency')}/{e.get('side')})"
        key = (e.get("country"), e.get("currency"), e.get("side"))
        if e.get("side") not in SIDES:
            invalid.append(f"{where}: side must be one of {SIDES}")
        if e.get("category") not in CATEGORIES:
            invalid.append(f"{where}: category {e.get('category')!r} is not one of {CATEGORIES}")
        for field in ("reason", "source"):
            if not (isinstance(e.get(field), str) and e[field].strip()):
                invalid.append(f"{where}: {field} is empty")
        if e.get("category") == "out-of-scope-historical" and not (isinstance(e.get("date"), str) and e["date"].strip()):
            invalid.append(f"{where}: out-of-scope-historical needs a date")
        if e.get("category") == "fix-in-3166" and not (isinstance(e.get("reference"), str) and e["reference"].strip()):
            invalid.append(f"{where}: fix-in-3166 needs a reference")
        if e.get("country") not in codes:
            invalid.append(f"{where}: country is not in the ISO 3166 snapshot")
        if key in listed:
            invalid.append(f"{where}: duplicate entry")
        listed[key] = e
    atoms = disagreement_atoms(registry, snapshot)
    unlisted = sorted(f"{c}: {cur} is {side}" for c, cur, side in atoms - set(listed))
    stale = sorted(f"{c}: {cur} {side} is allow-listed but no longer a disagreement" for c, cur, side in set(listed) - atoms)
    return {"unlisted": unlisted, "stale": stale, "invalid": invalid}


def report_membership(snapshot_version: str, total_atoms: int, result: dict[str, list[str]]) -> str:
    rule = "=" * 78
    lines = [rule, "  Country-Currency Membership - ISO 4217 vs ISO 3166 snapshot", rule,
             f"  Snapshot version:  {snapshot_version}", f"  Disagreements:     {total_atoms}", rule, ""]
    failed = False
    for label, key in (("UNLISTED disagreement", "unlisted"), ("STALE allow-list entry", "stale"),
                       ("INVALID allow-list entry", "invalid")):
        for item in result[key]:
            failed = True
            lines.append(f"    {label}: {item}")
    if failed:
        lines.insert(len(lines) - sum(len(v) for v in result.values()), "  FAIL")
    else:
        lines.append(f"  OK: all {total_atoms} disagreements are allow-listed and every entry is current")
    lines.append(rule)
    return "\n".join(lines)

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
        "--membership", action="store_true",
        help="compare currencies, not just codes, against docs/COUNTRY_CURRENCY_ALLOWLIST.md (ADR 0010)",
    )
    ap.add_argument(
        "--allowlist", type=Path, default=DEFAULT_ALLOWLIST,
        help=f"path to the allow-list (default: {DEFAULT_ALLOWLIST})",
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

    if args.membership:
        entries = load_allowlist(args.allowlist)
        result = check_membership(registry, snapshot, entries)
        total = len(disagreement_atoms(registry, snapshot))
        if args.json:
            print(json.dumps({"snapshot_version": snapshot_version, "disagreements": total, **result,
                              "pass": not any(result.values())}, indent=2, ensure_ascii=False))
        else:
            print(report_membership(snapshot_version, total, result))
        return EXIT_UNKNOWN if any(result.values()) else EXIT_OK

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