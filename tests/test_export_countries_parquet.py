"""
Tests for tools/export_countries_parquet.py.

Covers:
  - Module constants (COLUMNS, PARQUET_SCHEMA, metadata keys, exit codes)
  - Registry loading (valid fixture, missing file, malformed entries)
  - Row construction: count, columns, types, null semantics
  - Sort order: status, then currency_code, then country_code
  - Footer metadata: three keys, values match the fixture
  - Rendering and determinism (byte-identical output)
  - Atomic writes (no .tmp file lingers)
  - --check mode (clean, tampered value, tampered metadata, missing file)
  - CLI argument handling and exit codes
  - The committed file matches the committed registry
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.export_countries_parquet as ecp
from tools.export_countries_parquet import (
    COLUMNS,
    EXIT_FATAL,
    EXIT_MISMATCH,
    EXIT_MISSING,
    EXIT_OK,
    METADATA_ROWS_KEY,
    METADATA_UPDATED_KEY,
    METADATA_VERSION_KEY,
    PARQUET_SCHEMA,
    check_parquet,
    load_projection,
    main,
    render_parquet,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _entry(code: str, numeric: str, name: str, countries=None, **extra) -> dict:
    entry = {
        "code": code,
        "numeric": numeric,
        "name": name,
        "minor_units": 2,
        "is_independent": True,
        "classification": "circulating",
    }
    if countries is not None:
        entry["countries"] = [
            {"code": c, "name": n, "relationship": r} for c, n, r in countries
        ]
    entry.update(extra)
    return entry


@pytest.fixture
def registry_dict() -> dict:
    """
    Three active entries listed in non-sorted order, with countries in
    non-sorted order, plus two withdrawn entries (one with countries, one
    without). Total country rows: 3 + 2 + 1 + 1 = 7.
    """
    return {
        "meta": {"version": "9.9.9", "updated": "2026-01-01"},
        "source": {"last_amendment_applied": 1},
        "currencies": {
            "active": [
                _entry("USD", "840", "US Dollar", [
                    ("US", "United States", "issuing"),
                    ("EC", "Ecuador", "adopting"),
                    ("PA", "Panama", "adopting"),
                ]),
                _entry("EUR", "978", "Euro", [
                    ("FR", "France", "issuing"),
                    ("DE", "Germany", "issuing"),
                ]),
                _entry("CHF", "756", "Swiss Franc", [("CH", "Switzerland", "issuing")],
                       classification="circulating"),
                _entry("XAU", "959", "Gold", None, classification="indexation"),
            ],
            "withdrawn": [
                _entry("DEM", "276", "Deutsche Mark", [("DE", "Germany", "issuing")],
                       classification=None),
                _entry("ZZZ_OLD", "999", "No countries here"),
            ],
        },
    }


@pytest.fixture
def registry_path(tmp_path: Path, registry_dict: dict) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry_dict), encoding="utf-8")
    return path


@pytest.fixture
def projection(registry_path: Path):
    return load_projection(registry_path)


@pytest.fixture
def committed(tmp_path: Path, registry_path: Path) -> Path:
    """A freshly generated countries Parquet next to the fixture registry."""
    out = tmp_path / "countries.parquet"
    assert main(["--registry", str(registry_path), "--parquet", str(out)]) == EXIT_OK
    return out


# ---------------------------------------------------------------------------
# Constants and schema
# ---------------------------------------------------------------------------

class TestConstants:
    def test_columns(self):
        assert COLUMNS == (
            "currency_code", "country_code", "country_name",
            "relationship", "status", "classification",
        )

    def test_schema_matches_columns(self):
        assert tuple(PARQUET_SCHEMA.names) == COLUMNS

    def test_schema_types_and_nullability(self):
        for field in PARQUET_SCHEMA:
            assert field.type == pa.string()
        nullable = {f.name for f in PARQUET_SCHEMA if f.nullable}
        assert nullable == {"classification"}

    def test_exit_codes(self):
        assert (EXIT_OK, EXIT_MISMATCH, EXIT_FATAL, EXIT_MISSING) == (0, 1, 2, 3)

    def test_metadata_keys(self):
        assert METADATA_VERSION_KEY == "iso4217.version"
        assert METADATA_UPDATED_KEY == "iso4217.updated"
        assert METADATA_ROWS_KEY == "iso4217.countries_rows"


# ---------------------------------------------------------------------------
# Loading and projection
# ---------------------------------------------------------------------------

class TestLoading:
    def test_row_count_equals_sum_of_countries(self, projection, registry_dict):
        expected = sum(
            len(e.get("countries", []))
            for status in ("active", "withdrawn")
            for e in registry_dict["currencies"][status]
        )
        assert expected == 7
        assert projection.total_count == expected

    def test_column_names_and_types_after_render(self, projection):
        table = _read_bytes(render_parquet(projection))
        assert table.column_names == list(COLUMNS)
        for i, field in enumerate(PARQUET_SCHEMA):
            assert table.schema.field(i).type == field.type

    def test_sort_order(self, projection):
        keys = [(r.status, r.currency_code, r.country_code) for r in projection.rows]
        assert keys == sorted(keys)
        assert [k[0] for k in keys] == ["active"] * 6 + ["withdrawn"]
        assert keys[:3] == [
            ("active", "CHF", "CH"),
            ("active", "EUR", "DE"),
            ("active", "EUR", "FR"),
        ]

    def test_status_derived_from_array(self, projection):
        by_code = {r.currency_code: r.status for r in projection.rows}
        assert by_code["USD"] == "active"
        assert by_code["DEM"] == "withdrawn"

    def test_classification_carried_and_nullable(self, projection):
        by_code = {r.currency_code: r.classification for r in projection.rows}
        assert by_code["USD"] == "circulating"
        assert by_code["DEM"] is None

    def test_entry_without_countries_yields_no_rows(self, projection):
        codes = {r.currency_code for r in projection.rows}
        assert "XAU" not in codes
        assert "ZZZ_OLD" not in codes

    def test_missing_registry_is_fatal(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            load_projection(tmp_path / "nope.json")
        assert exc.value.code == EXIT_FATAL
        assert "nope.json" in capsys.readouterr().err

    def test_invalid_json_is_fatal(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            load_projection(bad)
        assert exc.value.code == EXIT_FATAL

    def test_duplicate_country_names_currency_and_country(self, tmp_path, registry_dict, capsys):
        registry_dict["currencies"]["active"][0]["countries"].append(
            {"code": "EC", "name": "Ecuador", "relationship": "adopting"}
        )
        path = tmp_path / "dup.json"
        path.write_text(json.dumps(registry_dict), encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            load_projection(path)
        assert exc.value.code == EXIT_FATAL
        err = capsys.readouterr().err
        assert "USD" in err and "EC" in err

    @pytest.mark.parametrize("bad_code", ["us", "USA", "U1", "", None, 7])
    def test_bad_country_code_is_fatal(self, tmp_path, registry_dict, capsys, bad_code):
        registry_dict["currencies"]["active"][0]["countries"][0]["code"] = bad_code
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(registry_dict), encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            load_projection(path)
        assert exc.value.code == EXIT_FATAL
        assert "USD.countries[0]" in capsys.readouterr().err

    def test_missing_relationship_is_fatal(self, tmp_path, registry_dict, capsys):
        del registry_dict["currencies"]["active"][0]["countries"][1]["relationship"]
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(registry_dict), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_projection(path)
        err = capsys.readouterr().err
        assert "USD.countries[1]" in err and "relationship" in err


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_exactly_three_keys_with_fixture_values(self, projection):
        table = _read_bytes(render_parquet(projection))
        meta = {k.decode(): v.decode() for k, v in table.schema.metadata.items()
                if not k.startswith(b"ARROW:")}
        assert meta == {
            "iso4217.version": "9.9.9",
            "iso4217.updated": "2026-01-01",
            "iso4217.countries_rows": "7",
        }


# ---------------------------------------------------------------------------
# Rendering, determinism, atomic writes
# ---------------------------------------------------------------------------

class TestRendering:
    def test_two_renders_are_byte_identical(self, projection):
        assert render_parquet(projection) == render_parquet(projection)

    def test_two_runs_write_byte_identical_files(self, tmp_path, registry_path):
        a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
        main(["--registry", str(registry_path), "--parquet", str(a)])
        main(["--registry", str(registry_path), "--parquet", str(b)])
        assert a.read_bytes() == b.read_bytes()

    def test_input_order_does_not_change_output(self, tmp_path, registry_dict):
        p1 = tmp_path / "r1.json"
        p1.write_text(json.dumps(registry_dict), encoding="utf-8")
        registry_dict["currencies"]["active"].reverse()
        for e in registry_dict["currencies"]["active"]:
            e.get("countries", []).reverse()
        p2 = tmp_path / "r2.json"
        p2.write_text(json.dumps(registry_dict), encoding="utf-8")
        assert render_parquet(load_projection(p1)) == render_parquet(load_projection(p2))

    def test_atomic_write_leaves_no_tmp(self, committed):
        assert committed.exists()
        assert not (committed.parent / (committed.name + ".tmp")).exists()

    def test_stdout_emits_valid_parquet(self, registry_path, capsysbinary):
        assert main(["--registry", str(registry_path), "--stdout"]) == EXIT_OK
        table = _read_bytes(capsysbinary.readouterr().out)
        assert table.num_rows == 7


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------

class TestCheck:
    def test_clean_file_passes(self, projection, committed, capsys):
        assert check_parquet(projection, committed) == EXIT_OK
        assert "matches" in capsys.readouterr().out

    def test_main_check_clean_exit_0(self, registry_path, committed):
        assert main(["--check", "--registry", str(registry_path), "--parquet", str(committed)]) == EXIT_OK

    def test_tampered_value_exit_1(self, registry_path, committed, capsys):
        table = pq.read_table(committed)
        rows = table.to_pylist()
        rows[2]["country_name"] = "Tampered"
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), committed)
        code = main(["--check", "--registry", str(registry_path), "--parquet", str(committed)])
        assert code == EXIT_MISMATCH
        err = capsys.readouterr().err
        assert "country_name" in err and "Tampered" in err

    def test_tampered_metadata_exit_1(self, registry_path, committed, capsys):
        table = pq.read_table(committed)
        meta = dict(table.schema.metadata)
        meta[b"iso4217.version"] = b"0.0.1"
        pq.write_table(table.replace_schema_metadata(meta), committed)
        code = main(["--check", "--registry", str(registry_path), "--parquet", str(committed)])
        assert code == EXIT_MISMATCH
        assert "iso4217.version" in capsys.readouterr().err

    def test_row_count_mismatch_exit_1(self, registry_path, committed):
        table = pq.read_table(committed)
        pq.write_table(table.slice(0, 3), committed)
        code = main(["--check", "--registry", str(registry_path), "--parquet", str(committed)])
        assert code == EXIT_MISMATCH

    def test_missing_file_exit_3(self, registry_path, tmp_path, capsys):
        code = main(["--check", "--registry", str(registry_path),
                     "--parquet", str(tmp_path / "absent.parquet")])
        assert code == EXIT_MISSING
        assert "absent.parquet" in capsys.readouterr().err

    def test_unreadable_file_exit_2(self, registry_path, tmp_path):
        junk = tmp_path / "junk.parquet"
        junk.write_bytes(b"not parquet")
        code = main(["--check", "--registry", str(registry_path), "--parquet", str(junk)])
        assert code == EXIT_FATAL

    def test_stdout_and_check_are_exclusive(self, registry_path):
        assert main(["--stdout", "--check", "--registry", str(registry_path)]) == EXIT_FATAL


# ---------------------------------------------------------------------------
# The committed artifact
# ---------------------------------------------------------------------------

class TestCommittedArtifact:
    def test_committed_file_matches_committed_registry(self):
        assert main(["--check"]) == EXIT_OK

    def test_every_active_currency_row_has_classification(self):
        table = pq.read_table(ecp.PARQUET_PATH)
        rows = table.to_pylist()
        assert rows
        assert all(r["classification"] for r in rows if r["status"] == "active")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_bytes(content: bytes) -> pa.Table:
    import io
    return pq.read_table(io.BytesIO(content))
