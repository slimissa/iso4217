"""
Cross-wrapper API consistency tests.

Validates that cross_language_consistency.json test vectors produce
correct results through the Python wrapper. Each wrapper in other
languages should run equivalent tests against the same JSON file.

This file is the reference implementation. Port it to JavaScript,
Rust, and Go to ensure identical behavior across all wrappers.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "wrappers" / "python"))

from iso4217 import CurrencyRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_vectors():
    """Load cross-language consistency test vectors."""
    path = PROJECT_ROOT / "tests" / "cross_language_consistency.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_registry():
    """Load the registry through the Python wrapper."""
    return CurrencyRegistry()


# ---------------------------------------------------------------------------
# Conversion tests
# ---------------------------------------------------------------------------

def test_conversion_vectors():
    """Every conversion test vector must produce the expected minor value."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None, f"{code} not found in registry"

        for conv in vector.get("conversions", []):
            major = conv["major"]
            expected_minor = conv["minor"]

            # to_minor: major → minor
            result = currency.to_minor(major)
            assert result == expected_minor, (
                f"{code}.to_minor({major}) = {result}, expected {expected_minor}"
            )

            # from_minor: minor → major (round-trip)
            back = currency.from_minor(result)
            assert back == major, (
                f"{code} round-trip failed: {major} → {result} → {back}"
            )


def test_conversion_vectors_handle_zero():
    """Zero major amount must produce zero minor units."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None

        assert currency.to_minor(0.0) == 0, f"{code}.to_minor(0.0) should be 0"
        assert currency.from_minor(0) == 0.0, f"{code}.from_minor(0) should be 0.0"


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------

def test_formatting_vectors():
    """Every formatting test vector must produce the expected string."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None, f"{code} not found in registry"

        for fmt in vector.get("formatting", []):
            major = fmt["major"]
            expected_formatted = fmt["formatted"]

            result = currency.format(major)
            assert result == expected_formatted, (
                f"{code}.format({major}) = '{result}', expected '{expected_formatted}'"
            )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

def test_minor_units_values():
    """Every test vector's minor_units must match the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None, f"{code} not found"

        expected_mu = vector["minor_units"]
        assert currency.minor_units == expected_mu, (
            f"{code}.minor_units = {currency.minor_units}, expected {expected_mu}"
        )


def test_peg_properties():
    """Every test vector's peg properties must match the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None, f"{code} not found"

        if "is_independent" in vector:
            assert currency.is_independent == vector["is_independent"], (
                f"{code}.is_independent = {currency.is_independent}, "
                f"expected {vector['is_independent']}"
            )

        if "is_pegged" in vector:
            assert currency.is_pegged == vector["is_pegged"], (
                f"{code}.is_pegged = {currency.is_pegged}, "
                f"expected {vector['is_pegged']}"
            )

        if "pegged_to" in vector:
            assert currency.pegged_to == vector["pegged_to"], (
                f"{code}.pegged_to = {currency.pegged_to!r}, "
                f"expected {vector['pegged_to']!r}"
            )

        if "peg_rate" in vector:
            assert currency.peg_rate == vector["peg_rate"], (
                f"{code}.peg_rate = {currency.peg_rate}, "
                f"expected {vector['peg_rate']}"
            )

        if "peg_band_pct" in vector:
            assert currency.peg_band_pct == vector["peg_band_pct"], (
                f"{code}.peg_band_pct = {currency.peg_band_pct}, "
                f"expected {vector['peg_band_pct']}"
            )


def test_withdrawn_properties():
    """Withdrawn currencies must have replacement metadata."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        if not vector.get("withdrawn"):
            continue

        code = vector["code"]
        currency = registry.currency(code)
        assert currency is not None, f"{code} not found"

        if "replaced_by" in vector:
            assert currency.replaced_by == vector["replaced_by"], (
                f"{code}.replaced_by = {currency.replaced_by!r}, "
                f"expected {vector['replaced_by']!r}"
            )

        if "conversion_rate" in vector:
            assert currency.conversion_rate == vector["conversion_rate"], (
                f"{code}.conversion_rate = {currency.conversion_rate}, "
                f"expected {vector['conversion_rate']}"
            )


# ---------------------------------------------------------------------------
# Lookup tests
# ---------------------------------------------------------------------------

def test_case_insensitive_lookup():
    """All lookup variations must return the same currency."""
    data = _load_vectors()
    registry = _load_registry()

    for test in data.get("lookup_tests", []):
        method_name = test["method"]
        method = getattr(registry, method_name)

        if test.get("expected_null"):
            for code in test["lookups"]:
                result = method(code)
                assert result is None, (
                    f"{method_name}('{code}') should return None"
                )
        else:
            expected_code = test["expected_code"]
            for code in test["lookups"]:
                result = method(code)
                assert result is not None, (
                    f"{method_name}('{code}') returned None"
                )
                assert result.code == expected_code, (
                    f"{method_name}('{code}').code = '{result.code}', "
                    f"expected '{expected_code}'"
                )


def test_lookup_methods_exist():
    """All lookup methods referenced in test vectors must exist on the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for test in data.get("lookup_tests", []):
        method_name = test["method"]
        assert hasattr(registry, method_name), (
            f"Registry has no method '{method_name}'"
        )
        assert callable(getattr(registry, method_name)), (
            f"Registry.{method_name} is not callable"
        )


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

def test_filter_vectors():
    """Filter methods must return expected currencies."""
    data = _load_vectors()
    registry = _load_registry()

    for test in data.get("filter_tests", []):
        method_name = test["method"]
        method = getattr(registry, method_name)

        if "argument" in test:
            results = method(test["argument"])
        else:
            results = method()

        result_codes = {c.code for c in results}

        for expected_code in test.get("expected_contains", []):
            assert expected_code in result_codes, (
                f"{method_name}() should contain {expected_code}"
            )

        for excluded_code in test.get("expected_not_contains", []):
            assert excluded_code not in result_codes, (
                f"{method_name}() should NOT contain {excluded_code}"
            )


def test_filter_methods_exist():
    """All filter methods referenced in test vectors must exist on the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for test in data.get("filter_tests", []):
        method_name = test["method"]
        assert hasattr(registry, method_name), (
            f"Registry has no method '{method_name}'"
        )
        assert callable(getattr(registry, method_name)), (
            f"Registry.{method_name} is not callable"
        )


# ---------------------------------------------------------------------------
# Summary tests
# ---------------------------------------------------------------------------

def test_summary_has_expected_keys():
    """Registry summary must contain all expected keys."""
    data = _load_vectors()
    registry = _load_registry()

    for test in data.get("summary_tests", []):
        summary = registry.summary()
        for key in test["expected_keys"]:
            assert key in summary, (
                f"Summary missing key: '{key}'"
            )


def test_summary_counts_are_consistent():
    """Summary counts must match collection sizes."""
    registry = _load_registry()
    summary = registry.summary()

    assert summary["active_currencies"] == registry.active_count, (
        f"active_currencies={summary['active_currencies']}, "
        f"active_count={registry.active_count}"
    )
    assert summary["withdrawn_currencies"] == registry.withdrawn_count, (
        f"withdrawn_currencies={summary['withdrawn_currencies']}, "
        f"withdrawn_count={registry.withdrawn_count}"
    )
    assert summary["non_iso_currencies"] == registry.non_iso_count, (
        f"non_iso_currencies={summary['non_iso_currencies']}, "
        f"non_iso_count={registry.non_iso_count}"
    )
    assert summary["pegged_currencies"] == registry.pegged_count, (
        f"pegged_currencies={summary['pegged_currencies']}, "
        f"pegged_count={registry.pegged_count}"
    )
    assert summary["independent_currencies"] == registry.independent_count, (
        f"independent_currencies={summary['independent_currencies']}, "
        f"independent_count={registry.independent_count}"
    )

    # Minor units distribution must sum to active count
    total = sum(summary["minor_units_distribution"].values())
    assert total == registry.active_count, (
        f"minor_units_distribution sums to {total}, "
        f"expected {registry.active_count}"
    )


def test_summary_types_are_correct():
    """Summary values must have correct types."""
    registry = _load_registry()
    summary = registry.summary()

    assert isinstance(summary["version"], str)
    assert isinstance(summary["updated"], str)
    assert isinstance(summary["active_currencies"], int)
    assert isinstance(summary["withdrawn_currencies"], int)
    assert isinstance(summary["non_iso_currencies"], int)
    assert isinstance(summary["pegged_currencies"], int)
    assert isinstance(summary["independent_currencies"], int)
    assert isinstance(summary["minor_units_distribution"], dict)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_registry_contains_all_test_vector_codes():
    """Every code in the test vectors must exist in the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for vector in data["test_vectors"]:
        code = vector["code"]
        assert registry.currency(code) is not None, (
            f"{code} from test vectors not found in registry"
        )


def test_to_minor_handles_negative_amounts():
    """Negative amounts should produce negative minor units."""
    registry = _load_registry()
    usd = registry.currency("USD")
    assert usd is not None

    assert usd.to_minor(-100.50) == -10050
    assert usd.to_minor(-0.01) == -1


def test_from_minor_handles_negative_amounts():
    """Negative minor units should produce negative major amounts."""
    registry = _load_registry()
    usd = registry.currency("USD")
    assert usd is not None

    assert usd.from_minor(-10050) == -100.5
    assert usd.from_minor(-1) == -0.01


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))