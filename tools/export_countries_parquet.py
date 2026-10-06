#!/usr/bin/env python3
"""
Countries Parquet export generator for the ISO 4217 Currency Registry.

Generates a single file at the repository root:

    iso4217.countries.parquet   Parquet 2.0, snappy-compressed, one row group

This is a CURATED artifact. It is a *projection* of the registry's
`countries[]` arrays, one row per (currency, country) pair, flattened so
that an analytical engine can join it without parsing nested JSON. It is
not an aggregate: no rows are collapsed, no counts are computed. The
AGGREGATED layer (tools/export_aggregated.py) reads this file; it never
reads the registry directly. See docs/decisions/aggregated-layer-0007.md for
why the projection lives here and not there.

Design invariants
-----------------
- **One row per (currency, country, relationship).** A country appears
  once per currency that lists it. A currency that lists three countries
  produces three rows. Within one currency a country code may appear only
  once; a duplicate is a data error and exits with EXIT_FATAL naming both
  the currency and the country.

- **Six columns.** The first five are the projection proper:
  `currency_code`, `country_code`, `country_name`, `relationship`,
  `status`. The sixth, `classification`, is a *denormalized currency
  attribute* (`circulating` | `fund` | `indexation`, null for withdrawn
  entries). It is carried here because no other CURATED artifact exposes
  it: `iso4217.parquet` has eleven columns (ADR 0002) and `classification`
  is not one of them. The AGGREGATED layer is forbidden to read the
  registry, so the only way for it to see `classification` is for a
  CURATED artifact to carry it. Widening the eleven-column file would
  break the CSV/Parquet column parity ADR 0002 establishes; widening this
  new file breaks nothing.

- **`status` is derived, not stored.** `"active"` for entries read from
  `currencies.active`, `"withdrawn"` for entries read from
  `currencies.withdrawn`, same derivation as `iso4217.parquet`. At the
  time of writing only active entries carry `countries[]`, so every row
  is `"active"`; the withdrawn branch is kept so the file does not need a
  schema change the day a withdrawn entry gains a country list.

- **Deterministic row order.** Sorted by (`status`, `currency_code`,
  `country_code`). `status` sorts `active` before `withdrawn`, matching
  `iso4217.parquet`'s status grouping. The registry's own per-currency
  country order is *not* preserved: it is editorial (issuing country
  first), and a stable sort key is what makes `--check` meaningful.

- **Three metadata keys, no more.** `iso4217.version`, `iso4217.updated`,
  `iso4217.countries_rows`. The first two identify the registry release
  that produced the file; the third lets a reader detect truncation
  without scanning the data. No wall-clock timestamps: two runs on the
  same registry produce the same logical content (and, for a fixed
  pyarrow version, the same bytes).

- **Atomic write.** The file is written to a temporary sibling and
  renamed into place. A crash mid-write never leaves a partial file.

Comparison semantics
--------------------
Same as `export_parquet.py`: `--check` compares *logical content*, not
bytes, because the Parquet format permits different but equivalent
physical layouts.

    1. Parse the committed file with pyarrow.parquet.read_table.
    2. Regenerate the table in memory from the current registry.
    3. Compare row count, column names, and column types.
    4. Compare every value.
    5. Compare the metadata key-value maps.

What this tool does not validate
--------------------------------
It does not check that country codes exist in ISO 3166. That is
`tools/check_country_codes.py`'s job against the vendored snapshot, and
the AGGREGATED tool re-asserts it at join time. This tool's contract is
narrower: faithfully project what the registry says.

Usage
-----
    # Regenerate the file (default)
    python3 tools/export_countries_parquet.py

    # Print the Parquet bytes to stdout (binary)
    python3 tools/export_countries_parquet.py --stdout

    # CI check — exit 0 if the committed file matches, 1 if it differs,
    # 3 if it is missing
    python3 tools/export_countries_parquet.py --check

Exit codes
----------
    0  Success (file written, or --check passed)
    1  --check mismatch
    2  Fatal error (missing registry, invalid JSON, bad entry, write failure)
    3  --check found the committed file missing

Dependency
----------
Requires pyarrow, a *build-time* dependency only. It must not appear in
wrappers/python/setup.py's install_requires or extras_require.
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
PARQUET_PATH: Path = PROJECT_ROOT / "iso4217.countries.parquet"

# Column names, in output order.
COLUMNS: tuple[str, ...] = (
    "currency_code",
    "country_code",
    "country_name",
    "relationship",
    "status",
    "classification",
)

# The Parquet schema. Declared once, used by both the renderer and the
# comparison. Column order here must match COLUMNS.
PARQUET_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("currency_code", pa.string(), nullable=False),
        pa.field("country_code", pa.string(), nullable=False),
        pa.field("country_name", pa.string(), nullable=False),
        pa.field("relationship", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("classification", pa.string(), nullable=True),
    ]
)

# Parquet footer metadata keys.
METADATA_VERSION_KEY: str = "iso4217.version"
METADATA_UPDATED_KEY: str = "iso4217.updated"
METADATA_ROWS_KEY: str = "iso4217.countries_rows"

# Exit codes, aligned with export_sql.py, export_csv.py, export_parquet.py.
EXIT_OK: int = 0
EXIT_MISMATCH: int = 1
EXIT_FATAL: int = 2
EXIT_MISSING: int = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CountryRow:
    """
    One (currency, country) pair, reduced to the six export columns.

    `classification` is None for entries that do not carry one (every
    withdrawn entry). All other fields are required and non-empty.
    """

    currency_code: str
    country_code: str
    country_name: str
    relationship: str
    status: str
    classification: Optional[str]

    def as_dict(self) -> dict:
        """Return the row as a dict in COLUMNS order."""
        return {
            "currency_code": self.currency_code,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "relationship": self.relationship,
            "status": self.status,
            "classification": self.classification,
        }


@dataclass
class CountriesProjection:
    """The registry reduced to exactly what this exporter needs."""

    version: str
    updated: str
    rows: list[CountryRow]

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

def load_projection(path: Path) -> CountriesProjection:
    """
    Load the registry and reduce it to a CountriesProjection.

    Structural problems exit with EXIT_FATAL; the message names the
    specific currency and country at fault.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        _fatal(f"Registry not found: {path}")
    except json.JSONDecodeError as e:
        _fatal(f"Invalid JSON in {path}: {e}")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        _fatal("Registry is missing 'meta' object")

    version = meta.get("version")
    updated = meta.get("updated")
    if not isinstance(version, str) or not version:
        _fatal("meta.version is missing or not a string")
    if not isinstance(updated, str) or not updated:
        _fatal("meta.updated is missing or not a string")

    currencies = data.get("currencies")
    if not isinstance(currencies, dict):
        _fatal("Registry is missing 'currencies' object")

    rows: list[CountryRow] = []
    for status in ("active", "withdrawn"):
        entries = currencies.get(status, [])
        if not isinstance(entries, list):
            _fatal(f"currencies.{status} is not an array")
        for entry in entries:
            rows.extend(_rows_from_entry(entry, status))

    # Deterministic ordering: (status, currency_code, country_code).
    # 'active' < 'withdrawn' lexicographically, which gives the same
    # status grouping as iso4217.parquet without a special case.
    rows.sort(key=lambda r: (r.status, r.currency_code, r.country_code))

    return CountriesProjection(version=version, updated=updated, rows=rows)


def _rows_from_entry(entry: dict, status: str) -> list[CountryRow]:
    """
    Convert one registry entry into zero or more CountryRow objects.

    An entry without `countries` (or with an empty list) yields no rows.
    That is not an error: every withdrawn entry is in this state today,
    and the registry's schema does not require the field.
    """
    code = entry.get("code")
    if not isinstance(code, str) or not code:
        _fatal(f"Invalid or missing 'code' in {status} entry: {entry!r}")

    countries = entry.get("countries")
    if countries is None:
        return []
    if not isinstance(countries, list):
        _fatal(f"'countries' for {code} is not an array: {countries!r}")

    classification = entry.get("classification")
    if classification is not None and (
        not isinstance(classification, str) or not classification
    ):
        _fatal(f"Invalid 'classification' for {code}: {classification!r}")

    seen: set[str] = set()
    rows: list[CountryRow] = []
    for i, country in enumerate(countries):
        where = f"{code}.countries[{i}]"
        if not isinstance(country, dict):
            _fatal(f"{where} is not an object: {country!r}")

        country_code = country.get("code")
        if (
            not isinstance(country_code, str)
            or len(country_code) != 2
            or not (country_code.isascii() and country_code.isalpha() and country_code.isupper())
        ):
            _fatal(f"{where}: invalid country 'code' {country_code!r} (expected two uppercase letters)")

        country_name = country.get("name")
        if not isinstance(country_name, str) or not country_name:
            _fatal(f"{where} ({country_code}): invalid or missing 'name'")

        relationship = country.get("relationship")
        if not isinstance(relationship, str) or not relationship:
            _fatal(f"{where} ({country_code}): invalid or missing 'relationship'")

        if country_code in seen:
            _fatal(f"{code} lists country {country_code!r} more than once")
        seen.add(country_code)

        rows.append(
            CountryRow(
                currency_code=code,
                country_code=country_code,
                country_name=country_name,
                relationship=relationship,
                status=status,
                classification=classification,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Parquet rendering
# ---------------------------------------------------------------------------

def _build_metadata(projection: CountriesProjection) -> dict[bytes, bytes]:
    """
    Return the Parquet footer metadata as a bytes->bytes dict.

    pyarrow stores metadata keys and values as bytes. The comparison in
    check_parquet() works on this exact representation.
    """
    return {
        METADATA_VERSION_KEY.encode("utf-8"): projection.version.encode("utf-8"),
        METADATA_UPDATED_KEY.encode("utf-8"): projection.updated.encode("utf-8"),
        METADATA_ROWS_KEY.encode("utf-8"): str(projection.total_count).encode("utf-8"),
    }


def _build_table(projection: CountriesProjection) -> pa.Table:
    """
    Build a pyarrow Table from the projection, with the exact schema in
    PARQUET_SCHEMA and the three metadata keys attached.

    The table is returned in memory; render_parquet() serializes it.
    """
    column_data: dict[str, list] = {col: [] for col in COLUMNS}
    for row in projection.rows:
        d = row.as_dict()
        for col in COLUMNS:
            column_data[col].append(d[col])

    # Attach metadata to the schema before creating the table, so the
    # metadata is written into the Parquet footer, not just the in-memory
    # schema.
    schema_with_metadata = PARQUET_SCHEMA.with_metadata(_build_metadata(projection))

    arrays = [
        pa.array(column_data[col], type=PARQUET_SCHEMA.field(col).type)
        for col in COLUMNS
    ]
    return pa.Table.from_arrays(arrays, schema=schema_with_metadata)


def render_parquet(projection: CountriesProjection) -> bytes:
    """
    Render the projection as a complete Parquet file and return the bytes.

    Snappy compression, one row group, no tuning.
    """
    table = _build_table(projection)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Comparison (logical, not byte-for-byte)
# ---------------------------------------------------------------------------

def check_parquet(projection: CountriesProjection, path: Path) -> int:
    """
    --check mode: compare the committed file against the regenerated
    table, logically. Returns the exit code.

    Byte comparison does not work for Parquet. See the module docstring.

    Missing file       -> EXIT_MISSING (3)
    Any mismatch       -> EXIT_MISMATCH (1)
    Identical content  -> EXIT_OK (0)
    """
    if not path.exists():
        print(f"Missing: {path.name}", file=sys.stderr)
        print("Run 'python3 tools/export_countries_parquet.py' to create it.", file=sys.stderr)
        return EXIT_MISSING

    try:
        committed = pq.read_table(path)
    except Exception as e:
        print(f"FATAL: cannot read {path}: {e}", file=sys.stderr)
        return EXIT_FATAL

    expected = _build_table(projection)

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
                    key = (
                        f"{committed_dict['currency_code'][i]}/"
                        f"{committed_dict['country_code'][i]}"
                    )
                    print(
                        f"Mismatch: row {i} ({key}), column '{col}': "
                        f"committed={a!r}, expected={b!r}.",
                        file=sys.stderr,
                    )
                    return EXIT_MISMATCH
            print(f"Mismatch: column '{col}' has unexpected length.", file=sys.stderr)
            return EXIT_MISMATCH

    # 5. Metadata
    c_meta = committed.schema.metadata or {}
    e_meta = expected.schema.metadata or {}
    if c_meta != e_meta:
        c_keys = set(c_meta.keys())
        e_keys = set(e_meta.keys())
        missing = e_keys - c_keys
        extra = c_keys - e_keys
        if missing:
            print(f"Mismatch: metadata missing keys: {sorted(k.decode() for k in missing)}", file=sys.stderr)
        if extra:
            print(f"Mismatch: metadata has unexpected keys: {sorted(k.decode() for k in extra)}", file=sys.stderr)
        for k in sorted(c_keys & e_keys):
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
        description="Generate the countries Parquet export from iso4217.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              Regenerate iso4217.countries.parquet
  %(prog)s --stdout     Print Parquet bytes to stdout (binary)
  %(prog)s --check      CI: exit 1 if the committed file is stale
  %(prog)s --registry /tmp/test.json --parquet /tmp/out.parquet
                        Use an alternate registry and output path
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
    parser.add_argument(
        "--parquet", "-p",
        type=Path,
        default=PARQUET_PATH,
        help=f"Path of the Parquet file to write or check (default: {PARQUET_PATH})",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.stdout and args.check:
        print("ERROR: --stdout and --check are mutually exclusive", file=sys.stderr)
        return EXIT_FATAL

    projection = load_projection(args.registry)

    if args.check:
        return check_parquet(projection, args.parquet)

    content = render_parquet(projection)

    if args.stdout:
        sys.stdout.buffer.write(content)
        return EXIT_OK

    _atomic_write_binary(args.parquet, content)
    print(
        f"Wrote {args.parquet.name} "
        f"({projection.total_count} rows, "
        f"{len(content)} bytes)",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
