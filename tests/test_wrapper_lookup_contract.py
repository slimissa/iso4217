"""
The wrapper lookup contract (v1.9.5, audit finding P5-09, ADR 0015, docs/decisions/wrapper-lookup-contract.md).

One fixture group, `lookup_contract` in tests/cross_language_consistency.json, states which entry `currency()` returns when a code
is in more than one section, what a repeated code does, and what a non-string argument does. Each wrapper's own suite reads it
(wrappers/javascript/lookup_contract.test.js, wrappers/go/lookup_contract_test.go, the `lookup_contract` module in
wrappers/rust/src/lib.rs); this file runs the Python wrapper and the JavaScript suite directly. Go and Rust run under
tools/check_cross_language.sh (the release gate) and the CI wrapper matrix; set LOOKUP_CONTRACT_RUN_NATIVE=1 to run them here too.

Test classes (ADR 0014, D1): R = red-first (fails on v1.9.4), C = characterization (passes on v1.9.4, must pass after).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "wrappers" / "python"))
import iso4217  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "cross_language_consistency.json"
LC = json.loads(FIXTURE.read_text(encoding="utf-8")).get("lookup_contract", {})
CASES = [("precedence", c) for c in LC.get("precedence", [])] + [("duplicates", c) for c in LC.get("duplicates", [])]
IDS = [f"{kind}:{c['id']}" for kind, c in CASES]
INVALID = LC.get("invalid_input", {})
# v1.9.6: the lookups that take a country or anchor code joined the group. A method named in method_applies_to applies only to
# the wrappers listed there; any other method applies to every wrapper in applies_to.
NEW_IN_V196 = ("pegged_to", "issued_by", "used_in")


def methods_for(lang: str) -> list[str]:
    scope = INVALID.get("method_applies_to", {})
    return [m for m in INVALID.get("methods", []) if lang in scope.get(m, INVALID.get("applies_to", []))]


def invalid_count_for(lang: str) -> int:
    return len(methods_for(lang)) * len(INVALID.get("values", []))
SENTENCE = "A code in more than one section resolves to the first of: active, withdrawn, non-ISO."


def build(tmp_path: Path, case: dict) -> "iso4217.CurrencyRegistry":
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(case["registry"]), encoding="utf-8")
    return iso4217.CurrencyRegistry(p)


class TestTheFixture:
    def test_R_the_group_exists_with_its_three_sub_groups(self):
        assert LC, "tests/cross_language_consistency.json has no lookup_contract group"
        assert LC["precedence"] and LC["duplicates"] and LC["invalid_input"]

    def test_R_the_declared_counts_are_the_real_counts(self):
        core = sum(len(c["lookups"]) for _k, c in CASES) + sum(1 for _k, c in CASES if "expected_active_count" in c)
        assert LC["vector_count"] == core
        assert LC["invalid_input_count"] == len(INVALID["methods"]) * len(INVALID["values"])

    def test_C_the_invalid_input_group_names_the_two_languages_that_can_receive_one(self):
        assert INVALID["applies_to"] == ["python", "javascript"] and INVALID["error"] == "TypeError"

    def test_R_the_country_and_anchor_lookups_are_in_the_group(self):
        assert set(NEW_IN_V196) <= set(INVALID["methods"])
        assert set(NEW_IN_V196) <= set(methods_for("python")), "the Python wrapper guards all three (v1.9.6)"
        assert set(NEW_IN_V196) <= set(methods_for("javascript")), "the JavaScript wrapper guards all three (v1.9.6)"

    def test_R_method_applies_to_only_narrows_and_only_names_listed_methods(self):
        for method, langs in INVALID.get("method_applies_to", {}).items():
            assert method in INVALID["methods"], method
            assert langs and set(langs) <= set(INVALID["applies_to"]), method


class TestPythonWrapper:
    @pytest.mark.parametrize("kind,case", CASES, ids=IDS)
    def test_R_the_vector_holds(self, tmp_path, kind, case):
        registry = build(tmp_path, case)
        for lk in case["lookups"]:
            found = getattr(registry, lk["method"])(lk["code"])
            assert found is not None and found.name == lk["expected_name"], f'{case["id"]}: {lk}'
        if "expected_active_count" in case:
            assert len(registry.all_active()) == case["expected_active_count"]

    @pytest.mark.parametrize("method", methods_for("python"))
    @pytest.mark.parametrize("value", INVALID.get("values", []), ids=lambda v: repr(v))
    def test_R_a_non_string_code_raises_type_error_with_a_message(self, tmp_path, method, value):
        registry = build(tmp_path, CASES[0][1])
        with pytest.raises(TypeError) as err:
            if method == "contains":          # Python's membership test is `code in registry` (JavaScript: isValid)
                value in registry
            else:
                getattr(registry, method)(value)
        assert INVALID["message_contains"] in str(err.value)

    def test_C_a_string_that_is_not_a_code_is_still_just_not_found(self, tmp_path):
        registry = build(tmp_path, CASES[0][1])
        assert registry.currency("") is None and registry.active("NOPE") is None and ("NOPE" in registry) is False

    def test_C_the_module_level_helpers_inherit_the_contract(self):
        with pytest.raises(TypeError):
            iso4217.currency(None)

    @pytest.mark.parametrize("value", INVALID.get("values", []), ids=lambda v: repr(v))
    def test_R_the_module_level_pegged_to_raises_type_error_with_a_message(self, value):
        with pytest.raises(TypeError) as err:
            iso4217.pegged_to(value)
        assert INVALID["message_contains"] in str(err.value) and str(err.value).startswith("code must be a string, got ")

    @pytest.mark.parametrize("method", NEW_IN_V196)
    def test_R_the_message_is_the_one_the_currency_lookups_use(self, tmp_path, method):
        registry = build(tmp_path, CASES[0][1])
        with pytest.raises(TypeError, match=r"^code must be a string, got NoneType$"):
            getattr(registry, method)(None)

    def test_C_a_string_country_or_anchor_still_works_in_any_case(self):
        registry = iso4217.CurrencyRegistry()
        assert [c.code for c in registry.pegged_to("usd")] == [c.code for c in registry.pegged_to("USD")] != []
        assert [c.code for c in registry.used_in("fr")] == [c.code for c in registry.used_in("FR")] != []
        assert registry.issued_by("") == [] and registry.used_in("ZZ") == []

    def test_C_the_shipped_registry_resolves_every_code_to_the_section_that_is_not_shadowed(self):
        registry = iso4217.CurrencyRegistry()
        for c in registry.all_active():
            assert registry.currency(c.code) is c or registry.currency(c.code).name == c.name


class TestJavaScriptWrapper:
    def test_R_the_suite_passes_and_checks_every_vector(self):
        node = shutil.which("node")
        assert node, "node is required: a contract that cannot run is not a contract (hygiene rule 7)"
        done = subprocess.run([node, "lookup_contract.test.js"], cwd=PROJECT_ROOT / "wrappers" / "javascript",
                              capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stdout[-2500:] + done.stderr[-1500:]
        assert f'LOOKUP_CONTRACT javascript vectors={LC["vector_count"]} invalid={invalid_count_for("javascript")}' in done.stdout


class TestNativeSuitesCoverTheContract:
    """Go and Rust are executed by check_cross_language.sh and CI. Here they must exist, read the group and declare the same
    count; with LOOKUP_CONTRACT_RUN_NATIVE=1 they also run."""

    GO = PROJECT_ROOT / "wrappers" / "go"
    RUST = PROJECT_ROOT / "wrappers" / "rust"

    def test_R_go_suite_exists_and_reads_the_group(self):
        text = (self.GO / "lookup_contract_test.go").read_text(encoding="utf-8")
        assert "lookup_contract" in text and "LOOKUP_CONTRACT go vectors=" in text and "loadRegistryFrom" in text

    def test_R_rust_suite_exists_and_reads_the_group(self):
        text = (self.RUST / "src" / "lib.rs").read_text(encoding="utf-8")
        assert "mod lookup_contract" in text and "LOOKUP_CONTRACT rust vectors=" in text and "lookup_contract" in text

    if os.environ.get("LOOKUP_CONTRACT_RUN_NATIVE") == "1":

        @pytest.mark.parametrize("lang", ["go", "rust"])
        def test_native_suite_passes(self, lang):
            tool = shutil.which("go" if lang == "go" else "cargo")
            assert tool, f"{lang} toolchain required when LOOKUP_CONTRACT_RUN_NATIVE=1"
            cmd = ([tool, "test", "-run", "TestLookupContract", "-v", "./..."] if lang == "go"
                   else [tool, "test", "--lib", "lookup_contract", "--", "--nocapture"])
            done = subprocess.run(cmd, cwd=self.GO if lang == "go" else self.RUST, capture_output=True, text=True, timeout=1200)
            assert done.returncode == 0, done.stdout[-2500:] + done.stderr[-1500:]
            assert f'LOOKUP_CONTRACT {lang} vectors={LC["vector_count"]}' in done.stdout


class TestTheWordsMatchTheCode:
    @pytest.mark.parametrize("lang", ["python", "javascript", "go", "rust"])
    def test_R_each_wrapper_readme_states_the_precedence_in_the_same_words(self, lang):
        assert SENTENCE in (PROJECT_ROOT / "wrappers" / lang / "README.md").read_text(encoding="utf-8")

    def test_R_python_and_javascript_readmes_state_the_type_error_contract(self):
        for lang, included in (("python", "`None` included"), ("javascript", "`null` and `undefined` included")):
            text = (PROJECT_ROOT / "wrappers" / lang / "README.md").read_text(encoding="utf-8")
            assert "`TypeError`" in text and included in text, lang
