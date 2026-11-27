"""
Collection order across the four wrappers (v1.9.6, the third audit pass's open item 7, ADR 0015).

One fixture group, `collection_order` in tests/cross_language_consistency.json, holds the full ordered code list of every
collection accessor and of `pegged_to` for several anchors, for the shipped registry and for a synthetic registry with repeated
and overlapping codes. Each wrapper's own suite reads it (wrappers/javascript/collection_order.test.js,
wrappers/go/collection_order_test.go, the `collection_order_fixture` module in wrappers/rust/src/lib.rs) and compares its full
lists with the fixture, so the four outputs are identical. This file runs the Python wrapper and the JavaScript suite directly;
Go and Rust run under tools/check_cross_language.sh (the release gate) and the CI wrapper matrix.

The shipped lists are also recomputed here from the root iso4217.json, so a data change that is not carried into the fixture
fails with the expected group printed, not with four confusing wrapper failures.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "wrappers" / "python"))
import iso4217  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "cross_language_consistency.json"
CO = json.loads(FIXTURE.read_text(encoding="utf-8")).get("collection_order", {})
COLLECTIONS = ["all_active", "all_withdrawn", "all_non_iso", "all_currencies"]
CATEGORIES = ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]
# The audit's three anchors, at least (the v1.9.6 brief); more may be added, none removed.
REQUIRED_ANCHORS = {"USD", "EUR", "XAF"}


def _cases() -> list[tuple[str, dict]]:
    out = []
    if CO.get("shipped"):
        out.append(("shipped", CO["shipped"]))
    for case in CO.get("synthetic", []):
        out.append((case["id"], case))
    return out


CASES = _cases()


def _first_seen(codes: list[str]) -> list[str]:
    out: list[str] = []
    for c in codes:
        if c not in out:
            out.append(c)
    return out


def _expected_from_json(data: dict, anchors: list[str]) -> dict:
    """The reference order, from the JSON alone: no wrapper involved."""
    cur, ni = data.get("currencies", {}), data.get("non_iso", {})
    active = _first_seen([c["code"] for c in cur.get("active", [])])
    withdrawn = _first_seen([c["code"] for c in cur.get("withdrawn", [])])
    non_iso = _first_seen([c["code"] for cat in CATEGORIES for c in ni.get(cat, [])])
    last = {c["code"]: c for c in cur.get("active", [])}
    return {
        "collections": {"all_active": active, "all_withdrawn": withdrawn, "all_non_iso": non_iso,
                        "all_currencies": _first_seen(active + withdrawn + non_iso)},
        "pegged_to": {a: [c for c in active if last[c].get("peg_type") == "single"
                          and (last[c].get("pegged_to") or "").upper() == a] for a in anchors},
    }


def _registry(tmp_path: Path, case: dict) -> "iso4217.CurrencyRegistry":
    if case.get("registry") == "shipped":
        return iso4217.CurrencyRegistry(PROJECT_ROOT / "wrappers" / "python" / "iso4217.json")
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(case["registry"]), encoding="utf-8")
    return iso4217.CurrencyRegistry(p)


class TestTheFixture:
    def test_the_group_exists_with_shipped_and_synthetic_cases(self):
        assert CO, "tests/cross_language_consistency.json has no collection_order group"
        assert CO.get("shipped") and CO.get("synthetic")

    def test_every_case_lists_every_collection_and_the_shipped_case_the_required_anchors(self):
        for name, case in CASES:
            assert sorted(case["collections"]) == sorted(COLLECTIONS), name
            assert case["pegged_to"], name
        assert REQUIRED_ANCHORS <= set(CO["shipped"]["pegged_to"])

    def test_the_declared_count_is_the_real_count(self):
        assert CO["vector_count"] == sum(len(c["collections"]) + len(c["pegged_to"]) for _n, c in CASES)

    def test_the_shipped_lists_are_the_order_of_the_root_registry(self):
        data = json.loads((PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8"))
        shipped = CO["shipped"]
        want = _expected_from_json(data, list(shipped["pegged_to"]))
        assert {"collections": shipped["collections"], "pegged_to": shipped["pegged_to"]} == want, (
            "iso4217.json changed and the fixture did not. Replace collection_order.shipped's two keys with:\n"
            + json.dumps(want, indent=2))

    @pytest.mark.parametrize("name,case", [c for c in CASES if c[0] != "shipped"], ids=[c[0] for c in CASES if c[0] != "shipped"])
    def test_each_synthetic_case_is_the_order_of_its_own_registry(self, name, case):
        assert {"collections": case["collections"], "pegged_to": case["pegged_to"]} == \
            _expected_from_json(case["registry"], list(case["pegged_to"]))

    def test_the_synthetic_case_exercises_repeats_overlaps_and_the_category_order(self):
        case = CO["synthetic"][0]
        cols = case["collections"]
        assert len(cols["all_currencies"]) < sum(len(cols[c]) for c in COLLECTIONS[:3]), "no overlap across sections"
        assert list(case["registry"]["non_iso"])[0] != CATEGORIES[0], "the object's key order must differ from the walk order"


class TestPythonWrapper:
    @pytest.mark.parametrize("name,case", CASES, ids=[c[0] for c in CASES])
    def test_every_list_is_identical(self, tmp_path, name, case):
        registry = _registry(tmp_path, case)
        for method, codes in case["collections"].items():
            assert [c.code for c in getattr(registry, method)()] == codes, f"{name}: {method}"
        for anchor, codes in case["pegged_to"].items():
            assert [c.code for c in registry.pegged_to(anchor)] == codes, f"{name}: pegged_to({anchor})"

    def test_the_module_level_helpers_return_the_same_order(self):
        shipped = CO["shipped"]
        assert [c.code for c in iso4217.all_active()] == shipped["collections"]["all_active"]
        assert [c.code for c in iso4217.pegged_to("USD")] == shipped["pegged_to"]["USD"]


class TestJavaScriptWrapper:
    def test_the_suite_passes_and_checks_every_vector(self):
        node = shutil.which("node")
        assert node, "node is required: a contract that cannot run is not a contract (hygiene rule 7)"
        done = subprocess.run([node, "collection_order.test.js"], cwd=PROJECT_ROOT / "wrappers" / "javascript",
                              capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stdout[-2500:] + done.stderr[-1500:]
        assert f'COLLECTION_ORDER javascript vectors={CO["vector_count"]}' in done.stdout


class TestEveryRunnerExecutesTheGroup:
    """Go and Rust are executed by check_cross_language.sh and CI. Here each suite must exist, read the group and declare the
    count; and check_cross_language.sh must run the four of them."""

    def test_go_suite_reads_the_group(self):
        text = (PROJECT_ROOT / "wrappers" / "go" / "collection_order_test.go").read_text(encoding="utf-8")
        assert '"collection_order"' in text and "COLLECTION_ORDER go vectors=" in text and "loadRegistryFrom" in text

    def test_rust_suite_reads_the_group(self):
        text = (PROJECT_ROOT / "wrappers" / "rust" / "src" / "lib.rs").read_text(encoding="utf-8")
        assert "mod collection_order_fixture" in text and "COLLECTION_ORDER rust vectors=" in text

    def test_the_cross_language_script_runs_every_suite_that_reads_the_group(self):
        script = (PROJECT_ROOT / "tools" / "check_cross_language.sh").read_text(encoding="utf-8")
        assert "tests/test_wrapper_collection_order.py" in script, "the Python runner"
        assert "node collection_order.test.js" in script, "the JavaScript runner"
        assert "go test ./..." in script and "cargo test" in script, "Go and Rust run every test in the package"
