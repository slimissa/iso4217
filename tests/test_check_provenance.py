"""
Tests for tools/check_provenance.py (v1.8.3, F22).

The check compares the field names of iso4217.json with the per-field table in docs/PROVENANCE.md.
Each test builds a small repository in tmp_path, so every finding is produced on purpose.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_provenance as cp  # noqa: E402

TOOL = PROJECT_ROOT / "tools" / "check_provenance.py"

REGISTRY = {
    "meta": {"version": "1.0.0", "updated": "2026-01-01"},
    "source": {"standard": "ISO 4217:2015"},
    "currencies": {
        "active": [{"code": "EUR", "name": "Euro", "countries": [{"code": "DE", "name": "Germany", "relationship": "issuing"}]}],
        "withdrawn": [{"code": "DEM", "name": "Mark", "withdrawn_date": "2002-01-01",
                       "code_lifetime": {"from": None, "to": "2002-01-01"}}],
    },
    "non_iso": {"cryptocurrencies": [{"code": "BTC", "name": "Bitcoin", "market_cap_rank": 1}], "stablecoins": []},
}

FIELDS = ["code", "code_lifetime", "countries", "market_cap_rank", "name", "relationship",
          "standard", "updated", "version", "withdrawn_date"]


def _row(field: str, where="meta", source="a source", trigger="every release", checked="`schema.json` (type only)") -> str:
    return f"| `{field}` | {where} | {source} | {trigger} | {checked} |"


HEADER = "| Field | Where | Source | Refresh trigger | Checked by |\n|---|---|---|---|---|\n"


def _doc(rows: list[str], before: str = "# Provenance\n\n## 1. Sources\n\nprose\n\n", after: str = "") -> str:
    return before + "## 9. Per-field provenance\n\n" + HEADER + "\n".join(rows) + "\n" + after


def _repo(tmp_path: Path, doc: str, registry: dict | None = None) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "iso4217.json").write_text(json.dumps(registry or REGISTRY), encoding="utf-8")
    (tmp_path / "docs" / "PROVENANCE.md").write_text(doc, encoding="utf-8")
    return tmp_path


def _run(root: Path, *args: str):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), *args], capture_output=True, text=True, timeout=60)


def _full_rows() -> list[str]:
    return [_row(f) for f in FIELDS]


# -- which names count as fields ------------------------------------------------------------------

def test_fields_come_from_all_six_kinds_of_object():
    found = cp.data_fields(REGISTRY)
    assert set(found) == set(FIELDS)
    assert found["relationship"] == {"countries[]"}
    assert found["market_cap_rank"] == {"non_iso"}
    assert found["withdrawn_date"] == {"withdrawn"}
    assert found["standard"] == {"source"}
    assert found["code"] == {"active", "withdrawn", "countries[]", "non_iso"}


def test_root_keys_and_code_lifetime_children_are_structure_not_fields():
    found = cp.data_fields(REGISTRY)
    for structural in ("currencies", "meta", "non_iso", "source", "from", "to"):
        assert structural not in found


# -- the happy path and each finding ----------------------------------------------------------------

def test_a_complete_table_passes(tmp_path):
    r = _run(_repo(tmp_path, _doc(_full_rows())))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "10 fields" in r.stdout


def test_an_unnamed_field_is_a_finding_and_is_named(tmp_path):
    rows = [row for row in _full_rows() if "`withdrawn_date`" not in row]
    r = _run(_repo(tmp_path, _doc(rows)))
    assert r.returncode == 1
    assert "field `withdrawn_date` (withdrawn) has no row" in r.stdout


def test_a_field_named_only_in_prose_does_not_count(tmp_path):
    rows = [row for row in _full_rows() if "`relationship`" not in row]
    doc = _doc(rows, before="# Provenance\n\nThe `relationship` field comes from ISO 3166.\n\n")
    r = _run(_repo(tmp_path, doc))
    assert r.returncode == 1 and "field `relationship`" in r.stdout


def test_a_row_for_a_field_that_does_not_exist_is_a_finding(tmp_path):
    r = _run(_repo(tmp_path, _doc(_full_rows() + [_row("ghost")])))
    assert r.returncode == 1 and "row for `ghost`" in r.stdout


def test_two_rows_for_one_field_are_a_finding(tmp_path):
    r = _run(_repo(tmp_path, _doc(_full_rows() + [_row("code")])))
    assert r.returncode == 1 and "2 rows for `code`" in r.stdout


@pytest.mark.parametrize("column,cell", [("source", ""), ("trigger", "TODO"), ("checked", "TBD")])
def test_an_empty_or_placeholder_cell_is_a_finding(tmp_path, column, cell):
    rows = _full_rows()[1:] + [_row("code", **{column: cell})]
    r = _run(_repo(tmp_path, _doc(rows)))
    assert r.returncode == 1 and "cell is empty" in r.stdout


def test_checked_by_must_name_a_file_or_say_none(tmp_path):
    rows = _full_rows()[1:] + [_row("code", checked="the validator")]
    r = _run(_repo(tmp_path, _doc(rows)))
    assert r.returncode == 1 and "names no file" in r.stdout


def test_checked_by_none_is_allowed_because_unchecked_is_a_true_answer(tmp_path):
    rows = _full_rows()[1:] + [_row("code", checked="`none`")]
    assert _run(_repo(tmp_path, _doc(rows))).returncode == 0


def test_checked_by_cannot_name_a_file_that_does_not_exist(tmp_path):
    rows = _full_rows()[1:] + [_row("code", checked="`tools/deleted_check.py` (format)")]
    r = _run(_repo(tmp_path, _doc(rows)))
    assert r.returncode == 1 and "tools/deleted_check.py, which does not exist" in r.stdout


def test_a_flag_after_the_path_is_ignored_when_resolving_it(tmp_path):
    rows = _full_rows()[1:] + [_row("code", checked="`schema.json --strict` (format)")]
    assert _run(_repo(tmp_path, _doc(rows))).returncode == 0


# -- fatal cases ------------------------------------------------------------------------------------

def test_a_document_without_the_section_is_fatal(tmp_path):
    r = _run(_repo(tmp_path, "# Provenance\n\nno table here\n"))
    assert r.returncode == 2 and "no 'Per-field provenance' section" in r.stderr


def test_a_section_without_a_table_is_fatal(tmp_path):
    r = _run(_repo(tmp_path, "## 9. Per-field provenance\n\njust prose\n"))
    assert r.returncode == 2 and "no table" in r.stderr


def test_a_wrong_header_is_fatal(tmp_path):
    doc = "## 9. Per-field provenance\n\n| Field | Source |\n|---|---|\n| `code` | x |\n"
    assert _run(_repo(tmp_path, doc)).returncode == 2


def test_a_missing_registry_is_fatal(tmp_path):
    root = _repo(tmp_path, _doc(_full_rows()))
    (root / "iso4217.json").unlink()
    assert _run(root).returncode == 2


def test_invalid_json_is_fatal(tmp_path):
    root = _repo(tmp_path, _doc(_full_rows()))
    (root / "iso4217.json").write_text("{ nope", encoding="utf-8")
    assert _run(root).returncode == 2


def test_json_output_lists_the_findings(tmp_path):
    rows = [row for row in _full_rows() if "`version`" not in row]
    out = json.loads(_run(_repo(tmp_path, _doc(rows)), "--json").stdout)
    assert out["fields"] == 10 and any("`version`" in f for f in out["findings"])


# -- the real tree ------------------------------------------------------------------------------------

def test_the_real_registry_is_fully_accounted_for():
    registry = json.loads((PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8"))
    doc = (PROJECT_ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
    assert cp.findings(registry, doc, PROJECT_ROOT) == []


def test_the_real_registry_has_the_forty_six_fields_the_audit_counted():
    registry = json.loads((PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8"))
    assert len(cp.data_fields(registry)) >= 46
