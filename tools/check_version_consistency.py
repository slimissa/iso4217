#!/usr/bin/env python3
"""
Two-axis version consistency check for the ISO 4217 Currency Registry.

Two independent version axes are tracked:

  Registry axis — source of truth: VERSION at repo root.
      Eight sites must agree: VERSION, the first CHANGELOG heading,
      iso4217.json's meta.version, the Parquet footer's iso4217.version
      key, the README's registry-X.Y.Z badge, and the three wrapper
      package manifests (Python setup.py, JavaScript package.json,
      Rust Cargo.toml).

      The Parquet footer site is limited to the flat iso4217.parquet.
      iso4217.countries.parquet and the three aggregated Parquet files
      also carry iso4217.version, but they are deliberately not sites:
      their own --check modes already fail when the footer is stale
      (ADR 0007, docs/decisions/aggregated-layer-0007.md), so a site here
      would add maintenance without adding detection.

  Schema axis — source of truth: schema.json's $id trailing /vX.Y.Z/.
      Three sites must agree: iso4217.json's meta.schema_version,
      schema.json's $id itself, and the README's schema-X.Y.Z badge.

Two axes because the data version and the format contract version can
move independently. The data can be corrected (patch bump) without
changing the format contract; the schema can gain an optional field
(minor bump) without touching the data. Conflating them is how a repo
ends up with schema.json at 1.3.0, the README badge at 1.1.0, and a
validator constant at 1.0.0 in the same checkout.

Go is deliberately NOT a site. Go modules carry no version field in
go.mod; the module version is the git tag. Do not "fix" this by adding
a version to go.mod — the Go toolchain will ignore it and the ecosystem
will diverge from the other three wrappers.

Exit codes:
    0  every present site agrees with its axis
    1  one or more sites disagree (or errored)
    2  fatal: VERSION missing/unparseable, schema.json $id missing

Usage:
    python3 tools/check_version_consistency.py
    python3 tools/check_version_consistency.py --json
    python3 tools/check_version_consistency.py --verbose
    python3 tools/check_version_consistency.py --quiet
    python3 tools/check_version_consistency.py --site changelog
    python3 tools/check_version_consistency.py --root /path/to/other/checkout
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ROOT: Path = Path(__file__).resolve().parent.parent

EXIT_OK: int = 0
EXIT_MISMATCH: int = 1
EXIT_FATAL: int = 2

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# Exceptions — one per failure mode the extractors can signal
# ---------------------------------------------------------------------------

class PyarrowMissing(Exception):
    """pyarrow is not installed, so the Parquet site cannot be read."""


class FooterKeyMissing(Exception):
    """The Parquet file exists but has no iso4217.version footer key."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SiteResult:
    axis: str                     # "registry" or "schema"
    name: str                     # human-readable site label
    expected: Optional[str]       # axis source-of-truth value
    actual: Optional[str]         # value found at the site, or None
    status: str                   # "OK", "MISMATCH", "SKIP", "ERROR"
    note: str = ""                # extra context for SKIP or ERROR


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------
# Each extractor takes the project root and returns the version string found
# at that site, or None if the site file is absent. Absence is treated as
# SKIP, not FAIL, so the script lands cleanly on a partial checkout and
# becomes stricter as more wrapper manifests are added.
#
# Two extractors may raise:
#   - extract_parquet_footer_version raises PyarrowMissing (SKIP)
#     or FooterKeyMissing (MISMATCH)
# Any other exception is caught by the evaluator and reported as ERROR.


def extract_version_file(root: Path) -> Optional[str]:
    p = root / "VERSION"
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip()


def extract_changelog_version(root: Path) -> Optional[str]:
    """
    Find the first *released* version heading in CHANGELOG.md.

    A heading whose trailing text starts with "Unreleased" is skipped.
    It marks a staged release whose version sites have not yet been
    bumped. Before the release script runs, VERSION still points at the
    previous release, so requiring the top heading to match would make
    the release precondition unsatisfiable.

    Example:
        ## [1.6.0] — Unreleased      <- skipped
        ## [1.5.4] — 2026-09-26     <- returned
    """
    p = root / "CHANGELOG.md"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    for m in re.finditer(
        r"^##\s+\[?(\d+\.\d+\.\d+)\]?\s*(?:—|-)?\s*(.*)$",
        text,
        re.MULTILINE,
    ):
        trailing = m.group(2).strip()
        if trailing.lower().startswith("unreleased"):
            continue
        return m.group(1)
    return None


def extract_registry_meta_version(root: Path) -> Optional[str]:
    p = root / "iso4217.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("meta", {}).get("version")


def extract_registry_meta_schema_version(root: Path) -> Optional[str]:
    p = root / "iso4217.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("meta", {}).get("schema_version")


def extract_parquet_footer_version(root: Path) -> Optional[str]:
    """
    Read the iso4217.version key from the Parquet footer.

    Uses pyarrow.parquet.read_schema (not read_table) so only the file's
    metadata block is read — the 302 data rows are never loaded.
    """
    p = root / "iso4217.parquet"
    if not p.is_file():
        return None
    try:
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as e:
        raise PyarrowMissing(str(e)) from e

    schema = pq.read_schema(str(p))
    metadata = schema.metadata or {}
    raw = metadata.get(b"iso4217.version")
    if raw is None:
        raise FooterKeyMissing(
            "iso4217.version footer key missing from iso4217.parquet"
        )
    return raw.decode("utf-8")


def _extract_readme_badge(root: Path, prefix: str) -> Optional[str]:
    """
    Extract the X.Y.Z from a shields.io badge of the form:

        https://img.shields.io/badge/<prefix>-X.Y.Z-<color>.svg

    Anchored on 'badge/<prefix>-' so it will not accidentally match a
    version mentioned elsewhere in the README's prose.
    """
    p = root / "README.md"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    pattern = rf"badge/{re.escape(prefix)}-(\d+\.\d+\.\d+)-"
    m = re.search(pattern, text)
    return m.group(1) if m else None


def extract_readme_registry_badge(root: Path) -> Optional[str]:
    return _extract_readme_badge(root, "registry")


def extract_readme_schema_badge(root: Path) -> Optional[str]:
    return _extract_readme_badge(root, "schema")


def extract_python_setup_version(root: Path) -> Optional[str]:
    p = root / "wrappers" / "python" / "setup.py"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    m = re.search(
        r'^VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
        text,
        re.MULTILINE,
    )
    return m.group(1) if m else None


def extract_js_package_version(root: Path) -> Optional[str]:
    p = root / "wrappers" / "javascript" / "package.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("version")


def extract_rust_cargo_version(root: Path) -> Optional[str]:
    """
    Read version from the [package] table of Cargo.toml.

    A naive regex would also match 'version = "1"' in the [dependencies]
    table's `serde = { version = "1", ... }` line. This parser is
    section-aware: it finds the [package] header, then scans only the
    lines that follow until the next section header.
    """
    p = root / "wrappers" / "rust" / "Cargo.toml"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    in_package = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_package = stripped == "[package]"
            continue
        if in_package:
            m = re.match(r'^version\s*=\s*["\'](\d+\.\d+\.\d+)["\']', stripped)
            if m:
                return m.group(1)
    return None


def extract_schema_id_version(root: Path) -> Optional[str]:
    """
    Extract the X.Y.Z from schema.json's $id trailing /vX.Y.Z/ segment.

    $id looks like:
        https://raw.githubusercontent.com/slimissa/iso4217/v1.3.0/schema.json
    The trailing /vX.Y.Z/ is the schema's own version declaration.
    """
    p = root / "schema.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    schema_id = data.get("$id", "")
    m = re.search(r"/v(\d+\.\d+\.\d+)/", schema_id)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Site registry
# ---------------------------------------------------------------------------
# Order within each axis is the order shown in the report. Keep the two
# lists sorted by reading order for a maintainer, not alphabetically.

REGISTRY_SITES: list[tuple[str, Callable[[Path], Optional[str]]]] = [
    ("VERSION", extract_version_file),
    ("CHANGELOG.md (first heading)", extract_changelog_version),
    ("iso4217.json -> meta.version", extract_registry_meta_version),
    (
        "iso4217.parquet -> iso4217.version footer",
        extract_parquet_footer_version,
    ),
    ("README.md -> registry badge", extract_readme_registry_badge),
    ("wrappers/python/setup.py -> VERSION", extract_python_setup_version),
    (
        "wrappers/javascript/package.json -> version",
        extract_js_package_version,
    ),
    (
        "wrappers/rust/Cargo.toml -> [package].version",
        extract_rust_cargo_version,
    ),
]

SCHEMA_SITES: list[tuple[str, Callable[[Path], Optional[str]]]] = [
    (
        "iso4217.json -> meta.schema_version",
        extract_registry_meta_schema_version,
    ),
    ("schema.json -> $id", extract_schema_id_version),
    ("README.md -> schema badge", extract_readme_schema_badge),
]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _evaluate(
    axis: str,
    name: str,
    extractor: Callable[[Path], Optional[str]],
    root: Path,
    expected: str,
) -> SiteResult:
    """
    Run one extractor and classify the result.

    SKIP is returned when the site file is absent, when the value cannot
    be located within it, or when pyarrow is not installed for the
    Parquet site. SKIP sites do not fail the check.
    """
    try:
        actual = extractor(root)
    except PyarrowMissing as e:
        return SiteResult(
            axis, name, expected, None, "SKIP",
            f"pyarrow not installed ({e})",
        )
    except FooterKeyMissing as e:
        return SiteResult(axis, name, expected, None, "MISMATCH", str(e))
    except Exception as e:  # noqa: BLE001 — surface any read/parse error
        return SiteResult(
            axis, name, expected, None, "ERROR",
            f"{type(e).__name__}: {e}",
        )

    if actual is None:
        return SiteResult(
            axis, name, expected, None, "SKIP",
            "site file absent or value not found",
        )

    status = "OK" if actual == expected else "MISMATCH"
    return SiteResult(axis, name, expected, actual, status)


def run_checks(
    root: Path,
) -> tuple[Optional[str], Optional[str], list[SiteResult], list[str]]:
    """
    Read both axis sources of truth, then evaluate every site.

    Returns (expected_registry, expected_schema, results, fatal_messages).
    If fatal_messages is non-empty, results is empty and the caller must
    exit with EXIT_FATAL.
    """
    fatal: list[str] = []

    # Registry axis source of truth: VERSION file
    expected_registry: Optional[str] = None
    try:
        expected_registry = extract_version_file(root)
    except Exception as e:  # noqa: BLE001
        fatal.append(f"cannot read VERSION: {e}")

    if expected_registry is None and not fatal:
        fatal.append(f"VERSION file is missing or empty: {root / 'VERSION'}")
    elif expected_registry is not None and not SEMVER_RE.match(expected_registry):
        fatal.append(
            f"VERSION contains {expected_registry!r}, not a X.Y.Z version"
        )

    # Schema axis source of truth: schema.json $id
    expected_schema: Optional[str] = None
    try:
        expected_schema = extract_schema_id_version(root)
    except Exception as e:  # noqa: BLE001
        fatal.append(f"cannot read schema.json $id: {e}")

    if expected_schema is None and not any("schema.json" in m for m in fatal):
        fatal.append(
            "schema.json is missing or has no parseable /vX.Y.Z/ in $id"
        )

    if fatal:
        return expected_registry, expected_schema, [], fatal

    results: list[SiteResult] = []
    for name, extractor in REGISTRY_SITES:
        results.append(
            _evaluate("registry", name, extractor, root, expected_registry)
        )
    for name, extractor in SCHEMA_SITES:
        results.append(
            _evaluate("schema", name, extractor, root, expected_schema)
        )

    return expected_registry, expected_schema, results, fatal


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _status_glyph(status: str) -> str:
    return {
        "OK": "\u2713",        # check mark
        "MISMATCH": "\u2717",  # ballot X
        "SKIP": "\u00b7",      # middle dot
        "ERROR": "!",          # literal bang
    }.get(status, "?")


def report_text(
    expected_registry: str,
    expected_schema: str,
    results: list[SiteResult],
    root: Path,
    quiet: bool = False,
    verbose: bool = False,
) -> str:
    lines: list[str] = []
    rule = "=" * 78

    lines.append(rule)
    lines.append("  Version Consistency Check - ISO 4217 Currency Registry")
    lines.append(rule)
    lines.append(f"  Project root:  {root}")
    lines.append(f"  Registry axis: VERSION = {expected_registry}")
    lines.append(f"  Schema axis:   schema.json $id = {expected_schema}")
    lines.append(rule)
    lines.append("")

    name_width = max(len(r.name) for r in results) + 2

    for axis in ("registry", "schema"):
        axis_results = [r for r in results if r.axis == axis]
        if not axis_results:
            continue
        lines.append(f"  [{axis} axis]")
        for r in axis_results:
            glyph = _status_glyph(r.status)
            label = f"{r.name:<{name_width}}"

            if r.status == "OK":
                lines.append(f"    {glyph} {label} = {r.actual}")
            elif r.status == "MISMATCH":
                actual = r.actual if r.actual is not None else "(missing)"
                line = (
                    f"    {glyph} {label} = {actual}"
                    f"   (expected {r.expected})"
                )
                lines.append(line)
                if r.note:
                    lines.append(f"        note: {r.note}")
            elif r.status == "ERROR":
                lines.append(f"    {glyph} {label} = ERROR")
                if r.note:
                    lines.append(f"        note: {r.note}")
            else:  # SKIP
                if verbose and not quiet:
                    lines.append(f"    {glyph} {label} = SKIPPED ({r.note})")
                else:
                    lines.append(f"    {glyph} {label} = skipped")
        lines.append("")

    total = len(results)
    mismatches = [r for r in results if r.status == "MISMATCH"]
    errors = [r for r in results if r.status == "ERROR"]
    skips = [r for r in results if r.status == "SKIP"]
    failures = mismatches + errors

    lines.append(rule)
    if failures:
        parts = []
        if mismatches:
            parts.append(f"{len(mismatches)} mismatch")
            if len(mismatches) != 1:
                parts[-1] += "es"
        if errors:
            parts.append(f"{len(errors)} error")
            if len(errors) != 1:
                parts[-1] += "s"
        summary = " and ".join(parts)
        lines.append(f"  \u2717 FAIL - {summary} across {total} sites")
    else:
        lines.append(f"  \u2713 PASS - all {total - len(skips)} present sites agree")
    if skips and not verbose:
        lines.append(
            f"    ({len(skips)} site(s) skipped; run --verbose to see why)"
        )
    lines.append(rule)

    return "\n".join(lines)


def report_json(
    expected_registry: str,
    expected_schema: str,
    results: list[SiteResult],
    root: Path,
) -> str:
    failures = [r for r in results if r.status in ("MISMATCH", "ERROR")]
    payload = {
        "root": str(root),
        "registry_expected": expected_registry,
        "schema_expected": expected_schema,
        "pass": len(failures) == 0,
        "mismatch_count": len(failures),
        "sites": [
            {
                "axis": r.axis,
                "name": r.name,
                "expected": r.expected,
                "actual": r.actual,
                "status": r.status,
                "note": r.note,
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_version_consistency.py",
        description=(
            "Check that every version site agrees with its axis. "
            "Two axes are tracked: registry (source: VERSION) and "
            "schema (source: schema.json $id)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  every present site agrees with its axis\n"
            "  1  one or more sites disagree (or errored)\n"
            "  2  fatal: VERSION missing or schema.json $id unparseable\n"
        ),
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="emit machine-readable JSON instead of the text table",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="suppress per-site output; print only the summary line",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="include skip reasons and notes in the output",
    )
    parser.add_argument(
        "--site",
        metavar="SUBSTRING",
        default=None,
        help=(
            "only check sites whose name contains SUBSTRING "
            "(case-insensitive)"
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=(
            "project root to check "
            f"(default: {DEFAULT_ROOT})"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    expected_registry, expected_schema, results, fatal = run_checks(args.root)

    if fatal:
        for msg in fatal:
            print(f"FATAL: {msg}", file=sys.stderr)
        return EXIT_FATAL

    # --site filter applies before output so --json also honours it
    if args.site:
        needle = args.site.lower()
        results = [r for r in results if needle in r.name.lower()]
        if not results:
            print(
                f"FATAL: no sites matched --site {args.site!r}",
                file=sys.stderr,
            )
            return EXIT_FATAL

    if args.json:
        print(
            report_json(
                expected_registry or "",
                expected_schema or "",
                results,
                args.root,
            )
        )
    elif args.quiet:
        failures = [
            r for r in results if r.status in ("MISMATCH", "ERROR")
        ]
        if failures:
            print(
                f"FAIL: {len(failures)} of {len(results)} sites mismatched"
            )
            for r in failures:
                actual = r.actual if r.actual is not None else "(missing)"
                print(f"  {r.name}: {actual} (expected {r.expected})")
        else:
            print(f"PASS: all {len(results)} sites agree")
    else:
        print(
            report_text(
                expected_registry or "",
                expected_schema or "",
                results,
                args.root,
                quiet=args.quiet,
                verbose=args.verbose,
            )
        )

    failures = [r for r in results if r.status in ("MISMATCH", "ERROR")]
    return EXIT_MISMATCH if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())