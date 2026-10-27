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

import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "wrappers" / "python"))

from iso4217 import CurrencyRegistry, RegistryDataError


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
            # Entries marked "lossy" represent rounding-boundary values that
            # are not exactly representable in integer minor units (e.g.
            # USD 100.005 rounds to 10001, whose true inverse is 100.01, not
            # the original 100.005). The forward to_minor check above is
            # still the point of those vectors; only the inverse is skipped.
            if conv.get("lossy"):
                continue
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

        if "peg_type" in vector:
            assert currency.peg_type == vector["peg_type"], (
                f"{code}.peg_type = {currency.peg_type!r}, "
                f"expected {vector['peg_type']!r}"
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
# Classification tests (v1.6.0)
# ---------------------------------------------------------------------------

def test_classification_values():
    """Every classification test vector must match the registry."""
    data = _load_vectors()
    registry = _load_registry()

    for block in data.get("classification_tests", []):
        expected = block.get("expected")
        if not expected:
            continue
        for code, expected_cls in expected.items():
            currency = registry.currency(code)
            assert currency is not None, f"{code} not found in registry"
            assert currency.classification == expected_cls, (
                f"{code}.classification = {currency.classification!r}, "
                f"expected {expected_cls!r}"
            )


def test_by_classification():
    """by_classification() must return the expected codes."""
    data = _load_vectors()
    registry = _load_registry()

    for block in data.get("classification_tests", []):
        if block.get("method") != "by_classification":
            continue
        arg = block["argument"]
        results = registry.by_classification(arg)
        codes = {c.code for c in results}

        for expected in block.get("expected_contains", []):
            assert expected in codes, (
                f"by_classification({arg!r}) should contain {expected}, "
                f"got {sorted(codes)}"
            )
        for excluded in block.get("expected_not_contains", []):
            assert excluded not in codes, (
                f"by_classification({arg!r}) should NOT contain {excluded}"
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


# ---------------------------------------------------------------------------
# Malformed registry data (v1.9.0, F13): the shared fixture, one error type
# ---------------------------------------------------------------------------

def _malformed_cases():
    return _load_vectors()["malformed_registry_tests"]


def _write_registry(tmp_path, registry):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(registry), encoding="utf-8")
    return p


def test_every_malformed_registry_is_rejected_with_the_error_type_and_the_path(tmp_path):
    cases = _malformed_cases()["malformed"]
    assert len(cases) >= 30
    for case in cases:
        with pytest.raises(RegistryDataError) as exc:
            CurrencyRegistry(_write_registry(tmp_path, case["registry"]))
        msg = str(exc.value)
        assert msg.startswith("malformed registry data: "), (case["id"], msg)
        assert case["path"] in msg, (case["id"], case["path"], msg)


def test_every_valid_fixture_registry_is_accepted(tmp_path):
    for case in _malformed_cases()["valid"]:
        CurrencyRegistry(_write_registry(tmp_path, case["registry"]))


def test_the_error_type_is_a_value_error():
    assert issubclass(RegistryDataError, ValueError)


@pytest.mark.parametrize("text, reason", [
    ("{", "invalid JSON"), ('{"a": NaN}', "non-standard JSON constant NaN"),
    ("[" * 100000 + "]" * 100000, "nested too deeply"),
])
def test_unparsable_files_raise_the_same_error_type(tmp_path, text, reason):
    p = tmp_path / "bad.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryDataError, match=reason):
        CurrencyRegistry(p)


def test_invalid_utf8_raises_the_same_error_type(tmp_path):
    p = tmp_path / "bad.json"
    p.write_bytes(b'{"a": "\xff"}')
    with pytest.raises(RegistryDataError, match="not valid UTF-8"):
        CurrencyRegistry(p)


def test_a_missing_file_is_still_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        CurrencyRegistry(tmp_path / "absent.json")


def test_the_real_registry_passes_the_strict_pass():
    assert CurrencyRegistry().currency("USD").minor_units == 2



# ---------------------------------------------------------------------------
# Decimal amounts (v1.9.0, F28)
# ---------------------------------------------------------------------------

def test_decimal_to_minor_is_exact_where_a_float_loses_digits():
    from decimal import Decimal
    usd = CurrencyRegistry().currency("USD")
    assert usd.to_minor(Decimal("99999999999999999999")) == 9999999999999999999900
    assert usd.to_minor(Decimal("123456789012345678.99")) == 12345678901234567899
    # The float path no longer returns a wrong number for an amount beyond int64; it raises (ADR 0013, D3).
    with pytest.raises(OverflowError, match="amount too large"):
        usd.to_minor(99999999999999999999.0)


def test_decimal_to_minor_rounds_half_away_from_zero():
    from decimal import Decimal
    reg = CurrencyRegistry()
    jpy, usd = reg.currency("JPY"), reg.currency("USD")
    assert [jpy.to_minor(Decimal(s)) for s in ("2.5", "-2.5", "0.5", "-0.5", "1.5", "-1.5")] == [3, -3, 1, -1, 2, -2]
    assert usd.to_minor(Decimal("1.005")) == 101          # a tie a binary float cannot hold
    assert usd.to_minor(1.005) == 100                      # the float path keeps its old behaviour


def test_decimal_to_minor_refuses_nan_and_infinity():
    from decimal import Decimal
    usd = CurrencyRegistry().currency("USD")
    for text in ("NaN", "sNaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError):
            usd.to_minor(Decimal(text))


def test_decimal_and_float_agree_on_ordinary_amounts():
    from decimal import Decimal
    usd = CurrencyRegistry().currency("USD")
    for text in ("0", "0.01", "100.50", "-100.50", "1234.56"):
        assert usd.to_minor(Decimal(text)) == usd.to_minor(float(text))


def test_decimal_format_is_exact():
    from decimal import Decimal
    reg = CurrencyRegistry()
    assert reg.currency("USD").format(Decimal("99999999999999999999.99")) == "$99,999,999,999,999,999,999.99"
    # ADR 0013: format rounds half away from zero like to_minor. It used to truncate a 0-decimal amount (500.9 -> 500).
    assert reg.currency("JPY").format(Decimal("500.9")) == "\u00a5501"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))