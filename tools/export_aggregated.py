#!/usr/bin/env python3
# This tool reads from the CURATED layer, never from iso4217.json.
# Reading the RAW source would violate the layering rule stated in
# docs/LAYERS.md: a layer may only assume what the layer below it
# guarantees. If you find yourself wanting to read the JSON directly,
# the projection you need belongs in a CURATED tool instead.
"""
AGGREGATED-layer export generator for the ISO 4217 Currency Registry.

Generates three files at the repository root:

    currencies_by_region.parquet   one row per (region, currency)
    pegs_summary.parquet           one row per anchor currency
    coverage_timeline.parquet      one row per released version

These files answer questions rather than reproduce facts. They are the
third layer of the RAW / CURATED / AGGREGATED model in docs/LAYERS.md,
and the rationale for each design choice below is in
docs/decisions/aggregated-layer-0007.md.

The layering rule, enforced in code
-----------------------------------
The AGGREGATED layer reads CURATED artifacts, never the RAW registry.
This tool enforces that structurally rather than by convention:

- It has no registry loader, no `--registry` flag, and imports nothing
  from the other generators.
- Every input passes through `_guard_input()`, an *allowlist* by input
  kind: Parquet files must end in `.parquet`, the ISO 3166 snapshot must
  end in `.json`, the changelog must end in `.md`, and no input may live
  under a `wrappers/` directory (the wrapper copies are downstream of the
  RAW file and reading them would create a circular dependency).
- The snapshot loader additionally refuses any JSON document that has a
  top-level `currencies` key. That is the signature of the RAW registry;
  passing it by mistake (or on purpose) as `--snapshot` fails with
  EXIT_FATAL instead of silently producing an aggregate with a second
  upstream.

Inputs
------
    iso4217.parquet              CURATED   (tools/export_parquet.py)
    iso4217.countries.parquet    CURATED   (tools/export_countries_parquet.py)
    tools/iso3166_snapshot.json  CURATED   (vendored external reference)
    CHANGELOG.md                 a document, not a data layer

The changelog is the one input that is not a CURATED data artifact, and
it feeds only `coverage_timeline.parquet`. It is not RAW: it is a
human-authored release record, it describes the repository's history
rather than the registry's contents, and no CURATED artifact is derived
from it. ADR 0007 records why this is the single sanctioned exception.

The two CURATED Parquet inputs must carry the same `iso4217.version` and
`iso4217.updated` footer values. If they do not, one of them is stale
relative to the other and the tool exits with EXIT_FATAL rather than
joining across two registry releases.

Design invariants
-----------------
- **Deterministic output.** Every file is sorted on a total key, written
  with snappy compression in one row group, and carries no wall-clock
  timestamp. Two runs on the same inputs produce the same logical content
  (and, for a fixed pyarrow version, the same bytes).

- **Three metadata keys per file.** `iso4217.version` and
  `iso4217.updated` are copied from the CURATED footers (never re-derived
  from the RAW registry); `iso4217.rows` is the row count.

- **Fail loudly, name the culprit.** Every failure names the specific
  code, version, or file at fault. A country code that does not resolve
  in the ISO 3166 snapshot stops the tool with EXIT_FATAL; it is never
  silently dropped.

- **Build everything, then write.** All three tables are built in memory
  before any file is touched, so a fatal error in the third never leaves
  the first two updated and the third stale.

- **Atomic writes.** Each file is written to a temporary sibling and
  renamed into place.

Artifact 1 — currencies_by_region.parquet
-----------------------------------------
Join: `iso4217.countries.parquet` x `iso3166_snapshot.json` x
`iso4217.parquet`.

- Only `status = 'active'` country rows contribute. The region a
  *withdrawn* currency used to circulate in is history, not coverage.
- **The join resolves against `countries.active` in the snapshot only.**
  The snapshot's `countries.withdrawn` list reuses two live alpha-2 codes
  for historical entities (`SK` was Sikkim, `AI` was Afars and Issas). A
  naive merge of both lists would let the withdrawn record overwrite the
  live one and file Slovakia under Southern Asia and Anguilla under
  Eastern Africa. A code that is found only in the withdrawn list is
  reported as such and is fatal.
- **Grain is (region, currency).** `subregion` is therefore a property of
  the group, not a key: it holds the subregion when every country in the
  group shares one, and is null when the countries span several
  subregions (EUR in Europe) or when the snapshot has none. Consumers who
  need the subregion breakdown join the countries Parquet to the snapshot
  themselves.
- **`region` is nullable.** The snapshot has no UN M49 region for
  Kosovo (`XK`) or Taiwan (`TW`). They are kept as rows with a null
  region rather than dropped (which would undercount) or filed under an
  invented label (which would assert something no source says). Nulls
  sort last.
- `country_count` counts distinct countries in the group across *all*
  relationships (issuing, adopting, territory, parallel, local_issue).
- `classification` comes from the countries Parquet, which carries it as
  a denormalized currency attribute (see export_countries_parquet.py for
  why); `currency_name` and `is_pegged` come from `iso4217.parquet`.
  `is_pegged` is `pegged_to IS NOT NULL`. A row where `pegged_to` and
  `peg_type` disagree on nullness is a data error and is fatal.

Artifact 2 — pegs_summary.parquet
---------------------------------
Aggregates `iso4217.parquet` over active rows where `peg_type = 'single'`,
grouped by `pegged_to` (the anchor). The anchor must exist as an active
row in the same file or the tool exits with EXIT_FATAL naming the anchor
and the first currency that references it.

`median_rate`, `min_rate`, `max_rate` are nullable because the schema
permits a `single` peg without a rate. No such row exists today (all 44
have one), so the nulls are dormant; they are kept so that a future
rate-less peg changes a value, not the schema. Caution when reading the
statistics: `peg_rate` is a per-currency exchange rate, and members of
one anchor can differ by orders of magnitude (EUR anchors both BAM at
about 1.96 and XOF at about 656). The median is faithful arithmetic, not
a "typical rate" in any financial sense.

Artifact 3 — coverage_timeline.parquet
--------------------------------------
One row per released version, sorted by version ascending.

Source choice: **static parse, no git.** This tool never shells out to
`git`. Versions come from `## [X.Y.Z] — YYYY-MM-DD` headings in
CHANGELOG.md. A git fallback exists in the column design (`source` may
one day be `"git"`) but is not implemented because it is not needed: the
first heading is 1.0.0, the first release, so no released version
predates the heading format. If one is ever found, supply it through a
helper script that edits the changelog; do not add a subprocess here.

Counts come from the `## Version History` table in the same file, matched
by version. Where the table has no row for a version, the counts are
null. They are not extrapolated from neighbouring rows: "unchanged since
1.5.0" is an inference, and this file records only what the changelog
states. At the time of writing the table ends at 1.5.0, so the 12
versions after it have null counts.

A heading whose date is a placeholder (`2026-09-XX`, as in 1.5.3) yields
a null `date` plus a note on stderr. A heading with a malformed or
impossible date, a duplicate version, a table row without a matching
heading, a table date that disagrees with its heading, or a non-integer
count are all EXIT_FATAL.

Comparison semantics
--------------------
`--check` compares *logical content*, never bytes (see
export_parquet.py): row count, column names, column types, every value,
and the metadata maps. All three files are checked and every finding is
printed. The exit code is the worst finding, in the order 2 (fatal),
1 (mismatch), 3 (missing).

Usage
-----
    # Regenerate all three files (default)
    python3 tools/export_aggregated.py

    # Print a JSON manifest of what would be written; writes nothing
    python3 tools/export_aggregated.py --stdout

    # CI check
    python3 tools/export_aggregated.py --check

    # Alternate inputs / output location
    python3 tools/export_aggregated.py --parquet P --countries C \\
        --snapshot S --changelog L --output-dir DIR

Exit codes
----------
    0  Success (files written, or --check passed)
    1  --check mismatch in at least one file
    2  Fatal error (missing or unreadable input, unresolved country code,
       inconsistent inputs, write failure)
    3  --check found at least one committed file missing

`--stdout` has no meaningful single stream for three binary files, so it
prints a deterministic JSON manifest (file, rows, columns, metadata)
instead.

Dependency
----------
Requires pyarrow, a *build-time* dependency only. No pandas, no polars.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

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

# Inputs (CURATED, plus the changelog document).
CURRENCIES_PARQUET_PATH: Path = PROJECT_ROOT / "iso4217.parquet"
COUNTRIES_PARQUET_PATH: Path = PROJECT_ROOT / "iso4217.countries.parquet"
SNAPSHOT_PATH: Path = PROJECT_ROOT / "tools" / "iso3166_snapshot.json"
CHANGELOG_PATH: Path = PROJECT_ROOT / "CHANGELOG.md"

# Outputs.
OUTPUT_DIR: Path = PROJECT_ROOT
REGION_FILE: str = "currencies_by_region.parquet"
PEGS_FILE: str = "pegs_summary.parquet"
TIMELINE_FILE: str = "coverage_timeline.parquet"

# Schemas. Declared once, used by both the builders and the comparison.
REGION_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("region", pa.string(), nullable=True),
        pa.field("subregion", pa.string(), nullable=True),
        pa.field("currency_code", pa.string(), nullable=False),
        pa.field("currency_name", pa.string(), nullable=False),
        pa.field("classification", pa.string(), nullable=False),
        pa.field("is_pegged", pa.bool_(), nullable=False),
        pa.field("country_count", pa.int32(), nullable=False),
    ]
)

PEGS_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("anchor_code", pa.string(), nullable=False),
        pa.field("anchor_name", pa.string(), nullable=False),
        pa.field("currency_count", pa.int32(), nullable=False),
        pa.field("median_rate", pa.float64(), nullable=True),
        pa.field("min_rate", pa.float64(), nullable=True),
        pa.field("max_rate", pa.float64(), nullable=True),
        pa.field("currencies", pa.list_(pa.string()), nullable=False),
    ]
)

TIMELINE_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("version", pa.string(), nullable=False),
        pa.field("date", pa.string(), nullable=True),
        pa.field("active_count", pa.int32(), nullable=True),
        pa.field("withdrawn_count", pa.int32(), nullable=True),
        pa.field("non_iso_count", pa.int32(), nullable=True),
        pa.field("source", pa.string(), nullable=False),
    ]
)

# What this tool requires of its CURATED Parquet inputs. Extra columns are
# tolerated (a CURATED file may grow); missing or retyped ones are fatal.
CURRENCIES_REQUIRED: dict = {
    "code": pa.string(),
    "name": pa.string(),
    "status": pa.string(),
    "pegged_to": pa.string(),
    "peg_type": pa.string(),
    "peg_rate": pa.float64(),
}
COUNTRIES_REQUIRED: dict = {
    "currency_code": pa.string(),
    "country_code": pa.string(),
    "status": pa.string(),
    "classification": pa.string(),
}

# Parquet footer metadata keys.
METADATA_VERSION_KEY: str = "iso4217.version"
METADATA_UPDATED_KEY: str = "iso4217.updated"
METADATA_ROWS_KEY: str = "iso4217.rows"
COUNTRIES_ROWS_KEY: str = "iso4217.countries_rows"

SOURCE_CHANGELOG: str = "changelog"

# Exit codes, aligned with the other generators.
EXIT_OK: int = 0
EXIT_MISMATCH: int = 1
EXIT_FATAL: int = 2
EXIT_MISSING: int = 3

# Input kinds for the guard, and the suffix each must carry.
_ALLOWED_SUFFIX: dict = {"parquet": ".parquet", "snapshot": ".json", "changelog": ".md"}

# CHANGELOG patterns.
_HEADING_RE = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] [\u2014\u2013-] (\S+)\s*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PLACEHOLDER_DATE_RE = re.compile(r"^\d{4}-(\d{2}|XX)-(\d{2}|XX)$", re.IGNORECASE)
_VERSION_HISTORY_HEADING = "## Version History"


# ---------------------------------------------------------------------------
# Fatal error helper and input guard
# ---------------------------------------------------------------------------

def _fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(EXIT_FATAL)


def _guard_input(path: Path, kind: str) -> None:
    """
    Refuse any input the layering rule does not allow.

    This is an allowlist by kind, not a denylist of the RAW file's name,
    so it holds even if the RAW file is renamed or copied.
    """
    if kind not in _ALLOWED_SUFFIX:
        _fatal(f"internal error: unknown input kind {kind!r}")
    if "wrappers" in path.resolve().parts:
        _fatal(
            f"{path}: inputs under wrappers/ are not allowed "
            "(wrapper copies are downstream of the RAW layer; reading them "
            "would create a circular dependency)"
        )
    if path.suffix != _ALLOWED_SUFFIX[kind]:
        _fatal(
            f"{path}: a {kind} input must end in {_ALLOWED_SUFFIX[kind]!r}; "
            "the AGGREGATED layer reads CURATED artifacts only"
        )


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _read_curated_parquet(path: Path, required: dict, generator: str) -> pa.Table:
    """Read a CURATED Parquet input and verify the columns this tool needs."""
    _guard_input(path, "parquet")
    if not path.exists():
        _fatal(f"Input not found: {path}. Run 'python3 tools/{generator}' to create it.")
    try:
        table = pq.read_table(path)
    except Exception as e:
        _fatal(f"cannot read {path}: {e}")
    for name, expected_type in required.items():
        if name not in table.column_names:
            _fatal(f"{path.name}: required column '{name}' is missing")
        actual = table.schema.field(name).type
        if actual != expected_type:
            _fatal(f"{path.name}: column '{name}' has type {actual}, expected {expected_type}")
    return table


def _footer(table: pa.Table, key: str, path: Path) -> str:
    meta = table.schema.metadata or {}
    value = meta.get(key.encode("utf-8"))
    if value is None:
        _fatal(f"{path.name}: footer metadata key '{key}' is missing")
    return value.decode("utf-8")


class CuratedInputs:
    """The two CURATED Parquet inputs, validated and cross-checked."""

    def __init__(self, currencies_path: Path, countries_path: Path) -> None:
        self.currencies = _read_curated_parquet(
            currencies_path, CURRENCIES_REQUIRED, "export_parquet.py"
        )
        self.countries = _read_curated_parquet(
            countries_path, COUNTRIES_REQUIRED, "export_countries_parquet.py"
        )

        # Both inputs must come from the same registry release.
        for key in (METADATA_VERSION_KEY, METADATA_UPDATED_KEY):
            a = _footer(self.currencies, key, currencies_path)
            b = _footer(self.countries, key, countries_path)
            if a != b:
                _fatal(
                    f"CURATED inputs disagree on {key}: "
                    f"{currencies_path.name}={a!r}, {countries_path.name}={b!r}. "
                    "Regenerate the stale one first."
                )
        self.version = _footer(self.currencies, METADATA_VERSION_KEY, currencies_path)
        self.updated = _footer(self.currencies, METADATA_UPDATED_KEY, currencies_path)

        declared = _footer(self.countries, COUNTRIES_ROWS_KEY, countries_path)
        if declared != str(self.countries.num_rows):
            _fatal(
                f"{countries_path.name}: footer {COUNTRIES_ROWS_KEY}={declared} "
                f"but the file has {self.countries.num_rows} rows (truncated?)"
            )


def load_snapshot(path: Path) -> dict:
    """
    Load the ISO 3166 snapshot and return its two country lists, keyed by
    alpha-2 code: {"active": {...}, "withdrawn": {...}}.
    """
    _guard_input(path, "snapshot")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        _fatal(f"Snapshot not found: {path}")
    except json.JSONDecodeError as e:
        _fatal(f"Invalid JSON in {path}: {e}")

    if not isinstance(data, dict):
        _fatal(f"{path.name}: top level is not an object")
    if "currencies" in data:
        _fatal(
            f"{path.name} has a top-level 'currencies' key: this is the RAW "
            "registry, not an ISO 3166 snapshot. The AGGREGATED layer must "
            "not read it."
        )
    groups = data.get("countries")
    if not isinstance(groups, dict):
        _fatal(f"{path.name}: missing 'countries' object")

    out: dict = {}
    for group in ("active", "withdrawn"):
        entries = groups.get(group)
        if not isinstance(entries, list):
            _fatal(f"{path.name}: countries.{group} is missing or not an array")
        index: dict = {}
        for entry in entries:
            alpha2 = entry.get("alpha_2") if isinstance(entry, dict) else None
            if not isinstance(alpha2, str) or not alpha2:
                _fatal(f"{path.name}: countries.{group} entry without alpha_2: {entry!r}")
            if alpha2 in index:
                _fatal(f"{path.name}: duplicate alpha_2 {alpha2!r} in countries.{group}")
            for field in ("region", "subregion"):
                value = entry.get(field)
                if value is not None and not isinstance(value, str):
                    _fatal(f"{path.name}: {alpha2}.{field} is not a string or null: {value!r}")
            index[alpha2] = entry
        out[group] = index
    return out


# ---------------------------------------------------------------------------
# Artifact 1: currencies_by_region
# ---------------------------------------------------------------------------

def _currency_index(currencies: pa.Table) -> dict:
    """Active rows of iso4217.parquet, keyed by code, as plain dicts."""
    index: dict = {}
    for row in currencies.to_pylist():
        if row["status"] != "active":
            continue
        if row["code"] in index:
            _fatal(f"iso4217.parquet: duplicate active code {row['code']!r}")
        pegged_to, peg_type = row["pegged_to"], row["peg_type"]
        if (pegged_to is None) != (peg_type is None):
            _fatal(
                f"iso4217.parquet: {row['code']} has pegged_to={pegged_to!r} "
                f"but peg_type={peg_type!r}; both must be null or both set"
            )
        index[row["code"]] = row
    return index


def build_region_table(inputs: CuratedInputs, snapshot: dict) -> pa.Table:
    active_index = snapshot["active"]
    withdrawn_index = snapshot["withdrawn"]
    currency_index = _currency_index(inputs.currencies)

    # (region, currency) -> {"countries": set, "subregions": set, "classification": str}
    groups: dict = {}
    for i, row in enumerate(inputs.countries.to_pylist()):
        if row["status"] != "active":
            continue
        code, country = row["currency_code"], row["country_code"]

        entry = active_index.get(country)
        if entry is None:
            hint = (
                " (found only as a withdrawn ISO 3166 entry)"
                if country in withdrawn_index
                else ""
            )
            _fatal(
                f"row {i}: country_code {country!r} (currency_code {code!r}) "
                f"not found in ISO 3166 snapshot countries.active{hint}"
            )
        if code not in currency_index:
            _fatal(f"row {i}: currency_code {code!r} not found among active rows of iso4217.parquet")
        if row["classification"] is None:
            _fatal(f"row {i}: active currency {code!r} has null classification in iso4217.countries.parquet")

        key = (entry["region"], code)
        group = groups.setdefault(
            key,
            {"countries": set(), "subregions": set(), "classification": row["classification"]},
        )
        if group["classification"] != row["classification"]:
            _fatal(
                f"row {i}: currency_code {code!r} has inconsistent classification "
                f"in iso4217.countries.parquet ({group['classification']!r} vs {row['classification']!r})"
            )
        group["countries"].add(country)
        group["subregions"].add(entry["subregion"])

    # Nulls last, then currency code. (region, currency) is unique, so the
    # key is total.
    keys = sorted(groups, key=lambda k: (k[0] is None, k[0] or "", k[1]))

    columns: dict = {name: [] for name in REGION_SCHEMA.names}
    for region, code in keys:
        group = groups[(region, code)]
        currency = currency_index[code]
        subregions = group["subregions"]
        columns["region"].append(region)
        columns["subregion"].append(next(iter(subregions)) if len(subregions) == 1 else None)
        columns["currency_code"].append(code)
        columns["currency_name"].append(currency["name"])
        columns["classification"].append(group["classification"])
        columns["is_pegged"].append(currency["pegged_to"] is not None)
        columns["country_count"].append(len(group["countries"]))
    return _make_table(REGION_SCHEMA, columns, inputs)


# ---------------------------------------------------------------------------
# Artifact 2: pegs_summary
# ---------------------------------------------------------------------------

def build_pegs_table(inputs: CuratedInputs) -> pa.Table:
    currency_index = _currency_index(inputs.currencies)

    members: dict = {}
    for code in sorted(currency_index):
        row = currency_index[code]
        if row["peg_type"] != "single":
            continue
        members.setdefault(row["pegged_to"], []).append(row)

    columns: dict = {name: [] for name in PEGS_SCHEMA.names}
    for anchor in sorted(members):
        rows = members[anchor]
        if anchor not in currency_index:
            _fatal(
                f"anchor {anchor!r} (pegged to by {rows[0]['code']}) "
                "not found among active rows of iso4217.parquet"
            )
        rates = [r["peg_rate"] for r in rows if r["peg_rate"] is not None]
        columns["anchor_code"].append(anchor)
        columns["anchor_name"].append(currency_index[anchor]["name"])
        columns["currency_count"].append(len(rows))
        columns["median_rate"].append(float(statistics.median(rates)) if rates else None)
        columns["min_rate"].append(min(rates) if rates else None)
        columns["max_rate"].append(max(rates) if rates else None)
        columns["currencies"].append([r["code"] for r in rows])
    return _make_table(PEGS_SCHEMA, columns, inputs)


# ---------------------------------------------------------------------------
# Artifact 3: coverage_timeline
# ---------------------------------------------------------------------------

def _parse_heading_date(version: str, raw: str, lineno: int, notes: list) -> Optional[str]:
    if _ISO_DATE_RE.match(raw):
        try:
            datetime.date.fromisoformat(raw)
        except ValueError:
            _fatal(f"CHANGELOG.md line {lineno}: version {version} has impossible date {raw!r}")
        return raw
    if _PLACEHOLDER_DATE_RE.match(raw):
        notes.append(
            f"note: CHANGELOG.md line {lineno}: version {version} has placeholder "
            f"date {raw!r}; date is null"
        )
        return None
    _fatal(f"CHANGELOG.md line {lineno}: version {version} has malformed date {raw!r}")
    return None  # unreachable


def _split_row(line: str) -> list:
    return [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]


def parse_changelog(path: Path) -> tuple:
    """
    Return (versions, notes). `versions` maps "X.Y.Z" to
    {"date", "active", "withdrawn", "non_iso", "line"}.
    """
    _guard_input(path, "changelog")
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _fatal(f"Changelog not found: {path}")
    except (OSError, UnicodeDecodeError) as e:
        _fatal(f"cannot read {path}: {e}")

    lines = text.splitlines()
    notes: list = []
    versions: dict = {}

    for lineno, line in enumerate(lines, start=1):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        version = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        if version in versions:
            _fatal(
                f"CHANGELOG.md line {lineno}: duplicate heading for version {version} "
                f"(first at line {versions[version]['line']})"
            )
        versions[version] = {
            "date": _parse_heading_date(version, m.group(4), lineno, notes),
            "active": None,
            "withdrawn": None,
            "non_iso": None,
            "line": lineno,
        }

    if not versions:
        _fatal("CHANGELOG.md: no '## [X.Y.Z] — YYYY-MM-DD' headings found")

    _apply_version_history(lines, versions)
    return versions, notes


def _apply_version_history(lines: list, versions: dict) -> None:
    """Attach counts from the '## Version History' table, matched by version."""
    start = next(
        (i for i, l in enumerate(lines) if l.strip() == _VERSION_HISTORY_HEADING), None
    )
    if start is None:
        return  # no table: every count stays null

    table: list = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        if l.lstrip().startswith("|"):
            table.append(l)
    if len(table) < 2:
        return

    header = [c.lower() for c in _split_row(table[0])]
    needed = {"version": "version", "date": "date", "active": "active",
              "withdrawn": "withdrawn", "non-iso": "non_iso"}
    idx: dict = {}
    for label, key in needed.items():
        if label not in header:
            _fatal(f"CHANGELOG.md Version History table has no '{label}' column")
        idx[key] = header.index(label)

    for raw in table[1:]:
        cells = _split_row(raw)
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        if len(cells) <= max(idx.values()):
            _fatal(f"CHANGELOG.md Version History: short row {raw.strip()!r}")
        version = cells[idx["version"]]
        if version not in versions:
            _fatal(f"CHANGELOG.md Version History lists {version!r}, which has no '## [{version}]' heading")
        entry = versions[version]
        if entry["date"] is not None and cells[idx["date"]] != entry["date"]:
            _fatal(
                f"CHANGELOG.md: version {version} is dated {entry['date']} in its heading "
                f"but {cells[idx['date']]} in the Version History table"
            )
        for key in ("active", "withdrawn", "non_iso"):
            value = cells[idx[key]]
            if not value.isdigit():
                _fatal(f"CHANGELOG.md Version History: version {version} has non-integer {key} count {value!r}")
            entry[key] = int(value)


def build_timeline_table(inputs: CuratedInputs, changelog_path: Path) -> tuple:
    versions, notes = parse_changelog(changelog_path)

    columns: dict = {name: [] for name in TIMELINE_SCHEMA.names}
    for version in sorted(versions, key=lambda v: tuple(int(p) for p in v.split("."))):
        entry = versions[version]
        columns["version"].append(version)
        columns["date"].append(entry["date"])
        columns["active_count"].append(entry["active"])
        columns["withdrawn_count"].append(entry["withdrawn"])
        columns["non_iso_count"].append(entry["non_iso"])
        columns["source"].append(SOURCE_CHANGELOG)
    return _make_table(TIMELINE_SCHEMA, columns, inputs), notes


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------

def _make_table(schema: pa.Schema, columns: dict, inputs: CuratedInputs) -> pa.Table:
    """
    Build a table with exactly `schema` and the three footer keys attached.
    Version and updated come from the CURATED footers, never from RAW.
    """
    num_rows = len(columns[schema.names[0]])
    metadata = {
        METADATA_VERSION_KEY.encode("utf-8"): inputs.version.encode("utf-8"),
        METADATA_UPDATED_KEY.encode("utf-8"): inputs.updated.encode("utf-8"),
        METADATA_ROWS_KEY.encode("utf-8"): str(num_rows).encode("utf-8"),
    }
    arrays = [pa.array(columns[f.name], type=f.type) for f in schema]
    return pa.Table.from_arrays(arrays, schema=schema.with_metadata(metadata))


def build_all(args: argparse.Namespace) -> tuple:
    """Build every output table in memory. Returns ({filename: table}, notes)."""
    inputs = CuratedInputs(args.parquet, args.countries)
    snapshot = load_snapshot(args.snapshot)
    timeline, notes = build_timeline_table(inputs, args.changelog)
    tables = {
        REGION_FILE: build_region_table(inputs, snapshot),
        PEGS_FILE: build_pegs_table(inputs),
        TIMELINE_FILE: timeline,
    }
    return tables, notes


def render_parquet(table: pa.Table) -> bytes:
    """Serialize a table: snappy, one row group, no tuning."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Comparison (logical, not byte-for-byte)
# ---------------------------------------------------------------------------

def _row_label(table_dict: dict, i: int) -> str:
    """A human-readable key for row i, built from the file's leading columns."""
    for cols in (("region", "currency_code"), ("anchor_code",), ("version",)):
        if all(c in table_dict for c in cols):
            return "/".join(str(table_dict[c][i]) for c in cols)
    return str(i)


def check_one(name: str, expected: pa.Table, directory: Path) -> int:
    """Compare one committed file against its regenerated table."""
    path = directory / name

    if not path.exists():
        print(f"Missing: {path.name}", file=sys.stderr)
        print("Run 'python3 tools/export_aggregated.py' to create it.", file=sys.stderr)
        return EXIT_MISSING

    try:
        committed = pq.read_table(path)
    except Exception as e:
        print(f"FATAL: cannot read {path}: {e}", file=sys.stderr)
        return EXIT_FATAL

    if committed.num_rows != expected.num_rows:
        print(
            f"Mismatch: {path.name} has {committed.num_rows} rows, expected {expected.num_rows}.",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    if committed.column_names != expected.column_names:
        print(
            f"Mismatch: {path.name} column names differ.\n"
            f"  committed: {committed.column_names}\n"
            f"  expected:  {expected.column_names}",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    for i, col in enumerate(committed.column_names):
        ctype = committed.schema.field(i).type
        etype = expected.schema.field(i).type
        if ctype != etype:
            print(f"Mismatch: {path.name} column '{col}' has type {ctype}, expected {etype}.", file=sys.stderr)
            return EXIT_MISMATCH

    committed_dict = committed.to_pydict()
    expected_dict = expected.to_pydict()
    for col in expected.column_names:
        if committed_dict[col] != expected_dict[col]:
            for i, (a, b) in enumerate(zip(committed_dict[col], expected_dict[col])):
                if a != b:
                    print(
                        f"Mismatch: {path.name} row {i} ({_row_label(expected_dict, i)}), "
                        f"column '{col}': committed={a!r}, expected={b!r}.",
                        file=sys.stderr,
                    )
                    return EXIT_MISMATCH
            print(f"Mismatch: {path.name} column '{col}' has unexpected length.", file=sys.stderr)
            return EXIT_MISMATCH

    c_meta = committed.schema.metadata or {}
    e_meta = expected.schema.metadata or {}
    if c_meta != e_meta:
        c_keys, e_keys = set(c_meta), set(e_meta)
        if e_keys - c_keys:
            print(f"Mismatch: {path.name} metadata missing keys: {sorted(k.decode() for k in e_keys - c_keys)}", file=sys.stderr)
        if c_keys - e_keys:
            print(f"Mismatch: {path.name} metadata has unexpected keys: {sorted(k.decode() for k in c_keys - e_keys)}", file=sys.stderr)
        for k in sorted(c_keys & e_keys):
            if c_meta[k] != e_meta[k]:
                print(
                    f"Mismatch: {path.name} metadata[{k.decode()!r}] = {c_meta[k]!r}, expected {e_meta[k]!r}.",
                    file=sys.stderr,
                )
        return EXIT_MISMATCH

    print(f"{path.name} matches the CURATED inputs.")
    return EXIT_OK


def check_all(tables: dict, directory: Path) -> int:
    """Check every output. Worst finding wins, in the order 2, 1, 3."""
    codes = [check_one(name, tables[name], directory) for name in sorted(tables)]
    for worst in (EXIT_FATAL, EXIT_MISMATCH, EXIT_MISSING):
        if worst in codes:
            return worst
    return EXIT_OK


# ---------------------------------------------------------------------------
# File I/O and manifest
# ---------------------------------------------------------------------------

def _atomic_write_binary(path: Path, content: bytes) -> None:
    """
    Write binary content to path atomically: temporary sibling, then
    os.replace, so a reader never sees a partially written Parquet file.
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


def manifest(tables: dict) -> str:
    """A deterministic JSON description of what would be written."""
    files: list = []
    for name in sorted(tables):
        table = tables[name]
        files.append(
            {
                "file": name,
                "rows": table.num_rows,
                "columns": [
                    {"name": f.name, "type": str(f.type), "nullable": f.nullable}
                    for f in table.schema
                ],
                "metadata": {
                    k.decode("utf-8"): v.decode("utf-8")
                    for k, v in sorted((table.schema.metadata or {}).items())
                },
            }
        )
    return json.dumps({"files": files}, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the AGGREGATED-layer Parquet files from CURATED artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              Regenerate the three aggregated files
  %(prog)s --stdout     Print a JSON manifest of what would be written
  %(prog)s --check      CI: exit 1 if any committed file is stale
  %(prog)s --output-dir /tmp/out
                        Write (or check) somewhere other than the repo root
        """,
    )
    parser.add_argument("--stdout", action="store_true",
                        help="Print a JSON manifest instead of writing files")
    parser.add_argument("--check", action="store_true",
                        help="Exit 0 if all committed files match, 1 if any differs, 3 if any is missing")
    parser.add_argument("--parquet", type=Path, default=CURRENCIES_PARQUET_PATH,
                        help=f"CURATED currencies Parquet (default: {CURRENCIES_PARQUET_PATH})")
    parser.add_argument("--countries", type=Path, default=COUNTRIES_PARQUET_PATH,
                        help=f"CURATED countries Parquet (default: {COUNTRIES_PARQUET_PATH})")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH,
                        help=f"ISO 3166 snapshot (default: {SNAPSHOT_PATH})")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_PATH,
                        help=f"Changelog document (default: {CHANGELOG_PATH})")
    parser.add_argument("--output-dir", "-o", type=Path, default=OUTPUT_DIR,
                        help=f"Directory to write or check the outputs in (default: {OUTPUT_DIR})")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)

    if args.stdout and args.check:
        print("ERROR: --stdout and --check are mutually exclusive", file=sys.stderr)
        return EXIT_FATAL

    tables, notes = build_all(args)
    for note in notes:
        print(note, file=sys.stderr)

    if args.check:
        return check_all(tables, args.output_dir)

    if args.stdout:
        sys.stdout.write(manifest(tables))
        return EXIT_OK

    # Everything is built; only now touch the disk.
    for name in sorted(tables):
        content = render_parquet(tables[name])
        _atomic_write_binary(args.output_dir / name, content)
        print(f"Wrote {name} ({tables[name].num_rows} rows, {len(content)} bytes)", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
