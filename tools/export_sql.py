#!/usr/bin/env python3
"""
SQL export generator for the ISO 4217 Currency Registry (v1.5.0).

Generates four dialect-specific SQL files at the repository root:
    iso4217.sql              — ANSI SQL-92 portable
    iso4217.postgresql.sql   — PostgreSQL 12+
    iso4217.mysql.sql        — MySQL 8+ / MariaDB 10.4+
    iso4217.sqlite.sql       — SQLite 3.37+

Design invariants
-----------------
- **Every INSERT is sorted by currency code, ascending.** Determinism is
  required so that CI diffing (--check mode) has no false positives.
- **Non-ISO entries are excluded.** Active + withdrawn ISO 4217 only.
  Crypto, stablecoins, commodities, and special-purpose codes belong in a
  future `non_iso_instruments` table (v1.6.0+), not in this seed.
- **Generated files are committed.** Regeneration is manual (or run under
  --check in CI to detect drift).
- **Atomic writes.** Each file is written to a temporary sibling and then
  renamed into place, so a crash mid-write never leaves a partial file.
- **No timestamps in output.** The header records the registry's
  `meta.updated`, not the current wall-clock time — otherwise every run
  would produce a different file and defeat --check.

Schema
------
One table, `currencies`, with seven columns:

    code          ISO 4217 alphabetic code (primary key)
    numeric_code  ISO 4217 numeric code as text (preserves leading zeros)
    name          English name
    minor_units   Decimal places, 0..18
    symbol        Display symbol (may be empty)
    entity        Issuing entity (may be empty)
    status        'active' or 'withdrawn'

Deliberately excluded: pegs, countries, central banks, non-ISO instruments.

Escaping
--------
Only the single-quote character needs escaping (doubled: `''`). The current
registry contains no backslashes; if that ever changes, MySQL's default
escape-processing would need attention (see the MySQL header in generated
output).

Usage
-----
    # Regenerate all four files (default)
    python3 tools/export_sql.py

    # Regenerate one dialect
    python3 tools/export_sql.py --dialect postgresql

    # Print one dialect to stdout
    python3 tools/export_sql.py --dialect sqlite --stdout

    # CI check — exit 0 if all committed files match, 1 if any differ,
    # 3 if any are missing
    python3 tools/export_sql.py --check

Exit codes
----------
    0 — Success (files written, or --check passed)
    1 — --check mismatch
    2 — Fatal error (missing registry, invalid JSON, write failure)
    3 — --check found one or more missing files
"""

from __future__ import annotations

import argparse
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
    "ansi": "iso4217.sql",
    "postgresql": "iso4217.postgresql.sql",
    "mysql": "iso4217.mysql.sql",
    "sqlite": "iso4217.sqlite.sql",
}

# Dialect name → human-readable label (for header comments)
DIALECT_LABELS: dict[str, str] = {
    "ansi": "ANSI SQL-92 (portable)",
    "postgresql": "PostgreSQL 12+",
    "mysql": "MySQL 8+ / MariaDB 10.4+",
    "sqlite": "SQLite 3.37+",
}

# Exit codes
EXIT_OK: int = 0
EXIT_MISMATCH: int = 1
EXIT_FATAL: int = 2
EXIT_MISSING: int = 3

# SQL identifiers used in every dialect
TABLE_NAME: str = "currencies"
INDEX_NAME: str = "idx_currencies_status"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrencyRow:
    """
    A single currency as it will appear in the SQL table.

    Frozen so rows can be put in sets or dicts without surprises.
    `status` is either "active" or "withdrawn".
    """
    code: str
    numeric_code: str
    name: str
    minor_units: int
    symbol: str
    entity: str
    status: str


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

    # Deterministic ordering: sort by code, ascending. The two status
    # groups are already separated by the loop above; sorting the combined
    # list keeps active rows before withdrawn rows only if code order
    # happens to align, so we sort within each group and concatenate.
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

    Missing optional fields (symbol, entity) default to empty strings rather
    than failing, because both are optional in the schema.
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

    symbol = entry.get("symbol") or ""
    entity = entry.get("entity") or ""

    return CurrencyRow(
        code=code,
        numeric_code=numeric,
        name=name,
        minor_units=minor_units,
        symbol=symbol,
        entity=entity,
        status=status,
    )


# ---------------------------------------------------------------------------
# SQL escaping and formatting
# ---------------------------------------------------------------------------

def sql_escape_standard(value: str) -> str:
    """
    Escape a Python string for ANSI, PostgreSQL, or SQLite string literals.

    Only the single quote needs doubling in these three dialects.
    """
    return value.replace("'", "''")


def sql_escape_mysql(value: str) -> str:
    """
    Escape a Python string for a MySQL/MariaDB string literal.

    MySQL treats backslash as an escape character by default, so both
    single quotes and backslashes are doubled here. This is correct
    regardless of whether the current sql_mode is strict or permissive,
    and produces identical results to sql_escape_standard for any input
    that contains no backslashes (which is every entry today).
    """
    return value.replace("\\", "\\\\").replace("'", "''")


def sql_escape(value: str, dialect: str = "standard") -> str:
    """Dispatch to the correct escaper. Kept for backward compatibility."""
    if dialect == "mysql":
        return sql_escape_mysql(value)
    return sql_escape_standard(value)


def _row_to_insert(row: CurrencyRow, dialect: str = "standard") -> str:
    """
    Render one `INSERT` statement. The column list is fixed so every
    generated file has the same INSERT shape, regardless of dialect.

    `dialect` selects the escaper: "mysql" for MySQL/MariaDB (backslashes
    and quotes doubled), "standard" for ANSI/PostgreSQL/SQLite (quotes
    doubled only).
    """
    esc = (lambda v: sql_escape_mysql(v)) if dialect == "mysql" else (lambda v: sql_escape_standard(v))
    return (
        f"INSERT INTO {TABLE_NAME} "
        f"(code, numeric_code, name, minor_units, symbol, entity, status) "
        f"VALUES ("
        f"'{esc(row.code)}', "
        f"'{esc(row.numeric_code)}', "
        f"'{esc(row.name)}', "
        f"{row.minor_units}, "
        f"'{esc(row.symbol)}', "
        f"'{esc(row.entity)}', "
        f"'{esc(row.status)}'"
        f");"
    )


def _render_header(dialect: str, registry: Registry) -> str:
    """
    Header comment block common to all dialects.

    Deliberately contains no timestamp of the current run — only the
    registry's own `meta.updated`. This keeps output deterministic.
    """
    label = DIALECT_LABELS[dialect]
    lines = [
        f"-- ISO 4217 Currency Registry — SQL Export ({label})",
        f"-- Source:      iso4217.json v{registry.version}",
        f"-- Updated:     {registry.updated}",
        f"-- Amendment:   {registry.amendment}",
        f"-- Repository:  {REPOSITORY_URL}",
        f"-- License:     {LICENSE_NAME}",
        f"--",
        f"-- Contents:    {registry.active_count} active + "
        f"{registry.withdrawn_count} withdrawn = {registry.total_count} rows",
        f"--",
        f"-- Note:        Active codes are 3 chars (e.g., USD). Withdrawn codes",
        f"--              may be up to 7 chars (e.g., MXN_OLD) for revaluation cases.",
        f"-- Excludes:    non-ISO instruments (crypto, stablecoins, commodities),",
        f"--              peg information, country relationships, central banks",
        f"--",
        f"-- Regenerate:  python3 tools/export_sql.py",
        f"--",
        f"",
    ]
    return "\n".join(lines)


def _render_footer(registry: Registry) -> str:
    """Trailing comment block common to all dialects."""
    return (
        f"\n-- End of export\n"
        f"-- Active rows:    {registry.active_count}\n"
        f"-- Withdrawn rows: {registry.withdrawn_count}\n"
        f"-- Total rows:     {registry.total_count}\n"
    )


# ---------------------------------------------------------------------------
# Dialect renderers
# ---------------------------------------------------------------------------

def _render_body(registry: Registry, dialect: str = "standard") -> str:
    """
    The INSERT block. Structure is identical across dialects; the escape
    function used differs (see _row_to_insert).
    """
    lines = ["-- Data", ""]
    for row in registry.rows:
        lines.append(_row_to_insert(row, dialect))
    return "\n".join(lines)


def render_ansi(registry: Registry) -> str:
    """
    ANSI SQL-92 portable export.

    Uses only standard types and syntax. Works on PostgreSQL, MySQL 8+,
    MariaDB 10.4+, SQLite 3.37+, SQL Server 2016+, Oracle 12c+, IBM Db2.
    """
    parts = [
        _render_header("ansi", registry),
        "DROP TABLE IF EXISTS currencies;",
        "",
        "CREATE TABLE currencies (",
        "  code          VARCHAR(7)    NOT NULL,",
        "  numeric_code  CHAR(3)       NOT NULL,",
        "  name          VARCHAR(100)  NOT NULL,",
        "  minor_units   SMALLINT      NOT NULL,",
        "  symbol        VARCHAR(20)   NULL,",
        "  entity        VARCHAR(100)  NULL,",
        "  status        VARCHAR(10)   NOT NULL,",
        "  PRIMARY KEY (code),",
        "  CONSTRAINT chk_currencies_code_length CHECK (LENGTH(code) BETWEEN 3 AND 7),",
        "  CONSTRAINT chk_currencies_minor_units CHECK (minor_units BETWEEN 0 AND 18),",
        "  CONSTRAINT chk_currencies_status CHECK (status IN ('active', 'withdrawn'))",
        ");",
        "",
        "CREATE INDEX idx_currencies_status ON currencies (status);",
        "",
        _render_body(registry, "standard"),
        _render_footer(registry),
    ]
    return "\n".join(parts)


def render_postgresql(registry: Registry) -> str:
    """
    PostgreSQL 12+ export.

    Same schema as ANSI, plus a commented alternative that demonstrates an
    append-only import (INSERT ... ON CONFLICT DO NOTHING) for users who
    do not want to drop the table on every re-import.
    """
    parts = [
        _render_header("postgresql", registry),
        "DROP TABLE IF EXISTS currencies;",
        "",
        "CREATE TABLE currencies (",
        "  code          VARCHAR(7)    NOT NULL,",
        "  numeric_code  CHAR(3)       NOT NULL,",
        "  name          VARCHAR(100)  NOT NULL,",
        "  minor_units   SMALLINT      NOT NULL,",
        "  symbol        VARCHAR(20)   NULL,",
        "  entity        VARCHAR(100)  NULL,",
        "  status        VARCHAR(10)   NOT NULL,",
        "  PRIMARY KEY (code),",
        "  CONSTRAINT chk_currencies_code_length CHECK (LENGTH(code) BETWEEN 3 AND 7),",
        "  CONSTRAINT chk_currencies_minor_units CHECK (minor_units BETWEEN 0 AND 18),",
        "  CONSTRAINT chk_currencies_status CHECK (status IN ('active', 'withdrawn'))",
        ");",
        "",
        "CREATE INDEX idx_currencies_status ON currencies (status);",
        "",
        "-- Alternative for append-only imports (do not DROP first):",
        "--   Replace the INSERT below with:",
        "--     INSERT INTO currencies (...) VALUES (...) ON CONFLICT (code) DO NOTHING;",
        "",
        _render_body(registry, "standard"),
        _render_footer(registry),
    ]
    return "\n".join(parts)


def render_mysql(registry: Registry) -> str:
    """
    MySQL 8+ / MariaDB 10.4+ export.

    Uses ENGINE=InnoDB and utf8mb4 for full Unicode support. minor_units is
    TINYINT UNSIGNED rather than SMALLINT, matching MySQL's smallest
    integer type that comfortably fits 0..18.
    """
    parts = [
        _render_header("mysql", registry),
        "DROP TABLE IF EXISTS currencies;",
        "",
        "CREATE TABLE currencies (",
        "  code          VARCHAR(7)       NOT NULL,",
        "  numeric_code  CHAR(3)          NOT NULL,",
        "  name          VARCHAR(100)     NOT NULL,",
        "  minor_units   TINYINT UNSIGNED NOT NULL,",
        "  symbol        VARCHAR(20)      NULL,",
        "  entity        VARCHAR(100)     NULL,",
        "  status        VARCHAR(10)      NOT NULL,",
        "  PRIMARY KEY (code),",
        "  CONSTRAINT chk_currencies_code_length CHECK (LENGTH(code) BETWEEN 3 AND 7),",
        "  CONSTRAINT chk_currencies_minor_units CHECK (minor_units BETWEEN 0 AND 18),",
        "  CONSTRAINT chk_currencies_status CHECK (status IN ('active', 'withdrawn'))",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "CREATE INDEX idx_currencies_status ON currencies (status);",
        "",
        _render_body(registry, "mysql"),
        _render_footer(registry),
    ]
    return "\n".join(parts)


def render_sqlite(registry: Registry) -> str:
    """
    SQLite 3.37+ export.

    Uses a STRICT table so SQLite actually enforces column types — otherwise
    SQLite accepts any value in any column, which defeats the CHECK constraints'
    intent. STRICT tables require declared types to be one of: INT, INTEGER,
    REAL, TEXT, BLOB, ANY.
    """
    parts = [
        _render_header("sqlite", registry),
        "DROP TABLE IF EXISTS currencies;",
        "",
        "CREATE TABLE currencies (",
        "  code          TEXT     NOT NULL,  -- active: 3 chars; withdrawn: up to 7",
        "  numeric_code  TEXT     NOT NULL,",
        "  name          TEXT     NOT NULL,",
        "  minor_units   INTEGER  NOT NULL,",
        "  symbol        TEXT     NULL,",
        "  entity        TEXT     NULL,",
        "  status        TEXT     NOT NULL,",
        "  PRIMARY KEY (code),",
        "  CONSTRAINT chk_currencies_code_length CHECK (LENGTH(code) BETWEEN 3 AND 7),",
        "  CONSTRAINT chk_currencies_minor_units CHECK (minor_units BETWEEN 0 AND 18),",
        "  CONSTRAINT chk_currencies_status CHECK (status IN ('active', 'withdrawn'))",
        ") STRICT;",
        "",
        "CREATE INDEX idx_currencies_status ON currencies (status);",
        "",
        _render_body(registry, "standard"),
        _render_footer(registry),
    ]
    return "\n".join(parts)


# Dialect name → render function
RENDERERS: dict[str, Callable[[Registry], str]] = {
    "ansi": render_ansi,
    "postgresql": render_postgresql,
    "mysql": render_mysql,
    "sqlite": render_sqlite,
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
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as e:
        # Clean up the temp file if the rename failed
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
        print("Mismatched SQL files:", file=sys.stderr)
        for name in mismatched:
            print(f"  ✗ {name}", file=sys.stderr)
        print(
            "Run 'python3 tools/export_sql.py' to regenerate.",
            file=sys.stderr,
        )

    if missing:
        print("Missing SQL files:", file=sys.stderr)
        for name in missing:
            print(f"  ✗ {name}", file=sys.stderr)
        print(
            "Run 'python3 tools/export_sql.py' to create them.",
            file=sys.stderr,
        )

    if missing:
        return EXIT_MISSING
    if mismatched:
        return EXIT_MISMATCH

    print("All four SQL files match the registry.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SQL exports from iso4217.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  Regenerate all four files
  %(prog)s --dialect postgresql             Regenerate one file
  %(prog)s --dialect sqlite --stdout        Print one dialect to stdout
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
        help="Write SQL to stdout instead of a file (requires --dialect)",
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
                    "Run 'python3 tools/export_sql.py' to regenerate.",
                    file=sys.stderr,
                )
                return EXIT_MISMATCH
            print(f"{path.name} matches the registry.")
            return EXIT_OK
        return check_all(registry)

    # --stdout mode
    if args.stdout:
        content = generate_one(registry, args.dialect)
        print(content, end="")
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