"""
Tests for tools/export_sql.py.

Covers:
  - Data classes (CurrencyRow, Registry)
  - Registry loading (valid, missing, malformed, bad field types)
  - Row construction (_row_from_entry)
  - SQL escaping (standard + MySQL)
  - Per-dialect renderers (ANSI, PostgreSQL, MySQL, SQLite)
  - Determinism, sort order
  - Header and footer blocks
  - CHECK constraints in all four dialects
  - Non-ISO exclusion
  - Atomic writes
  - --check / --stdout / --dialect modes
  - CLI argument parsing and exit codes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.export_sql as export_sql
from tools.export_sql import (
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
    _render_body,
    _render_footer,
    _render_header,
    _row_from_entry,
    _row_to_insert,
    check_all,
    generate_all,
    generate_one,
    load_registry,
    main,
    parse_args,
    render_ansi,
    render_mysql,
    render_postgresql,
    render_sqlite,
    sql_escape,
    sql_escape_mysql,
    sql_escape_standard,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_registry_json() -> dict:
    """A minimal but structurally valid registry, enough for all renderers."""
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
                    "code": "USD",
                    "numeric": "840",
                    "name": "US Dollar",
                    "minor_units": 2,
                    "symbol": "$",
                    "entity": "United States",
                },
                {
                    "code": "JPY",
                    "numeric": "392",
                    "name": "Japanese Yen",
                    "minor_units": 0,
                    "symbol": "¥",
                    "entity": "Japan",
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
                },
                {
                    "code": "MXN_OLD",
                    "numeric": "484",
                    "name": "Mexican Peso (pre-1993)",
                    "minor_units": 2,
                    "symbol": "MXP",
                    "entity": "Mexico",
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
    """A representative CurrencyRow for renderer and escaping tests."""
    return CurrencyRow(
        code="USD",
        numeric_code="840",
        name="US Dollar",
        minor_units=2,
        symbol="$",
        entity="United States",
        status="active",
    )


@pytest.fixture
def project_root_in_tmp(tmp_path: Path, minimal_registry_json: dict, monkeypatch) -> Path:
    """
    Redirect export_sql.PROJECT_ROOT to a temp directory so generate_all
    and check_all operate on isolated files rather than the real repo.
    """
    # Write a registry the module can find
    (tmp_path / "iso4217.json").write_text(
        json.dumps(minimal_registry_json, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(export_sql, "PROJECT_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# CurrencyRow
# ---------------------------------------------------------------------------

class TestCurrencyRow:
    def test_frozen(self):
        """CurrencyRow is frozen — assignment raises."""
        r = CurrencyRow("USD", "840", "US Dollar", 2, "$", "United States", "active")
        with pytest.raises(Exception):  # FrozenInstanceError
            r.code = "EUR"  # type: ignore

    def test_hashable(self):
        """Frozen dataclass is hashable — usable in sets."""
        r = CurrencyRow("USD", "840", "US Dollar", 2, "$", "United States", "active")
        assert {r}  # no exception

    def test_equality(self):
        a = CurrencyRow("USD", "840", "US Dollar", 2, "$", "United States", "active")
        b = CurrencyRow("USD", "840", "US Dollar", 2, "$", "United States", "active")
        assert a == b

    def test_inequality(self):
        a = CurrencyRow("USD", "840", "US Dollar", 2, "$", "United States", "active")
        b = CurrencyRow("EUR", "978", "Euro", 2, "€", "European Union", "active")
        assert a != b


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_active_count(self, minimal_registry: Registry):
        assert minimal_registry.active_count == 2

    def test_withdrawn_count(self, minimal_registry: Registry):
        assert minimal_registry.withdrawn_count == 2

    def test_total_count(self, minimal_registry: Registry):
        assert minimal_registry.total_count == 4

    def test_active_rows_come_first(self, minimal_registry: Registry):
        statuses = [r.status for r in minimal_registry.rows]
        # All active rows precede any withdrawn rows
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
        p.write_text(json.dumps({
            "meta": {"updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_source_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_amendment_not_int_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": "179"},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_missing_currencies_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_active_not_array_fatal(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {"active": "USD", "withdrawn": []},
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            load_registry(p)
        assert e.value.code == EXIT_FATAL

    def test_empty_currencies_ok(self, tmp_path: Path):
        p = tmp_path / "r.json"
        p.write_text(json.dumps({
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {"active": [], "withdrawn": []},
        }), encoding="utf-8")
        r = load_registry(p)
        assert r.active_count == 0
        assert r.withdrawn_count == 0


# ---------------------------------------------------------------------------
# _row_from_entry — validation
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
        }
        base.update(overrides)
        return base

    def test_valid_active(self):
        row = _row_from_entry(self._entry(), "active")
        assert row.code == "USD"
        assert row.numeric_code == "840"
        assert row.status == "active"

    def test_valid_withdrawn(self):
        row = _row_from_entry(self._entry(), "withdrawn")
        assert row.status == "withdrawn"

    def test_missing_symbol_defaults_empty(self):
        row = _row_from_entry(self._entry(symbol=None), "active")
        assert row.symbol == ""

    def test_missing_entity_defaults_empty(self):
        row = _row_from_entry(self._entry(entity=None), "active")
        assert row.entity == ""

    def test_code_3_chars_accepted(self):
        row = _row_from_entry(self._entry(code="JPY"), "active")
        assert row.code == "JPY"

    def test_code_7_chars_accepted(self):
        """MXN_OLD is 7 chars — revaluation case."""
        row = _row_from_entry(self._entry(code="MXN_OLD"), "withdrawn")
        assert row.code == "MXN_OLD"

    def test_code_2_chars_rejected(self):
        with pytest.raises(SystemExit) as e:
            _row_from_entry(self._entry(code="US"), "active")
        assert e.value.code == EXIT_FATAL

    def test_code_8_chars_rejected(self):
        with pytest.raises(SystemExit) as e:
            _row_from_entry(self._entry(code="ABCDEFGH"), "active")
        assert e.value.code == EXIT_FATAL

    def test_code_lowercase_rejected(self):
        with pytest.raises(SystemExit) as e:
            _row_from_entry(self._entry(code="usd"), "active")
        assert e.value.code == EXIT_FATAL

    def test_code_with_dash_rejected(self):
        with pytest.raises(SystemExit) as e:
            _row_from_entry(self._entry(code="US-"), "active")
        assert e.value.code == EXIT_FATAL

    def test_code_underscore_accepted(self):
        """Underscore is allowed in withdrawn codes."""
        row = _row_from_entry(self._entry(code="A_B"), "withdrawn")
        assert row.code == "A_B"

    def test_numeric_must_be_3_digits(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84"), "active")

    def test_numeric_leading_zero_preserved(self):
        row = _row_from_entry(self._entry(numeric="036"), "active")
        assert row.numeric_code == "036"

    def test_numeric_non_digit_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(numeric="84X"), "active")

    def test_name_empty_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(name=""), "active")

    def test_minor_units_negative_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=-1), "active")

    def test_minor_units_above_18_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=19), "active")

    def test_minor_units_zero_accepted(self):
        row = _row_from_entry(self._entry(minor_units=0), "active")
        assert row.minor_units == 0

    def test_minor_units_18_accepted(self):
        row = _row_from_entry(self._entry(minor_units=18), "active")
        assert row.minor_units == 18

    def test_minor_units_float_rejected(self):
        with pytest.raises(SystemExit):
            _row_from_entry(self._entry(minor_units=2.5), "active")


# ---------------------------------------------------------------------------
# SQL escaping
# ---------------------------------------------------------------------------

class TestEscaping:
    def test_standard_plain_string_unchanged(self):
        assert sql_escape_standard("US Dollar") == "US Dollar"

    def test_standard_single_quote_doubled(self):
        assert sql_escape_standard("O'Brien") == "O''Brien"

    def test_standard_multiple_quotes(self):
        assert sql_escape_standard("a'b'c") == "a''b''c"

    def test_standard_leading_quote(self):
        assert sql_escape_standard("'leading") == "''leading"

    def test_standard_trailing_quote(self):
        assert sql_escape_standard("trailing'") == "trailing''"

    def test_standard_backslash_untouched(self):
        """ANSI/PostgreSQL/SQLite: backslash is literal."""
        assert sql_escape_standard("a\\b") == "a\\b"

    def test_standard_unicode_untouched(self):
        assert sql_escape_standard("€¥") == "€¥"

    def test_standard_arabic_untouched(self):
        assert sql_escape_standard("د.ك") == "د.ك"

    def test_mysql_plain_string_unchanged(self):
        assert sql_escape_mysql("US Dollar") == "US Dollar"

    def test_mysql_single_quote_doubled(self):
        assert sql_escape_mysql("O'Brien") == "O''Brien"

    def test_mysql_backslash_doubled(self):
        assert sql_escape_mysql("a\\b") == "a\\\\b"

    def test_mysql_both_escapes(self):
        """Quotes and backslashes both escaped in MySQL."""
        result = sql_escape_mysql("O'Bri\\en")
        assert result == "O''Bri\\\\en"

    def test_mysql_backslash_n_escaped(self):
        """Literal backslash-n in data must not become newline."""
        assert sql_escape_mysql("a\\nb") == "a\\\\nb"

    def test_dispatcher_standard_default(self):
        assert sql_escape("O'Brien") == "O''Brien"

    def test_dispatcher_explicit_standard(self):
        assert sql_escape("O'Brien", "standard") == "O''Brien"

    def test_dispatcher_mysql(self):
        assert sql_escape("a\\b", "mysql") == "a\\\\b"


# ---------------------------------------------------------------------------
# _row_to_insert
# ---------------------------------------------------------------------------

class TestRowToInsert:
    def test_produces_valid_insert_sql(self, sample_row):
        stmt = _row_to_insert(sample_row)
        assert stmt.startswith("INSERT INTO currencies")
        assert "'USD'" in stmt
        assert "'840'" in stmt
        assert "2," in stmt
        assert "'active'" in stmt
        assert stmt.endswith(";")

    def test_column_list_fixed(self, sample_row):
        stmt = _row_to_insert(sample_row)
        expected_cols = "(code, numeric_code, name, minor_units, symbol, entity, status)"
        assert expected_cols in stmt

    def test_standard_escaping_used_by_default(self):
        row = CurrencyRow("USD", "840", "O'Brien", 2, "", "", "active")
        stmt = _row_to_insert(row, "standard")
        assert "O''Brien" in stmt
        assert "O'Bri\\n" not in stmt  # just verifying no accidental double-escape

    def test_mysql_escaping_used_when_dialect_mysql(self):
        row = CurrencyRow("USD", "840", "a\\b", 2, "", "", "active")
        stmt = _row_to_insert(row, "mysql")
        assert "a\\\\b" in stmt


# ---------------------------------------------------------------------------
# Header and footer
# ---------------------------------------------------------------------------

class TestHeaderFooter:
    def test_header_contains_version(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "9.9.9" in header

    def test_header_contains_updated(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "2026-01-01" in header

    def test_header_contains_amendment(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "179" in header

    def test_header_contains_license(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "Apache 2.0" in header

    def test_header_contains_counts(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "2 active" in header
        assert "2 withdrawn" in header
        assert "4 rows" in header

    def test_header_mentions_excluded_fields(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "non-ISO" in header

    def test_header_dialect_label_ansi(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        assert "ANSI" in header

    def test_header_dialect_label_postgres(self, minimal_registry):
        header = _render_header("postgresql", minimal_registry)
        assert "PostgreSQL" in header

    def test_header_dialect_label_mysql(self, minimal_registry):
        header = _render_header("mysql", minimal_registry)
        assert "MySQL" in header

    def test_header_dialect_label_sqlite(self, minimal_registry):
        header = _render_header("sqlite", minimal_registry)
        assert "SQLite" in header

    def test_header_uses_sql_comments(self, minimal_registry):
        header = _render_header("ansi", minimal_registry)
        for line in header.split("\n"):
            if line.strip():
                assert line.startswith("--"), f"non-comment line: {line!r}"

    def test_footer_has_active_count(self, minimal_registry):
        footer = _render_footer(minimal_registry)
        assert "Active rows:    2" in footer

    def test_footer_has_withdrawn_count(self, minimal_registry):
        footer = _render_footer(minimal_registry)
        assert "Withdrawn rows: 2" in footer

    def test_footer_has_total(self, minimal_registry):
        footer = _render_footer(minimal_registry)
        assert "Total rows:     4" in footer

    def test_footer_uses_sql_comments(self, minimal_registry):
        footer = _render_footer(minimal_registry)
        for line in footer.split("\n"):
            if line.strip():
                assert line.startswith("--")


# ---------------------------------------------------------------------------
# Per-dialect renderers
# ---------------------------------------------------------------------------

class TestRendererANSI:
    def test_contains_drop_table(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert "DROP TABLE IF EXISTS currencies;" in sql

    def test_contains_create_table(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert "CREATE TABLE currencies (" in sql

    def test_contains_index(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert "CREATE INDEX idx_currencies_status" in sql

    def test_contains_all_check_constraints(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert "chk_currencies_code_length" in sql
        assert "chk_currencies_minor_units" in sql
        assert "chk_currencies_status" in sql

    def test_insert_count_matches_rows(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert sql.count("INSERT INTO currencies") == minimal_registry.total_count

    def test_no_dialect_specific_syntax(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        assert "ENGINE=InnoDB" not in sql
        assert "STRICT" not in sql
        assert "utf8mb4" not in sql


class TestRendererPostgreSQL:
    def test_contains_drop_table(self, minimal_registry):
        sql = render_postgresql(minimal_registry)
        assert "DROP TABLE IF EXISTS currencies;" in sql

    def test_contains_on_conflict_alternative(self, minimal_registry):
        sql = render_postgresql(minimal_registry)
        assert "ON CONFLICT (code) DO NOTHING" in sql

    def test_on_conflict_is_commented(self, minimal_registry):
        sql = render_postgresql(minimal_registry)
        for line in sql.split("\n"):
            if "ON CONFLICT" in line:
                assert line.strip().startswith("--")

    def test_insert_count_matches_rows(self, minimal_registry):
        sql = render_postgresql(minimal_registry)
        # Count only actual INSERTs, not the commented example
        actual = [l for l in sql.split("\n") if l.startswith("INSERT INTO")]
        assert len(actual) == minimal_registry.total_count


class TestRendererMySQL:
    def test_contains_engine_innoDB(self, minimal_registry):
        sql = render_mysql(minimal_registry)
        assert "ENGINE=InnoDB" in sql

    def test_contains_utf8mb4(self, minimal_registry):
        sql = render_mysql(minimal_registry)
        assert "utf8mb4" in sql

    def test_uses_tinyint_unsigned_for_minor_units(self, minimal_registry):
        sql = render_mysql(minimal_registry)
        assert "TINYINT UNSIGNED" in sql

    def test_no_outdated_backslash_note(self, minimal_registry):
        """The old outdated note about manual escaping must be gone."""
        sql = render_mysql(minimal_registry)
        assert "SET sql_mode = 'NO_BACKSLASH_ESCAPES'" not in sql

    def test_insert_count_matches_rows(self, minimal_registry):
        sql = render_mysql(minimal_registry)
        assert sql.count("INSERT INTO currencies") == minimal_registry.total_count


class TestRendererSQLite:
    def test_contains_strict_modifier(self, minimal_registry):
        sql = render_sqlite(minimal_registry)
        assert ") STRICT;" in sql

    def test_uses_text_types(self, minimal_registry):
        sql = render_sqlite(minimal_registry)
        assert "code          TEXT" in sql
        assert "name          TEXT" in sql

    def test_uses_integer_for_minor_units(self, minimal_registry):
        sql = render_sqlite(minimal_registry)
        assert "minor_units   INTEGER" in sql

    def test_insert_count_matches_rows(self, minimal_registry):
        sql = render_sqlite(minimal_registry)
        assert sql.count("INSERT INTO currencies") == minimal_registry.total_count


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_two_runs_identical(self, minimal_registry, dialect):
        r1 = RENDERERS[dialect](minimal_registry)
        r2 = RENDERERS[dialect](minimal_registry)
        assert r1 == r2

    def test_no_wall_clock_in_output(self, minimal_registry):
        """Header must not contain the current date, only meta.updated."""
        from datetime import date
        sql = render_ansi(minimal_registry)
        # Today's date should not appear unless it happens to equal meta.updated
        if str(date.today()) != minimal_registry.updated:
            assert str(date.today()) not in sql


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

class TestSortOrder:
    def test_active_codes_sorted(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        active_inserts = [
            l for l in sql.split("\n")
            if l.startswith("INSERT") and "'active'" in l
        ]
        codes = [l.split("'")[1] for l in active_inserts]
        assert codes == sorted(codes)

    def test_withdrawn_codes_sorted(self, minimal_registry):
        sql = render_ansi(minimal_registry)
        withdrawn_inserts = [
            l for l in sql.split("\n")
            if l.startswith("INSERT") and "'withdrawn'" in l
        ]
        codes = [l.split("'")[1] for l in withdrawn_inserts]
        assert codes == sorted(codes)

    def test_withdrawn_after_active(self, minimal_registry):
        """All active INSERT rows must precede any withdrawn INSERT row.

        Scoped to INSERT lines only. The CHECK constraint in CREATE TABLE
        also contains the literals 'active' and 'withdrawn', so a naive
        find() on the whole file matches the constraint, not the data.
        """
        sql = render_ansi(minimal_registry)
        insert_lines = [l for l in sql.split("\n") if l.startswith("INSERT INTO")]
        statuses = []
        for line in insert_lines:
            if "'active'" in line:
                statuses.append("active")
            elif "'withdrawn'" in line:
                statuses.append("withdrawn")
        assert statuses, "no INSERT lines found in output"
        first_withdrawn = statuses.index("withdrawn")
        assert all(s == "active" for s in statuses[:first_withdrawn]), (
            f"active row appears after a withdrawn row: {statuses}"
        )
        assert all(s == "withdrawn" for s in statuses[first_withdrawn:]), (
            f"withdrawn rows are not contiguous at the end: {statuses}"
        )


# ---------------------------------------------------------------------------
# Non-ISO exclusion
# ---------------------------------------------------------------------------

class TestNonIsoExclusion:
    def test_btc_not_in_output(self, minimal_registry):
        """Non-ISO entries in the JSON must not appear in SQL."""
        sql = render_ansi(minimal_registry)
        assert "BTC" not in sql
        assert "Bitcoin" not in sql


# ---------------------------------------------------------------------------
# Constraints — checked on real renderer output
# ---------------------------------------------------------------------------

class TestConstraints:
    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_code_length_check(self, minimal_registry, dialect):
        sql = RENDERERS[dialect](minimal_registry)
        assert "chk_currencies_code_length" in sql
        assert "LENGTH(code) BETWEEN 3 AND 7" in sql

    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_minor_units_check(self, minimal_registry, dialect):
        sql = RENDERERS[dialect](minimal_registry)
        assert "chk_currencies_minor_units" in sql
        assert "minor_units BETWEEN 0 AND 18" in sql

    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_status_check(self, minimal_registry, dialect):
        sql = RENDERERS[dialect](minimal_registry)
        assert "chk_currencies_status" in sql
        assert "'active', 'withdrawn'" in sql

    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_primary_key_on_code(self, minimal_registry, dialect):
        sql = RENDERERS[dialect](minimal_registry)
        assert "PRIMARY KEY (code)" in sql


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_writes_content(self, tmp_path):
        p = tmp_path / "out.sql"
        _atomic_write(p, "-- hello\n")
        assert p.read_text() == "-- hello\n"

    def test_no_tmp_file_lingers(self, tmp_path):
        p = tmp_path / "out.sql"
        _atomic_write(p, "content")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.sql"
        p.write_text("old")
        _atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_write_failure_exits_fatal(self, tmp_path):
        """Attempt to write to a directory path (invalid target)."""
        p = tmp_path / "subdir"
        p.mkdir()
        with pytest.raises(SystemExit) as e:
            _atomic_write(p, "content")
        assert e.value.code == EXIT_FATAL


# ---------------------------------------------------------------------------
# generate_one
# ---------------------------------------------------------------------------

class TestGenerateOne:
    @pytest.mark.parametrize("dialect", ["ansi", "postgresql", "mysql", "sqlite"])
    def test_returns_string(self, minimal_registry, dialect):
        content = generate_one(minimal_registry, dialect)
        assert isinstance(content, str)
        assert content.startswith("-- ISO 4217 Currency Registry")

    def test_unknown_dialect_fatal(self, minimal_registry):
        with pytest.raises(SystemExit) as e:
            generate_one(minimal_registry, "oracle")
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
        tmp_files = list(project_root_in_tmp.glob("*.tmp"))
        assert tmp_files == []


# ---------------------------------------------------------------------------
# check_all — exit codes
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_all_match_returns_ok(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        assert check_all(minimal_registry) == EXIT_OK

    def test_mismatch_returns_1(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        # Tamper with one file
        target = project_root_in_tmp / DIALECT_FILES["ansi"]
        target.write_text(target.read_text() + "\n-- tamper\n")
        assert check_all(minimal_registry) == EXIT_MISMATCH

    def test_missing_returns_3(self, minimal_registry, project_root_in_tmp):
        generate_all(minimal_registry)
        # Delete one file
        (project_root_in_tmp / DIALECT_FILES["ansi"]).unlink()
        assert check_all(minimal_registry) == EXIT_MISSING

    def test_missing_takes_precedence_over_mismatch(
        self, minimal_registry, project_root_in_tmp
    ):
        """If both missing and mismatched exist, exit code is 3 (missing)."""
        generate_all(minimal_registry)
        (project_root_in_tmp / DIALECT_FILES["ansi"]).unlink()
        target = project_root_in_tmp / DIALECT_FILES["mysql"]
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
        # Registry default should be the module's own constant
        from tools.export_sql import REGISTRY_PATH
        assert args.registry == REGISTRY_PATH

    def test_dialect_short(self):
        assert parse_args(["-d", "sqlite"]).dialect == "sqlite"

    def test_dialect_long(self):
        assert parse_args(["--dialect", "postgresql"]).dialect == "postgresql"

    def test_check_flag(self):
        assert parse_args(["--check"]).check is True

    def test_stdout_flag(self):
        assert parse_args(["--stdout"]).stdout is True

    def test_registry_override(self):
        args = parse_args(["--registry", "/tmp/x.json"])
        assert args.registry == Path("/tmp/x.json")

    def test_unknown_dialect_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--dialect", "oracle"])


# ---------------------------------------------------------------------------
# main() — end-to-end exit code matrix
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_registry_exits_fatal(self, tmp_path):
        """_fatal() calls sys.exit(), which raises SystemExit rather than
        returning an int. The test must expect the exception and inspect
        its .code, not compare main()'s return value.
        """
        with pytest.raises(SystemExit) as exc_info:
            main(["--registry", str(tmp_path / "missing.json")])
        assert exc_info.value.code == EXIT_FATAL

    def test_stdout_without_dialect_fatal(self, minimal_registry_file):
        code = main([
            "--registry", str(minimal_registry_file),
            "--stdout",
        ])
        assert code == EXIT_FATAL

    def test_check_and_stdout_mutually_exclusive(self, minimal_registry_file):
        code = main([
            "--registry", str(minimal_registry_file),
            "--check",
            "--stdout",
            "--dialect", "ansi",
        ])
        assert code == EXIT_FATAL

    def test_check_clean_returns_ok(self, minimal_registry, project_root_in_tmp,
                                     minimal_registry_file):
        # Registry path must point at the temp registry too
        generate_all(minimal_registry)
        code = main([
            "--registry", str(minimal_registry_file),
            "--check",
        ])
        assert code == EXIT_OK

    def test_check_mismatch_returns_1(self, minimal_registry, project_root_in_tmp,
                                       minimal_registry_file):
        generate_all(minimal_registry)
        target = project_root_in_tmp / DIALECT_FILES["ansi"]
        target.write_text(target.read_text() + "\n-- tamper\n")
        code = main([
            "--registry", str(minimal_registry_file),
            "--check",
        ])
        assert code == EXIT_MISMATCH

    def test_check_missing_returns_3(self, minimal_registry, project_root_in_tmp,
                                      minimal_registry_file):
        generate_all(minimal_registry)
        (project_root_in_tmp / DIALECT_FILES["ansi"]).unlink()
        code = main([
            "--registry", str(minimal_registry_file),
            "--check",
        ])
        assert code == EXIT_MISSING

    def test_default_writes_all_four(self, minimal_registry, project_root_in_tmp,
                                      minimal_registry_file, capsys):
        code = main(["--registry", str(minimal_registry_file)])
        assert code == EXIT_OK
        for filename in DIALECT_FILES.values():
            assert (project_root_in_tmp / filename).exists()
        # Something was logged to stderr
        captured = capsys.readouterr()
        assert "Wrote" in captured.err

    def test_single_dialect_writes_one(self, minimal_registry, project_root_in_tmp,
                                        minimal_registry_file):
        code = main([
            "--registry", str(minimal_registry_file),
            "--dialect", "sqlite",
        ])
        assert code == EXIT_OK
        assert (project_root_in_tmp / DIALECT_FILES["sqlite"]).exists()
        # Others should NOT exist
        assert not (project_root_in_tmp / DIALECT_FILES["ansi"]).exists()

    def test_stdout_prints_to_stdout(self, minimal_registry_file, capsys):
        code = main([
            "--registry", str(minimal_registry_file),
            "--dialect", "ansi",
            "--stdout",
        ])
        assert code == EXIT_OK
        captured = capsys.readouterr()
        assert captured.out.startswith("-- ISO 4217 Currency Registry")
        # stderr should be empty or minimal
        assert "Wrote" not in captured.err


# ---------------------------------------------------------------------------
# Integration: real project files
# ---------------------------------------------------------------------------

class TestRealProject:
    """
    Sanity checks against the actual committed SQL files and iso4217.json.
    These tests fail if the repository is in an inconsistent state.
    """

    def test_committed_files_match_registry(self):
        code = main(["--check"])
        assert code == EXIT_OK, (
            "Committed SQL files are out of sync with iso4217.json. "
            "Run 'python3 tools/export_sql.py' and commit the result."
        )

    def test_sql_files_exist(self):
        for filename in DIALECT_FILES.values():
            p = PROJECT_ROOT / filename
            assert p.exists(), f"Missing committed file: {filename}"

    def test_ansi_file_insert_count_matches_registry(self):
        """Derive the expected count from iso4217.json rather than hardcoding
        a number. The count changes on every registry update, so a literal
        will be stale after the next release.
        """
        registry = json.loads(
            (PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8")
        )
        expected = (
            len(registry["currencies"]["active"])
            + len(registry["currencies"]["withdrawn"])
        )
        sql = (PROJECT_ROOT / "iso4217.sql").read_text(encoding="utf-8")
        actual = sql.count("INSERT INTO currencies")
        assert actual == expected, (
            f"iso4217.sql has {actual} INSERTs, expected {expected} "
            f"(active + withdrawn in iso4217.json)"
        )

    def test_ansi_file_has_mxn_old(self):
        sql = (PROJECT_ROOT / "iso4217.sql").read_text(encoding="utf-8")
        assert "'MXN_OLD'" in sql