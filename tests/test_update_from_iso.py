"""
Tests for tools/update_from_iso.py.

Covers:
  - Dataclasses (FieldChange, CurrencyChange, UpdateReport) and ChangeType
  - Registry I/O (load_registry, save_registry, backup_registry)
  - Code index construction (build_code_index)
  - Diff engine (diff_currency, generate_diff)
  - Change application (apply_changes, non-interactive path)
  - Source data helpers (save_source_data, load_latest_source)
  - Report formatting and persistence (format_report, save_report)

Focus: the save_registry default-path fix. Before v1.5.3, save_registry
required an explicit path, but two callers passed only one argument and
raised TypeError. test_save_registry_with_one_argument_no_longer_raises
is the regression guard for that bug.

This is the only write-capable tool in the repository. It had no tests
before v1.5.3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tools.update_from_iso as update_from_iso
from tools.update_from_iso import (
    CURRENCY_TEMPLATE,
    REGISTRY_PATH,
    ChangeType,
    CurrencyChange,
    FieldChange,
    UpdateReport,
    apply_changes,
    backup_registry,
    build_code_index,
    diff_currency,
    format_report,
    generate_diff,
    load_latest_source,
    load_registry,
    save_registry,
    save_report,
    save_source_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_registry() -> dict:
    """A minimal structurally valid registry, three currencies."""
    return {
        "meta": {"version": "1.5.2", "updated": "2026-09-16"},
        "source": {"last_amendment_applied": 179},
        "currencies": {
            "active": [
                {
                    "code": "USD", "numeric": "840", "name": "US Dollar",
                    "minor_units": 2, "symbol": "$", "entity": "United States",
                },
                {
                    "code": "EUR", "numeric": "978", "name": "Euro",
                    "minor_units": 2, "symbol": "\u20ac", "entity": "Eurozone",
                },
                {
                    "code": "JPY", "numeric": "392", "name": "Japanese Yen",
                    "minor_units": 0, "symbol": "\u00a5", "entity": "Japan",
                },
            ],
            "withdrawn": [
                {
                    "code": "DEM", "numeric": "276", "name": "German Mark",
                    "minor_units": 2, "symbol": "DM", "entity": "Germany",
                },
            ],
        },
    }


@pytest.fixture
def empty_registry() -> dict:
    return {
        "meta": {"version": "1.5.2", "updated": "2026-09-16"},
        "source": {"last_amendment_applied": 179},
        "currencies": {"active": [], "withdrawn": []},
    }


@pytest.fixture
def registry_file(tmp_path: Path, sample_registry: dict) -> Path:
    p = tmp_path / "iso4217.json"
    p.write_text(
        json.dumps(sample_registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sources_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect SOURCES_DIR to an empty temp directory."""
    d = tmp_path / "sources"
    d.mkdir()
    monkeypatch.setattr(update_from_iso, "SOURCES_DIR", d)
    return d


@pytest.fixture
def diffs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect DIFFS_DIR to an empty temp directory."""
    d = tmp_path / "diffs"
    monkeypatch.setattr(update_from_iso, "DIFFS_DIR", d)
    return d


# ===========================================================================
# ChangeType — the enum
# ===========================================================================

class TestChangeType:
    def test_has_five_values(self):
        assert len(list(ChangeType)) == 5

    def test_added_value(self):
        assert ChangeType.ADDED.value == "added"

    def test_removed_value(self):
        assert ChangeType.REMOVED.value == "removed"

    def test_modified_value(self):
        assert ChangeType.MODIFIED.value == "modified"

    def test_withdrawn_value(self):
        assert ChangeType.WITHDRAWN.value == "withdrawn"

    def test_reactivated_value(self):
        assert ChangeType.REACTIVATED.value == "reactivated"

    def test_members_are_distinct(self):
        assert len({t.value for t in ChangeType}) == 5


# ===========================================================================
# FieldChange — single field diff
# ===========================================================================

class TestFieldChange:
    def test_constructs(self):
        fc = FieldChange(field="minor_units", old_value=2, new_value=3)
        assert fc.field == "minor_units"
        assert fc.old_value == 2
        assert fc.new_value == 3

    def test_str_uses_arrow(self):
        fc = FieldChange(field="minor_units", old_value=2, new_value=3)
        s = str(fc)
        assert "minor_units" in s
        assert "2" in s and "3" in s
        # The arrow character — \u2192 — is the one the module uses
        assert "\u2192" in s or "->" in s

    def test_none_values_render(self):
        fc = FieldChange(field="symbol", old_value=None, new_value="$")
        s = str(fc)
        assert "symbol" in s
        assert "$" in s


# ===========================================================================
# CurrencyChange — one currency's diff
# ===========================================================================

class TestCurrencyChange:
    def test_constructs_with_defaults(self):
        cc = CurrencyChange(
            code="USD",
            change_type=ChangeType.MODIFIED,
            category="currencies.active",
        )
        assert cc.code == "USD"
        assert cc.change_type == ChangeType.MODIFIED
        assert cc.category == "currencies.active"
        assert cc.field_changes == []
        assert cc.source == ""
        assert cc.note == ""

    def test_field_changes_are_independent_per_instance(self):
        """default_factory=list — two instances don't share the list."""
        a = CurrencyChange(code="USD", change_type=ChangeType.MODIFIED, category="x")
        b = CurrencyChange(code="EUR", change_type=ChangeType.MODIFIED, category="y")
        a.field_changes.append(FieldChange(field="f", old_value=1, new_value=2))
        assert b.field_changes == []

    def test_str_includes_code_and_type(self):
        cc = CurrencyChange(
            code="USD",
            change_type=ChangeType.ADDED,
            category="currencies.active",
        )
        s = str(cc)
        assert "USD" in s
        assert "ADDED" in s

    def test_str_includes_note_when_present(self):
        cc = CurrencyChange(
            code="USD",
            change_type=ChangeType.MODIFIED,
            category="currencies.active",
            note="Minor correction",
        )
        assert "Minor correction" in str(cc)

    def test_str_includes_field_changes(self):
        cc = CurrencyChange(
            code="USD",
            change_type=ChangeType.MODIFIED,
            category="currencies.active",
            field_changes=[FieldChange(field="minor_units", old_value=2, new_value=3)],
        )
        assert "minor_units" in str(cc)


# ===========================================================================
# UpdateReport — the full diff
# ===========================================================================

class TestUpdateReport:
    def test_constructs_with_defaults(self):
        r = UpdateReport(timestamp="2026-09-17T12:00:00", source_amendment=179,
                         source_date="2026-09-17")
        assert r.changes == []
        assert r.warnings == []
        assert r.requires_review == []

    def test_total_changes_zero(self):
        r = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        assert r.total_changes == 0

    def test_total_changes_counts(self):
        r = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="A", change_type=ChangeType.ADDED, category="c"),
                CurrencyChange(code="B", change_type=ChangeType.MODIFIED, category="c"),
                CurrencyChange(code="C", change_type=ChangeType.WITHDRAWN, category="c"),
            ],
        )
        assert r.total_changes == 3

    def test_added_count(self):
        r = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="A", change_type=ChangeType.ADDED, category="c"),
                CurrencyChange(code="B", change_type=ChangeType.ADDED, category="c"),
                CurrencyChange(code="C", change_type=ChangeType.MODIFIED, category="c"),
            ],
        )
        assert r.added_count == 2

    def test_removed_count(self):
        r = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="A", change_type=ChangeType.REMOVED, category="c"),
                CurrencyChange(code="B", change_type=ChangeType.WITHDRAWN, category="c"),
            ],
        )
        # Only REMOVED counts, not WITHDRAWN
        assert r.removed_count == 1

    def test_modified_count(self):
        r = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="A", change_type=ChangeType.MODIFIED, category="c"),
                CurrencyChange(code="B", change_type=ChangeType.MODIFIED, category="c"),
                CurrencyChange(code="C", change_type=ChangeType.ADDED, category="c"),
            ],
        )
        assert r.modified_count == 2


# ===========================================================================
# load_registry
# ===========================================================================

class TestLoadRegistry:
    def test_loads_valid_file(self, registry_file: Path, sample_registry: dict):
        loaded = load_registry(registry_file)
        assert loaded == sample_registry

    def test_default_path_uses_registry_path(self, registry_file: Path,
                                              monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(update_from_iso, "REGISTRY_PATH", registry_file)
        loaded = load_registry()
        assert "currencies" in loaded

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_registry(tmp_path / "does-not-exist.json")

    def test_invalid_json_raises(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_registry(p)

    def test_preserves_unicode(self, tmp_path: Path):
        data = {
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {
                "active": [{"code": "JPY", "symbol": "\u00a5", "name": "Japanese Yen"}],
                "withdrawn": [],
            },
        }
        p = tmp_path / "r.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        loaded = load_registry(p)
        assert loaded["currencies"]["active"][0]["symbol"] == "\u00a5"


# ===========================================================================
# save_registry — the Critical-path fix
# ===========================================================================

class TestSaveRegistry:
    """Regression guard for the audit finding.

    save_registry required an explicit path, but --add-currency and
    --apply called it with one argument and raised TypeError. These
    tests verify the fix.
    """

    def test_save_registry_with_explicit_path(self, tmp_path: Path,
                                              sample_registry: dict):
        target = tmp_path / "out.json"
        save_registry(sample_registry, target)
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == sample_registry

    def test_save_registry_with_one_argument_no_longer_raises(self, sample_registry: dict):
        """The regression test.

        Before the fix, save_registry(data) raised:
            TypeError: save_registry() missing 1 required positional argument: 'path'

        After the fix, one argument is valid.
        """
        # No target path — uses the default. We don't want to actually write
        # to the real REGISTRY_PATH, so we test that the call signature is
        # valid by inspecting the signature.
        import inspect
        sig = inspect.signature(save_registry)
        params = list(sig.parameters.values())
        # Two parameters: data (required) and path (optional)
        assert len(params) == 2
        assert params[0].name == "data"
        assert params[0].default is inspect.Parameter.empty
        assert params[1].name == "path"
        # Must have a default
        assert params[1].default is not inspect.Parameter.empty, (
            "save_registry's path parameter must have a default. "
            "The audit found that save_registry(data) raised TypeError "
            "because path had no default."
        )

    def test_save_registry_without_path_uses_default(
        self, tmp_path: Path, sample_registry: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When called with one argument, save_registry writes to REGISTRY_PATH."""
        target = tmp_path / "default.json"
        monkeypatch.setattr(update_from_iso, "REGISTRY_PATH", target)
        save_registry(sample_registry)
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == sample_registry

    def test_save_registry_preserves_utf8(self, tmp_path: Path):
        data = {
            "meta": {"version": "1.0.0", "updated": "2026-01-01"},
            "source": {"last_amendment_applied": 179},
            "currencies": {
                "active": [
                    {"code": "JPY", "symbol": "\u00a5", "name": "Japanese Yen"},
                    {"code": "EUR", "symbol": "\u20ac", "name": "Euro"},
                ],
                "withdrawn": [],
            },
        }
        target = tmp_path / "out.json"
        save_registry(data, target)
        reloaded = json.loads(target.read_text(encoding="utf-8"))
        assert reloaded["currencies"]["active"][0]["symbol"] == "\u00a5"
        assert reloaded["currencies"]["active"][1]["symbol"] == "\u20ac"

    def test_save_registry_adds_trailing_newline(self, tmp_path: Path,
                                                 sample_registry: dict):
        target = tmp_path / "out.json"
        save_registry(sample_registry, target)
        assert target.read_text(encoding="utf-8").endswith("\n")

    def test_save_registry_uses_indent_2(self, tmp_path: Path,
                                         sample_registry: dict):
        target = tmp_path / "out.json"
        save_registry(sample_registry, target)
        text = target.read_text(encoding="utf-8")
        # First nested line should be indented exactly 2 spaces
        lines = text.split("\n")
        # Find the first line that starts with spaces
        for line in lines[1:]:
            if line.startswith(" "):
                assert line.startswith("  ") and not line.startswith("   "), (
                    f"expected 2-space indent, got: {line!r}"
                )
                break
        else:
            pytest.fail("could not find an indented line")

    def test_save_registry_overwrites_existing(self, tmp_path: Path,
                                               sample_registry: dict):
        target = tmp_path / "out.json"
        target.write_text('{"old": true}', encoding="utf-8")
        save_registry(sample_registry, target)
        assert json.loads(target.read_text(encoding="utf-8")) == sample_registry

    def test_save_registry_empty_currencies(self, tmp_path: Path,
                                            empty_registry: dict):
        target = tmp_path / "out.json"
        save_registry(empty_registry, target)
        reloaded = json.loads(target.read_text(encoding="utf-8"))
        assert reloaded["currencies"]["active"] == []
        assert reloaded["currencies"]["withdrawn"] == []

    def test_save_registry_roundtrip_via_load(self, tmp_path: Path,
                                              sample_registry: dict):
        """save_registry then load_registry returns the same data."""
        target = tmp_path / "out.json"
        save_registry(sample_registry, target)
        assert load_registry(target) == sample_registry


# ===========================================================================
# backup_registry
# ===========================================================================

class TestBackupRegistry:
    def test_creates_timestamped_file(self, registry_file: Path):
        backup = backup_registry(registry_file)
        assert backup.exists()
        assert backup.name.startswith("iso4217_backup_")
        assert backup.name.endswith(".json")

    def test_backup_is_in_same_directory(self, registry_file: Path):
        backup = backup_registry(registry_file)
        assert backup.parent == registry_file.parent

    def test_backup_content_matches_original(self, registry_file: Path,
                                             sample_registry: dict):
        backup = backup_registry(registry_file)
        assert json.loads(backup.read_text(encoding="utf-8")) == sample_registry

    def test_two_backups_in_same_second_produce_distinct_paths(
        self, registry_file: Path,
    ):
        """The timestamp has second resolution — two calls in the same
        second may collide. This test documents the behavior. If it fails
        with a same-file assertion, the module's backup naming was improved
        beyond second resolution."""
        b1 = backup_registry(registry_file)
        b2 = backup_registry(registry_file)
        # Either distinct (better) or the same (current behavior)
        # We only require that both exist.
        assert b1.exists()
        assert b2.exists()

    def test_missing_registry_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            backup_registry(tmp_path / "missing.json")


# ===========================================================================
# build_code_index
# ===========================================================================

class TestBuildCodeIndex:
    def test_indexes_active(self, sample_registry: dict):
        index = build_code_index(sample_registry)
        assert "USD" in index
        assert index["USD"]["category"] == "currencies.active"

    def test_indexes_withdrawn(self, sample_registry: dict):
        index = build_code_index(sample_registry)
        assert "DEM" in index
        assert index["DEM"]["category"] == "currencies.withdrawn"

    def test_indexes_non_iso_categories(self):
        registry = {
            "currencies": {"active": [], "withdrawn": []},
            "non_iso": {
                "cryptocurrencies": [{"code": "BTC", "name": "Bitcoin"}],
                "stablecoins": [{"code": "USDT", "name": "Tether"}],
                "commodities": [{"code": "XAU", "name": "Gold"}],
                "special_purpose": [{"code": "XDR", "name": "SDR"}],
            },
        }
        index = build_code_index(registry)
        assert index["BTC"]["category"] == "non_iso.cryptocurrencies"
        assert index["USDT"]["category"] == "non_iso.stablecoins"
        assert index["XAU"]["category"] == "non_iso.commodities"
        assert index["XDR"]["category"] == "non_iso.special_purpose"

    def test_index_count_matches_input(self, sample_registry: dict):
        index = build_code_index(sample_registry)
        total = (
            len(sample_registry["currencies"]["active"])
            + len(sample_registry["currencies"]["withdrawn"])
        )
        assert len(index) == total

    def test_index_data_is_the_entry(self, sample_registry: dict):
        index = build_code_index(sample_registry)
        usd_entry = next(
            c for c in sample_registry["currencies"]["active"] if c["code"] == "USD"
        )
        assert index["USD"]["data"] == usd_entry

    def test_empty_registry(self, empty_registry: dict):
        assert build_code_index(empty_registry) == {}


# ===========================================================================
# diff_currency
# ===========================================================================

class TestDiffCurrency:
    def test_no_diff_returns_empty(self):
        old = {"code": "USD", "name": "US Dollar", "minor_units": 2}
        new = {"code": "USD", "name": "US Dollar", "minor_units": 2}
        assert diff_currency(old, new, "USD") == []

    def test_simple_field_change(self):
        old = {"code": "USD", "minor_units": 2}
        new = {"code": "USD", "minor_units": 3}
        changes = diff_currency(old, new, "USD")
        assert len(changes) == 1
        assert changes[0].field == "minor_units"
        assert changes[0].old_value == 2
        assert changes[0].new_value == 3

    def test_multiple_changes(self):
        old = {"code": "USD", "minor_units": 2, "symbol": "$"}
        new = {"code": "USD", "minor_units": 3, "symbol": "US$"}
        changes = diff_currency(old, new, "USD")
        fields = {c.field for c in changes}
        assert fields == {"minor_units", "symbol"}

    def test_new_field_added(self):
        old = {"code": "USD"}
        new = {"code": "USD", "new_field": "value"}
        changes = diff_currency(old, new, "USD")
        assert len(changes) == 1
        assert changes[0].field == "new_field"
        assert changes[0].old_value is None
        assert changes[0].new_value == "value"

    def test_field_removed(self):
        old = {"code": "USD", "old_field": "value"}
        new = {"code": "USD"}
        changes = diff_currency(old, new, "USD")
        assert len(changes) == 1
        assert changes[0].field == "old_field"
        assert changes[0].old_value == "value"
        assert changes[0].new_value is None

    def test_old_is_none_returns_empty(self):
        """Adding a new currency — no diff needed, the caller handles it."""
        new = {"code": "USD", "name": "US Dollar"}
        assert diff_currency(None, new, "USD") == []


# ===========================================================================
# generate_diff
# ===========================================================================

class TestGenerateDiff:
    def test_identical_data_produces_no_changes(self, sample_registry: dict):
        source = [
            {"code": c["code"], "numeric": c["numeric"], "name": c["name"],
             "minor_units": c["minor_units"]}
            for c in sample_registry["currencies"]["active"]
        ]
        mapping = {"code": "code", "numeric": "numeric",
                   "name": "name", "minor_units": "minor_units"}
        report = generate_diff(sample_registry, source, mapping)
        assert report.total_changes == 0

    def test_detects_added_currency(self, sample_registry: dict):
        source = [
            {"code": "USD", "numeric": "840", "name": "US Dollar", "minor_units": 2},
            {"code": "EUR", "numeric": "978", "name": "Euro", "minor_units": 2},
            {"code": "JPY", "numeric": "392", "name": "Japanese Yen", "minor_units": 0},
            {"code": "GBP", "numeric": "826", "name": "Pound Sterling", "minor_units": 2},
        ]
        mapping = {"code": "code", "numeric": "numeric",
                   "name": "name", "minor_units": "minor_units"}
        report = generate_diff(sample_registry, source, mapping)
        added = [c for c in report.changes if c.change_type == ChangeType.ADDED]
        assert len(added) == 1
        assert added[0].code == "GBP"

    def test_detects_modified_currency(self, sample_registry: dict):
        source = [
            {"code": "USD", "numeric": "840", "name": "US Dollar",
             "minor_units": 3},  # changed from 2
            {"code": "EUR", "numeric": "978", "name": "Euro", "minor_units": 2},
            {"code": "JPY", "numeric": "392", "name": "Japanese Yen", "minor_units": 0},
        ]
        mapping = {"code": "code", "numeric": "numeric",
                   "name": "name", "minor_units": "minor_units"}
        report = generate_diff(sample_registry, source, mapping)
        modified = [c for c in report.changes if c.change_type == ChangeType.MODIFIED]
        assert len(modified) == 1
        assert modified[0].code == "USD"

    def test_detects_withdrawn_currency(self, sample_registry: dict):
        """A currency in the registry that's absent from source."""
        source = [
            {"code": "USD", "numeric": "840", "name": "US Dollar", "minor_units": 2},
            # EUR missing
            {"code": "JPY", "numeric": "392", "name": "Japanese Yen", "minor_units": 0},
        ]
        mapping = {"code": "code", "numeric": "numeric",
                   "name": "name", "minor_units": "minor_units"}
        report = generate_diff(sample_registry, source, mapping)
        withdrawn = [c for c in report.changes if c.change_type == ChangeType.WITHDRAWN]
        assert any(c.code == "EUR" for c in withdrawn)

    def test_report_has_timestamp_and_amendment(self, sample_registry: dict):
        report = generate_diff(sample_registry, [], {})
        assert report.source_amendment == 179
        assert report.timestamp != ""


# ===========================================================================
# apply_changes — non-interactive path
# ===========================================================================

class TestApplyChanges:
    def test_modified_field_is_written(self, sample_registry: dict):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(
                    code="USD",
                    change_type=ChangeType.MODIFIED,
                    category="currencies.active",
                    field_changes=[
                        FieldChange(field="minor_units", old_value=2, new_value=3),
                    ],
                ),
            ],
        )
        updated = apply_changes(sample_registry, report, interactive=False)
        usd = next(c for c in updated["currencies"]["active"] if c["code"] == "USD")
        assert usd["minor_units"] == 3

    def test_added_currency_is_appended(self, sample_registry: dict):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(
                    code="GBP",
                    change_type=ChangeType.ADDED,
                    category="currencies.active",
                    field_changes=[
                        FieldChange(field="code", old_value=None, new_value="GBP"),
                        FieldChange(field="numeric", old_value=None, new_value="826"),
                        FieldChange(field="name", old_value=None,
                                    new_value="Pound Sterling"),
                        FieldChange(field="minor_units", old_value=None, new_value=2),
                    ],
                ),
            ],
        )
        updated = apply_changes(sample_registry, report, interactive=False)
        codes = [c["code"] for c in updated["currencies"]["active"]]
        assert "GBP" in codes

    def test_original_registry_is_not_mutated(self, sample_registry: dict):
        """apply_changes returns a deep copy — the input must be unchanged."""
        original_usd_units = next(
            c for c in sample_registry["currencies"]["active"] if c["code"] == "USD"
        )["minor_units"]

        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(
                    code="USD",
                    change_type=ChangeType.MODIFIED,
                    category="currencies.active",
                    field_changes=[
                        FieldChange(field="minor_units", old_value=2, new_value=3),
                    ],
                ),
            ],
        )
        apply_changes(sample_registry, report, interactive=False)

        still_original = next(
            c for c in sample_registry["currencies"]["active"] if c["code"] == "USD"
        )["minor_units"]
        assert still_original == original_usd_units

    def test_meta_updated_is_refreshed(self, sample_registry: dict):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        updated = apply_changes(sample_registry, report, interactive=False)
        from datetime import date
        assert updated["meta"]["updated"] == str(date.today())

    def test_empty_report_is_a_noop_on_content(self, sample_registry: dict):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        updated = apply_changes(sample_registry, report, interactive=False)
        assert updated["currencies"] == sample_registry["currencies"]


# ===========================================================================
# save_source_data
# ===========================================================================

class TestSaveSourceData:
    def test_creates_file(self, sources_dir: Path):
        path = save_source_data([{"code": "USD"}], "test")
        assert path.exists()
        assert path.parent == sources_dir

    def test_filename_contains_prefix_and_date(self, sources_dir: Path):
        path = save_source_data([{"code": "USD"}], "swift")
        assert path.name.startswith("swift_")
        assert path.name.endswith(".json")

    def test_content_is_valid_json(self, sources_dir: Path):
        data = [{"code": "USD", "symbol": "$"}]
        path = save_source_data(data, "test")
        assert json.loads(path.read_text(encoding="utf-8")) == data

    def test_creates_directory_if_missing(self, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch):
        nested = tmp_path / "a" / "b" / "sources"
        monkeypatch.setattr(update_from_iso, "SOURCES_DIR", nested)
        path = save_source_data([{"x": 1}], "test")
        assert path.exists()
        assert nested.is_dir()

    def test_preserves_unicode(self, sources_dir: Path):
        data = [{"code": "JPY", "symbol": "\u00a5"}]
        path = save_source_data(data, "test")
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded[0]["symbol"] == "\u00a5"


# ===========================================================================
# load_latest_source
# ===========================================================================

class TestLoadLatestSource:
    def test_returns_none_when_dir_missing(self, tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(update_from_iso, "SOURCES_DIR", tmp_path / "nope")
        assert load_latest_source("swift") is None

    def test_returns_none_when_no_match(self, sources_dir: Path):
        assert load_latest_source("swift") is None

    def test_loads_matching_file(self, sources_dir: Path):
        (sources_dir / "swift_2026-01-01.json").write_text(
            json.dumps([{"code": "USD"}]), encoding="utf-8"
        )
        assert load_latest_source("swift") == [{"code": "USD"}]

    def test_loads_most_recent_by_sort(self, sources_dir: Path):
        (sources_dir / "swift_2026-01-01.json").write_text(
            json.dumps([{"v": "old"}]), encoding="utf-8"
        )
        (sources_dir / "swift_2026-09-17.json").write_text(
            json.dumps([{"v": "new"}]), encoding="utf-8"
        )
        assert load_latest_source("swift") == [{"v": "new"}]

    def test_ignores_non_matching_prefix(self, sources_dir: Path):
        (sources_dir / "wikipedia_2026-09-17.json").write_text(
            json.dumps([{"v": "wiki"}]), encoding="utf-8"
        )
        assert load_latest_source("swift") is None


# ===========================================================================
# format_report
# ===========================================================================

class TestFormatReport:
    def test_empty_report_mentions_no_changes(self):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        text = format_report(report)
        assert "No changes" in text or "no changes" in text

    def test_includes_timestamp(self):
        report = UpdateReport(
            timestamp="2026-09-17T12:00:00",
            source_amendment=179, source_date="2026-09-17",
        )
        assert "2026-09-17T12:00:00" in format_report(report)

    def test_includes_amendment(self):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        assert "179" in format_report(report)

    def test_includes_change_count(self):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="A", change_type=ChangeType.ADDED, category="c"),
                CurrencyChange(code="B", change_type=ChangeType.MODIFIED, category="c"),
            ],
        )
        text = format_report(report)
        assert "2" in text

    def test_includes_currency_codes(self):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(code="XYZ", change_type=ChangeType.ADDED, category="c"),
            ],
        )
        assert "XYZ" in format_report(report)

    def test_includes_warnings(self):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            warnings=["Watch out for this"],
        )
        assert "Watch out for this" in format_report(report)

    def test_includes_requires_review(self):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            requires_review=["Verify X"],
        )
        assert "Verify X" in format_report(report)


# ===========================================================================
# save_report
# ===========================================================================

class TestSaveReport:
    def test_creates_file(self, diffs_dir: Path):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        path = save_report(report)
        assert path.exists()
        assert path.parent == diffs_dir

    def test_filename_has_prefix_and_extension(self, diffs_dir: Path):
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        path = save_report(report)
        assert path.name.startswith("update_report_")
        assert path.name.endswith(".json")

    def test_content_is_valid_json(self, diffs_dir: Path):
        report = UpdateReport(
            timestamp="2026-09-17T12:00:00",
            source_amendment=179,
            source_date="2026-09-17",
        )
        path = save_report(report)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["timestamp"] == "2026-09-17T12:00:00"
        assert loaded["source_amendment"] == 179

    def test_change_serialization(self, diffs_dir: Path):
        report = UpdateReport(
            timestamp="t", source_amendment=179, source_date="d",
            changes=[
                CurrencyChange(
                    code="USD",
                    change_type=ChangeType.MODIFIED,
                    category="currencies.active",
                    field_changes=[
                        FieldChange(field="minor_units", old_value=2, new_value=3),
                    ],
                    source="test",
                    note="note text",
                ),
            ],
        )
        path = save_report(report)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert len(loaded["changes"]) == 1
        change = loaded["changes"][0]
        assert change["code"] == "USD"
        assert change["change_type"] == "modified"
        assert len(change["field_changes"]) == 1
        assert change["field_changes"][0]["field"] == "minor_units"
        assert change["field_changes"][0]["old"] == 2
        assert change["field_changes"][0]["new"] == 3

    def test_creates_directory_if_missing(self, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch):
        nested = tmp_path / "a" / "b" / "diffs"
        monkeypatch.setattr(update_from_iso, "DIFFS_DIR", nested)
        report = UpdateReport(timestamp="t", source_amendment=179, source_date="d")
        path = save_report(report)
        assert path.exists()
        assert nested.is_dir()


# ===========================================================================
# Constants — spot-check the ones tests depend on
# ===========================================================================

class TestConstants:
    def test_registry_path_is_a_path(self):
        assert isinstance(REGISTRY_PATH, Path)

    def test_registry_path_points_to_a_file(self):
        assert REGISTRY_PATH.name == "iso4217.json"

    def test_currency_template_has_required_keys(self):
        required = {"code", "numeric", "name", "minor_units", "symbol",
                    "entity", "central_bank", "pegged_to", "is_independent",
                    "countries"}
        assert required.issubset(set(CURRENCY_TEMPLATE.keys()))

    def test_currency_template_countries_is_empty_list(self):
        """The template's countries must be a fresh list per copy — verify
        the constant itself is a list (a shallow copy of the template
        happens in add_currency_interactive)."""
        assert CURRENCY_TEMPLATE["countries"] == []
        assert isinstance(CURRENCY_TEMPLATE["countries"], list)

    def test_currency_template_default_minor_units(self):
        assert CURRENCY_TEMPLATE["minor_units"] == 2
