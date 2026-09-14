#!/usr/bin/env python3
"""
CSV/TSV export generator for the ISO 4217 Currency Registry (v1.5.0).

Generates four dialect-specific flat files at the repository root:
    iso4217.csv              — RFC 4180 comma-separated (universal default)
    iso4217.excel.csv        — Excel-compatible (UTF-8 BOM), comma-separated
    iso4217.european.csv     — Semicolon-delimited (European Excel locales)
    iso4217.tsv              — Tab-separated (clipboard and terminal)

Design invariants
-----------------
- **Every row is sorted by currency code, ascending.** Active rows first,
  then withdrawn. Determinism is required so that CI diffing (--check mode)
  has no false positives.

- **Non-ISO entries are excluded.** Active + withdrawn ISO 4217 only.
  Crypto, stablecoins, commodities, and special-purpose codes belong in a
  future `non_iso_instruments` export (v1.6.0+), not in this seed.

- **Generated files are committed.** Regeneration is manual (or run under
  --check in CI to detect drift).

- **Atomic writes.** Each file is written to a temporary sibling and then
  renamed into place, so a crash mid-write never leaves a partial file.

- **No timestamps in output.** Nothing derived from the current wall-clock
  time appears in any file. The registry's own `meta.updated` is not even
  emitted — CSV has no comment syntax — so output is deterministic forever.

- **LF line endings in all four files.** RFC 4180 specifies CRLF, but every
  modern parser (Python csv, Go encoding/csv, Rust csv, JS csv-parse,
  pandas, Excel 2016+) accepts LF. CRLF would produce noisy diffs and
  break --check on Windows checkouts where git rewrote line endings. The
  repository's .gitattributes enforces LF as a second line of defense.

- **Quote-when-needed.** Quoting is delegated to Python's csv module with
  QUOTE_MINIMAL. A field is quoted if and only if it contains the dialect's
  delimiter, a double quote, CR, or LF. Fields are never quoted
  unnecessarily — that keeps diffs minimal and stable across regeneration.

Schema
------
Eleven columns, all dialects, same names, same order:

    code            ISO 4217 alphabetic code (e.g. USD)
    numeric_code    ISO 4217 numeric code as text (preserves leading zeros)
    name            English name
    minor_units     Decimal places, 0..18
    symbol          Display symbol (may be empty)
    entity          Issuing entity (may be empty)
    status          'active' or 'withdrawn'
    is_independent  'true' or 'false'
    pegged_to       Anchor currency code, basket description, or empty
    peg_type        'single', 'basket', 'undisclosed', or empty
    peg_rate        Anchor rate, or empty for basket/undisclosed pegs

The first seven columns have the same names as the SQL export's columns, so
a join between the two exports is a straight comparison on `code`. The CSV
export adds the four peg columns SQL deliberately omits; the SQL export
carries withdrawn/replacement metadata the CSV export deliberately omits.

Deliberately excluded: countries, central banks, withdrawn-date and
replacement metadata, notes, and non-ISO instruments.

BOM policy
----------
Only iso4217.excel.csv carries a UTF-8 BOM (EF BB BF at the start of file).
Excel on Windows uses the BOM to auto-detect UTF-8 and render symbols like
¥, €, and د.ك correctly; without it, Excel guesses the code page and shows
mojibake. Every other consumer treats a leading BOM as a phantom first
field and would produce a spurious header column, so only this dialect
carries one. The BOM is emitted as Unicode codepoint U+FEFF at the start
of the string; writing with encoding='utf-8' turns it into the three bytes
on disk.

Usage
-----
    # Regenerate all four files (default)
    python3 tools/export_csv.py

    # Regenerate one dialect
    python3 tools/export_csv.py --dialect european

    # Print one dialect to stdout
    python3 tools/export_csv.py --dialect tsv --stdout

    # CI check — exit 0 if all committed files match, 1 if any differ,
    # 3 if any are missing
    python3 tools/export_csv.py --check

Exit codes
----------
    0 — Success (files written, or --check passed)
    1 — --check mismatch
    2 — Fatal error (missing registry, invalid JSON, write failure)
    3 — --check found one or more missing files
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
REGISTRY_PATH: Path = PROJECT_ROOT / "iso4217.json"

REPOSITORY_URL: str = "https://github.com/slimissa/iso4217"
LICENSE_NAME: str = "Apache 2.0"

# Dialect name → output filename
DIALECT_FILES: dict[str, str] = {
    "rfc": "iso4217.csv",
    "excel": "iso4217.excel.csv",
    "european": "iso4217.european.csv",
    "tsv": "iso4217.tsv",
}

# Dialect name → field delimiter
DIALECT_DELIMITERS: dict[str, str] = {
    "rfc": ",",
    "excel": ",",
    "european": ";",
    "tsv": "\t",
}

# Dialect name → whether to prefix the file with a UTF-8 BOM.
# Only the Excel dialect needs it; every other parser treats a leading
# BOM as a phantom first field and would produce a spurious header column.
DIALECT_BOM: dict[str, bool] = {
    "rfc": False,
    "excel": True,
    "european": False,
    "tsv": False,
}

# Dialect name → human-readable label (parallel to export_sql.py's labels;
# used in error messages and future log lines).
DIALECT_LABELS: dict[str, str] = {
    "rfc": "RFC 4180 comma-separated",
    "excel": "Excel-compatible (UTF-8 BOM), comma-separated",
    "european": "Semicolon-delimited (European locales)",
    "tsv": "Tab-separated",
}

# Column names, in output order. Identical for all four dialects. The
# first seven match the SQL export's column names exactly, so joining
# the two exports on `code` is straightforward.
COLUMNS: tuple[str, ...] = (
    "code",
    "numeric_code",
    "name",
    "minor_units",
    "symbol",
    "entity",
    "status",
    "is_independent",
    "pegged_to",
    "peg_type",
    "peg_rate",
)

# Exit codes (aligned with export_sql.py, refresh_market_caps.py, and
# sync_wrappers.py).
EXIT_OK: int = 0
EXIT_MISMATCH: int = 1
EXIT_FATAL: int = 2
EXIT_MISSING: int = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrencyRow:
    """
    A single currency as it will appear in every CSV/TSV file.

    Every field is a string because CSV has no type system. Numeric fields
    (minor_units, peg_rate) are pre-formatted here so the renderer stays a
    pure stringification pass. `repr()` of a Python float gives the
    shortest representation that round-trips back to the same value, so
    "3.6725" stays "3.6725" and never becomes "3.6725000000000003".

    Frozen so rows can be put in sets or dicts without surprises.
    `status` is either "active" or "withdrawn".
    """
    code: str
    numeric_code: str
    name: str
    minor_units: str
    symbol: str
    entity: str
    status: str
    is_independent: str
    pegged_to: str
    peg_type: str
    peg_rate: str

    def as_tuple(self) -> tuple[str, ...]:
        """Return the row as a tuple in COLUMNS order."""
        return (
            self.code,
            self.numeric_code,
            self.name,
            self.minor_units,
            self.symbol,
            self.entity,
            self.status,
            self.is_independent,
            self.pegged_to,
            self.peg_type,
            self.peg_rate,
        )


@dataclass
class Registry:
    """
    The parsed registry, reduced to exactly what the exporter needs.
    Keeping only the header-relevant metadata plus the two currency arrays
    means the export logic never has to touch anything else in the JSON.
    """
    version: str
    updated: str
    amendment: int
    rows: list[CurrencyRow]

    @property
    def active_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "active")

    @property
    def withdrawn_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "withdrawn")

    @property
    def total_count(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def _fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(EXIT_FATAL)


def load_registry(path: Path) -> Registry:
    """
    Load, validate, and reduce the registry to a `Registry` object.

    Any structural problem exits with EXIT_FATAL and a message that names
    the specific code or field at fault, so a maintainer can jump straight
    to the offending entry.

    The loading logic is intentionally parallel to tools/export_sql.py's
    loader — same validation, same error messages, same sort order. The
    two loaders are deliberately duplicated rather than shared, because a
    shared loader that drifts is worse than two loaders that must be kept
    in sync by a test. If you change one, change both.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        _fatal(f"Registry not found: {path}")
    except json.JSONDecodeError as e:
        _fatal(f"Invalid JSON in {path}: {e}")

    # Metadata
    meta = data.get("meta")
    if not isinstance(meta, dict):
        _fatal("Registry is missing 'meta' object")

    version = meta.get("version")
    updated = meta.get("updated")
    if not isinstance(version, str) or not version:
        _fatal("meta.version is missing or not a string")
    if not isinstance(updated, str) or not updated:
        _fatal("meta.updated is missing or not a string")

    source = data.get("source", {})
    amendment = source.get("last_amendment_applied")
    if not isinstance(amendment, int):
        _fatal("source.last_amendment_applied is missing or not an integer")

    # Currencies
    currencies = data.get("currencies")
    if not isinstance(currencies, dict):
        _fatal("Registry is missing 'currencies' object")

    rows: list[CurrencyRow] = []
    for status_key, status_value in (("active", "active"), ("withdrawn", "withdrawn")):
        entries = currencies.get(status_key, [])
        if not isinstance(entries, list):
            _fatal(f"currencies.{status_key} is not an array")

        for entry in entries:
            rows.append(_row_from_entry(entry, status_value))

    # Deterministic ordering: sort by code, ascending. Active rows first,
    # then withdrawn. Identical to tools/export_sql.py's ordering, so a
    # row-by-row join between the two exports is a straight comparison.
    active_rows = sorted((r for r in rows if r.status == "active"), key=lambda r: r.code)
    withdrawn_rows = sorted((r for r in rows if r.status == "withdrawn"), key=lambda r: r.code)
    ordered = active_rows + withdrawn_rows

    return Registry(
        version=version,
        updated=updated,
        amendment=amendment,
        rows=ordered,
    )


def _row_from_entry(entry: dict, status: str) -> CurrencyRow:
    """
    Convert one registry entry into a CurrencyRow.

    Missing optional fields (symbol, entity) default to empty strings
    rather than failing, because both are optional in the schema.

    Peg fields default to empty strings for the same reason: withdrawn
    currencies never carry peg metadata, and independent currencies
    deliberately leave it absent. An empty CSV field between two
    delimiters is the correct representation of "not applicable".

    `is_independent` defaults to "false" when the field is absent, which
    is the conservative choice. Silently reporting a pegged currency as
    independent is a correctness bug no downstream consumer would notice;
    reporting an independent currency as not-independent is visible in
    any filter and easy to correct.
    """
    code = entry.get("code")
    # Active codes are always exactly 3 uppercase letters. Withdrawn codes
    # may be up to 7 chars (schema pattern: ^[A-Z][A-Z0-9_]{2,6}$) to
    # accommodate revaluation cases like MXN_OLD.
    if (
        not isinstance(code, str)
        or len(code) < 3
        or len(code) > 7
        or not code[0].isupper()
        or not all(c.isupper() or c.isdigit() or c == "_" for c in code)
    ):
        _fatal(f"Invalid or missing 'code' in {status} entry: {entry!r}")

    numeric = entry.get("numeric")
    if not isinstance(numeric, str) or len(numeric) != 3 or not numeric.isdigit():
        _fatal(f"Invalid or missing 'numeric' for {code}: {numeric!r}")

    name = entry.get("name")
    if not isinstance(name, str) or not name:
        _fatal(f"Invalid or missing 'name' for {code}")

    minor_units = entry.get("minor_units")
    if not isinstance(minor_units, int) or minor_units < 0 or minor_units > 18:
        _fatal(f"Invalid or missing 'minor_units' for {code}: {minor_units!r}")

    # Optional text fields — absent and empty are equivalent, both render
    # as a zero-length field between two delimiters.
    symbol = entry.get("symbol") or ""
    entity = entry.get("entity") or ""
    pegged_to = entry.get("pegged_to") or ""
    peg_type = entry.get("peg_type") or ""

    # is_independent — conservative default of "false" on absent field.
    # See the docstring above for rationale.
    is_independent_raw = entry.get("is_independent")
    if isinstance(is_independent_raw, bool):
        is_independent = "true" if is_independent_raw else "false"
    elif is_independent_raw is None:
        is_independent = "false"
    else:
        _fatal(f"Invalid 'is_independent' for {code}: {is_independent_raw!r}")

    # peg_rate — absent means "not applicable" for basket/undisclosed pegs
    # and for any currency not pegged at all. repr() of a float gives the
    # shortest round-trippable decimal representation, which keeps the
    # output stable and lets float(cell) recover the exact original value.
    peg_rate_raw = entry.get("peg_rate")
    if peg_rate_raw is None:
        peg_rate = ""
    elif isinstance(peg_rate_raw, (int, float)) and not isinstance(peg_rate_raw, bool):
        peg_rate = repr(float(peg_rate_raw))
    else:
        _fatal(f"Invalid 'peg_rate' for {code}: {peg_rate_raw!r}")

    return CurrencyRow(
        code=code,
        numeric_code=numeric,
        name=name,
        minor_units=str(minor_units),
        symbol=symbol,
        entity=entity,
        status=status,
        is_independent=is_independent,
        pegged_to=pegged_to,
        peg_type=peg_type,
        peg_rate=peg_rate,
    )


# ---------------------------------------------------------------------------
# CSV rendering
# ---------------------------------------------------------------------------

def _render(registry: Registry, dialect: str) -> str:
    """
    Render one dialect's complete file content as a string.

    Quoting is delegated to Python's csv module with QUOTE_MINIMAL: a
    field is quoted if and only if it contains the delimiter, a double
    quote, CR, or LF, and embedded quotes are doubled. Fields are never
    quoted unnecessarily — that keeps diffs minimal and stable across
    regeneration. Hand-rolling this logic is the classic way to end up
    with a CSV parser that eventually meets a field containing "\\r\\n"
    and mangles it.

    lineterminator is LF, not the csv module's CRLF default. RFC 4180
    specifies CRLF, but every modern parser accepts LF, and CRLF would
    make --check fail on Windows checkouts where git rewrote line
    endings. .gitattributes is a second line of defense.

    The BOM, when enabled for this dialect, is prepended as the Unicode
    codepoint U+FEFF. When the string is written with encoding='utf-8',
    that becomes the three bytes EF BB BF on disk. Writing with
    encoding='utf-8-sig' would also work, but would also strip any BOM
    appearing mid-content — an unlikely but real hazard if a future
    currency name ever began with U+FEFF.
    """
    if dialect not in DIALECT_FILES:
        _fatal(f"Unknown dialect: {dialect}")

    delimiter = DIALECT_DELIMITERS[dialect]
    buffer = io.StringIO()

    writer = csv.writer(
        buffer,
        delimiter=delimiter,
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
    )

    writer.writerow(COLUMNS)
    for row in registry.rows:
        writer.writerow(row.as_tuple())

    content = buffer.getvalue()

    if DIALECT_BOM[dialect]:
        content = "\ufeff" + content

    return content


def render_rfc(registry: Registry) -> str:
    """
    RFC 4180 comma-separated export.

    Universal default: every CSV parser accepts it, whether that's Python's
    csv module, Go's encoding/csv, Rust's csv crate, JavaScript's csv-parse,
    pandas, or any spreadsheet application.
    """
    return _render(registry, "rfc")


def render_excel(registry: Registry) -> str:
    """
    Excel-compatible comma-separated export.

    Identical to the RFC 4180 dialect except for a leading UTF-8 BOM
    (EF BB BF). Excel on Windows uses the BOM to auto-detect UTF-8 and
    correctly render symbols like ¥, €, and د.ك. Without it, Excel guesses
    the code page and shows mojibake for every non-ASCII symbol.
    """
    return _render(registry, "excel")


def render_european(registry: Registry) -> str:
    """
    Semicolon-delimited export for European Excel locales.

    In French, German, Spanish, Italian, and most other European locales
    the comma is the decimal separator. Excel in those locales treats a
    comma-delimited file as a single column unless the user runs an import
    wizard. Semicolon-delimited files open directly, which is why ISO 4217
    ships one.
    """
    return _render(registry, "european")


def render_tsv(registry: Registry) -> str:
    """
    Tab-separated export.

    Tabs are the paste delimiter for Google Sheets, most SQL clients, and
    every terminal. A TSV file pastes with columns aligned and needs no
    escaping for values that legitimately contain commas.
    """
    return _render(registry, "tsv")


# Dialect name → render function
RENDERERS: dict[str, Callable[[Registry], str]] = {
    "rfc": render_rfc,
    "excel": render_excel,
    "european": render_european,
    "tsv": render_tsv,
}


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """
    Write `content` to `path` atomically.

    Writes to a temporary sibling file first, then renames. On POSIX the
    rename is atomic on the same filesystem, so a reader never sees a
    partially written file.

    `newline=""` disables Python's automatic line-ending translation, so
    the exact LF bytes we produced are what land on disk. Without it,
    Windows would rewrite every LF as CRLF, and --check would then fail
    on Windows for a file whose intended content is LF. Note: unlike
    Path.write_text, this uses open() directly so the newline parameter
    is honoured on every supported Python version.
    """
    tmp_path = path.parent / (path.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except OSError as e:
        # Clean up the temp file if the write or rename failed.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        _fatal(f"Failed to write {path}: {e}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_all(registry: Registry) -> dict[str, Path]:
    """
    Render and write all four dialect files.

    Returns a mapping of dialect name → written path.
    """
    written: dict[str, Path] = {}
    for dialect, filename in DIALECT_FILES.items():
        content = RENDERERS[dialect](registry)
        path = PROJECT_ROOT / filename
        _atomic_write(path, content)
        written[dialect] = path
    return written


def generate_one(registry: Registry, dialect: str) -> str:
    """Render one dialect's content as a string (no file write)."""
    if dialect not in RENDERERS:
        _fatal(f"Unknown dialect: {dialect}")
    return RENDERERS[dialect](registry)


def check_all(registry: Registry) -> int:
    """
    --check mode: regenerate each dialect in memory, compare against the
    committed file. Returns the exit code.

    Missing files → EXIT_MISSING (3).
    Any mismatch → EXIT_MISMATCH (1).
    All match → EXIT_OK (0).

    Multiple problems are all reported; the exit code reflects the most
    severe (missing > mismatch).

    Note on BOM comparison: read_text(encoding="utf-8") preserves a
    leading BOM as U+FEFF in the returned string, exactly as the renderer
    emits it. So the comparison is byte-faithful including the BOM, and a
    file whose BOM has been stripped by an editor will register as a
    mismatch — which is the correct behavior.
    """
    missing: list[str] = []
    mismatched: list[str] = []

    for dialect, filename in DIALECT_FILES.items():
        path = PROJECT_ROOT / filename
        if not path.exists():
            missing.append(filename)
            continue
        expected = RENDERERS[dialect](registry)
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            mismatched.append(filename)

    if mismatched:
        print("Mismatched CSV/TSV files:", file=sys.stderr)
        for name in mismatched:
            print(f"  ✗ {name}", file=sys.stderr)
        print(
            "Run 'python3 tools/export_csv.py' to regenerate.",
            file=sys.stderr,
        )

    if missing:
        print("Missing CSV/TSV files:", file=sys.stderr)
        for name in missing:
            print(f"  ✗ {name}", file=sys.stderr)
        print(
            "Run 'python3 tools/export_csv.py' to create them.",
            file=sys.stderr,
        )

    if missing:
        return EXIT_MISSING
    if mismatched:
        return EXIT_MISMATCH

    print("All four CSV/TSV files match the registry.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CSV/TSV exports from iso4217.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  Regenerate all four files
  %(prog)s --dialect european               Regenerate one file
  %(prog)s --dialect tsv --stdout           Print one dialect to stdout
  %(prog)s --check                          CI: exit 1 if any file is stale
  %(prog)s --registry /tmp/test.json        Use an alternate registry
        """,
    )
    parser.add_argument(
        "--dialect", "-d",
        choices=sorted(DIALECT_FILES.keys()),
        default=None,
        help="Limit to one dialect (default: all four)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write CSV/TSV to stdout instead of a file (requires --dialect)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if committed files match, 1 if any differ, 3 if any missing",
    )
    parser.add_argument(
        "--registry", "-r",
        type=Path,
        default=REGISTRY_PATH,
        help=f"Path to iso4217.json (default: {REGISTRY_PATH})",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    # --stdout requires --dialect
    if args.stdout and not args.dialect:
        print(
            "ERROR: --stdout requires --dialect",
            file=sys.stderr,
        )
        return EXIT_FATAL

    # --check and --stdout are mutually exclusive
    if args.check and args.stdout:
        print(
            "ERROR: --check and --stdout are mutually exclusive",
            file=sys.stderr,
        )
        return EXIT_FATAL

    registry = load_registry(args.registry)

    # --check mode
    if args.check:
        if args.dialect:
            # Check a single dialect
            path = PROJECT_ROOT / DIALECT_FILES[args.dialect]
            if not path.exists():
                print(f"  ✗ Missing: {path.name}", file=sys.stderr)
                return EXIT_MISSING
            expected = RENDERERS[args.dialect](registry)
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                print(f"  ✗ Mismatched: {path.name}", file=sys.stderr)
                print(
                    "Run 'python3 tools/export_csv.py' to regenerate.",
                    file=sys.stderr,
                )
                return EXIT_MISMATCH
            print(f"{path.name} matches the registry.")
            return EXIT_OK
        return check_all(registry)

    # --stdout mode. sys.stdout.write is used directly (not print) so the
    # exact content is emitted without an added trailing newline and with
    # the BOM, if any, preserved as the first codepoint.
    if args.stdout:
        content = generate_one(registry, args.dialect)
        sys.stdout.write(content)
        return EXIT_OK

    # Single dialect
    if args.dialect:
        content = generate_one(registry, args.dialect)
        path = PROJECT_ROOT / DIALECT_FILES[args.dialect]
        _atomic_write(path, content)
        print(
            f"Wrote {path.name} "
            f"({registry.active_count} active + "
            f"{registry.withdrawn_count} withdrawn = "
            f"{registry.total_count} rows)",
            file=sys.stderr,
        )
        return EXIT_OK

    # All dialects
    written = generate_all(registry)
    for dialect, path in sorted(written.items()):
        print(
            f"Wrote {path.name} "
            f"({registry.active_count} active + "
            f"{registry.withdrawn_count} withdrawn = "
            f"{registry.total_count} rows)",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())