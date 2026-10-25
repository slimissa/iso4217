"""
Gate mutation tests (v1.9.1, audit finding P5-02; RELEASE_PATTERN.md hygiene rule 10).

A check that cannot fail is not a check. The fifth-pass audit forced each of
these gate tools to exit 0 and the whole suite stayed green: nothing proved the
gate could go red. This module is that proof. Every case here builds a copy of
the project, breaks exactly one thing in the copy, runs the real tool as a
subprocess, and asserts the exit code the tool exists to produce.

Rules of the module:

* It runs inside `pytest tests/`, so a gate tool that cannot fail fails the
  suite, in CI and in the release gate alike.
* Every case has a twin that runs the same tool on the unbroken copy and
  asserts exit 0. A fixture that was already broken proves nothing.
* The expected code is the one the tool itself documents. Exit 2 is "a local
  input is missing or unreadable" and exit 3 is "an artifact the tool compares
  against is missing" (only tools that declare it); the audit brief's
  "exit 3 for any missing file" is not the convention in RELEASE_PATTERN.md.
* `test_every_gate_tool_is_covered_or_exempt_with_a_reason` parses release.sh
  and fails when a tool joins the gate without a case here or a written
  exemption, so rule 10 is enforced by this file, not by memory.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"

# The copy of the project every case breaks. It must never include a virtualenv, a build tree or anything else a
# developer keeps inside the repository: the first version of this fixture copied `.venv` once per test and filled a disk.
# Source of truth is git itself: tracked files plus untracked files that are not ignored. The fallback (no git, or not a
# work tree) is a name list, and both paths refuse to continue if the copy is implausibly large.
_FALLBACK_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "env", ".tox", ".nox", ".mypy_cache", ".ruff_cache", ".pytest_cache", "node_modules",
    "target", "__pycache__", "dist", "build", "*.egg-info", ".eggs", "site-packages",
)
MAX_COPY_BYTES = 150 * 1024 * 1024


def _project_files() -> list[Path] | None:
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return [PROJECT_ROOT / name for name in done.stdout.decode("utf-8").split("\0") if name]


def _tree_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


@pytest.fixture(scope="module")
def pristine(tmp_path_factory) -> Path:
    """One copy of the project per module; each case copies it again and breaks the copy."""
    dest = tmp_path_factory.mktemp("pristine") / "p"
    files = _project_files()
    if files is None:
        shutil.copytree(PROJECT_ROOT, dest, ignore=_FALLBACK_IGNORE)
    else:
        total = 0
        for source in files:
            if not source.is_file() or source.is_symlink():
                continue
            total += source.stat().st_size
            if total > MAX_COPY_BYTES:
                pytest.fail(
                    f"the project files git reports exceed {MAX_COPY_BYTES // 1024 // 1024} MB; "
                    "something large is tracked or not ignored (a virtualenv? a build tree?)"
                )
            target = dest / source.relative_to(PROJECT_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    size = _tree_size(dest)
    assert size <= MAX_COPY_BYTES, f"the project copy is {size // 1024 // 1024} MB; refusing to copy it once per test"
    return dest


@pytest.fixture
def tree(pristine, tmp_path) -> Path:
    """A private copy of the pristine tree, removed after the case so a run never holds more than one."""
    dest = tmp_path / "t"
    shutil.copytree(pristine, dest)
    yield dest
    shutil.rmtree(dest, ignore_errors=True)


def run(tree: Path, tool: str, *args: str) -> tuple[int, str]:
    """Run tools/<tool> from the copied tree, exactly as the gate does."""
    path = tree / "tools" / tool
    cmd = ["bash", str(path)] if tool.endswith(".sh") else [sys.executable, str(path)]
    done = subprocess.run(cmd + list(args), cwd=tree, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def edit_registry(tree: Path, mutate) -> None:
    path = tree / "iso4217.json"
    data = load(path)
    mutate(data)
    save(path, data)


# ---------------------------------------------------------------------------
# The unbroken copy is green for every tool exercised below.
# ---------------------------------------------------------------------------

GREEN = [
    ("check_country_codes.py", ()),
    ("check_version_consistency.py", ()),
    ("sync_wrappers.py", ("--check",)),
    ("enrich_field.py", ("--field", "classification", "--check")),
    ("enrich_field.py", ("--field", "code_lifetime", "--check")),
    ("enrich_field.py", ("--field", "numeric_reused", "--check")),
    ("enrich_field.py", ("--field", "source_url", "--check")),
    ("check_snapshot_freshness.py", ()),
    ("check_registry_freshness.py", ("--today", "2026-10-23")),
    ("export_sql.py", ("--check",)),
    ("export_csv.py", ("--check",)),
    ("export_parquet.py", ("--check",)),
    ("export_countries_parquet.py", ("--check",)),
    ("export_aggregated.py", ("--check",)),
    ("validate.py", ()),
    ("check_mojibake.py", ()),
]


@pytest.mark.parametrize("tool,args", GREEN, ids=[f"{t} {' '.join(a)}".strip() for t, a in GREEN])
def test_the_unbroken_copy_is_green(tree, tool, args):
    code, out = run(tree, tool, *args)
    assert code == 0, out[-800:]


# ---------------------------------------------------------------------------
# check_country_codes.py: 0 ok, 1 unknown code, 2 fatal
# ---------------------------------------------------------------------------


class TestCheckCountryCodes:
    def test_a_country_code_missing_from_the_snapshot_exits_1(self, tree):
        def mutate(d):
            d["currencies"]["active"][0]["countries"][0]["code"] = "ZZ"

        edit_registry(tree, mutate)
        code, out = run(tree, "check_country_codes.py")
        assert code == 1 and "ZZ" in out

    def test_a_missing_snapshot_exits_2(self, tree):
        (tree / "tools" / "iso3166_snapshot.json").unlink()
        code, _ = run(tree, "check_country_codes.py")
        assert code == 2


# ---------------------------------------------------------------------------
# check_version_consistency.py: 0 ok, 1 mismatch, 2 fatal
# ---------------------------------------------------------------------------


class TestCheckVersionConsistency:
    def test_a_version_file_that_disagrees_exits_1(self, tree):
        (tree / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        code, out = run(tree, "check_version_consistency.py")
        assert code == 1 and "9.9.9" in out

    def test_a_missing_version_file_exits_2(self, tree):
        (tree / "VERSION").unlink()
        code, _ = run(tree, "check_version_consistency.py")
        assert code == 2


# ---------------------------------------------------------------------------
# sync_wrappers.py --check: 0 ok, 1 mismatch, 2 fatal, 3 a copy is missing
# ---------------------------------------------------------------------------


class TestSyncWrappersCheck:
    def test_a_copy_that_differs_exits_1(self, tree):
        copy = tree / "wrappers" / "go" / "iso4217.json"
        copy.write_text(copy.read_text(encoding="utf-8") + " ", encoding="utf-8")
        code, out = run(tree, "sync_wrappers.py", "--check")
        assert code == 1 and "wrappers/go/iso4217.json" in out

    def test_a_missing_copy_exits_3(self, tree):
        (tree / "wrappers" / "rust" / "iso4217.json").unlink()
        code, out = run(tree, "sync_wrappers.py", "--check")
        assert code == 3 and "wrappers/rust/iso4217.json" in out

    def test_a_missing_root_registry_exits_2(self, tree):
        (tree / "iso4217.json").unlink()
        code, _ = run(tree, "sync_wrappers.py", "--check")
        assert code == 2


# ---------------------------------------------------------------------------
# enrich_field.py --check: 0 ok, 1 changes pending, 2 fatal
# ---------------------------------------------------------------------------


class TestEnrichFieldCheck:
    @pytest.mark.parametrize("field", ["classification", "code_lifetime", "numeric_reused", "source_url"])
    def test_a_missing_field_exits_1(self, tree, field):
        def mutate(d):
            entries = d["currencies"]["active"] + d["currencies"]["withdrawn"]
            entry = next((e for e in entries if field in e), None)
            assert entry is not None, f"no entry carries {field}; the fixture cannot break it"
            del entry[field]

        edit_registry(tree, mutate)
        code, out = run(tree, "enrich_field.py", "--field", field, "--check")
        assert code == 1, out[-800:]

    def test_a_missing_registry_exits_2(self, tree):
        (tree / "iso4217.json").unlink()
        code, _ = run(tree, "enrich_field.py", "--field", "classification", "--check")
        assert code == 2


# ---------------------------------------------------------------------------
# check_snapshot_freshness.py: 0 ok, 1 stale, 2 fatal
# ---------------------------------------------------------------------------


class TestCheckSnapshotFreshness:
    def test_a_review_by_date_in_the_past_exits_1(self, tree):
        meta = tree / "tools" / "iso3166_snapshot.meta.json"
        data = load(meta)
        data["meta"]["review_by"] = "2020-01-01"
        save(meta, data)
        code, out = run(tree, "check_snapshot_freshness.py")
        assert code == 1 and "2020-01-01" in out

    def test_an_unparseable_review_by_exits_2(self, tree):
        meta = tree / "tools" / "iso3166_snapshot.meta.json"
        data = load(meta)
        data["meta"]["review_by"] = "not-a-date"
        save(meta, data)
        code, _ = run(tree, "check_snapshot_freshness.py")
        assert code == 2


# ---------------------------------------------------------------------------
# check_registry_freshness.py: 0 ok, 1 stale, 2 fatal. --today pins the clock.
# ---------------------------------------------------------------------------

TODAY = datetime.date(2026, 10, 23)


class TestCheckRegistryFreshness:
    @pytest.mark.parametrize("age,expected", [(181, 1), (180, 0)])
    def test_the_180_day_boundary(self, tree, age, expected):
        updated = (TODAY - datetime.timedelta(days=age)).isoformat()
        edit_registry(tree, lambda d: d["meta"].__setitem__("updated", updated))
        code, out = run(tree, "check_registry_freshness.py", "--today", TODAY.isoformat())
        assert code == expected, out[-600:]

    def test_an_unparseable_updated_exits_2(self, tree):
        edit_registry(tree, lambda d: d["meta"].__setitem__("updated", "yesterday"))
        code, _ = run(tree, "check_registry_freshness.py", "--today", TODAY.isoformat())
        assert code == 2


# ---------------------------------------------------------------------------
# The exporters' --check modes: 0 ok, 1 stale, 3 artifact missing
# ---------------------------------------------------------------------------


def _rename_first_active(d):
    d["currencies"]["active"][0]["name"] = d["currencies"]["active"][0]["name"] + " (stale)"


class TestExportSqlCheck:
    def test_a_stale_export_exits_1(self, tree):
        sql = tree / "iso4217.sql"
        sql.write_text(sql.read_text(encoding="utf-8") + "-- stale\n", encoding="utf-8")
        code, _ = run(tree, "export_sql.py", "--check")
        assert code == 1

    def test_a_missing_export_exits_3(self, tree):
        (tree / "iso4217.sql").unlink()
        code, _ = run(tree, "export_sql.py", "--check")
        assert code == 3


class TestExportCsvCheck:
    def test_a_stale_export_exits_1(self, tree):
        csv = tree / "iso4217.csv"
        csv.write_bytes(csv.read_bytes() + b"stale\n")
        code, _ = run(tree, "export_csv.py", "--check")
        assert code == 1

    def test_a_missing_export_exits_3(self, tree):
        (tree / "iso4217.csv").unlink()
        code, _ = run(tree, "export_csv.py", "--check")
        assert code == 3


class TestExportParquetCheck:
    def test_a_registry_that_moved_on_exits_1(self, tree):
        edit_registry(tree, _rename_first_active)
        code, _ = run(tree, "export_parquet.py", "--check")
        assert code == 1

    def test_a_missing_export_exits_3(self, tree):
        (tree / "iso4217.parquet").unlink()
        code, _ = run(tree, "export_parquet.py", "--check")
        assert code == 3


class TestExportCountriesParquetCheck:
    def test_a_registry_that_moved_on_exits_1(self, tree):
        def mutate(d):
            d["currencies"]["active"][0]["countries"][0]["name"] = "Stale Land"

        edit_registry(tree, mutate)
        code, _ = run(tree, "export_countries_parquet.py", "--check")
        assert code == 1

    def test_a_missing_export_exits_3(self, tree):
        (tree / "iso4217.countries.parquet").unlink()
        code, _ = run(tree, "export_countries_parquet.py", "--check")
        assert code == 3


class TestExportAggregatedCheck:
    def test_a_stale_aggregate_exits_1(self, tree):
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = tree / "currencies_by_region.parquet"
        table = pq.read_table(path)
        first = table.column_names[0]
        column = table.column(first).to_pylist()
        assert column, "the aggregate has no rows to corrupt"
        column[0] = "stale" if isinstance(column[0], str) else (column[0] or 0) + 1
        table = table.set_column(0, first, pa.array(column, type=table.schema.field(first).type))
        pq.write_table(table, path)
        code, _ = run(tree, "export_aggregated.py", "--check")
        assert code == 1

    def test_a_missing_aggregate_exits_3(self, tree):
        (tree / "currencies_by_region.parquet").unlink()
        code, _ = run(tree, "export_aggregated.py", "--check")
        assert code == 3


# ---------------------------------------------------------------------------
# validate.py and check_mojibake.py
# ---------------------------------------------------------------------------


class TestValidate:
    def test_a_registry_that_breaks_the_rules_exits_1(self, tree):
        def mutate(d):
            d["currencies"]["active"].append(dict(d["currencies"]["active"][0]))  # duplicate code

        edit_registry(tree, mutate)
        code, out = run(tree, "validate.py")
        assert code == 1 and "USD" in out


class TestCheckMojibake:
    def test_mojibake_in_a_tracked_text_file_exits_1(self, tree):
        readme = tree / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nit\u00e2\u20ac\u2122s broken\n", encoding="utf-8")
        code, _ = run(tree, "check_mojibake.py")
        assert code == 1


class TestCheckReleaseClaims:
    """The real manifest describes released versions and is allowed to disagree with a tree under development,
    so these cases write a small manifest of their own: one claim, for version 9.9.9."""

    @staticmethod
    def _setup(tree: Path) -> None:
        (tree / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        save(tree / "tools" / "release_claims.json", {"9.9.9": [{"file": "VERSION", "contains": "9.9.9"}], "doc-facts": []})

    def test_the_unbroken_copy_is_green(self, tree):
        self._setup(tree)
        code, out = run(tree, "check_release_claims.py", "9.9.9")
        assert code == 0, out[-600:]

    def test_a_claim_that_no_longer_holds_exits_1(self, tree):
        self._setup(tree)
        (tree / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        code, out = run(tree, "check_release_claims.py", "9.9.9")
        assert code == 1 and "VERSION" in out

    def test_a_version_with_no_manifest_entry_exits_2(self, tree):
        self._setup(tree)
        code, _ = run(tree, "check_release_claims.py", "0.0.0")
        assert code == 2

    def test_a_missing_manifest_exits_2(self, tree):
        self._setup(tree)
        (tree / "tools" / "release_claims.json").unlink()
        code, _ = run(tree, "check_release_claims.py", "9.9.9")
        assert code == 2


# ---------------------------------------------------------------------------
# Rule 10 enforces itself: every gate tool has a case above or a written exemption.
# ---------------------------------------------------------------------------

COVERED = {
    "check_country_codes.py",
    "check_version_consistency.py",
    "sync_wrappers.py",
    "enrich_field.py",
    "check_snapshot_freshness.py",
    "check_registry_freshness.py",
    "export_sql.py",
    "export_csv.py",
    "export_parquet.py",
    "export_countries_parquet.py",
    "export_aggregated.py",
    "validate.py",
    "check_mojibake.py",
    "check_release_claims.py",
}

# Each exemption names the evidence. Adding a tool here instead of a case needs
# a reason a reviewer can check; "it has tests" is not one unless a test fails
# when the tool is forced to exit 0 (the v1.9.1 mutation sweep is the method).
EXEMPT = {
    "check_readme_drift.py": "forcing exit 0 fails a test in tests/ (v1.9.1 sweep)",
    "check_provenance.py": "forcing exit 0 fails a test in tests/ (v1.9.1 sweep)",
    "check_verification_doc.py": "forcing exit 0 fails a test in tests/ (v1.9.1 sweep)",
    "vendor_iso3166.py": "needs the network for --check; forcing exit 0 fails a test in tests/ (v1.9.1 sweep)",
    "check_cross_language.sh": "needs four toolchains; tests/test_check_cross_language.py covers its exit codes",
}


def _gate_tools() -> set[str]:
    text = RELEASE_SH.read_text(encoding="utf-8")
    found = re.search(r"(?ms)^run_gate\(\)\s*\{\n(.*?)^\}", text)
    assert found, "release.sh has no run_gate() function"
    body = found.group(1)
    return set(re.findall(r"run_gate_step\s+\"[^\"]+\"\s+(?:python3|bash)\s+tools/([\w.]+)", body))


def test_every_gate_tool_is_covered_or_exempt_with_a_reason():
    gate = _gate_tools()
    assert len(gate) >= 15, f"parsed too few gate tools: {sorted(gate)}"
    missing = sorted(gate - COVERED - set(EXEMPT))
    assert not missing, (
        f"gate tools with no failing-state case and no written exemption: {missing}. "
        "Add a case to tests/test_gate_mutations.py (RELEASE_PATTERN.md hygiene rule 10)."
    )


def test_covered_and_exempt_name_only_real_gate_tools():
    gate = _gate_tools()
    stale = sorted((COVERED | set(EXEMPT)) - gate)
    assert not stale, f"entries that are no longer gate steps: {stale}"
    assert not (COVERED & set(EXEMPT)), "a tool is both covered and exempt"
