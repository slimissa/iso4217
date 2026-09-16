"""
Tests for tools/export_parquet.py.

Covers:
  - Module constants (COLUMNS, PARQUET_SCHEMA, metadata keys, exit codes)
  - Data classes (CurrencyRow, Registry)
  - Registry loading (valid, missing, malformed, bad field types)
  - Row construction (_row_from_entry) with native types and null semantics
  - The Parquet schema (column names, types, nullability)
  - Metadata (three keys, values match the registry, only those three)
  - Rendering (render_parquet produces a valid Parquet file)
  - Native type round-trips (int8, bool, float64, string)
  - Null semantics (pegged_to, peg_type, peg_rate)
  - Determinism (same registry produces identical logical content)
  - Sort order (active first, sorted; withdrawn after, sorted)
  - Atomic writes (no .tmp file lingers; content preserved)
  - --check mode (clean, tampered value, tampered type, tampered metadata,
    missing file, row-count mismatch, column-name mismatch)
  - CLI argument parsing and exit codes
  - Cross-checks against the CSV and SQL exports
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.export_parquet as export_parquet
from tools.export_parquet import (
    COLUMNS,
    EXIT_FATAL,
    EXIT_MISMATCH,
    EXIT_MISSING,
    EXIT_OK,
    METADATA_AMENDMENT_KEY,
    METADATA_UPDATED_KEY,
    METADATA_VERSION_KEY,
    PARQUET_PATH,
    PARQUET_SCHEMA,
    CurrencyRow,
    Registry,
    _atomic_write_binary,
    _build_metadata,
    _build_table,
    _row_from_entry,
    check_parquet,
    load_registry,
    main,
    parse_args,
    render_parquet,
)


# ---------------------------------------------------------------------------
# Module-level test helpers
# ---------------------------------------------------------------------------

def _build_row(**overrides) -> CurrencyRow:
    """Build a CurrencyRow with sensible defaults, overridable per field."""
    base = {
        "code": "USD",
        "numeric_code": "840",
        "name": "US Dollar",
        "minor_units": 2,
        "symbol": "$",
        "entity": "United States",
        "status": "active",
        "is_independent": True,
        "pegged_to": None,
        "peg_type": None,
        "peg_rate": None,
    }
    base.update(overrides)
    return CurrencyRow(**base)


def _wrap_rows(*rows: CurrencyRow, version: str = "9.9.9",
               updated: str = "2026-01-01", amendment: int = 179) -> Registry:
    """Wrap one or more rows in a Registry for rendering tests."""
    return Registry(
        version=version,
        updated=updated,
        amendment=amendment,
        rows=list(rows),
    )


def _write_tampered(source_path: Path, dest_path: Path, mutate) -> None:
    """
    Read a Parquet file, apply `mutate(table) -> table`, write to dest.

    Keeps the caller test concise: each tamper test is one small lambda.
    """
    table = pq.read_table(source_path)
    mutated = mutate(table)
    pq.write_table(mutated, dest_path, compression="snappy")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_registry_json() -> dict:
    """
    A minimal structurally valid registry, enough for all renderers.

    Covers the four peg cases (independent, single, basket, undisclosed),
    plus a withdrawn entry. Small enough to reason about, complete enough
    to exercise every type and null path.
    """
    return {
        "meta": {"version": "9.9.9", "updated": "2026-01-01"},
        "source": {"last_amendment_applied": 179},
        "currencies": {
            "active": [
                {
                    "code": "AED", "numeric": "784",
                    "name": "UAE Dirham", "minor_units": 2,
                    "symbol": "د.إ", "entity": "United Arab Emirates",
                    "is_independent": False,
                    "pegged_to": "USD", "peg_type": "single", "peg_rate": 3.6725,
                },
                {
                    "code": "EUR", "numeric": "978",
                    "name": "Euro", "minor_units": 2,
                    "symbol": "€", "entity": "European Union",
                    "is_independent": True,
                },
                {
                    "code": "JPY", "numeric": "392",
                    "name": "Japanese Yen", "minor_units": 0,
                    "symbol": "¥", "entity": "Japan",
                    "is_independent": True,
                },
                {
                    "code": "KWD", "numeric": "414",
                    "name": "Kuwaiti Dinar", "minor_units": 3,
                    "symbol": "د.ك", "entity": "Kuwait",
                    "is_independent": False,
                    "pegged_to": "Currency basket", "peg_type": "undisclosed",
                },
                {
                    "code": "MAD", "numeric": "504",
                    "name": "Moroccan Dirham", "minor_units": 2,
                    "symbol": "د.م.", "entity": "Morocco",
                    "is_independent": False,
                    "pegged_to": "EUR+USD basket", "peg_type": "basket",
                },
            ],
            "withdrawn": [
                {
                    "code": "DEM", "numeric": "276",
                    "name": "German Mark", "minor_units": 2,
                    "symbol": "DM", "entity": "Germany",
                    "is_independent": False,
                },
                {
                    "code": "MXN_OLD", "numeric": "484",
                    "name": "Mexican Peso (pre-1993)", "minor_units": 2,
                    "symbol": "MXP", "entity": "Mexico",
                    "is_independent": False,
                },
            ],
        },
    }


@pytest.fixture
def minimal_registry_file(tmp_path: Path, minimal_registry_json: dict) -> Path:
    path = tmp_path / "iso4217.json"
    path.write_text(json.dumps(minimal_registry_json, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def minimal_registry(minimal_registry_file: Path) -> Registry:
    return load_registry(minimal_registry_file)


@pytest.fixture
def empty_registry_json() -> dict:
    return {
        "meta": {"version": "0.0.0", "updated": "2026-01-01"},
        "source": {"last_amendment_applied": 179},
        "currencies": {"active": [], "withdrawn": []},
    }


@pytest.fixture
def project_root_in_tmp(
    tmp_path: Path,
    minimal_registry_json: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """
    Redirect export_parquet's module-level path constants to a temp dir.

    Both PROJECT_ROOT (used at call time by some helpers) and PARQUET_PATH
    (read by check_parquet) must be patched. REGISTRY_PATH is passed
    explicitly by the tests that need it, so it does not need patching.
    """
    (tmp_path / "iso4217.json").write_text(
        json.dumps(minimal_registry_json, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(export_parquet, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(export_parquet, "PARQUET_PATH", tmp_path / "iso4217.parquet")
    return tmp_path


# ===========================================================================
# Module constants
# ===========================================================================

class TestConstants:
    def test_columns_has_eleven(self):
        assert len(COLUMNS) == 11

    def test_columns_names_match_csv_export(self):
        """The Parquet columns must be identical to the CSV columns.
        A consumer choosing between formats chooses on format, not schema."""
        assert COLUMNS == (
            "code", "numeric_code", "name", "minor_units", "symbol",
            "entity", "status", "is_independent", "pegged_to",
            "peg_type", "peg_rate",
        )

    def test_schema_field_names_match_columns(self):
        assert tuple(PARQUET_SCHEMA.names) == COLUMNS

    def test_exit_codes(self):
        assert EXIT_OK == 0
        assert EXIT_MISMATCH == 1
        assert EXIT_FATAL == 2
        assert EXIT_MISSING == 3

    def test_metadata_keys_are_distinct(self):
        keys = {METADATA_VERSION_KEY, METADATA_UPDATED_KEY, METADATA_AMENDMENT_KEY}
        assert len(keys) == 3

    def test_metadata_keys_are_strings(self):
        for k in (METADATA_VERSION_KEY, METADATA_UPDATED_KEY, METADATA_AMENDMENT_KEY):
            assert isinstance(k, str)
            assert k.startswith("iso4217.")


# ===========================================================================
# Parquet schema
# ===========================================================================

class TestParquetSchema:
    """The schema is declared once, in PARQUET_SCHEMA. Verify its shape."""

    def test_code_is_non_nullable_string(self):
        f = PARQUET_SCHEMA.field("code")
        assert f.type == pa.string()
        assert f.nullable is False

    def test_numeric_code_is_non_nullable_string(self):
        f = PARQUET_SCHEMA.field("numeric_code")
        assert f.type == pa.string()
        assert f.nullable is False

    def test_name_is_non_nullable_string(self):
        f = PARQUET_SCHEMA.field("name")
        assert f.type == pa.string()
        assert f.nullable is False

    def test_minor_units_is_non_nullable_int8(self):
        f = PARQUET_SCHEMA.field("minor_units")
        assert f.type == pa.int8()
        assert f.nullable is False

    def test_symbol_is_nullable_string(self):
        f = PARQUET_SCHEMA.field("symbol")
        assert f.type == pa.string()
        assert f.nullable is True

    def test_entity_is_nullable_string(self):
        f = PARQUET_SCHEMA.field("entity")
        assert f.type == pa.string()
        assert f.nullable is True

    def test_status_is_non_nullable_string(self):
        f = PARQUET_SCHEMA.field("status")
        assert f.type == pa.string()
        assert f.nullable is False

    def test_is_independent_is_non_nullable_bool(self):
        f = PARQUET_SCHEMA.field("is_independent")
        assert f.type == pa.bool_()
        assert f.nullable is False

    def test_pegged_to_is_nullable_string(self):
        f = PARQUET_SCHEMA.field("pegged_to")
        assert f.type == pa.string()
        assert f.nullable is True

    def test_peg_type_is_nullable_string(self):
        f = PARQUET_SCHEMA.field("peg_type")
        assert f.type == pa.string()
        assert f.nullable is True

    def test_peg_rate_is_nullable_float64(self):
        f = PARQUET_SCHEMA.field("peg_rate")
        assert f.type == pa.float64()
        assert f.nullable is True


# ===========================================================================
# CurrencyRow
# ===========================================================================

class TestCurrencyRow:
    def test_frozen(self):
        r = _build_row()
        with pytest.raises(Exception):
            r.code = "EUR"  # type: ignore

    def test_hashable(self):
        assert {_build_row()}

    def test_equality(self):
        assert _build_row() == _build_row()

    def test_inequality(self):
        assert _build_row() != _build_row(code="EUR", numeric_code="978")

    def test_as_dict_has_eleven_fields(self):
        assert len(_build_row().as_dict()) == 11

    def test_as_dict_keys_match_columns(self):
        assert tuple(_build_row().as_dict().keys()) == COLUMNS


# ===========================================================================
# Registry
# ===========================================================================

class TestRegistry:
    def test_active_count(self, minimal_registry: Registry):
        assert minimal_registry.active_count == 5

    def test_withdrawn_count(self, minimal_registry: Registry):
        assert minimal_registry.withdrawn_count == 2

    def test_total_count(self, minimal_registry: Registry):
        assert minimal_registry.total_count == 7

    def test_active_rows_come_first(self, minimal_registry: Registry):
        statuses = [r.status for r in minimal_registry.rows]
        first_withdrawn = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_withdrawn])
        assert all(s == "withdrawn" for s in statuses[first_withdrawn:])


# ===========================================================================
# load_registry
# ===========================================================================

class TestLoadRegistry:
    def test_loads_valid(self, minimal_registry_file: Path):
        r = load_registry(minimal_registry_file)
        assert r.version == "9.9.9"
        assert r.updated == "2026-01-01"
        assert r.amendment == 179

    def test_missing_file_fatal(self, tmp_path: Path):
        with pytest.raises(SystemExit) as e:
            load_registry(tmp_path / "nope.json")
        assert e.value.code == EXIT_FATAL

    def test_invalid_json_fatal(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_missing_meta_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({"source": {}, "currencies": {}}), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_missing_version_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_missing_source_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_amendment_not_int_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": "179"},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_missing_currencies_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
        }), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_active_not_array_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {"active": "USD", "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_registry(p)

    def test_empty_currencies_ok(self, tmp_path: Path, empty_registry_json: dict):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(empty_registry_json), encoding="utf-8")
        r = load_registry(p)
        assert r.active_count == 0
        assert r.withdrawn_count == 0
        assert r.total_count == 0


# ===========================================================================
# _row_from_entry — validation and native-type conversion
# ===========================================================================

class TestRowFromEntry:
    def _entry(self, **overrides) -> dict:
        base = {
            "code": "USD", "numeric": "840", "name": "US Dollar",
            "minor_units": 2, "symbol": "$", "entity": "United States",
            "is_independent": True,
        }
        base.update(overrides)
        return base

    # ---- code ----

    def test_valid_active(self):
        row = _row_from_entry(self._entry(), "active")
        assert row.code == "USD"
        assert row.status == "active"

    def test_valid_withdrawn(self):
        assert _row_from_entry(self._entry(), "withdrawn").status == "withdrawn"

    def test_code_7_chars_accepted(self):
        row = _row_from_entry(self._entry(code="MXN_OLD"), "withdrawn")
        assert row.code == "MXN_OLD"

    def test_code_2_chars_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(code="US"), "active")

    def test_code_lowercase_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(code="usd"), "active")

    # ---- numeric ----

    def test_numeric_must_be_3_digits(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84"), "active")

    def test_numeric_leading_zero_preserved(self):
        assert _row_from_entry(self._entry(numeric="036"), "active").numeric_code == "036"

    def test_numeric_non_digit_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84X"), "active")

    # ---- minor_units ----

    def test_minor_units_is_int(self):
        row = _row_from_entry(self._entry(minor_units=2), "active")
        assert isinstance(row.minor_units, int)
        assert not isinstance(row.minor_units, bool)

    def test_minor_units_zero_accepted(self):
        assert _row_from_entry(self._entry(minor_units=0), "active").minor_units == 0

    def test_minor_units_18_accepted(self):
        assert _row_from_entry(self._entry(minor_units=18), "active").minor_units == 18

    def test_minor_units_negative_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=-1), "active")

    def test_minor_units_above_18_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=19), "active")

    def test_minor_units_float_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=2.5), "active")

    # ---- optional text ----

    def test_missing_symbol_becomes_empty_string(self):
        assert _row_from_entry(self._entry(symbol=None), "active").symbol == ""

    def test_missing_entity_becomes_empty_string(self):
        assert _row_from_entry(self._entry(entity=None), "active").entity == ""

    # ---- is_independent ----

    def test_is_independent_true_preserved(self):
        assert _row_from_entry(self._entry(is_independent=True), "active").is_independent is True

    def test_is_independent_false_preserved(self):
        assert _row_from_entry(self._entry(is_independent=False), "active").is_independent is False

    def test_is_independent_missing_defaults_false(self):
        """Conservative default, matching the wrapper and CSV export."""
        entry = {"code": "XYZ", "numeric": "999", "name": "X", "minor_units": 2}
        assert _row_from_entry(entry, "active").is_independent is False

    def test_is_independent_non_bool_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(is_independent="yes"), "active")

    # ---- peg columns: null semantics ----

    def test_absent_peg_columns_become_none(self):
        row = _row_from_entry(self._entry(), "active")
        assert row.pegged_to is None
        assert row.peg_type is None
        assert row.peg_rate is None

    def test_explicit_null_peg_columns_stay_none(self):
        row = _row_from_entry(
            self._entry(pegged_to=None, peg_type=None, peg_rate=None), "active"
        )
        assert row.pegged_to is None
        assert row.peg_type is None
        assert row.peg_rate is None

    def test_single_peg_has_all_fields(self):
        row = _row_from_entry(
            self._entry(
                is_independent=False, pegged_to="USD",
                peg_type="single", peg_rate=3.6725,
            ),
            "active",
        )
        assert row.pegged_to == "USD"
        assert row.peg_type == "single"
        assert row.peg_rate == 3.6725

    def test_peg_rate_is_float(self):
        row = _row_from_entry(
            self._entry(pegged_to="USD", peg_type="single", peg_rate=2),
            "active",
        )
        assert isinstance(row.peg_rate, float)
        assert row.peg_rate == 2.0

    def test_basket_peg_has_no_rate(self):
        row = _row_from_entry(
            self._entry(
                is_independent=False, pegged_to="EUR+USD basket",
                peg_type="basket",
            ),
            "active",
        )
        assert row.pegged_to == "EUR+USD basket"
        assert row.peg_type == "basket"
        assert row.peg_rate is None

    def test_undisclosed_peg_has_no_rate(self):
        row = _row_from_entry(
            self._entry(
                is_independent=False, pegged_to="Currency basket",
                peg_type="undisclosed",
            ),
            "active",
        )
        assert row.pegged_to == "Currency basket"
        assert row.peg_type == "undisclosed"
        assert row.peg_rate is None

    def test_peg_rate_bool_rejected(self):
        """bool is a subclass of int in Python; must not be accepted."""
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(peg_rate=True), "active")

    def test_peg_rate_string_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(peg_rate="3.6725"), "active")


# ===========================================================================
# Metadata
# ===========================================================================

class TestMetadata:
    def test_three_keys(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        assert len(meta) == 3

    def test_keys_are_bytes(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        for k in meta:
            assert isinstance(k, bytes)

    def test_values_are_bytes(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        for v in meta.values():
            assert isinstance(v, bytes)

    def test_version_value_matches_registry(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        assert meta[METADATA_VERSION_KEY.encode()] == b"9.9.9"

    def test_updated_value_matches_registry(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        assert meta[METADATA_UPDATED_KEY.encode()] == b"2026-01-01"

    def test_amendment_value_matches_registry(self, minimal_registry: Registry):
        meta = _build_metadata(minimal_registry)
        assert meta[METADATA_AMENDMENT_KEY.encode()] == b"179"

    def test_amendment_rendered_as_string(self):
        reg = _wrap_rows(_build_row(), amendment=42)
        meta = _build_metadata(reg)
        assert meta[METADATA_AMENDMENT_KEY.encode()] == b"42"

    def test_no_extra_metadata_keys(self, minimal_registry: Registry):
        """Only three keys. No timestamp, no git commit, no author."""
        meta = _build_metadata(minimal_registry)
        expected = {
            METADATA_VERSION_KEY.encode(),
            METADATA_UPDATED_KEY.encode(),
            METADATA_AMENDMENT_KEY.encode(),
        }
        assert set(meta.keys()) == expected


# ===========================================================================
# render_parquet — the whole pipeline from Registry to bytes
# ===========================================================================

class TestRenderParquet:
    def test_produces_bytes(self, minimal_registry: Registry):
        assert isinstance(render_parquet(minimal_registry), bytes)

    def test_non_empty(self, minimal_registry: Registry):
        assert len(render_parquet(minimal_registry)) > 0

    def test_round_trips_through_pyarrow(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        table = pq.read_table(io.BytesIO(content))
        assert table.num_rows == minimal_registry.total_count
        assert table.num_columns == 11

    def test_metadata_present_in_file(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        table = pq.read_table(io.BytesIO(content))
        meta = table.schema.metadata or {}
        assert METADATA_VERSION_KEY.encode() in meta
        assert METADATA_UPDATED_KEY.encode() in meta
        assert METADATA_AMENDMENT_KEY.encode() in meta

    def test_metadata_values_correct(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        table = pq.read_table(io.BytesIO(content))
        meta = table.schema.metadata or {}
        assert meta[METADATA_VERSION_KEY.encode()] == b"9.9.9"
        assert meta[METADATA_UPDATED_KEY.encode()] == b"2026-01-01"
        assert meta[METADATA_AMENDMENT_KEY.encode()] == b"179"

    def test_empty_registry_renders(self, empty_registry_json: dict, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(empty_registry_json), encoding="utf-8")
        reg = load_registry(p)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.num_rows == 0
        assert table.num_columns == 11


# ===========================================================================
# Native type round-trips
# ===========================================================================

class TestNativeTypes:
    """The whole point of Parquet: the file carries typed columns."""

    def test_minor_units_is_int8(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        assert t.schema.field("minor_units").type == pa.int8()

    def test_is_independent_is_bool(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        assert t.schema.field("is_independent").type == pa.bool_()

    def test_peg_rate_is_float64(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        assert t.schema.field("peg_rate").type == pa.float64()

    def test_pegged_to_is_string(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        assert t.schema.field("pegged_to").type == pa.string()

    def test_minor_units_values_survive_roundtrip(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        values = t.column("minor_units").to_pylist()
        assert 0 in values and 2 in values and 3 in values

    def test_is_independent_values_are_python_bool(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        values = t.column("is_independent").to_pylist()
        for v in values:
            assert isinstance(v, bool)

    def test_peg_rate_values_are_python_float_or_none(self, minimal_registry: Registry):
        content = render_parquet(minimal_registry)
        t = pq.read_table(io.BytesIO(content))
        for v in t.column("peg_rate").to_pylist():
            assert v is None or isinstance(v, float)


# ===========================================================================
# Null semantics — the substantive difference from CSV
# ===========================================================================

class TestNullSemantics:
    """peg columns use null, not empty string, when not applicable."""

    def _read(self, registry: Registry) -> dict:
        content = render_parquet(registry)
        t = pq.read_table(io.BytesIO(content))
        return t.to_pydict()

    def test_independent_currency_has_null_peg_columns(self, minimal_registry: Registry):
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "EUR":
                assert d["pegged_to"][i] is None
                assert d["peg_type"][i] is None
                assert d["peg_rate"][i] is None
                return
        pytest.fail("EUR not found")

    def test_single_peg_has_non_null_all_three(self, minimal_registry: Registry):
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "AED":
                assert d["pegged_to"][i] == "USD"
                assert d["peg_type"][i] == "single"
                assert d["peg_rate"][i] == 3.6725
                return
        pytest.fail("AED not found")

    def test_basket_peg_has_null_rate(self, minimal_registry: Registry):
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "MAD":
                assert d["pegged_to"][i] == "EUR+USD basket"
                assert d["peg_type"][i] == "basket"
                assert d["peg_rate"][i] is None
                return
        pytest.fail("MAD not found")

    def test_undisclosed_peg_has_null_rate(self, minimal_registry: Registry):
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "KWD":
                assert d["pegged_to"][i] == "Currency basket"
                assert d["peg_type"][i] == "undisclosed"
                assert d["peg_rate"][i] is None
                return
        pytest.fail("KWD not found")

    def test_withdrawn_currency_has_null_peg_columns(self, minimal_registry: Registry):
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "DEM":
                assert d["pegged_to"][i] is None
                assert d["peg_type"][i] is None
                assert d["peg_rate"][i] is None
                return
        pytest.fail("DEM not found")

    def test_null_is_not_empty_string(self, minimal_registry: Registry):
        """A None value in the schema must not be read back as ''."""
        d = self._read(minimal_registry)
        for i, code in enumerate(d["code"]):
            if code == "EUR":
                assert d["pegged_to"][i] is not ""
                assert d["pegged_to"][i] is None
                return
        pytest.fail("EUR not found")


# ===========================================================================
# Determinism
# ===========================================================================

class TestDeterminism:
    def test_two_renders_produce_same_logical_content(self, minimal_registry: Registry):
        a = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        b = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        assert a.to_pydict() == b.to_pydict()
        assert a.schema.metadata == b.schema.metadata

    def test_two_renders_produce_same_row_order(self, minimal_registry: Registry):
        a = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        b = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        assert a.column("code").to_pylist() == b.column("code").to_pylist()


# ===========================================================================
# Sort order
# ===========================================================================

class TestSortOrder:
    def test_active_codes_sorted(self, minimal_registry: Registry):
        t = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        d = t.to_pydict()
        active = [d["code"][i] for i in range(len(d["code"])) if d["status"][i] == "active"]
        assert active == sorted(active)

    def test_withdrawn_codes_sorted(self, minimal_registry: Registry):
        t = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        d = t.to_pydict()
        withdrawn = [d["code"][i] for i in range(len(d["code"])) if d["status"][i] == "withdrawn"]
        assert withdrawn == sorted(withdrawn)

    def test_withdrawn_rows_after_active(self, minimal_registry: Registry):
        t = pq.read_table(io.BytesIO(render_parquet(minimal_registry)))
        statuses = t.column("status").to_pylist()
        first_w = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_w])
        assert all(s == "withdrawn" for s in statuses[first_w:])


# ===========================================================================
# Atomic write
# ===========================================================================

class TestAtomicWrite:
    def test_writes_binary_content(self, tmp_path: Path):
        p = tmp_path / "out.parquet"
        _atomic_write_binary(p, b"\x00\x01\x02")
        assert p.read_bytes() == b"\x00\x01\x02"

    def test_no_tmp_file_lingers(self, tmp_path: Path):
        p = tmp_path / "out.parquet"
        _atomic_write_binary(p, b"content")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_overwrites_existing(self, tmp_path: Path):
        p = tmp_path / "out.parquet"
        p.write_bytes(b"old")
        _atomic_write_binary(p, b"new")
        assert p.read_bytes() == b"new"

    def test_write_failure_exits_fatal(self, tmp_path: Path):
        p = tmp_path / "subdir"
        p.mkdir()
        with pytest.raises(SystemExit) as e:
            _atomic_write_binary(p, b"content")
        assert e.value.code == EXIT_FATAL


# ===========================================================================
# check_parquet — the logical comparison
# ===========================================================================

class TestCheckParquet:
    def test_missing_file_returns_missing(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        # No file written yet
        assert check_parquet(minimal_registry) == EXIT_MISSING

    def test_clean_file_returns_ok(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))
        assert check_parquet(minimal_registry) == EXIT_OK

    def test_tampered_value_returns_mismatch(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))

        def mutate(t):
            names = t.column("name").to_pylist()
            names[0] = "TAMPERED"
            idx = t.column_names.index("name")
            return t.set_column(idx, pa.field("name", pa.string()),
                                pa.array(names, type=pa.string()))

        _write_tampered(path, path, mutate)
        assert check_parquet(minimal_registry) == EXIT_MISMATCH

    def test_tampered_type_returns_mismatch(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))

        def mutate(t):
            # Rebuild with int64 instead of int8
            idx = t.column_names.index("minor_units")
            values = t.column("minor_units").to_pylist()
            return t.set_column(
                idx,
                pa.field("minor_units", pa.int64()),
                pa.array(values, type=pa.int64()),
            )

        _write_tampered(path, path, mutate)
        assert check_parquet(minimal_registry) == EXIT_MISMATCH

    def test_tampered_metadata_returns_mismatch(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))

        table = pq.read_table(path)
        # Replace metadata with an extra key
        new_meta = dict(table.schema.metadata or {})
        new_meta[b"iso4217.extra"] = b"surprise"
        new_schema = table.schema.with_metadata(new_meta)
        new_table = table.cast(new_schema)
        pq.write_table(new_table, path, compression="snappy")

        assert check_parquet(minimal_registry) == EXIT_MISMATCH

    def test_row_count_mismatch_returns_mismatch(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))

        def mutate(t):
            return t.slice(0, t.num_rows - 1)

        _write_tampered(path, path, mutate)
        assert check_parquet(minimal_registry) == EXIT_MISMATCH

    def test_different_metadata_value_returns_mismatch(
        self, minimal_registry: Registry, project_root_in_tmp: Path
    ):
        path = project_root_in_tmp / "iso4217.parquet"
        path.write_bytes(render_parquet(minimal_registry))

        table = pq.read_table(path)
        new_meta = dict(table.schema.metadata or {})
        new_meta[METADATA_VERSION_KEY.encode()] = b"999.999.999"
        new_schema = table.schema.with_metadata(new_meta)
        new_table = table.cast(new_schema)
        pq.write_table(new_table, path, compression="snappy")

        assert check_parquet(minimal_registry) == EXIT_MISMATCH


# ===========================================================================
# parse_args
# ===========================================================================

class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.stdout is False
        assert args.check is False
        from tools.export_parquet import REGISTRY_PATH
        assert args.registry == REGISTRY_PATH

    def test_stdout_flag(self):
        assert parse_args(["--stdout"]).stdout is True

    def test_check_flag(self):
        assert parse_args(["--check"]).check is True

    def test_registry_override(self):
        args = parse_args(["--registry", "/tmp/x.json"])
        assert args.registry == Path("/tmp/x.json")

    def test_unknown_flag_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--bogus"])


# ===========================================================================
# main() — end-to-end exit code matrix
# ===========================================================================

class TestMain:
    def test_missing_registry_exits_fatal(self, tmp_path: Path):
        with pytest.raises(SystemExit) as exc_info:
            main(["--registry", str(tmp_path / "missing.json")])
        assert exc_info.value.code == EXIT_FATAL

    def test_stdout_and_check_mutually_exclusive(self, minimal_registry_file: Path):
        code = main([
            "--registry", str(minimal_registry_file),
            "--stdout", "--check",
        ])
        assert code == EXIT_FATAL

    def test_check_clean_returns_ok(
        self, minimal_registry: Registry, project_root_in_tmp: Path,
        minimal_registry_file: Path,
    ):
        (project_root_in_tmp / "iso4217.parquet").write_bytes(
            render_parquet(minimal_registry)
        )
        code = main(["--registry", str(minimal_registry_file), "--check"])
        assert code == EXIT_OK

    def test_check_missing_returns_missing(
        self, project_root_in_tmp: Path, minimal_registry_file: Path,
    ):
        code = main(["--registry", str(minimal_registry_file), "--check"])
        assert code == EXIT_MISSING

    def test_default_writes_file(
        self, project_root_in_tmp: Path, minimal_registry_file: Path, capsys
    ):
        code = main(["--registry", str(minimal_registry_file)])
        assert code == EXIT_OK
        assert (project_root_in_tmp / "iso4217.parquet").exists()
        captured = capsys.readouterr()
        assert "Wrote" in captured.err

    def test_stdout_writes_binary(
        self, minimal_registry_file: Path, capsysbinary
    ):
        code = main(["--registry", str(minimal_registry_file), "--stdout"])
        assert code == EXIT_OK
        captured = capsysbinary.readouterr()
        # Binary Parquet starts with "PAR1"
        assert captured.out.startswith(b"PAR1")


# ===========================================================================
# Real project files
# ===========================================================================

class TestRealProject:
    """Checks against the actual committed Parquet file."""

    def test_committed_file_matches_registry(self):
        code = main(["--check"])
        assert code == EXIT_OK, (
            "Committed iso4217.parquet is out of sync with iso4217.json. "
            "Run 'python3 tools/export_parquet.py' and commit the result."
        )

    def test_parquet_file_exists(self):
        assert (PROJECT_ROOT / "iso4217.parquet").exists()

    def test_row_count_matches_registry(self):
        registry = json.loads(
            (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")
        )
        expected = (
            len(registry["currencies"]["active"])
            + len(registry["currencies"]["withdrawn"])
        )
        t = pq.read_table(PROJECT_ROOT / "iso4217.parquet")
        assert t.num_rows == expected

    def test_column_names_match_constants(self):
        t = pq.read_table(PROJECT_ROOT / "iso4217.parquet")
        assert tuple(t.column_names) == COLUMNS

    def test_metadata_uses_current_registry_version(self):
        registry = json.loads(
            (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")
        )
        t = pq.read_table(PROJECT_ROOT / "iso4217.parquet")
        meta = t.schema.metadata or {}
        assert meta[METADATA_VERSION_KEY.encode()] == registry["meta"]["version"].encode()
        assert meta[METADATA_UPDATED_KEY.encode()] == registry["meta"]["updated"].encode()
        assert meta[METADATA_AMENDMENT_KEY.encode()] == str(
            registry["source"]["last_amendment_applied"]
        ).encode()

    def test_real_minor_units_distribution(self):
        """Mirrors the registry's 0/2/3/4 minor-units distribution."""
        t = pq.read_table(PROJECT_ROOT / "iso4217.parquet")
        d = t.to_pydict()
        active = [d["minor_units"][i] for i in range(len(d["code"])) if d["status"][i] == "active"]
        dist = {}
        for v in active:
            dist[v] = dist.get(v, 0) + 1
        # 0, 2, 3, 4 all present in the current registry
        assert set(dist.keys()) == {0, 2, 3, 4}

    def test_real_null_count_for_pegged_to(self):
        """121 independent + 135 withdrawn = 256 nulls expected."""
        t = pq.read_table(PROJECT_ROOT / "iso4217.parquet")
        values = t.column("pegged_to").to_pylist()
        nulls = sum(1 for v in values if v is None)
        assert nulls == 256, f"expected 256 nulls, got {nulls}"


# ===========================================================================
# Cross-check with the CSV export
# ===========================================================================

class TestCrossCheckWithCSV:
    """
    The eleven columns of iso4217.parquet and iso4217.csv must contain
    the same values, row for row, once the CSV's string-encoded scalars
    are converted to their Parquet-native types.
    """

    @staticmethod
    def _parquet_rows() -> list[dict]:
        path = PROJECT_ROOT / "iso4217.parquet"
        if not path.exists():
            pytest.skip("iso4217.parquet not present")
        t = pq.read_table(path)
        return t.to_pylist()

    @staticmethod
    def _csv_rows() -> list[dict]:
        import csv as _csv
        path = PROJECT_ROOT / "iso4217.csv"
        if not path.exists():
            pytest.skip("iso4217.csv not present")
        with open(path, encoding="utf-8", newline="") as f:
            return list(_csv.DictReader(f))

    def test_row_counts_match(self):
        assert len(self._parquet_rows()) == len(self._csv_rows())

    def test_shared_columns_match(self):
        pq_rows = sorted(self._parquet_rows(), key=lambda r: (r["status"] != "active", r["code"]))
        csv_rows = sorted(self._csv_rows(), key=lambda r: (r["status"] != "active", r["code"]))

        for pq_row, csv_row in zip(pq_rows, csv_rows):
            code = pq_row["code"]
            assert pq_row["code"] == csv_row["code"], code
            assert pq_row["numeric_code"] == csv_row["numeric_code"], code
            assert pq_row["name"] == csv_row["name"], code
            assert pq_row["minor_units"] == int(csv_row["minor_units"]), code
            assert pq_row["symbol"] == csv_row["symbol"], code
            assert pq_row["entity"] == csv_row["entity"], code
            assert pq_row["status"] == csv_row["status"], code
            assert pq_row["is_independent"] == (csv_row["is_independent"] == "true"), code

            # CSV encodes null as empty string; Parquet uses None
            csv_pegged = csv_row["pegged_to"] or None
            csv_type = csv_row["peg_type"] or None
            csv_rate = csv_row["peg_rate"] or None
            assert pq_row["pegged_to"] == csv_pegged, code
            assert pq_row["peg_type"] == csv_type, code
            if csv_rate is None:
                assert pq_row["peg_rate"] is None, code
            else:
                assert pq_row["peg_rate"] == float(csv_rate), code


# ===========================================================================
# Cross-check with the SQL export
# ===========================================================================

class TestCrossCheckWithSQL:
    """
    The seven shared columns (code, numeric_code, name, minor_units,
    symbol, entity, status) must match iso4217.sqlite.sql row for row.
    """

    SQL_PATH = PROJECT_ROOT / "iso4217.sqlite.sql"

    @staticmethod
    def _sql_rows() -> list[tuple]:
        if not TestCrossCheckWithSQL.SQL_PATH.exists():
            pytest.skip("iso4217.sqlite.sql not present")
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(
                TestCrossCheckWithSQL.SQL_PATH.read_text(encoding="utf-8")
            )
            return db.execute(
                "SELECT code, numeric_code, name, minor_units, symbol, entity, status "
                "FROM currencies"
            ).fetchall()
        finally:
            db.close()

    @staticmethod
    def _parquet_rows() -> list[tuple]:
        path = PROJECT_ROOT / "iso4217.parquet"
        if not path.exists():
            pytest.skip("iso4217.parquet not present")
        t = pq.read_table(path)
        d = t.to_pydict()
        rows = []
        for i in range(t.num_rows):
            rows.append((
                d["code"][i],
                d["numeric_code"][i],
                d["name"][i],
                d["minor_units"][i],
                d["symbol"][i],
                d["entity"][i],
                d["status"][i],
            ))
        return rows

    def test_row_counts_match(self):
        assert len(self._parquet_rows()) == len(self._sql_rows())

    def test_shared_columns_match(self):
        def key(row):
            return (0 if row[6] == "active" else 1, row[0])

        sql = sorted(self._sql_rows(), key=key)
        pq = sorted(self._parquet_rows(), key=key)
        for s, p in zip(sql, pq):
            assert s == p, f"sql={s!r} pq={p!r}"


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_empty_registry_renders_and_checks(self, tmp_path: Path, empty_registry_json: dict):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(empty_registry_json), encoding="utf-8")
        reg = load_registry(p)

        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.num_rows == 0

    def test_single_row_registry(self):
        reg = _wrap_rows(_build_row())
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.num_rows == 1
        assert table.column("code").to_pylist() == ["USD"]

    def test_all_null_peg_columns_render(self):
        row = _build_row(pegged_to=None, peg_type=None, peg_rate=None)
        reg = _wrap_rows(row)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.column("pegged_to").to_pylist() == [None]
        assert table.column("peg_type").to_pylist() == [None]
        assert table.column("peg_rate").to_pylist() == [None]

    def test_non_ascii_symbol_round_trips(self):
        row = _build_row(symbol="د.ك")
        reg = _wrap_rows(row)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.column("symbol").to_pylist() == ["د.ك"]

    def test_leading_zero_in_numeric_code_preserved(self):
        row = _build_row(numeric_code="036")
        reg = _wrap_rows(row)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.column("numeric_code").to_pylist() == ["036"]

    def test_zero_minor_units_round_trips(self):
        row = _build_row(minor_units=0)
        reg = _wrap_rows(row)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.column("minor_units").to_pylist() == [0]

    def test_18_minor_units_round_trips(self):
        row = _build_row(minor_units=18)
        reg = _wrap_rows(row)
        content = render_parquet(reg)
        table = pq.read_table(io.BytesIO(content))
        assert table.column("minor_units").to_pylist() == [18]
