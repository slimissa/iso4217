"""
Tests for tools/export_aggregated.py.

Covers:
  - The layering rule, enforced in code: no reference to the RAW file
    outside comments; refusal of wrappers/ paths, wrong suffixes, and a
    JSON input that is the RAW registry
  - CURATED input validation (version skew, truncation, missing columns)
  - currencies_by_region: known-code rows, unresolved-code failure naming
    the code, null-region rows sorted last, the active-only join (a code
    present in both snapshot lists), subregion semantics, country_count
  - pegs_summary: grouping, statistics, null-rate handling, real-data shape
  - coverage_timeline: heading parsing, Version History counts, placeholder
    date, malformed changelogs, real-data shape
  - --check (clean, tampered value in each file, missing file, precedence)
  - --stdout manifest
  - Determinism (byte-identical output for all three files)
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.export_aggregated as agg
import tools.export_countries_parquet as ecp
import tools.export_parquet as ep
from tools.export_aggregated import (
    EXIT_FATAL,
    EXIT_MISMATCH,
    EXIT_MISSING,
    EXIT_OK,
    PEGS_FILE,
    REGION_FILE,
    TIMELINE_FILE,
    main,
)

OUTPUTS = (REGION_FILE, PEGS_FILE, TIMELINE_FILE)


# ---------------------------------------------------------------------------
# Fixtures: a tiny registry -> real CURATED files via the real generators
# ---------------------------------------------------------------------------

def _entry(code, numeric, name, countries=(), **extra) -> dict:
    entry = {
        "code": code, "numeric": numeric, "name": name, "minor_units": 2,
        "is_independent": True, "classification": "circulating",
    }
    if countries:
        entry["countries"] = [{"code": c, "name": c, "relationship": "issuing"} for c in countries]
    entry.update(extra)
    return entry


def _peg(anchor, rate=None) -> dict:
    out = {"pegged_to": anchor, "peg_type": "single"}
    if rate is not None:
        out["peg_rate"] = rate
    return out


REGISTRY = {
    "meta": {"version": "9.9.9", "updated": "2026-01-01"},
    "source": {"last_amendment_applied": 1},
    "currencies": {
        "active": [
            _entry("USD", "840", "US Dollar", ["US", "EC"]),
            _entry("EUR", "978", "Euro", ["FR", "DE", "IT", "XK"]),
            _entry("TWD", "901", "New Taiwan Dollar", ["TW"]),
            _entry("GBP", "826", "Pound Sterling", ["GB"]),
            _entry("FKP", "238", "Falkland Pound", ["FK"], **_peg("GBP")),
            _entry("AED", "784", "UAE Dirham", ["AE"], **_peg("USD", 3.6725)),
            _entry("SAR", "682", "Saudi Riyal", ["SA"], **_peg("USD", 3.75)),
            _entry("DKK", "208", "Danish Krone", ["DK"], **_peg("EUR", 7.46038)),
            _entry("BGN", "975", "Bulgarian Lev", ["BG"], **_peg("EUR")),
            _entry("MAD", "504", "Moroccan Dirham", ["MA"],
                   pegged_to="Currency basket", peg_type="basket"),
        ],
        "withdrawn": [
            _entry("DEM", "276", "Deutsche Mark", ["DE"], classification=None),
        ],
    },
}


def _region(region, subregion):
    return {"region": region, "subregion": subregion}


SNAPSHOT = {
    "countries": {
        "active": [
            {"alpha_2": "US", **_region("Americas", "Northern America")},
            {"alpha_2": "EC", **_region("Americas", "South America")},
            {"alpha_2": "FK", **_region("Americas", "South America")},
            {"alpha_2": "FR", **_region("Europe", "Western Europe")},
            {"alpha_2": "DE", **_region("Europe", "Western Europe")},
            {"alpha_2": "IT", **_region("Europe", "Southern Europe")},
            {"alpha_2": "GB", **_region("Europe", "Northern Europe")},
            {"alpha_2": "DK", **_region("Europe", "Northern Europe")},
            {"alpha_2": "BG", **_region("Europe", "Eastern Europe")},
            {"alpha_2": "AE", **_region("Asia", "Western Asia")},
            {"alpha_2": "SA", **_region("Asia", "Western Asia")},
            {"alpha_2": "MA", **_region("Africa", "Northern Africa")},
            {"alpha_2": "XK", **_region(None, None)},
            {"alpha_2": "TW", **_region(None, None)},
        ],
        # FR also appears here, as a historical entity with a different
        # region. A merged index would let it overwrite the live record.
        "withdrawn": [
            {"alpha_2": "FR", **_region("Asia", "Wrongland")},
            {"alpha_2": "YU", **_region("Europe", "Southern Europe")},
        ],
    },
    "meta": {"version": "0"},
}

CHANGELOG = """\
# Changelog

---
## [1.2.0] — 2026-XX-XX

Unreleased-date placeholder.

---
## [1.1.0] — 2026-02-01

Second release.

---
## [1.0.0] — 2026-01-01

First release.

---

## Version History

| Version | Date | Active | Withdrawn | Non-ISO | Wrappers | Exports |
|---------|------|--------|-----------|---------|----------|---------|
| **1.1.0** | **2026-02-01** | **10** | **1** | **3** | Python | — |
| 1.0.0 | 2026-01-01 | 8 | 1 | 2 | Python | — |
"""


class Env:
    """Paths and helpers for one self-contained input set."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.registry = root / "registry.json"
        self.parquet = root / "iso4217.parquet"
        self.countries = root / "iso4217.countries.parquet"
        self.snapshot = root / "snapshot.json"
        self.changelog = root / "CHANGELOG.md"
        self.out = root / "out"
        self.out.mkdir(exist_ok=True)

    def write_curated(self, registry: dict = REGISTRY) -> None:
        self.registry.write_text(json.dumps(registry), encoding="utf-8")
        self.parquet.write_bytes(ep.render_parquet(ep.load_registry(self.registry)))
        self.countries.write_bytes(ecp.render_parquet(ecp.load_projection(self.registry)))

    def argv(self, *extra: str) -> list:
        return [
            "--parquet", str(self.parquet), "--countries", str(self.countries),
            "--snapshot", str(self.snapshot), "--changelog", str(self.changelog),
            "--output-dir", str(self.out), *extra,
        ]

    def run(self, *extra: str) -> int:
        return main(self.argv(*extra))

    def table(self, name: str) -> pa.Table:
        return pq.read_table(self.out / name)

    def rows(self, name: str) -> list:
        return self.table(name).to_pylist()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.write_curated()
    e.snapshot.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    e.changelog.write_text(CHANGELOG, encoding="utf-8")
    return e


@pytest.fixture
def built(env: Env) -> Env:
    assert env.run() == EXIT_OK
    return env


def _fatal_message(env: Env, capsys, *extra: str) -> str:
    with pytest.raises(SystemExit) as exc:
        env.run(*extra)
    assert exc.value.code == EXIT_FATAL
    return capsys.readouterr().err


def _tamper(path: Path, column: str, value, row: int = 0) -> None:
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[row][column] = value
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)


# ---------------------------------------------------------------------------
# The layering rule
# ---------------------------------------------------------------------------

class TestLayeringRule:
    def test_module_never_references_the_raw_file_outside_comments(self):
        source = inspect.getsource(agg)
        code_lines = [l for l in source.splitlines() if not l.lstrip().startswith("#")]
        assert "iso4217.json" not in "\n".join(code_lines)
        # ...and the guard comment that explains why is present.
        assert "never from iso4217.json" in source

    def test_no_registry_loader_or_flag(self):
        assert not hasattr(agg, "load_registry")
        assert not hasattr(agg, "REGISTRY_PATH")
        with pytest.raises(SystemExit):
            agg.parse_args(["--registry", "x.json"])

    def test_module_imports_no_sibling_generator(self):
        source = inspect.getsource(agg)
        for name in ("export_parquet", "export_countries_parquet", "export_csv", "export_sql"):
            assert f"import {name}" not in source
            assert f"from tools.{name}" not in source

    def test_snapshot_under_wrappers_is_refused(self, env, capsys):
        wrapped = env.root / "wrappers" / "python"
        wrapped.mkdir(parents=True)
        (wrapped / "snapshot.json").write_text(json.dumps(SNAPSHOT), encoding="utf-8")
        err = _fatal_message(env, capsys, "--snapshot", str(wrapped / "snapshot.json"))
        assert "wrappers/" in err

    def test_parquet_input_under_wrappers_is_refused(self, env, capsys):
        wrapped = env.root / "wrappers"
        wrapped.mkdir()
        (wrapped / "iso4217.parquet").write_bytes(env.parquet.read_bytes())
        err = _fatal_message(env, capsys, "--parquet", str(wrapped / "iso4217.parquet"))
        assert "wrappers/" in err

    def test_snapshot_that_is_the_raw_registry_is_refused(self, env, capsys):
        # Same content as the RAW registry: top-level 'currencies' key.
        err = _fatal_message(env, capsys, "--snapshot", str(env.registry))
        assert "RAW registry" in err

    def test_the_real_raw_file_is_refused_as_snapshot(self, env, capsys):
        err = _fatal_message(env, capsys, "--snapshot", str(PROJECT_ROOT / "iso4217.json"))
        assert "RAW registry" in err

    def test_wrong_suffixes_are_refused(self, env, capsys):
        csv = env.root / "iso4217.csv"
        csv.write_text("code\n", encoding="utf-8")
        assert ".parquet" in _fatal_message(env, capsys, "--parquet", str(csv))
        assert ".md" in _fatal_message(env, capsys, "--changelog", str(env.snapshot))
        assert ".json" in _fatal_message(env, capsys, "--snapshot", str(csv))


# ---------------------------------------------------------------------------
# CURATED input validation
# ---------------------------------------------------------------------------

class TestCuratedInputs:
    def test_version_skew_is_fatal_and_names_both_files(self, env, capsys):
        table = pq.read_table(env.countries)
        meta = dict(table.schema.metadata)
        meta[b"iso4217.version"] = b"9.9.8"
        pq.write_table(table.replace_schema_metadata(meta), env.countries)
        err = _fatal_message(env, capsys)
        assert "iso4217.version" in err
        assert "iso4217.parquet" in err and "iso4217.countries.parquet" in err

    def test_truncated_countries_file_is_fatal(self, env, capsys):
        table = pq.read_table(env.countries)
        pq.write_table(table.slice(0, 2), env.countries)
        assert "truncated" in _fatal_message(env, capsys)

    def test_missing_input_names_the_generator(self, env, capsys):
        env.countries.unlink()
        err = _fatal_message(env, capsys)
        assert "export_countries_parquet.py" in err

    def test_missing_required_column_is_fatal(self, env, capsys):
        table = pq.read_table(env.countries).drop(["classification"])
        pq.write_table(table, env.countries)
        assert "'classification'" in _fatal_message(env, capsys)

    def test_pegged_to_and_peg_type_must_agree(self, tmp_path, capsys):
        broken = json.loads(json.dumps(REGISTRY))
        broken["currencies"]["active"][4].pop("peg_type")  # FKP: pegged_to without peg_type
        e = Env(tmp_path)
        e.write_curated(broken)
        e.snapshot.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
        e.changelog.write_text(CHANGELOG, encoding="utf-8")
        assert "FKP" in _fatal_message(e, capsys)


# ---------------------------------------------------------------------------
# currencies_by_region
# ---------------------------------------------------------------------------

class TestCurrenciesByRegion:
    def test_columns_and_types(self, built):
        t = built.table(REGION_FILE)
        assert t.column_names == [
            "region", "subregion", "currency_code", "currency_name",
            "classification", "is_pegged", "country_count",
        ]
        assert t.schema.field("is_pegged").type == pa.bool_()
        assert t.schema.field("country_count").type == pa.int32()

    def test_known_code_rows(self, built):
        by_key = {(r["region"], r["currency_code"]): r for r in built.rows(REGION_FILE)}
        usd = by_key[("Americas", "USD")]
        assert usd["currency_name"] == "US Dollar"
        assert usd["classification"] == "circulating"
        assert usd["is_pegged"] is False
        assert usd["country_count"] == 2
        assert by_key[("Asia", "AED")]["is_pegged"] is True
        assert by_key[("Africa", "MAD")]["is_pegged"] is True  # basket peg counts

    def test_subregion_shared_vs_mixed(self, built):
        by_key = {(r["region"], r["currency_code"]): r for r in built.rows(REGION_FILE)}
        # AE alone: one subregion -> kept.
        assert by_key[("Asia", "AED")]["subregion"] == "Western Asia"
        # USD in the Americas spans Northern and South America -> null.
        assert by_key[("Americas", "USD")]["subregion"] is None
        # EUR in Europe spans Western and Southern Europe -> null.
        eur = by_key[("Europe", "EUR")]
        assert eur["subregion"] is None
        assert eur["country_count"] == 3

    def test_null_region_rows_kept_and_sorted_last(self, built):
        rows = built.rows(REGION_FILE)
        tail = rows[-2:]
        assert [(r["region"], r["subregion"], r["currency_code"]) for r in tail] == [
            (None, None, "EUR"), (None, None, "TWD"),
        ]
        assert all(r["region"] is not None for r in rows[:-2])
        assert next(r for r in tail if r["currency_code"] == "EUR")["country_count"] == 1

    def test_sorted_by_region_then_currency(self, built):
        keys = [(r["region"] is None, r["region"] or "", r["currency_code"])
                for r in built.rows(REGION_FILE)]
        assert keys == sorted(keys)

    def test_one_row_per_region_currency(self, built):
        keys = [(r["region"], r["currency_code"]) for r in built.rows(REGION_FILE)]
        assert len(keys) == len(set(keys))

    def test_join_ignores_the_withdrawn_snapshot_list(self, built):
        # FR is Europe in countries.active and 'Asia' in countries.withdrawn.
        rows = built.rows(REGION_FILE)
        assert not any(r["subregion"] == "Wrongland" for r in rows)
        assert any(r["region"] == "Europe" and r["currency_code"] == "EUR" for r in rows)
        assert not any(r["region"] == "Asia" and r["currency_code"] == "EUR" for r in rows)

    def test_withdrawn_currencies_do_not_contribute(self, built):
        assert "DEM" not in {r["currency_code"] for r in built.rows(REGION_FILE)}

    def test_unresolved_country_code_is_fatal_and_named(self, env, capsys):
        _tamper(env.countries, "country_code", "ZZ", row=3)
        table = pq.read_table(env.countries).to_pylist()
        currency = table[3]["currency_code"]
        err = _fatal_message(env, capsys)
        assert "row 3" in err
        assert "'ZZ'" in err and repr(currency) in err
        assert "snapshot" in err

    def test_code_only_in_withdrawn_list_is_fatal_with_hint(self, env, capsys):
        _tamper(env.countries, "country_code", "YU", row=0)
        err = _fatal_message(env, capsys)
        assert "'YU'" in err and "withdrawn" in err

    def test_unknown_currency_is_fatal_and_named(self, env, capsys):
        _tamper(env.countries, "currency_code", "QQQ", row=0)
        assert "'QQQ'" in _fatal_message(env, capsys)

    def test_nothing_is_written_when_a_later_step_fails(self, env, capsys):
        env.changelog.write_text("# no headings here\n", encoding="utf-8")
        _fatal_message(env, capsys)
        assert list(env.out.iterdir()) == []


@pytest.fixture(scope="module")
def real_outputs(tmp_path_factory) -> Path:
    """The three files generated from the committed CURATED inputs."""
    out = tmp_path_factory.mktemp("real_outputs")
    assert main(["--output-dir", str(out)]) == EXIT_OK
    return out


# ---------------------------------------------------------------------------
# pegs_summary
# ---------------------------------------------------------------------------

class TestPegsSummary:
    def test_one_row_per_anchor_sorted(self, built):
        rows = built.rows(PEGS_FILE)
        assert [r["anchor_code"] for r in rows] == ["EUR", "GBP", "USD"]

    def test_members_are_sorted_and_counted(self, built):
        by_anchor = {r["anchor_code"]: r for r in built.rows(PEGS_FILE)}
        assert by_anchor["USD"]["currencies"] == ["AED", "SAR"]
        assert by_anchor["USD"]["currency_count"] == 2
        assert by_anchor["EUR"]["currencies"] == ["BGN", "DKK"]
        assert by_anchor["USD"]["anchor_name"] == "US Dollar"

    def test_statistics(self, built):
        usd = next(r for r in built.rows(PEGS_FILE) if r["anchor_code"] == "USD")
        assert usd["min_rate"] == 3.6725
        assert usd["max_rate"] == 3.75
        assert usd["median_rate"] == pytest.approx((3.6725 + 3.75) / 2)

    def test_null_rates_are_ignored_not_zero(self, built):
        eur = next(r for r in built.rows(PEGS_FILE) if r["anchor_code"] == "EUR")
        # BGN has no rate; only DKK's counts.
        assert eur["currency_count"] == 2
        assert eur["median_rate"] == eur["min_rate"] == eur["max_rate"] == 7.46038

    def test_anchor_with_no_numeric_rate_has_null_statistics(self, built):
        gbp = next(r for r in built.rows(PEGS_FILE) if r["anchor_code"] == "GBP")
        assert gbp["currency_count"] == 1
        assert gbp["median_rate"] is None and gbp["min_rate"] is None and gbp["max_rate"] is None

    def test_basket_pegs_are_excluded(self, built):
        members = {c for r in built.rows(PEGS_FILE) for c in r["currencies"]}
        assert "MAD" not in members

    def test_missing_anchor_is_fatal_and_named(self, tmp_path, capsys):
        broken = json.loads(json.dumps(REGISTRY))
        broken["currencies"]["active"] = [
            e for e in broken["currencies"]["active"] if e["code"] != "GBP"
        ]
        e = Env(tmp_path)
        e.write_curated(broken)
        e.snapshot.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
        e.changelog.write_text(CHANGELOG, encoding="utf-8")
        err = _fatal_message(e, capsys)
        assert "'GBP'" in err and "FKP" in err


class TestPegsSummaryRealData:
    @pytest.fixture
    def real(self, real_outputs):
        return real_outputs

    def test_44_single_pegs_across_8_anchors(self, real):
        rows = pq.read_table(real / PEGS_FILE).to_pylist()
        assert len(rows) == 8
        assert sum(r["currency_count"] for r in rows) == 44
        for r in rows:
            assert r["currency_count"] == len(r["currencies"])
            assert r["currencies"] == sorted(r["currencies"])

    def test_median_present_for_every_anchor_with_a_numeric_rate(self, real):
        flat = pq.read_table(PROJECT_ROOT / "iso4217.parquet").to_pylist()
        rates = {}
        for row in flat:
            if row["status"] == "active" and row["peg_type"] == "single" and row["peg_rate"] is not None:
                rates.setdefault(row["pegged_to"], []).append(row["peg_rate"])
        for r in pq.read_table(real / PEGS_FILE).to_pylist():
            if rates.get(r["anchor_code"]):
                assert r["median_rate"] is not None
                assert r["min_rate"] <= r["median_rate"] <= r["max_rate"]
            else:
                assert r["median_rate"] is None


# ---------------------------------------------------------------------------
# coverage_timeline
# ---------------------------------------------------------------------------

class TestCoverageTimeline:
    def test_sorted_ascending_by_version_not_lexically(self, env):
        env.changelog.write_text(
            CHANGELOG + "\n## [1.10.0] — 2026-03-01\n\n## [1.9.0] — 2026-02-15\n", encoding="utf-8"
        )
        assert env.run() == EXIT_OK
        assert [r["version"] for r in env.rows(TIMELINE_FILE)] == [
            "1.0.0", "1.1.0", "1.2.0", "1.9.0", "1.10.0",
        ]

    def test_counts_come_from_the_version_history_table(self, built):
        by_v = {r["version"]: r for r in built.rows(TIMELINE_FILE)}
        assert (by_v["1.0.0"]["active_count"], by_v["1.0.0"]["withdrawn_count"],
                by_v["1.0.0"]["non_iso_count"]) == (8, 1, 2)
        assert (by_v["1.1.0"]["active_count"], by_v["1.1.0"]["withdrawn_count"],
                by_v["1.1.0"]["non_iso_count"]) == (10, 1, 3)

    def test_versions_missing_from_the_table_have_null_counts(self, built):
        v120 = next(r for r in built.rows(TIMELINE_FILE) if r["version"] == "1.2.0")
        assert v120["active_count"] is None
        assert v120["withdrawn_count"] is None
        assert v120["non_iso_count"] is None

    def test_placeholder_date_is_null_with_stderr_note(self, env, capsys):
        assert env.run() == EXIT_OK
        err = capsys.readouterr().err
        assert "1.2.0" in err and "placeholder" in err
        assert next(r for r in env.rows(TIMELINE_FILE) if r["version"] == "1.2.0")["date"] is None

    def test_unreleased_heading_has_no_row(self, env, built):
        before = (built.out / TIMELINE_FILE).read_bytes()
        env.changelog.write_text(
            CHANGELOG.replace("## [1.2.0]", "## [1.3.0] \u2014 Unreleased\n\nNext release.\n\n---\n## [1.2.0]", 1),
            encoding="utf-8",
        )
        assert env.run() == EXIT_OK
        assert "1.3.0" not in [r["version"] for r in env.rows(TIMELINE_FILE)]
        assert (env.out / TIMELINE_FILE).read_bytes() == before
        assert env.run("--check") == EXIT_OK

    def test_source_is_changelog(self, built):
        assert {r["source"] for r in built.rows(TIMELINE_FILE)} == {"changelog"}

    def test_no_table_means_all_counts_null(self, env):
        env.changelog.write_text(CHANGELOG.split("## Version History")[0], encoding="utf-8")
        assert env.run() == EXIT_OK
        assert all(r["active_count"] is None for r in env.rows(TIMELINE_FILE))

    def test_no_headings_is_fatal(self, env, capsys):
        env.changelog.write_text("# Changelog\n", encoding="utf-8")
        assert "no '## [X.Y.Z]" in _fatal_message(env, capsys)

    def test_duplicate_version_is_fatal_and_named(self, env, capsys):
        env.changelog.write_text(CHANGELOG + "\n## [1.0.0] — 2026-01-02\n", encoding="utf-8")
        err = _fatal_message(env, capsys)
        assert "1.0.0" in err and "duplicate" in err

    def test_impossible_date_is_fatal_and_named(self, env, capsys):
        env.changelog.write_text(CHANGELOG.replace("2026-02-01", "2026-02-30", 1), encoding="utf-8")
        err = _fatal_message(env, capsys)
        assert "1.1.0" in err and "2026-02-30" in err

    def test_malformed_date_is_fatal(self, env, capsys):
        env.changelog.write_text(CHANGELOG + "\n## [1.3.0] — soon\n", encoding="utf-8")
        assert "1.3.0" in _fatal_message(env, capsys)

    def test_table_row_without_heading_is_fatal(self, env, capsys):
        env.changelog.write_text(CHANGELOG + "| 7.7.7 | 2026-05-05 | 1 | 1 | 1 | x | — |\n", encoding="utf-8")
        assert "7.7.7" in _fatal_message(env, capsys)

    def test_table_date_disagreeing_with_heading_is_fatal(self, env, capsys):
        env.changelog.write_text(CHANGELOG.replace("| 1.0.0 | 2026-01-01", "| 1.0.0 | 2026-01-09"), encoding="utf-8")
        err = _fatal_message(env, capsys)
        assert "1.0.0" in err and "2026-01-09" in err

    def test_non_integer_count_is_fatal(self, env, capsys):
        env.changelog.write_text(CHANGELOG.replace("| 8 | 1 | 2 |", "| many | 1 | 2 |"), encoding="utf-8")
        err = _fatal_message(env, capsys)
        assert "1.0.0" in err and "'many'" in err


class TestCoverageTimelineRealData:
    @pytest.fixture
    def real(self, real_outputs):
        return pq.read_table(real_outputs / TIMELINE_FILE).to_pylist()

    def test_parsed_from_the_committed_changelog(self, real):
        versions = [r["version"] for r in real]
        assert versions[0] == "1.0.0"
        assert "1.5.0" in versions and "1.7.3" in versions
        assert len(versions) == len(set(versions))

    def test_counts_known_through_1_5_0_and_null_after(self, real):
        def key(v):
            return tuple(int(p) for p in v.split("."))
        for r in real:
            if key(r["version"]) <= (1, 5, 0):
                assert r["active_count"] is not None
            else:
                assert r["active_count"] is None
                assert r["withdrawn_count"] is None
                assert r["non_iso_count"] is None

    def test_1_5_3_has_real_date(self, tmp_path, capsys):
        # Since v1.7.5 the v1.5.3 CHANGELOG heading carries its actual
        # tag date instead of the placeholder '2026-09-XX'. The
        # placeholder-handling code path in the tool is therefore not
        # exercised by the real data anymore; a synthetic-fixture test
        # would be needed to cover it (tracked as a follow-up).
        assert main(["--output-dir", str(tmp_path)]) == EXIT_OK
        err = capsys.readouterr().err
        assert "1.5.3" not in err
        rows = pq.read_table(tmp_path / TIMELINE_FILE).to_pylist()
        row = next(r for r in rows if r["version"] == "1.5.3")
        assert row["date"] == "2026-09-18"
        assert all(r["date"] for r in rows)


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------

class TestCheck:
    def test_clean_files_pass_for_all_three(self, built, capsys):
        assert built.run("--check") == EXIT_OK
        out = capsys.readouterr().out
        for name in OUTPUTS:
            assert f"{name} matches" in out

    @pytest.mark.parametrize("name, column, value", [
        (REGION_FILE, "country_count", 99),
        (PEGS_FILE, "currency_count", 99),
        (TIMELINE_FILE, "source", "git"),
    ])
    def test_tampered_value_exit_1_names_the_file(self, built, capsys, name, column, value):
        _tamper(built.out / name, column, value)
        assert built.run("--check") == EXIT_MISMATCH
        err = capsys.readouterr().err
        assert f"Mismatch: {name}" in err and column in err
        for other in OUTPUTS:
            if other != name:
                assert f"Mismatch: {other}" not in err

    def test_tampered_metadata_exit_1(self, built, capsys):
        table = pq.read_table(built.out / PEGS_FILE)
        meta = dict(table.schema.metadata)
        meta[b"iso4217.rows"] = b"999"
        pq.write_table(table.replace_schema_metadata(meta), built.out / PEGS_FILE)
        assert built.run("--check") == EXIT_MISMATCH
        assert "iso4217.rows" in capsys.readouterr().err

    def test_row_count_mismatch_exit_1(self, built):
        pq.write_table(pq.read_table(built.out / REGION_FILE).slice(0, 2), built.out / REGION_FILE)
        assert built.run("--check") == EXIT_MISMATCH

    def test_missing_file_exit_3(self, built, capsys):
        (built.out / TIMELINE_FILE).unlink()
        assert built.run("--check") == EXIT_MISSING
        assert f"Missing: {TIMELINE_FILE}" in capsys.readouterr().err

    def test_mismatch_outranks_missing(self, built):
        (built.out / TIMELINE_FILE).unlink()
        _tamper(built.out / PEGS_FILE, "currency_count", 99)
        assert built.run("--check") == EXIT_MISMATCH

    def test_all_files_are_reported_not_just_the_first(self, built, capsys):
        _tamper(built.out / REGION_FILE, "country_count", 99)
        _tamper(built.out / TIMELINE_FILE, "source", "git")
        assert built.run("--check") == EXIT_MISMATCH
        err = capsys.readouterr().err
        assert REGION_FILE in err and TIMELINE_FILE in err

    def test_stale_changelog_fails_the_check(self, built):
        built.changelog.write_text(CHANGELOG + "\n## [1.3.0] — 2026-03-01\n", encoding="utf-8")
        assert built.run("--check") == EXIT_MISMATCH

    def test_stdout_and_check_are_exclusive(self, built):
        assert built.run("--stdout", "--check") == EXIT_FATAL

    def test_committed_files_match_committed_inputs(self):
        assert main(["--check"]) == EXIT_OK


# ---------------------------------------------------------------------------
# --stdout manifest, writes, determinism
# ---------------------------------------------------------------------------

class TestOutputs:
    def test_stdout_prints_a_manifest_and_writes_nothing(self, env, capsys):
        assert env.run("--stdout") == EXIT_OK
        manifest = json.loads(capsys.readouterr().out)
        assert [f["file"] for f in manifest["files"]] == sorted(OUTPUTS)
        pegs = next(f for f in manifest["files"] if f["file"] == PEGS_FILE)
        assert pegs["rows"] == 3
        assert {c["name"] for c in pegs["columns"]} >= {"anchor_code", "currencies"}
        assert pegs["metadata"]["iso4217.version"] == "9.9.9"
        assert list(env.out.iterdir()) == []

    def test_manifest_is_deterministic(self, env, capsys):
        env.run("--stdout")
        first = capsys.readouterr().out
        env.run("--stdout")
        assert capsys.readouterr().out == first

    def test_footer_metadata_is_copied_from_curated_inputs(self, built):
        for name in OUTPUTS:
            meta = {k.decode(): v.decode() for k, v in built.table(name).schema.metadata.items()
                    if not k.startswith(b"ARROW:")}
            assert meta["iso4217.version"] == "9.9.9"
            assert meta["iso4217.updated"] == "2026-01-01"
            assert meta["iso4217.rows"] == str(built.table(name).num_rows)

    def test_no_tmp_files_linger(self, built):
        assert sorted(p.name for p in built.out.iterdir()) == sorted(OUTPUTS)

    def test_two_runs_are_byte_identical_for_all_three(self, tmp_path, env):
        second = tmp_path / "second"
        second.mkdir()
        assert env.run() == EXIT_OK
        assert env.run("--output-dir", str(second)) == EXIT_OK
        for name in OUTPUTS:
            assert (env.out / name).read_bytes() == (second / name).read_bytes()

    def test_committed_inputs_regenerate_byte_identically(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir(); b.mkdir()
        assert main(["--output-dir", str(a)]) == EXIT_OK
        assert main(["--output-dir", str(b)]) == EXIT_OK
        for name in OUTPUTS:
            assert (a / name).read_bytes() == (b / name).read_bytes()
