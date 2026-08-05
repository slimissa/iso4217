"""
Tests for JSON Schema validation of iso4217.json.

Verifies that the registry file validates against schema.json
and that all required fields are present on all currencies.
Runs as part of the CI pipeline on every push.
"""

import json
import sys
from pathlib import Path

# Add project root to path so we can import from tools/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure tools/ is importable as a package
TOOLS_INIT = PROJECT_ROOT / "tools" / "__init__.py"
if not TOOLS_INIT.exists():
    TOOLS_INIT.touch()

from tools.validate import (
    load_registry,
    load_schema,
    validate_against_schema,
    validate_active_currencies,
    validate_withdrawn_currencies,
    validate_cross_references,
    validate_meta,
    validate_source,
    validate_statistics,
    MIN_ACTIVE_CURRENCIES,
    WARN_ACTIVE_CURRENCIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_errors(errors, severity="error"):
    """Filter validation results to a specific severity level."""
    return [e for e in errors if e.severity == severity]


def _registry():
    """Load the registry once per test session."""
    return load_registry(PROJECT_ROOT / "iso4217.json")


def _schema():
    """Load the schema once."""
    return load_schema(PROJECT_ROOT / "schema.json")


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_schema_valid():
    """iso4217.json validates against schema.json without errors."""
    registry = _registry()
    schema = _schema()
    errors = validate_against_schema(registry, schema)

    schema_errors = _get_errors(errors)
    assert len(schema_errors) == 0, (
        f"Schema validation failed with {len(schema_errors)} error(s):\n" +
        "\n".join(f"  [{e.code}] {e.field}: {e.message}" for e in schema_errors)
    )


# ---------------------------------------------------------------------------
# Meta and source validation
# ---------------------------------------------------------------------------

def test_meta_valid():
    """Meta section has valid version, dates, and required fields."""
    registry = _registry()
    errors = validate_meta(registry)

    meta_errors = _get_errors(errors)
    assert len(meta_errors) == 0, (
        f"Meta validation failed:\n" +
        "\n".join(f"  [{e.code}] {e.message}" for e in meta_errors)
    )


def test_meta_version_is_semver():
    """Version follows MAJOR.MINOR.PATCH format."""
    registry = _registry()
    version = registry.get("meta", {}).get("version", "")
    parts = version.split(".")
    assert len(parts) == 3, f"Version '{version}' is not semver"
    assert all(p.isdigit() for p in parts), f"Version '{version}' has non-numeric parts"


def test_meta_updated_is_valid_date():
    """Updated field is a valid ISO 8601 date."""
    registry = _registry()
    updated = registry.get("meta", {}).get("updated", "")
    from datetime import date
    try:
        date.fromisoformat(updated)
    except ValueError:
        assert False, f"Updated date '{updated}' is not valid ISO 8601"


def test_source_valid():
    """Source section has valid amendment and verification data."""
    registry = _registry()
    errors = validate_source(registry)

    source_errors = _get_errors(errors)
    assert len(source_errors) == 0, (
        f"Source validation failed:\n" +
        "\n".join(f"  [{e.code}] {e.message}" for e in source_errors)
    )


def test_source_has_required_fields():
    """Source section contains all required metadata."""
    registry = _registry()
    source = registry.get("source", {})

    required = ["standard", "maintenance_agency", "last_amendment_applied",
                "last_amendment_date", "last_verified", "verified_against"]
    for field in required:
        assert field in source, f"Source missing required field: '{field}'"


# ---------------------------------------------------------------------------
# Active currency tests
# ---------------------------------------------------------------------------

def test_active_currencies_have_required_fields():
    """Every active currency has code, numeric, name, and minor_units."""
    registry = _registry()
    active = registry.get("currencies", {}).get("active", [])

    assert len(active) > 0, "No active currencies found in registry"

    for c in active:
        code = c.get("code", "[unknown]")
        assert "code" in c, f"Missing 'code' in active currency"
        assert "numeric" in c, f"Missing 'numeric' in {code}"
        assert "name" in c, f"Missing 'name' in {code}"
        assert "minor_units" in c, f"Missing 'minor_units' in {code}"
        assert isinstance(c["minor_units"], int), (
            f"minor_units is {type(c['minor_units']).__name__} in {code}, expected int"
        )


def test_active_currencies_have_unique_codes():
    """No duplicate codes in active currencies."""
    registry = _registry()
    active = registry.get("currencies", {}).get("active", [])
    codes = [c["code"] for c in active]
    duplicates = {code for code in codes if codes.count(code) > 1}
    assert len(duplicates) == 0, f"Duplicate active codes: {duplicates}"


def test_active_currencies_pass_integrity_checks():
    """Active currencies pass all integrity validations from the validator."""
    registry = _registry()
    active = registry.get("currencies", {}).get("active", [])
    errors = validate_active_currencies(active)

    active_errors = _get_errors(errors)
    assert len(active_errors) == 0, (
        f"Active currency validation failed with {len(active_errors)} error(s):\n" +
        "\n".join(f"  [{e.code}] {e.field}: {e.message}" for e in active_errors)
    )


def test_active_currencies_have_countries():
    """Every active currency has at least one country with an issuer."""
    registry = _registry()
    active = registry.get("currencies", {}).get("active", [])

    for c in active:
        code = c.get("code", "[unknown]")
        countries = c.get("countries", [])
        assert len(countries) > 0, f"{code} has no countries"

        issuers = [ct for ct in countries if ct.get("relationship") == "issuing"]
        assert len(issuers) >= 1, f"{code} has no issuing country"


# ---------------------------------------------------------------------------
# Withdrawn currency tests
# ---------------------------------------------------------------------------

def test_withdrawn_currencies_have_required_fields():
    """Every withdrawn currency has withdrawal metadata."""
    registry = _registry()
    withdrawn = registry.get("currencies", {}).get("withdrawn", [])

    for c in withdrawn:
        code = c.get("code", "[unknown]")
        assert "withdrawn_date" in c, f"Missing 'withdrawn_date' in {code}"
        assert "replaced_by" in c, f"Missing 'replaced_by' in {code}"
        assert "conversion_rate" in c, f"Missing 'conversion_rate' in {code}"
        assert isinstance(c["conversion_rate"], (int, float)), (
            f"conversion_rate is {type(c['conversion_rate']).__name__} in {code}"
        )
        assert c["conversion_rate"] > 0, (
            f"conversion_rate is {c['conversion_rate']} in {code}, must be positive"
        )


def test_withdrawn_currencies_pass_integrity_checks():
    """Withdrawn currencies pass all integrity validations."""
    registry = _registry()
    withdrawn = registry.get("currencies", {}).get("withdrawn", [])
    errors = validate_withdrawn_currencies(withdrawn)

    withdrawn_errors = _get_errors(errors)
    assert len(withdrawn_errors) == 0, (
        f"Withdrawn currency validation failed:\n" +
        "\n".join(f"  [{e.code}] {e.field}: {e.message}" for e in withdrawn_errors)
    )


# ---------------------------------------------------------------------------
# Cross-reference tests
# ---------------------------------------------------------------------------

def test_no_duplicate_codes_across_categories():
    """No currency code appears in both active and withdrawn."""
    registry = _registry()
    errors = validate_cross_references(registry)

    cross_errors = _get_errors(errors)
    assert len(cross_errors) == 0, (
        f"Cross-reference validation failed:\n" +
        "\n".join(f"  [{e.code}] {e.message}" for e in cross_errors)
    )


def test_active_and_withdrawn_are_disjoint():
    """No code is simultaneously active and withdrawn."""
    registry = _registry()
    active_codes = {c["code"] for c in registry.get("currencies", {}).get("active", [])}
    withdrawn_codes = {c["code"] for c in registry.get("currencies", {}).get("withdrawn", [])}

    overlap = active_codes & withdrawn_codes
    assert len(overlap) == 0, (
        f"Codes found in both active and withdrawn: {sorted(overlap)}"
    )


def test_non_iso_does_not_overlap_iso():
    """Non-ISO codes do not shadow ISO 4217 codes."""
    registry = _registry()
    active_codes = {c["code"] for c in registry.get("currencies", {}).get("active", [])}
    withdrawn_codes = {c["code"] for c in registry.get("currencies", {}).get("withdrawn", [])}
    iso_codes = active_codes | withdrawn_codes

    non_iso = registry.get("non_iso", {})
    for category in ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]:
        for c in non_iso.get(category, []):
            code = c["code"]
            assert code not in iso_codes, (
                f"Non-ISO code '{code}' in '{category}' conflicts with ISO 4217 code"
            )


# ---------------------------------------------------------------------------
# Active currency count plausibility (issue #9)
#
# A registry with 5 active currencies previously passed validation with no
# complaint — nothing checked that the count was plausible relative to real
# ISO 4217 coverage (~180 active codes). That's exactly how the 61/180 gap
# shipped in v1.0.0 without any test catching it. These tests exercise the
# check directly against synthetic active-count values rather than only
# asserting on the real registry's current count, so they keep meaning
# something once v1.1.0 changes that count.
# ---------------------------------------------------------------------------

def _registry_with_active_count(n):
    """Build a synthetic registry with exactly n active currency entries.

    The entries are shallow copies of the real registry's first active
    currency, repeated. validate_statistics only counts len(active) for
    this check — it doesn't require unique codes — so duplicate entries
    are fine here and keep the test fast and dependency-free.
    """
    import copy
    registry = copy.deepcopy(_registry())
    template = registry["currencies"]["active"][0]
    registry["currencies"]["active"] = [dict(template) for _ in range(n)]
    return registry


def test_current_registry_active_count_is_below_min_active_currencies():
    """
    Sanity check on the constants themselves: this test intentionally FAILS
    once v1.1.0 raises active_count to >= MIN_ACTIVE_CURRENCIES, which is
    the point — it's a tripwire reminding whoever ships full coverage to
    also revisit --allow-partial in CI (see .github/workflows/validate.yml).
    """
    registry = _registry()
    active_count = len(registry["currencies"]["active"])
    assert active_count < MIN_ACTIVE_CURRENCIES, (
        f"Active count is now {active_count}, which meets MIN_ACTIVE_CURRENCIES "
        f"({MIN_ACTIVE_CURRENCIES}). If v1.1.0 shipped full ISO 4217 coverage, "
        "remove --allow-partial from .github/workflows/validate.yml and delete "
        "this tripwire test."
    )


def test_active_count_below_warn_threshold_emits_warning():
    registry = _registry_with_active_count(WARN_ACTIVE_CURRENCIES - 1)
    errors, stats = validate_statistics(registry)
    assert stats["active_count"] == WARN_ACTIVE_CURRENCIES - 1
    codes = {e.code for e in errors}
    assert "ACTIVE_COUNT_LOW" in codes


def test_active_count_at_warn_threshold_does_not_emit_low_warning():
    registry = _registry_with_active_count(WARN_ACTIVE_CURRENCIES)
    errors, _ = validate_statistics(registry)
    codes = {e.code for e in errors}
    assert "ACTIVE_COUNT_LOW" not in codes


def test_active_count_below_min_emits_error_by_default():
    registry = _registry_with_active_count(MIN_ACTIVE_CURRENCIES - 1)
    errors, stats = validate_statistics(registry)
    assert stats["active_count"] == MIN_ACTIVE_CURRENCIES - 1
    below_min = [e for e in errors if e.code == "ACTIVE_COUNT_BELOW_MINIMUM"]
    assert len(below_min) == 1
    assert below_min[0].severity == "error"
    assert str(MIN_ACTIVE_CURRENCIES) in below_min[0].message
    assert "--allow-partial" in below_min[0].message


def test_active_count_below_min_downgrades_to_warning_with_allow_partial():
    registry = _registry_with_active_count(MIN_ACTIVE_CURRENCIES - 1)
    errors, _ = validate_statistics(registry, allow_partial=True)
    below_min = [e for e in errors if e.code == "ACTIVE_COUNT_BELOW_MINIMUM"]
    assert len(below_min) == 1
    assert below_min[0].severity == "warning"


def test_active_count_at_min_threshold_does_not_emit_below_minimum_error():
    registry = _registry_with_active_count(MIN_ACTIVE_CURRENCIES)
    errors, _ = validate_statistics(registry)
    codes = {e.code for e in errors}
    assert "ACTIVE_COUNT_BELOW_MINIMUM" not in codes


def test_low_active_count_emits_both_thresholds_independently():
    """A count below BOTH thresholds should surface both signals, not just
    the more severe one — that's the whole point of having two independent
    checks instead of one, per the issue's spec."""
    registry = _registry_with_active_count(5)
    errors, _ = validate_statistics(registry)
    codes = {e.code for e in errors}
    assert "ACTIVE_COUNT_LOW" in codes
    assert "ACTIVE_COUNT_BELOW_MINIMUM" in codes


def test_full_coverage_active_count_emits_neither_check():
    registry = _registry_with_active_count(180)
    errors, _ = validate_statistics(registry)
    codes = {e.code for e in errors}
    assert "ACTIVE_COUNT_LOW" not in codes
    assert "ACTIVE_COUNT_BELOW_MINIMUM" not in codes


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))