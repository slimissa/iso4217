"""
Tests for tools/export_csv.py.

Covers:
  - Module constants (COLUMNS, DIALECT_FILES, DIALECT_BOM, DIALECT_DELIMITERS)
  - Data classes (CurrencyRow, Registry)
  - Registry loading (valid, missing, malformed, bad field types)
  - Row construction (_row_from_entry) including the four peg columns
  - CSV quoting (delimiters, quotes, newlines, Unicode)
  - Per-dialect renderers (RFC, Excel, European, TSV)
  - BOM handling (only the Excel dialect)
  - LF line endings (never CRLF)
  - Round-trip parse with the stdlib csv.reader
  - Determinism, sort order
  - Non-ISO exclusion
  - Atomic writes
  - --check / --stdout / --dialect modes
  - CLI argument parsing and exit codes
  - Cross-check with the SQL export (seven shared columns, row for row)
"""

from __future__ import annotations

import csv as csv_module
import io
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.export_csv as export_csv
from tools.export_csv import (
    COLUMNS,
    DIALECT_BOM,
    DIALECT_DELIMITERS,
    DIALECT_FILES,
    DIALECT_LABELS,
    EXIT_FATAL,
    EXIT_MISMATCH,
    EXIT_MISSING,
    EXIT_OK,
    RENDERERS,
    CurrencyRow,
    Registry,
    _atomic_write,
    _row_from_entry,
    check_all,
    generate_all,
    generate_one,
    load_registry,
    main,
    parse_args,
    render_european,
    render_excel,
    render_rfc,
    render_tsv,
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
        "minor_units": "2",
        "symbol": "$",
        "entity": "United States",
        "status": "active",
        "is_independent": "true",
        "pegged_to": "",
        "peg_type": "",
        "peg_rate": "",
    }
    base.update(overrides)
    return CurrencyRow(**base)


def _wrap_rows(*rows: CurrencyRow) -> Registry:
    """Wrap one or more rows in a Registry for rendering tests."""
    return Registry(
        version="9.9.9",
        updated="2026-01-01",
        amendment=179,
        rows=list(rows),
    )


def _parse(content: str, dialect: str) -> list[list[str]]:
    """
    Parse a rendered file back into rows using the stdlib csv.reader.

    Strips the BOM if present (Excel dialect) because csv.reader would
    treat it as part of the first header field. The delimiter is looked
    up per dialect, same as the exporter.
    """
    text = content.lstrip("\ufeff")
    return list(
        csv_module.reader(io.StringIO(text), delimiter=DIALECT_DELIMITERS[dialect])
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_registry_json() -> dict:
    """
    A minimal but structurally valid registry, enough for all renderers.

    Includes four active currencies (two independent, one single-peg,
    one basket-peg) and two withdrawn currencies — enough to exercise
    every rendering branch: quoting, non-ASCII symbols, empty peg
    columns, 7-char withdrawn codes, and the withdrawn metadata.
    """
    return {
        "meta": {
            "version": "9.9.9",
            "updated": "2026-01-01",
        },
        "source": {
            "last_amendment_applied": 179,
        },
        "currencies": {
            "active": [
                {
                    "code": "AED",
                    "numeric": "784",
                    "name": "United Arab Emirates dirham",
                    "minor_units": 2,
                    "symbol": "د.إ",
                    "entity": "United Arab Emirates",
                    "is_independent": False,
                    "pegged_to": "USD",
                    "peg_type": "single",
                    "peg_rate": 3.6725,
                },
                {
                    "code": "JPY",
                    "numeric": "392",
                    "name": "Japanese Yen",
                    "minor_units": 0,
                    "symbol": "¥",
                    "entity": "Japan",
                    "is_independent": True,
                },
                {
                    "code": "MAD",
                    "numeric": "504",
                    "name": "Moroccan dirham",
                    "minor_units": 2,
                    "symbol": "د.م.",
                    "entity": "Morocco",
                    "is_independent": False,
                    "pegged_to": "EUR+USD basket",
                    "peg_type": "basket",
                },
                {
                    "code": "USD",
                    "numeric": "840",
                    "name": "US Dollar",
                    "minor_units": 2,
                    "symbol": "$",
                    "entity": "United States",
                    "is_independent": True,
                },
            ],
            "withdrawn": [
                {
                    "code": "DEM",
                    "numeric": "276",
                    "name": "German Mark",
                    "minor_units": 2,
                    "symbol": "DM",
                    "entity": "Germany",
                    "is_independent": False,
                },
                {
                    "code": "MXN_OLD",
                    "numeric": "484",
                    "name": "Mexican Peso (pre-1993)",
                    "minor_units": 2,
                    "symbol": "MXP",
                    "entity": "Mexico",
                    "is_independent": False,
                },
            ],
        },
        "non_iso": {
            "cryptocurrencies": [
                {"code": "BTC", "name": "Bitcoin", "minor_units": 8}
            ],
            "stablecoins": [],
            "commodities": [],
            "special_purpose": [],
        },
    }


@pytest.fixture
def minimal_registry_file(tmp_path: Path, minimal_registry_json: dict) -> Path:
    """Write the minimal registry to a temp file."""
    path = tmp_path / "iso4217.json"
    path.write_text(json.dumps(minimal_registry_json, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def minimal_registry(minimal_registry_file: Path) -> Registry:
    """Load the minimal registry as a Registry object."""
    return load_registry(minimal_registry_file)


@pytest.fixture
def sample_row() -> CurrencyRow:
    """A representative CurrencyRow for renderer and quoting tests."""
    return _build_row()


@pytest.fixture
def project_root_in_tmp(
    tmp_path: Path, minimal_registry_json: dict, monkeypatch
) -> Path:
    """
    Redirect export_csv.PROJECT_ROOT to a temp directory so generate_all
    and check_all operate on isolated files rather than the real repo.
    """
    (tmp_path / "iso4217.json").write_text(
        json.dumps(minimal_registry_json, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(export_csv, "PROJECT_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_dialect_files_has_four(self):
        assert len(DIALECT_FILES) == 4

    def test_dialect_filenames_match_spec(self):
        assert DIALECT_FILES["rfc"] == "iso4217.csv"
        assert DIALECT_FILES["excel"] == "iso4217.excel.csv"
        assert DIALECT_FILES["european"] == "iso4217.european.csv"
        assert DIALECT_FILES["tsv"] == "iso4217.tsv"

    def test_columns_has_eleven(self):
        assert len(COLUMNS) == 11

    def test_columns_first_seven_match_sql_export(self):
        """The first seven columns must be identical to the SQL export's,
        so a join between the two exports on `code` is a straight compare."""
        expected = (
            "code",
            "numeric_code",
            "name",
            "minor_units",
            "symbol",
            "entity",
            "status",
        )
        assert COLUMNS[:7] == expected

    def test_columns_last_four_are_peg_metadata(self):
        assert COLUMNS[7:] == ("is_independent", "pegged_to", "peg_type", "peg_rate")

    def test_bom_only_on_excel_dialect(self):
        for name, has_bom in DIALECT_BOM.items():
            assert has_bom == (name == "excel"), f"unexpected BOM for {name}"

    def test_dialect_delimiters(self):
        assert DIALECT_DELIMITERS["rfc"] == ","
        assert DIALECT_DELIMITERS["excel"] == ","
        assert DIALECT_DELIMITERS["european"] == ";"
        assert DIALECT_DELIMITERS["tsv"] == "\t"

    def test_dialect_labels_cover_all_dialects(self):
        assert set(DIALECT_LABELS.keys()) == set(DIALECT_FILES.keys())


# ---------------------------------------------------------------------------
# CurrencyRow
# ---------------------------------------------------------------------------

class TestCurrencyRow:
    def test_frozen(self):
        r = _build_row()
        with pytest.raises(Exception):  # FrozenInstanceError
            r.code = "EUR"  # type: ignore

    def test_hashable(self):
        r = _build_row()
        assert {r}  # no exception

    def test_equality(self):
        assert _build_row() == _build_row()

    def test_inequality(self):
        a = _build_row()
        b = _build_row(code="EUR", numeric_code="978", name="Euro")
        assert a != b

    def test_as_tuple_has_eleven_fields(self):
        assert len(_build_row().as_tuple()) == 11

    def test_as_tuple_order_matches_columns(self):
        row = _build_row(
            code="X",
            numeric_code="123",
            name="N",
            minor_units="0",
            symbol="S",
            entity="E",
            status="withdrawn",
            is_independent="false",
            pegged_to="P",
            peg_type="single",
            peg_rate="1.0",
        )
        assert row.as_tuple() == (
            "X",
            "123",
            "N",
            "0",
            "S",
            "E",
            "withdrawn",
            "false",
            "P",
            "single",
            "1.0",
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_active_count(self, minimal_registry: Registry):
        assert minimal_registry.active_count == 4

    def test_withdrawn_count(self, minimal_registry: Registry):
        assert minimal_registry.withdrawn_count == 2

    def test_total_count(self, minimal_registry: Registry):
        assert minimal_registry.total_count == 6

    def test_active_rows_come_first(self, minimal_registry: Registry):
        statuses = [r.status for r in minimal_registry.rows]
        first_withdrawn = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_withdrawn])
        assert all(s == "withdrawn" for s in statuses[first_withdrawn:])

    def test_rows_sorted_within_group(self, minimal_registry: Registry):
        active = [r.code for r in minimal_registry.rows if r.status == "active"]
        withdrawn = [r.code for r in minimal_registry.rows if r.status == "withdrawn"]
        assert active == sorted(active)
        assert withdrawn == sorted(withdrawn)


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------

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
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_meta_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({"source": {}, "currencies": {}}), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_version_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"updated": "2026-01-01"},
                "source": {"last_amendment_applied": 179},
                "currencies": {"active": [], "withdrawn": []},
            }),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_source_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"version": "1.0.0", "updated": "2026-01-01"},
                "currencies": {"active": [], "withdrawn": []},
            }),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_amendment_not_int_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"version": "1.0.0", "updated": "2026-01-01"},
                "source": {"last_amendment_applied": "179"},
                "currencies": {"active": [], "withdrawn": []},
            }),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_currencies_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"version": "1.0.0", "updated": "2026-01-01"},
                "source": {"last_amendment_applied": 179},
            }),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_active_not_array_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"version": "1.0.0", "updated": "2026-01-01"},
                "source": {"last_amendment_applied": 179},
                "currencies": {"active": "USD", "withdrawn": []},
            }),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_empty_currencies_ok(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(
            json.dumps({
                "meta": {"version": "1.0.0", "updated": "2026-01-01"},
                "source": {"last_amendment_applied": 179},
                "currencies": {"active": [], "withdrawn": []},
            }),
            encoding="utf-8",
        )
        r = load_registry(p)
        assert r.active_count == 0
        assert r.withdrawn_count == 0


# ---------------------------------------------------------------------------
# _row_from_entry — validation and field conversion
# ---------------------------------------------------------------------------

class TestRowFromEntry:
    def _entry(self, **overrides) -> dict:
        base = {
            "code": "USD",
            "numeric": "840",
            "name": "US Dollar",
            "minor_units": 2,
            "symbol": "$",
            "entity": "United States",
            "is_independent": True,
        }
        base.update(overrides)
        return base

    # -- code ---------------------------------------------------------------

    def test_valid_active(self):
        row = _row_from_entry(self._entry(), "active")
        assert row.code == "USD"
        assert row.status == "active"

    def test_valid_withdrawn(self):
        row = _row_from_entry(self._entry(), "withdrawn")
        assert row.status == "withdrawn"

    def test_code_3_chars_accepted(self):
        assert _row_from_entry(self._entry(code="JPY"), "active").code == "JPY"

    def test_code_7_chars_accepted(self):
        row = _row_from_entry(self._entry(code="MXN_OLD"), "withdrawn")
        assert row.code == "MXN_OLD"

    def test_code_2_chars_rejected(self):
        with pytest.raises(SystemExit) as e:
            _row_from_entry(self._entry(code="US"), "active")
        assert e.value.code == EXIT_FATAL

    def test_code_8_chars_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(code="ABCDEFGH"), "active")

    def test_code_lowercase_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(code="usd"), "active")

    def test_code_with_dash_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(code="US-"), "active")

    def test_code_underscore_accepted(self):
        assert _row_from_entry(self._entry(code="A_B"), "withdrawn").code == "A_B"

    # -- numeric ------------------------------------------------------------

    def test_numeric_must_be_3_digits(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84"), "active")

    def test_numeric_leading_zero_preserved(self):
        row = _row_from_entry(self._entry(numeric="036"), "active")
        assert row.numeric_code == "036"

    def test_numeric_non_digit_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84X"), "active")

    def test_numeric_not_string_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric=840), "active")

    # -- name ---------------------------------------------------------------

    def test_name_empty_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(name=""), "active")

    # -- minor_units --------------------------------------------------------

    def test_minor_units_negative_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=-1), "active")

    def test_minor_units_above_18_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=19), "active")

    def test_minor_units_zero_accepted(self):
        row = _row_from_entry(self._entry(minor_units=0), "active")
        assert row.minor_units == "0"

    def test_minor_units_18_accepted(self):
        row = _row_from_entry(self._entry(minor_units=18), "active")
        assert row.minor_units == "18"

    def test_minor_units_float_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=2.5), "active")

    def test_minor_units_is_string_in_row(self):
        row = _row_from_entry(self._entry(minor_units=2), "active")
        assert isinstance(row.minor_units, str)
        assert row.minor_units == "2"

    # -- optional text fields ----------------------------------------------

    def test_missing_symbol_defaults_empty(self):
        assert _row_from_entry(self._entry(symbol=None), "active").symbol == ""

    def test_missing_entity_defaults_empty(self):
        assert _row_from_entry(self._entry(entity=None), "active").entity == ""

    def test_empty_symbol_stays_empty(self):
        assert _row_from_entry(self._entry(symbol=""), "active").symbol == ""

    # -- is_independent -----------------------------------------------------

    def test_is_independent_true_rendered_lowercase(self):
        row = _row_from_entry(self._entry(is_independent=True), "active")
        assert row.is_independent == "true"

    def test_is_independent_false_rendered_lowercase(self):
        row = _row_from_entry(self._entry(is_independent=False), "active")
        assert row.is_independent == "false"

    def test_is_independent_missing_defaults_to_false(self):
        """Conservative default: absence means not-independent. See the
        _row_from_entry docstring for rationale."""
        entry = {"code": "XYZ", "numeric": "999", "name": "X", "minor_units": 2}
        row = _row_from_entry(entry, "active")
        assert row.is_independent == "false"

    def test_is_independent_non_bool_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(is_independent="yes"), "active")

    # -- peg columns --------------------------------------------------------

    def test_peg_columns_empty_when_unset(self):
        row = _row_from_entry(self._entry(), "active")
        assert row.pegged_to == ""
        assert row.peg_type == ""
        assert row.peg_rate == ""

    def test_peg_columns_none_become_empty(self):
        row = _row_from_entry(
            self._entry(pegged_to=None, peg_type=None, peg_rate=None), "active"
        )
        assert row.pegged_to == ""
        assert row.peg_type == ""
        assert row.peg_rate == ""

    def test_single_peg_renders_all_fields(self):
        row = _row_from_entry(
            self._entry(
                is_independent=False,
                pegged_to="USD",
                peg_type="single",
                peg_rate=3.6725,
            ),
            "active",
        )
        assert row.pegged_to == "USD"
        assert row.peg_type == "single"
        assert row.peg_rate == "3.6725"

    def test_basket_peg_has_no_rate(self):
        row = _row_from_entry(
            self._entry(
                is_independent=False,
                pegged_to="EUR+USD basket",
                peg_type="basket",
            ),
            "active",
        )
        assert row.pegged_to == "EUR+USD basket"
        assert row.peg_type == "basket"
        assert row.peg_rate == ""

    def test_peg_rate_uses_shortest_repr(self):
        """repr(float) gives the shortest round-trippable decimal, so
        reading the CSV back and parsing as float recovers the exact
        same value."""
        for value, expected in [
            (3.6725, "3.6725"),
            (1.0, "1.0"),
            (0.0, "0.0"),
            (2.25, "2.25"),
            (7.8, "7.8"),
        ]:
            row = _row_from_entry(self._entry(peg_rate=value), "active")
            assert row.peg_rate == expected, f"{value} -> {row.peg_rate!r}"

    def test_peg_rate_int_coerced_to_float_repr(self):
        row = _row_from_entry(self._entry(peg_rate=1), "active")
        assert row.peg_rate == "1.0"

    def test_peg_rate_bool_rejected(self):
        """bool is a subclass of int in Python; it must not be accepted."""
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(peg_rate=True), "active")

    def test_peg_rate_string_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(peg_rate="3.6725"), "active")


# ---------------------------------------------------------------------------
# CSV quoting — the behaviour the roadmap says must never be hand-rolled
# ---------------------------------------------------------------------------

class TestQuoting:
    """
    Every assertion parses the rendered output back with csv.reader and
    compares the recovered field against the input. This proves the
    quoter round-trips, not just that it emitted a quote character.
    """

    def _one_field(self, field: str, column: str = "name") -> Registry:
        return _wrap_rows(_build_row(**{column: field}))

    # -- RFC dialect --------------------------------------------------------

    def test_plain_field_has_no_quotes(self):
        content = render_rfc(self._one_field("US Dollar"))
        assert '"' not in content

    def test_comma_field_is_quoted(self):
        content = render_rfc(self._one_field("Dollar, Canadian"))
        rows = _parse(content, "rfc")
        assert rows[1][2] == "Dollar, Canadian"

    def test_double_quote_field_is_quoted_and_doubled(self):
        content = render_rfc(self._one_field('The "Best" Dollar'))
        rows = _parse(content, "rfc")
        assert rows[1][2] == 'The "Best" Dollar'

    def test_newline_field_is_quoted(self):
        content = render_rfc(self._one_field("Line1\nLine2"))
        rows = _parse(content, "rfc")
        assert rows[1][2] == "Line1\nLine2"

    def test_semicolon_field_not_quoted_in_rfc(self):
        """Semicolon isn't the delimiter for this dialect, so no quotes."""
        content = render_rfc(self._one_field("A;B"))
        assert '"' not in content

    def test_tab_field_not_quoted_in_rfc(self):
        content = render_rfc(self._one_field("A\tB"))
        assert '"' not in content

    def test_unicode_symbol_not_quoted(self):
        content = render_rfc(self._one_field("¥", column="symbol"))
        rows = _parse(content, "rfc")
        assert rows[1][4] == "¥"

    def test_arabic_symbol_not_quoted(self):
        content = render_rfc(self._one_field("د.ك", column="symbol"))
        rows = _parse(content, "rfc")
        assert rows[1][4] == "د.ك"

    # -- European dialect ---------------------------------------------------

    def test_comma_field_not_quoted_in_european(self):
        """Comma isn't the delimiter here, so no quotes."""
        content = render_european(self._one_field("Dollar, Canadian"))
        assert '"' not in content

    def test_semicolon_field_quoted_in_european(self):
        content = render_european(self._one_field("A;B"))
        rows = _parse(content, "european")
        assert rows[1][2] == "A;B"

    # -- TSV dialect --------------------------------------------------------

    def test_comma_field_not_quoted_in_tsv(self):
        content = render_tsv(self._one_field("Dollar, Canadian"))
        assert '"' not in content

    def test_tab_field_quoted_in_tsv(self):
        content = render_tsv(self._one_field("A\tB"))
        rows = _parse(content, "tsv")
        assert rows[1][2] == "A\tB"

    # -- Round-trip through real registry data ------------------------------

    def test_entity_with_comma_round_trips(self):
        """The real registry has at least one entity containing a comma
        (SHP — 'Saint Helena, Ascension and Tristan da Cunha')."""
        reg = _wrap_rows(
            _build_row(entity="Saint Helena, Ascension and Tristan da Cunha")
        )
        for dialect in DIALECT_FILES:
            content = RENDERERS[dialect](reg)
            rows = _parse(content, dialect)
            assert rows[1][5] == "Saint Helena, Ascension and Tristan da Cunha"


# ---------------------------------------------------------------------------
# Common renderer invariants — run against all four dialects
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
class TestCommonRenderer:
    def test_returns_non_empty_string(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        assert isinstance(content, str)
        assert content

    def test_header_is_exactly_the_columns(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry).lstrip("\ufeff")
        header = content.split("\n")[0]
        delimiter = DIALECT_DELIMITERS[dialect]
        assert header == delimiter.join(COLUMNS)

    def test_row_count_is_header_plus_data(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        rows = _parse(content, dialect)
        assert len(rows) == minimal_registry.total_count + 1

    def test_deterministic(self, minimal_registry, dialect):
        a = RENDERERS[dialect](minimal_registry)
        b = RENDERERS[dialect](minimal_registry)
        assert a == b

    def test_lf_only_never_cr(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        assert "\r" not in content

    def test_bom_policy(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        if DIALECT_BOM[dialect]:
            assert content.startswith("\ufeff")
        else:
            assert not content.startswith("\ufeff")

    def test_no_wall_clock_in_output(self, minimal_registry, dialect):
        from datetime import date
        content = RENDERERS[dialect](minimal_registry)
        if str(date.today()) != minimal_registry.updated:
            assert str(date.today()) not in content

    def test_round_trip_preserves_all_fields(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        rows = _parse(content, dialect)
        assert rows[0] == list(COLUMNS)
        for source_row, parsed_row in zip(minimal_registry.rows, rows[1:]):
            assert parsed_row == list(source_row.as_tuple()), (
                f"{dialect}: parsed {parsed_row!r} != source "
                f"{list(source_row.as_tuple())!r}"
            )

    def test_non_iso_excluded(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        assert "BTC" not in content
        assert "Bitcoin" not in content


# ---------------------------------------------------------------------------
# Dialect-specific renderers
# ---------------------------------------------------------------------------

class TestRendererRFC:
    def test_uses_comma_delimiter(self, minimal_registry):
        content = render_rfc(minimal_registry)
        header = content.split("\n")[0]
        assert header.count(",") == len(COLUMNS) - 1

    def test_has_no_bom(self, minimal_registry):
        assert not render_rfc(minimal_registry).startswith("\ufeff")

    def test_unicode_symbol_present(self, minimal_registry):
        rows = _parse(render_rfc(minimal_registry), "rfc")
        jpy = next(r for r in rows if r[0] == "JPY")
        assert jpy[4] == "¥"


class TestRendererExcel:
    def test_starts_with_bom(self, minimal_registry):
        assert render_excel(minimal_registry).startswith("\ufeff")

    def test_comma_delimiter_after_bom(self, minimal_registry):
        content = render_excel(minimal_registry)[1:]  # strip BOM
        header = content.split("\n")[0]
        assert header.count(",") == len(COLUMNS) - 1

    def test_bom_is_three_bytes_on_disk(self, tmp_path, minimal_registry):
        content = render_excel(minimal_registry)
        p = tmp_path / "x.csv"
        _atomic_write(p, content)
        assert p.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_remainder_parses_as_valid_csv(self, minimal_registry):
        content = render_excel(minimal_registry)
        rows = _parse(content, "excel")
        assert rows[0] == list(COLUMNS)
        assert len(rows) == minimal_registry.total_count + 1


class TestRendererEuropean:
    def test_uses_semicolon_delimiter(self, minimal_registry):
        content = render_european(minimal_registry)
        header = content.split("\n")[0]
        assert header.count(";") == len(COLUMNS) - 1
        assert header.count(",") == 0

    def test_has_no_bom(self, minimal_registry):
        assert not render_european(minimal_registry).startswith("\ufeff")

    def test_comma_inside_field_not_quoted(self):
        content = render_european(_wrap_rows(_build_row(name="Dollar, Canadian")))
        assert '"' not in content

    def test_semicolon_inside_field_quoted(self):
        content = render_european(_wrap_rows(_build_row(name="A;B")))
        rows = _parse(content, "european")
        assert rows[1][2] == "A;B"


class TestRendererTSV:
    def test_uses_tab_delimiter(self, minimal_registry):
        content = render_tsv(minimal_registry)
        header = content.split("\n")[0]
        assert header.count("\t") == len(COLUMNS) - 1

    def test_has_no_bom(self, minimal_registry):
        assert not render_tsv(minimal_registry).startswith("\ufeff")

    def test_comma_inside_field_not_quoted(self):
        content = render_tsv(_wrap_rows(_build_row(name="Dollar, Canadian")))
        assert '"' not in content

    def test_tab_inside_field_quoted(self):
        content = render_tsv(_wrap_rows(_build_row(name="A\tB")))
        rows = _parse(content, "tsv")
        assert rows[1][2] == "A\tB"


# ---------------------------------------------------------------------------
# Round-trip via csv.reader (parametrized across all four dialects)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
class TestRoundTrip:
    def test_parses_with_stdlib_reader(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        rows = _parse(content, dialect)
        assert rows[0] == list(COLUMNS)
        assert len(rows) == minimal_registry.total_count + 1

    def test_fields_match_source_rows(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)
        for expected, actual in zip(minimal_registry.rows, rows[1:]):
            assert actual == list(expected.as_tuple())

    def test_status_grouping_preserved(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        statuses = [r[6] for r in rows]
        first_w = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_w])
        assert all(s == "withdrawn" for s in statuses[first_w:])

    def test_sort_order_preserved(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        active = [r[0] for r in rows if r[6] == "active"]
        withdrawn = [r[0] for r in rows if r[6] == "withdrawn"]
        assert active == sorted(active)
        assert withdrawn == sorted(withdrawn)

    def test_peg_rate_round_trips_as_float(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        aed = next(r for r in rows if r[0] == "AED")
        assert float(aed[10]) == 3.6725

    def test_numeric_code_leading_zeros_preserved(self, dialect):
        entry = {
            "code": "AUD",
            "numeric": "036",
            "name": "Australian dollar",
            "minor_units": 2,
            "is_independent": True,
        }
        reg = _wrap_rows(_row_from_entry(entry, "active"))
        rows = _parse(RENDERERS[dialect](reg), dialect)
        assert rows[1][1] == "036"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_two_runs_identical(self, minimal_registry, dialect):
        assert RENDERERS[dialect](minimal_registry) == RENDERERS[dialect](minimal_registry)

    def test_no_wall_clock_leaks_into_any_dialect(self, minimal_registry):
        from datetime import date
        if str(date.today()) == minimal_registry.updated:
            pytest.skip("today matches meta.updated; assertion cannot distinguish")
        for dialect in DIALECT_FILES:
            assert str(date.today()) not in RENDERERS[dialect](minimal_registry)


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

class TestSortOrder:
    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_active_codes_sorted(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        codes = [r[0] for r in rows if r[6] == "active"]
        assert codes == sorted(codes)

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_withdrawn_codes_sorted(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        codes = [r[0] for r in rows if r[6] == "withdrawn"]
        assert codes == sorted(codes)

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_withdrawn_after_active(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)[1:]
        statuses = [r[6] for r in rows]
        first_w = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_w])
        assert all(s == "withdrawn" for s in statuses[first_w:])


# ---------------------------------------------------------------------------
# Non-ISO exclusion
# ---------------------------------------------------------------------------

class TestNonIsoExclusion:
    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_btc_not_in_output(self, minimal_registry, dialect):
        content = RENDERERS[dialect](minimal_registry)
        assert "BTC" not in content
        assert "Bitcoin" not in content

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_row_count_excludes_non_iso(self, minimal_registry, dialect):
        rows = _parse(RENDERERS[dialect](minimal_registry), dialect)
        # 6 ISO rows + 1 header; BTC would make it 7 + header
        assert len(rows) == minimal_registry.total_count + 1


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_writes_content(self, tmp_path):
        p = tmp_path / "out.csv"
        _atomic_write(p, "code\nUSD\n")
        assert p.read_text() == "code\nUSD\n"

    def test_no_tmp_file_lingers(self, tmp_path):
        p = tmp_path / "out.csv"
        _atomic_write(p, "content")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.csv"
        p.write_text("old")
        _atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_preserves_lf_on_all_platforms(self, tmp_path):
        """open(newline='') must not translate LF to CRLF on Windows."""
        p = tmp_path / "out.csv"
        _atomic_write(p, "a\nb\nc\n")
        raw = p.read_bytes()
        assert b"\r" not in raw
        assert raw == b"a\nb\nc\n"

    def test_write_failure_exits_fatal(self, tmp_path):
        p = tmp_path / "subdir"
        p.mkdir()
        with pytest.raises(SystemExit) as e:
            _atomic_write(p, "content")
        assert e.value.code == EXIT_FATAL

    def test_bom_persists_through_write(self, tmp_path):
        p = tmp_path / "out.csv"
        _atomic_write(p, "\ufeffcode\nUSD\n")
        assert p.read_bytes()[:3] == b"\xef\xbb\xbf"


# ---------------------------------------------------------------------------
# generate_one
# ---------------------------------------------------------------------------

class TestGenerateOne:
    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_returns_string(self, minimal_registry, dialect):
        content = generate_one(minimal_registry, dialect)
        assert isinstance(content, str)
        # Every dialect starts with the columns header (after any BOM)
        assert content.lstrip("\ufeff").startswith("code")

    def test_unknown_dialect_fatal(self, minimal_registry):
        with pytest.raises(SystemExit) as e:
            generate_one(minimal_registry, "parquet")
        assert e.value.code == EXIT_FATAL


# ---------------------------------------------------------------------------
# generate_all — writes all four files
# ---------------------------------------------------------------------------

class TestGenerateAll:
    def test_writes_all_four(self, minimal_registry, project_root_in_tmp):
        written = generate_all(minimal_registry)
        assert len(written) == 4
        for dialect, path in written.items():
            assert path.exists(), f"{path} not written"

    def test_files_have_correct_names(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        for filename in DIALECT_FILES.values():
            assert (project_root_in_tmp / filename).exists()

    def test_no_tmp_after_generate_all(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        assert list(project_root_in_tmp.glob("*.tmp")) == []

    def test_written_content_matches_generate_one(
        self, minimal_registry, project_root_in_tmp
    ):
        written = generate_all(minimal_registry)
        for dialect, path in written.items():
            expected = generate_one(minimal_registry, dialect)
            assert path.read_text(encoding="utf-8") == expected


# ---------------------------------------------------------------------------
# check_all — exit codes
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_all_match_returns_ok(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        assert check_all(minimal_registry) == EXIT_OK

    def test_mismatch_returns_1(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        target = project_root_in_tmp / DIALECT_FILES["rfc"]
        target.write_text(target.read_text() + "\n-- tamper\n")
        assert check_all(minimal_registry) == EXIT_MISMATCH

    def test_missing_returns_3(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        (project_root_in_tmp / DIALECT_FILES["rfc"]).unlink()
        assert check_all(minimal_registry) == EXIT_MISSING

    def test_missing_takes_precedence_over_mismatch(
        self, minimal_registry, project_root_in_tmp
    ):
        generate_all(minimal_registry)
        (project_root_in_tmp / DIALECT_FILES["rfc"]).unlink()
        target = project_root_in_tmp / DIALECT_FILES["tsv"]
        target.write_text(target.read_text() + "\n-- tamper\n")
        assert check_all(minimal_registry) == EXIT_MISSING


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.dialect is None
        assert args.stdout is False
        assert args.check is False
        from tools.export_csv import REGISTRY_PATH
        assert args.registry == REGISTRY_PATH

    def test_dialect_short(self):
        assert parse_args(["-d", "european"]).dialect == "european"

    def test_dialect_long(self):
        assert parse_args(["--dialect", "tsv"]).dialect == "tsv"

    def test_check_flag(self):
        assert parse_args(["--check"]).check is True

    def test_stdout_flag(self):
        assert parse_args(["--stdout"]).stdout is True

    def test_registry_override(self):
        args = parse_args(["--registry", "/tmp/x.json"])
        assert args.registry == Path("/tmp/x.json")

    def test_unknown_dialect_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--dialect", "parquet"])


# ---------------------------------------------------------------------------
# main() — end-to-end exit code matrix
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_registry_exits_fatal(self, tmp_path):
        """_fatal() calls sys.exit(), which raises SystemExit rather than
        returning an int. The test must expect the exception and inspect
        its .code, not compare main()'s return value."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--registry", str(tmp_path / "missing.json")])
        assert exc_info.value.code == EXIT_FATAL

    def test_stdout_without_dialect_fatal(self, minimal_registry_file):
        code = main(["--registry", str(minimal_registry_file), "--stdout"])
        assert code == EXIT_FATAL

    def test_check_and_stdout_mutually_exclusive(self, minimal_registry_file):
        code = main(
            [
                "--registry",
                str(minimal_registry_file),
                "--check",
                "--stdout",
                "--dialect",
                "rfc",
            ]
        )
        assert code == EXIT_FATAL

    def test_check_clean_returns_ok(
        self, minimal_registry, project_root_in_tmp, minimal_registry_file
    ):
        generate_all(minimal_registry)
        code = main(["--registry", str(minimal_registry_file), "--check"])
        assert code == EXIT_OK

    def test_check_mismatch_returns_1(
        self, minimal_registry, project_root_in_tmp, minimal_registry_file
    ):
        generate_all(minimal_registry)
        target = project_root_in_tmp / DIALECT_FILES["rfc"]
        target.write_text(target.read_text() + "\n-- tamper\n")
        code = main(["--registry", str(minimal_registry_file), "--check"])
        assert code == EXIT_MISMATCH

    def test_check_missing_returns_3(
        self, minimal_registry, project_root_in_tmp, minimal_registry_file
    ):
        generate_all(minimal_registry)
        (project_root_in_tmp / DIALECT_FILES["rfc"]).unlink()
        code = main(["--registry", str(minimal_registry_file), "--check"])
        assert code == EXIT_MISSING

    def test_default_writes_all_four(
        self, minimal_registry, project_root_in_tmp, minimal_registry_file, capsys
    ):
        code = main(["--registry", str(minimal_registry_file)])
        assert code == EXIT_OK
        for filename in DIALECT_FILES.values():
            assert (project_root_in_tmp / filename).exists()
        captured = capsys.readouterr()
        assert "Wrote" in captured.err

    def test_single_dialect_writes_one(
        self, minimal_registry, project_root_in_tmp, minimal_registry_file
    ):
        code = main(
            ["--registry", str(minimal_registry_file), "--dialect", "tsv"]
        )
        assert code == EXIT_OK
        assert (project_root_in_tmp / DIALECT_FILES["tsv"]).exists()
        assert not (project_root_in_tmp / DIALECT_FILES["rfc"]).exists()

    def test_stdout_prints_to_stdout(self, minimal_registry_file, capsys):
        code = main(
            [
                "--registry",
                str(minimal_registry_file),
                "--dialect",
                "rfc",
                "--stdout",
            ]
        )
        assert code == EXIT_OK
        captured = capsys.readouterr()
        assert captured.out.startswith("code,")
        assert "Wrote" not in captured.err

    def test_stdout_preserves_bom_for_excel(self, minimal_registry_file, capsys):
        """sys.stdout.write must not add a trailing newline and must
        preserve the BOM as the first codepoint."""
        code = main(
            [
                "--registry",
                str(minimal_registry_file),
                "--dialect",
                "excel",
                "--stdout",
            ]
        )
        assert code == EXIT_OK
        captured = capsys.readouterr()
        assert captured.out.startswith("\ufeff")


# ---------------------------------------------------------------------------
# Integration: real project files
# ---------------------------------------------------------------------------

class TestRealProject:
    """Sanity checks against the actual committed CSV/TSV files."""

    def test_committed_files_match_registry(self):
        code = main(["--check"])
        assert code == EXIT_OK, (
            "Committed CSV/TSV files are out of sync with iso4217.json. "
            "Run 'python3 tools/export_csv.py' and commit the result."
        )

    def test_csv_files_exist(self):
        for filename in DIALECT_FILES.values():
            p = PROJECT_ROOT / filename
            assert p.exists(), f"Missing committed file: {filename}"

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_header_row_is_exactly_columns(self, dialect):
        path = PROJECT_ROOT / DIALECT_FILES[dialect]
        content = path.read_text(encoding="utf-8").lstrip("\ufeff")
        header = content.split("\n")[0]
        assert header == DIALECT_DELIMITERS[dialect].join(COLUMNS)

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_row_count_matches_registry(self, dialect):
        registry = json.loads(
            (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")
        )
        expected = (
            len(registry["currencies"]["active"])
            + len(registry["currencies"]["withdrawn"])
        )
        path = PROJECT_ROOT / DIALECT_FILES[dialect]
        content = path.read_text(encoding="utf-8").lstrip("\ufeff")
        rows = list(
            csv_module.reader(
                io.StringIO(content),
                delimiter=DIALECT_DELIMITERS[dialect],
            )
        )
        assert len(rows) - 1 == expected, (
            f"{DIALECT_FILES[dialect]}: {len(rows) - 1} data rows, expected {expected}"
        )

    def test_excel_file_has_bom_on_disk(self):
        raw = (PROJECT_ROOT / "iso4217.excel.csv").read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"

    @pytest.mark.parametrize(
        "filename",
        ["iso4217.csv", "iso4217.european.csv", "iso4217.tsv"],
    )
    def test_non_excel_files_have_no_bom(self, filename):
        raw = (PROJECT_ROOT / filename).read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf", f"{filename} should not have a BOM"

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_no_cr_bytes(self, dialect):
        raw = (PROJECT_ROOT / DIALECT_FILES[dialect]).read_bytes()
        assert b"\r" not in raw, f"{DIALECT_FILES[dialect]} contains CR"

    @pytest.mark.parametrize("dialect", sorted(DIALECT_FILES))
    def test_parses_as_utf8(self, dialect):
        """Every file must decode as UTF-8 without errors."""
        (PROJECT_ROOT / DIALECT_FILES[dialect]).read_text(encoding="utf-8")

    def test_real_usd_row_matches_json(self):
        """Compare the USD row in iso4217.csv against its source in
        iso4217.json, field by field. This is a real-data smoke test,
        not a synthetic-fixture test."""
        registry = json.loads(
            (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")
        )
        usd_json = next(
            c for c in registry["currencies"]["active"] if c["code"] == "USD"
        )
        with open(PROJECT_ROOT / "iso4217.csv", encoding="utf-8", newline="") as f:
            rows = list(csv_module.DictReader(f))
        usd_csv = next(r for r in rows if r["code"] == "USD")
        assert usd_csv["numeric_code"] == usd_json["numeric"]
        assert usd_csv["name"] == usd_json["name"]
        assert usd_csv["minor_units"] == str(usd_json["minor_units"])
        assert usd_csv["symbol"] == usd_json.get("symbol", "")
        assert usd_csv["entity"] == usd_json.get("entity", "")
        assert usd_csv["status"] == "active"

    def test_real_aed_peg_row_is_correct(self):
        """AED must carry a USD peg with the correct rate, rendered with
        the shortest round-trippable float representation."""
        with open(PROJECT_ROOT / "iso4217.csv", encoding="utf-8", newline="") as f:
            rows = list(csv_module.DictReader(f))
        aed = next(r for r in rows if r["code"] == "AED")
        assert aed["is_independent"] == "false"
        assert aed["pegged_to"] == "USD"
        assert aed["peg_type"] == "single"
        assert float(aed["peg_rate"]) == 3.6725

    def test_no_duplicate_codes(self):
        """The registry has no duplicate ISO codes, so the CSV must not
        either — this is the invariant every downstream consumer relies on."""
        with open(PROJECT_ROOT / "iso4217.csv", encoding="utf-8", newline="") as f:
            rows = list(csv_module.DictReader(f))
        codes = [r["code"] for r in rows]
        duplicates = {c for c in codes if codes.count(c) > 1}
        assert not duplicates, f"duplicate codes in iso4217.csv: {duplicates}"


# ---------------------------------------------------------------------------
# Cross-check with the SQL export
# ---------------------------------------------------------------------------

class TestCrossCheckWithSQL:
    """
    The seven shared columns must be identical between iso4217.csv and
    iso4217.sqlite.sql, row for row. This is the test that catches
    divergence between the two exports — the exact scenario the roadmap
    warns about.
    """

    SQL_PATH = PROJECT_ROOT / "iso4217.sqlite.sql"
    CSV_PATH = PROJECT_ROOT / "iso4217.csv"

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
    def _csv_rows() -> list[tuple]:
        if not TestCrossCheckWithSQL.CSV_PATH.exists():
            pytest.skip("iso4217.csv not present")
        with open(
            TestCrossCheckWithSQL.CSV_PATH, encoding="utf-8", newline=""
        ) as f:
            reader = csv_module.DictReader(f)
            return [
                (
                    r["code"],
                    r["numeric_code"],
                    r["name"],
                    int(r["minor_units"]),
                    r["symbol"],
                    r["entity"],
                    r["status"],
                )
                for r in reader
            ]

    def test_row_counts_match(self):
        assert len(self._csv_rows()) == len(self._sql_rows())

    def test_shared_columns_match_row_for_row(self):
        """Sort both sides by (status_group, code) so this is
        independent of iteration order in either file."""
        def key(row):
            return (0 if row[6] == "active" else 1, row[0])

        sql = sorted(self._sql_rows(), key=key)
        csv_rows = sorted(self._csv_rows(), key=key)
        for sql_row, csv_row in zip(sql, csv_rows):
            assert sql_row == csv_row, (
                f"row mismatch: sql={sql_row!r} csv={csv_row!r}"
            )

    def test_active_count_matches(self):
        sql_active = sum(1 for r in self._sql_rows() if r[6] == "active")
        csv_active = sum(1 for r in self._csv_rows() if r[6] == "active")
        assert sql_active == csv_active

    def test_withdrawn_count_matches(self):
        sql_w = sum(1 for r in self._sql_rows() if r[6] == "withdrawn")
        csv_w = sum(1 for r in self._csv_rows() if r[6] == "withdrawn")
        assert sql_w == csv_w

    def test_sqlite_file_loads_without_errors(self):
        """Loading iso4217.sqlite.sql into an in-memory database proves
        the SQL executes. The cross-check tests above depend on this
        having worked, so if it fails, this test names the real cause."""
        self._sql_rows()  # raises if executescript failed