"""
The wrapper numeric contract (v1.9.3, audit finding P5-04, ADR 0013).

One fixture group, `numeric_contract` in tests/cross_language_consistency.json, states what `to_minor` and `format` return
for every input that mattered in the audit. Each wrapper's own suite reads it (wrappers/go/numeric_contract_test.go,
wrappers/rust/tests/numeric_contract.rs, wrappers/javascript/numeric_contract.test.js) and this file runs the Python
wrapper and the JavaScript suite directly. Go and Rust run under tools/check_cross_language.sh (the release gate) and the
CI wrapper matrix; set NUMERIC_CONTRACT_RUN_NATIVE=1 to run them from here too.

The expected values are not trusted: `TestTheFixtureIsTheOracle` recomputes every one with tests/numeric_contract_oracle.py,
which shares no code with any wrapper, so a vector cannot be edited to match a wrapper's bug (rule 10).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "wrappers" / "python"))

import numeric_contract_oracle as oracle  # noqa: E402
import iso4217  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "cross_language_consistency.json"
REGISTRY = PROJECT_ROOT / "iso4217.json"
NC = json.loads(FIXTURE.read_text(encoding="utf-8"))["numeric_contract"]

REQUIRED_GROUPS = {
    "rounding", "rounding_edges", "overflow", "non_finite", "jpy_ties",
    "format_agrees_with_to_minor", "zero_sign", "large_amounts",
}
VECTORS = [(g["id"], v) for g in NC["groups"] for v in g["vectors"]]
IDS = [f'{gid}:{v["currency"]}:{v["x"]}' for gid, v in VECTORS]


def registry_currency(registry, code):
    return registry.currency(code) or registry.non_iso(code)


@pytest.fixture(scope="module")
def registry():
    return iso4217.CurrencyRegistry()


def raw_registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def minor_units_and_symbol(code):
    data = raw_registry()
    for section in (data["currencies"]["active"], data["currencies"]["withdrawn"], *data["non_iso"].values()):
        for c in section:
            if c["code"] == code:
                return c["minor_units"], c["symbol"]
    raise KeyError(code)


class TestTheFixtureIsTheOracle:
    def test_every_required_group_is_present(self):
        assert {g["id"] for g in NC["groups"]} == REQUIRED_GROUPS

    def test_the_declared_vector_count_is_the_real_count(self):
        assert NC["vector_count"] == len(VECTORS)

    def test_every_vector_uses_known_keys_and_tokens(self):
        for gid, v in VECTORS:
            assert set(v) <= {"currency", "x", "to_minor", "format"}, (gid, v)
            assert "to_minor" in v or "format" in v, (gid, v)
            if isinstance(v["x"], str):
                assert v["x"] in oracle.NON_FINITE_TOKENS, (gid, v)

    @pytest.mark.parametrize("gid,vector", VECTORS, ids=IDS)
    def test_the_expected_values_are_the_oracles(self, gid, vector):
        n, symbol = minor_units_and_symbol(vector["currency"])
        x = oracle.decode_x(vector["x"])
        if "to_minor" in vector:
            assert vector["to_minor"] == oracle.to_minor(x, n)
        if "format" in vector:
            assert vector["format"] == oracle.format_amount(x, n, symbol)

    def test_every_registry_scale_has_an_exact_power_of_ten(self):
        # 10^n is an exact double only up to n = 22; every wrapper takes it from an exact table (ADR 0013, D2).
        data = raw_registry()
        scales = [c["minor_units"] for s in (data["currencies"]["active"], data["currencies"]["withdrawn"], *data["non_iso"].values())
                  for c in s if c.get("minor_units") is not None]
        assert max(scales) <= oracle.MAX_SCALE


class TestPythonWrapper:
    @pytest.mark.parametrize("gid,vector", VECTORS, ids=IDS)
    def test_the_vector_holds(self, registry, gid, vector):
        c = registry_currency(registry, vector["currency"])
        assert c is not None
        x = oracle.decode_x(vector["x"])
        wanted_minor = None
        if "to_minor" in vector:
            expected = vector["to_minor"]
            if isinstance(expected, dict):
                kind = expected["error"]
                with pytest.raises(ValueError if kind == "non_finite" else OverflowError) as info:
                    c.to_minor(x)
                if kind == "overflow":
                    assert "amount too large" in str(info.value)
                else:
                    assert not isinstance(info.value, OverflowError)
            else:
                wanted_minor = expected
                assert c.to_minor(x) == expected
        if "format" in vector:
            shown = c.format(x)
            assert shown == vector["format"]
            if wanted_minor is not None:
                assert re.sub(r"\D", "", shown).lstrip("0") == str(abs(wanted_minor)).lstrip("0")

    def test_exact_integers_and_decimals_keep_their_exactness(self, registry):
        jpy, usd, eth = registry.active("JPY"), registry.active("USD"), registry_currency(registry, "ETH")
        assert jpy.to_minor(4503599627370497) == 4503599627370497          # int input is exact
        assert usd.to_minor(Decimal("1.005")) == 101                        # Decimal input is exact half away from zero
        assert usd.format(Decimal("0.125")) == "$0.13"                      # Decimal format follows to_minor (was half-even)
        assert usd.format(Decimal("-0.004")) == "$-0.00"                    # D6, as for floats
        assert eth.to_minor(Decimal("9.000000000000000001")) == 9000000000000000001
        assert eth.to_minor(Decimal("10")) == 10**19                        # Decimal is exact and unbounded (v1.9.0, F28)
        assert usd.to_minor(Decimal("9" * 100)) == int("9" * 100 + "00")
        with pytest.raises(OverflowError):
            eth.to_minor(10)                                                # an int is a float in the other wrappers
        with pytest.raises(OverflowError):
            eth.to_minor(10.0)
        assert usd.format(Decimal("NaN")) == "$nan"
        assert usd.format(Decimal("-Infinity")) == "$-inf"

    def test_a_bool_or_str_is_not_silently_accepted(self, registry):
        usd = registry.active("USD")
        with pytest.raises((TypeError, ValueError)):
            usd.to_minor("5")


class TestJavaScriptWrapper:
    def test_the_suite_passes_and_checks_every_vector(self):
        node = shutil.which("node")
        assert node, "node is required: a contract that cannot run is not a contract (rule 7)"
        done = subprocess.run([node, "numeric_contract.test.js"], cwd=PROJECT_ROOT / "wrappers" / "javascript",
                              capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stdout[-2500:] + done.stderr[-1500:]
        assert f"NUMERIC_CONTRACT javascript vectors={len(VECTORS)}" in done.stdout


class TestNativeSuitesCoverTheContract:
    """Go and Rust are executed by check_cross_language.sh and CI. Here: they must exist, must call the contract's API
    and must declare the same vector count; with NUMERIC_CONTRACT_RUN_NATIVE=1 they also run."""

    GO = PROJECT_ROOT / "wrappers" / "go"
    RUST = PROJECT_ROOT / "wrappers" / "rust"

    def test_go_suite_exists_and_uses_the_checked_api(self):
        text = (self.GO / "numeric_contract_test.go").read_text(encoding="utf-8")
        assert "ToMinorChecked" in text and "ErrOverflow" in text and "ErrNonFinite" in text
        assert "NUMERIC_CONTRACT go vectors=" in text
        src = (self.GO / "iso4217.go").read_text(encoding="utf-8")
        for needle in ("func (c *Currency) ToMinorChecked", "ErrNonFinite", "ErrOverflow"):
            assert needle in src

    def test_rust_suite_exists_and_uses_the_checked_api(self):
        text = (self.RUST / "tests" / "numeric_contract.rs").read_text(encoding="utf-8")
        assert "try_to_minor" in text and "MinorError" in text
        assert "NUMERIC_CONTRACT rust vectors=" in text
        src = (self.RUST / "src" / "lib.rs").read_text(encoding="utf-8")
        for needle in ("pub fn try_to_minor", "pub enum MinorError"):
            assert needle in src

    # Defined only when asked for: the repo runs pytest with --fail-on-skip, so an opt-in test must not exist as a skip.
    if os.environ.get("NUMERIC_CONTRACT_RUN_NATIVE") == "1":

        @pytest.mark.parametrize("lang", ["go", "rust"])
        def test_native_suite_passes(self, lang):
            tool = shutil.which("go" if lang == "go" else "cargo")
            assert tool, f"{lang} toolchain required when NUMERIC_CONTRACT_RUN_NATIVE=1"
            cmd = ([tool, "test", "-run", "TestNumericContract", "-v", "./..."] if lang == "go"
                   else [tool, "test", "--test", "numeric_contract", "--", "--nocapture"])
            done = subprocess.run(cmd, cwd=self.GO if lang == "go" else self.RUST, capture_output=True, text=True, timeout=1200)
            assert done.returncode == 0, done.stdout[-2500:] + done.stderr[-1500:]
            assert f"NUMERIC_CONTRACT {lang} vectors={len(VECTORS)}" in done.stdout
