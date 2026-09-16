#!/usr/bin/env python3
"""
Parquet export generator for the ISO 4217 Currency Registry (v1.5.2).

Generates a single file at the repository root:

    iso4217.parquet     Parquet 2.0, snappy-compressed, one row group

Design invariants
-----------------
- **Eleven columns, identical to the CSV export.** Same names, same order,
  same semantics. A consumer choosing between CSV and Parquet chooses on
  format, not on schema.

- **Native types.** `minor_units` is `int8`, `is_independent` is `bool`,
  `peg_rate` is `float64`. The CSV export uses strings because CSV has no
  type system. Parquet does, and the export uses it.

- **Null, not empty string, for not-applicable values.** `pegged_to`,
  `peg_type`, and `peg_rate` are `null` for independent currencies, for
  basket/undisclosed pegs (rate only), and for all withdrawn currencies.
  A query like `WHERE pegged_to IS NOT NULL` correctly filters. The
  equivalent CSV query would need `WHERE pegged_to != ''`, an implicit
  convention the schema cannot enforce.

- **Deterministic row order.** Active currencies first, sorted by `code`
  ascending; withdrawn currencies after, sorted by `code` ascending.
  Identical to the SQL and CSV exports. This is what makes the row-for-row
  cross-check in tests/test_export_parquet.py a straight comparison.

- **Three metadata keys, no more.** `iso4217.version`, `iso4217.updated`,
  `iso4217.amendment`. They make the file self-describing without turning
  the Parquet footer into a log.

- **Atomic write.** The file is written to a temporary sibling and renamed
  into place. A crash mid-write never leaves a partial file.

Comparison semantics differ from the other generators
-----------------------------------------------------
`export_sql.py --check` and `export_csv.py --check` compare bytes. Parquet
cannot be compared byte-for-byte: the format permits different row-group
sizes, dictionary-encoding decisions, compression block boundaries, and
metadata key ordering, all producing byte-different files with identical
logical content. A byte comparison would report "stale" on every run where
pyarrow made a different-but-valid layout choice.

This generator's `--check` mode compares *logical content*:

    1. Parse the committed file with pyarrow.parquet.read_table.
    2. Regenerate the table in memory from the current registry.
    3. Compare column names, count, and types.
    4. Compare every value.
    5. Compare the metadata key-value maps.

Slower than a byte comparison, but correct.

Schema
------
Eleven columns, declared once in PARQUET_SCHEMA below. The full rationale
is in docs/decisions/parquet-schema.md.

Usage
-----
    # Regenerate the file (default)
    python3 tools/export_parquet.py

    # Print the Parquet bytes to stdout (binary)
    python3 tools/export_parquet.py --stdout

    # CI check — exit 0 if the committed file matches, 1 if it differs,
    # 3 if it is missing
    python3 tools/export_parquet.py --check

Exit codes
----------
    0  Success (file written, or --check passed)
    1  --check mismatch
    2  Fatal error (missing registry, invalid JSON, write failure)
    3  --check found the committed file missing

Dependency
----------
This tool requires pyarrow. It is a *build-time* dependency — pyarrow must
not appear in wrappers/python/setup.py's install_requires or extras_require.
The wrapper stays zero-dependency; only this generator imports pyarrow.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as e:
    print(f"FATAL: pyarrow is required for this tool: {e}", file=sys.stderr)
    print("Install with: pip install pyarrow", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
REGISTRY_PATH: Path = PROJECT_ROOT / "iso4217.json"
PARQUET_PATH: Path = PROJECT_ROOT / "iso4217.parquet"

# Column names, in output order. Identical to the CSV export's COLUMNS.
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

# The Parquet schema. Declared once, used by both the renderer and the
# comparison. Column order here must match COLUMNS.
PARQUET_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("code", pa.string(), nullable=False),
        pa.field("numeric_code", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("minor_units", pa.int8(), nullable=False),
        pa.field("symbol", pa.string(), nullable=True),
        pa.field("entity", pa.string(), nullable=True),
        pa.field("status", pa.string(), nullable=False),
        pa.field("is_independent", pa.bool_(), nullable=False),
        pa.field("pegged_to", pa.string(), nullable=True),
        pa.field("peg_type", pa.string(), nullable=True),
        pa.field("peg_rate", pa.float64(), nullable=True),
    ]
)

# Parquet footer metadata keys.
METADATA_VERSION_KEY: str = "iso4217.version"
METADATA_UPDATED_KEY: str = "iso4217.updated"
METADATA_AMENDMENT_KEY: str = "iso4217.amendment"

# Exit codes, aligned with export_sql.py and export_csv.py.
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
    A single currency, reduced to the eleven export columns with native
    Python types. The renderer converts these to Arrow arrays; the
    comparison converts the committed table back to this shape.

    `symbol` and `entity` default to empty string when absent — matching
    the CSV export. `pegged_to`, `peg_type`, and `peg_rate` are None when
    not applicable — this is the substantive difference from CSV.
    """

    code: str
    numeric_code: str
    name: str
    minor_units: int
    symbol: str
    entity: str
    status: str
    is_independent: bool
    pegged_to: Optional[str]
    peg_type: Optional[str]
    peg_rate: Optional[float]

    def as_dict(self) -> dict:
        """Return the row as a dict in COLUMNS order."""
        return {
            "code": self.code,
            "numeric_code": self.numeric_code,
            "name": self.name,
            "minor_units": self.minor_units,
            "symbol": self.symbol,
            "entity": self.entity,
            "status": self.status,
            "is_independent": self.is_independent,
            "pegged_to": self.pegged_to,
            "peg_type": self.peg_type,
            "peg_rate": self.peg_rate,
        }


@dataclass
class Registry:
    """The parsed registry reduced to exactly what the exporter needs."""

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
# Fatal error helper
# ---------------------------------------------------------------------------

def _fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(EXIT_FATAL)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

def load_registry(path: Path) -> Registry:
    """
    Load, validate, and reduce the registry to a Registry object.

    The validation logic mirrors export_csv.py exactly for the eleven
    export fields. Structural problems exit with EXIT_FATAL; the error
    message names the specific code or field at fault.
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

    # Deterministic ordering — active first, sorted by code; withdrawn
    # after, sorted by code. Identical to export_sql.py and export_csv.py.
    active_rows = sorted((r for r in rows if r.status == "active"), key=lambda r: r.code)
    withdrawn_rows = sorted((r for r in rows if r.status == "withdrawn"), key=lambda r: r.code)

    return Registry(
        version=version,
        updated=updated,
        amendment=amendment,
        rows=active_rows + withdrawn_rows,
    )


def _row_from_entry(entry: dict, status: str) -> CurrencyRow:
    """
    Convert one registry entry into a CurrencyRow with native types.

    Validation mirrors export_csv.py: same code/numeric/name/minor_units
    checks, same error messages. The difference is the value conversion:
    integers stay integers, booleans stay booleans, absent peg fields
    become None rather than empty string.
    """
    code = entry.get("code")
    # Active codes are 3 chars; withdrawn codes may be up to 7 (the
    # <STEM>_<OLD> synthetic identifier convention — see ADR 0001).
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

    # Optional text: absent becomes empty string, matching CSV.
    symbol = entry.get("symbol") or ""
    entity = entry.get("entity") or ""

    # is_independent: conservative default of False on absent field,
    # matching the wrapper and the CSV export.
    is_independent_raw = entry.get("is_independent")
    if isinstance(is_independent_raw, bool):
        is_independent = is_independent_raw
    elif is_independent_raw is None:
        is_independent = False
    else:
        _fatal(f"Invalid 'is_independent' for {code}: {is_independent_raw!r}")

    # Peg columns: absent means "not applicable". None, not empty string.
    pegged_to = entry.get("pegged_to")
    if pegged_to is not None and not isinstance(pegged_to, str):
        _fatal(f"Invalid 'pegged_to' for {code}: {pegged_to!r}")

    peg_type = entry.get("peg_type")
    if peg_type is not None and not isinstance(peg_type, str):
        _fatal(f"Invalid 'peg_type' for {code}: {peg_type!r}")

    peg_rate_raw = entry.get("peg_rate")
    if peg_rate_raw is None:
        peg_rate = None
    elif isinstance(peg_rate_raw, (int, float)) and not isinstance(peg_rate_raw, bool):
        peg_rate = float(peg_rate_raw)
    else:
        _fatal(f"Invalid 'peg_rate' for {code}: {peg_rate_raw!r}")

    return CurrencyRow(
        code=code,
        numeric_code=numeric,
        name=name,
        minor_units=minor_units,
        symbol=symbol,
        entity=entity,
        status=status,
        is_independent=is_independent,
        pegged_to=pegged_to,
        peg_type=peg_type,
        peg_rate=peg_rate,
    )


# ---------------------------------------------------------------------------
# Parquet rendering
# ---------------------------------------------------------------------------

def _build_metadata(registry: Registry) -> dict[bytes, bytes]:
    """
    Return the Parquet footer metadata as a bytes->bytes dict.

    pyarrow stores metadata keys and values as bytes. The comparison in
    check_parquet() works on this exact representation.
    """
    return {
        METADATA_VERSION_KEY.encode("utf-8"): registry.version.encode("utf-8"),
        METADATA_UPDATED_KEY.encode("utf-8"): registry.updated.encode("utf-8"),
        METADATA_AMENDMENT_KEY.encode("utf-8"): str(registry.amendment).encode("utf-8"),
    }


def _build_table(registry: Registry) -> pa.Table:
    """
    Build a pyarrow Table from the registry, with the exact schema in
    PARQUET_SCHEMA and the three metadata keys attached.

    The table is returned in memory; render_parquet() serializes it.
    """
    # Column-major dict: one list per column, in COLUMNS order.
    column_data: dict[str, list] = {col: [] for col in COLUMNS}
    for row in registry.rows:
        d = row.as_dict()
        for col in COLUMNS:
            column_data[col].append(d[col])

    # Attach metadata to the schema before creating the table, so the
    # metadata is written into the Parquet footer, not just the in-memory
    # schema.
    schema_with_metadata = PARQUET_SCHEMA.with_metadata(_build_metadata(registry))

    # Build the table with explicit types per column.
    arrays = [
        pa.array(column_data["code"], type=pa.string()),
        pa.array(column_data["numeric_code"], type=pa.string()),
        pa.array(column_data["name"], type=pa.string()),
        pa.array(column_data["minor_units"], type=pa.int8()),
        pa.array(column_data["symbol"], type=pa.string()),
        pa.array(column_data["entity"], type=pa.string()),
        pa.array(column_data["status"], type=pa.string()),
        pa.array(column_data["is_independent"], type=pa.bool_()),
        pa.array(column_data["pegged_to"], type=pa.string()),
        pa.array(column_data["peg_type"], type=pa.string()),
        pa.array(column_data["peg_rate"], type=pa.float64()),
    ]

    return pa.Table.from_arrays(arrays, schema=schema_with_metadata)


def render_parquet(registry: Registry) -> bytes:
    """
    Render the registry as a complete Parquet file and return the bytes.

    Uses snappy compression (pyarrow's default). One row group. No tuning.
    """
    table = _build_table(registry)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Comparison (logical, not byte-for-byte)
# ---------------------------------------------------------------------------

def check_parquet(registry: Registry) -> int:
    """
    --check mode: compare the committed file against the regenerated
    table, logically. Returns the exit code.

    Byte comparison does not work for Parquet. See the module docstring.

    Missing file       -> EXIT_MISSING (3)
    Any mismatch       -> EXIT_MISMATCH (1)
    Identical content  -> EXIT_OK (0)
    """
    path = PARQUET_PATH

    if not path.exists():
        print(f"Missing: {path.name}", file=sys.stderr)
        print("Run 'python3 tools/export_parquet.py' to create it.", file=sys.stderr)
        return EXIT_MISSING

    try:
        committed = pq.read_table(path)
    except Exception as e:
        print(f"FATAL: cannot read {path}: {e}", file=sys.stderr)
        return EXIT_FATAL

    expected = _build_table(registry)

    # 1. Row count
    if committed.num_rows != expected.num_rows:
        print(
            f"Mismatch: {path.name} has {committed.num_rows} rows, "
            f"expected {expected.num_rows}.",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    # 2. Column names
    if committed.column_names != expected.column_names:
        print(
            f"Mismatch: column names differ.\n"
            f"  committed: {committed.column_names}\n"
            f"  expected:  {expected.column_names}",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    # 3. Column types
    for i, name in enumerate(committed.column_names):
        ctype = committed.schema.field(i).type
        etype = expected.schema.field(i).type
        if ctype != etype:
            print(
                f"Mismatch: column '{name}' has type {ctype}, expected {etype}.",
                file=sys.stderr,
            )
            return EXIT_MISMATCH

    # 4. Values, column by column
    committed_dict = committed.to_pydict()
    expected_dict = expected.to_pydict()
    for col in expected.column_names:
        c_col = committed_dict[col]
        e_col = expected_dict[col]
        if c_col != e_col:
            for i, (a, b) in enumerate(zip(c_col, e_col)):
                if a != b:
                    code = committed_dict["code"][i]
                    print(
                        f"Mismatch: row {i} ({code}), column '{col}': "
                        f"committed={a!r}, expected={b!r}.",
                        file=sys.stderr,
                    )
                    return EXIT_MISMATCH
            # Column lengths differ despite num_rows match — should not
            # happen, but fail cleanly rather than silently.
            print(f"Mismatch: column '{col}' has unexpected length.", file=sys.stderr)
            return EXIT_MISMATCH

    # 5. Metadata
    c_meta = committed.schema.metadata or {}
    e_meta = expected.schema.metadata or {}
    if c_meta != e_meta:
        # Report which keys differ
        c_keys = set(c_meta.keys())
        e_keys = set(e_meta.keys())
        missing = e_keys - c_keys
        extra = c_keys - e_keys
        if missing:
            print(f"Mismatch: metadata missing keys: {sorted(k.decode() for k in missing)}", file=sys.stderr)
        if extra:
            print(f"Mismatch: metadata has unexpected keys: {sorted(k.decode() for k in extra)}", file=sys.stderr)
        for k in c_keys & e_keys:
            if c_meta[k] != e_meta[k]:
                print(
                    f"Mismatch: metadata[{k.decode()!r}] = {c_meta[k]!r}, "
                    f"expected {e_meta[k]!r}.",
                    file=sys.stderr,
                )
        return EXIT_MISMATCH

    print(f"{path.name} matches the registry.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _atomic_write_binary(path: Path, content: bytes) -> None:
    """
    Write binary content to path atomically.

    Writes to a temporary sibling file first, then renames. On POSIX the
    rename is atomic on the same filesystem, so a reader never sees a
    partially written Parquet file.
    """
    tmp_path = path.parent / (path.name + ".tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except OSError as e:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        _fatal(f"Failed to write {path}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Parquet export from iso4217.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              Regenerate iso4217.parquet
  %(prog)s --stdout     Print Parquet bytes to stdout (binary)
  %(prog)s --check      CI: exit 1 if the committed file is stale
  %(prog)s --registry /tmp/test.json
                        Use an alternate registry
        """,
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write Parquet bytes to stdout instead of a file",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if the committed file matches, 1 if it differs, 3 if missing",
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

    if args.stdout and args.check:
        print("ERROR: --stdout and --check are mutually exclusive", file=sys.stderr)
        return EXIT_FATAL

    registry = load_registry(args.registry)

    if args.check:
        return check_parquet(registry)

    if args.stdout:
        content = render_parquet(registry)
        sys.stdout.buffer.write(content)
        return EXIT_OK

    content = render_parquet(registry)
    _atomic_write_binary(PARQUET_PATH, content)
    print(
        f"Wrote {PARQUET_PATH.name} "
        f"({registry.active_count} active + "
        f"{registry.withdrawn_count} withdrawn = "
        f"{registry.total_count} rows, "
        f"{len(content)} bytes)",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
