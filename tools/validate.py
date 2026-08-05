#!/usr/bin/env python3
"""
ISO 4217 Currency Registry — Comprehensive Validator

Validates iso4217.json against:
1. JSON Schema (structural and type correctness)
2. Data integrity rules (domain-specific constraints)
3. Cross-reference consistency (no duplicate codes, valid peg targets, etc.)
4. Business logic rules (currency relationships, conversion rates, etc.)

Usage:
    python tools/validate.py                    # Validate default registry
    python tools/validate.py --registry path    # Validate specific file
    python tools/validate.py --quiet            # Only print errors
    python tools/validate.py --json             # Output results as JSON

Exit codes:
    0 — All validations passed
    1 — Validation errors found
    2 — Fatal error (file not found, invalid JSON, etc.)
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REQUIRED_PYTHON = (3, 8)

# Active-currency count sanity check (issue #9). ISO 4217 currently defines
# roughly 180 active currency codes. Nothing previously checked that the
# registry's active count was in a plausible range at all — a registry with
# 5 active currencies passed validation cleanly, which is exactly how the
# 61/180 coverage gap shipped in v1.0.0 without any test catching it.
MIN_ACTIVE_CURRENCIES = 150   # Expected once full ISO 4217 coverage lands (v1.1.0 target)
WARN_ACTIVE_CURRENCIES = 100  # Below this, warn even if not yet treated as an error

# Currencies that ISO 4217 lists with N minor_units but market convention uses M
# Format: code -> (iso_minor_units, market_minor_units, explanation)
KNOWN_MARKET_CONVENTIONS = {
    "IDR": (2, 0, "ISO specifies 2 decimal places, but market practice quotes without decimals"),
    "ISK": (0, 0, "Officially 0 minor units per ISO 4217"),
}

# Currencies with known complexities worth validating
THREE_DECIMAL_CURRENCIES = {"KWD", "BHD", "OMR", "JOD", "TND", "LYD", "IQD"}

# Valid relationship types for country-currency associations
VALID_RELATIONSHIPS = {"issuing", "adopting", "territory", "parallel", "local_issue"}

# Valid peg mechanisms for stablecoins
VALID_PEG_MECHANISMS = {
    "Fiat-collateralized",
    "Crypto-overcollateralized",
    "Algorithmic",
    "Commodity-collateralized",
    "Hybrid",
}

# Valid non-ISO types
VALID_NON_ISO_TYPES = {"cryptocurrency", "stablecoin", "commodity", "basket", "offshore", "unit_of_account", "other"}

# Maximum reasonable minor_units (Ethereum = 18)
MAX_MINOR_UNITS = 18


# ---------------------------------------------------------------------------
# Data classes for structured results
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    """A single validation error."""
    severity: str  # "error" or "warning"
    category: str  # "schema", "integrity", "business_logic", "cross_reference"
    field: str     # JSON path or field name
    code: str      # Machine-readable error code
    message: str   # Human-readable description
    suggestion: Optional[str] = None  # How to fix it


@dataclass
class ValidationResult:
    """Aggregated validation results."""
    registry_path: str
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def is_valid(self) -> bool:
        return not self.has_errors


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_against_schema(registry: Dict, schema: Dict) -> List[ValidationError]:
    """Validate registry against JSON Schema. Returns list of schema errors."""
    errors: List[ValidationError] = []

    try:
        import jsonschema
        from jsonschema import validate, ValidationError as SchemaError

        validator = jsonschema.Draft7Validator(schema)
        schema_errors = sorted(validator.iter_errors(registry), key=lambda e: e.path)

        for err in schema_errors:
            path = " → ".join(str(p) for p in err.path) if err.path else "(root)"
            errors.append(ValidationError(
                severity="error",
                category="schema",
                field=path,
                code="SCHEMA_VIOLATION",
                message=err.message,
                suggestion="Check field types, required fields, and pattern constraints."
            ))

    except ImportError:
        errors.append(ValidationError(
            severity="warning",
            category="schema",
            field="(schema validation)",
            code="JSONSCHEMA_NOT_INSTALLED",
            message="jsonschema library not installed. Install with: pip install jsonschema",
            suggestion="Schema validation skipped. Install jsonschema for full validation."
        ))

    return errors


# ---------------------------------------------------------------------------
# Meta and source validation
# ---------------------------------------------------------------------------

def validate_meta(registry: Dict) -> List[ValidationError]:
    """Validate meta section of the registry."""
    errors: List[ValidationError] = []
    meta = registry.get("meta", {})

    # Version format
    version = meta.get("version", "")
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        errors.append(ValidationError(
            severity="error",
            category="integrity",
            field="meta.version",
            code="INVALID_VERSION",
            message=f"Version '{version}' is not valid semver (MAJOR.MINOR.PATCH)."
        ))

    # Updated date is not in the future
    updated = meta.get("updated", "")
    if updated:
        try:
            updated_date = date.fromisoformat(updated)
            if updated_date > date.today():
                errors.append(ValidationError(
                    severity="warning",
                    category="integrity",
                    field="meta.updated",
                    code="FUTURE_DATE",
                    message=f"Updated date '{updated}' is in the future.",
                    suggestion="Set updated to today's date or the date of last change."
                ))
        except ValueError:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field="meta.updated",
                code="INVALID_DATE",
                message=f"Updated date '{updated}' is not valid ISO 8601 (YYYY-MM-DD)."
            ))

    # Schema version matches
    schema_version = meta.get("schema_version", "")
    if schema_version != "1.0.0":
        errors.append(ValidationError(
            severity="warning",
            category="integrity",
            field="meta.schema_version",
            code="SCHEMA_VERSION_MISMATCH",
            message=f"Schema version is '{schema_version}', but validator expects '1.0.0'.",
            suggestion="Update schema_version or update the validator."
        ))

    return errors


def validate_source(registry: Dict) -> List[ValidationError]:
    """Validate source section."""
    errors: List[ValidationError] = []
    source = registry.get("source", {})

    # Amendment is a reasonable number
    amendment = source.get("last_amendment_applied")
    if amendment is not None:
        if not isinstance(amendment, int) or amendment < 1 or amendment > 500:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field="source.last_amendment_applied",
                code="INVALID_AMENDMENT",
                message=f"Amendment number {amendment} is out of expected range (1–500)."
            ))

    # Amendment date is consistent
    amd_date = source.get("last_amendment_date", "")
    if amd_date:
        try:
            date.fromisoformat(amd_date)
        except ValueError:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field="source.last_amendment_date",
                code="INVALID_DATE",
                message=f"Amendment date '{amd_date}' is not valid ISO 8601."
            ))

    # Verification date is not ancient
    verified = source.get("last_verified", "")
    if verified:
        try:
            verified_date = date.fromisoformat(verified)
            days_since = (date.today() - verified_date).days
            if days_since > 365:
                errors.append(ValidationError(
                    severity="warning",
                    category="integrity",
                    field="source.last_verified",
                    code="STALE_VERIFICATION",
                    message=f"Last verified {days_since} days ago. Consider re-verifying.",
                    suggestion="Re-verify against SWIFT table and central bank sources."
                ))
        except ValueError:
            pass  # Already caught elsewhere

    return errors


# ---------------------------------------------------------------------------
# Currency data integrity
# ---------------------------------------------------------------------------

def validate_active_currencies(active: List[Dict]) -> List[ValidationError]:
    """Validate the active currencies array."""
    errors: List[ValidationError] = []

    # NOTE: active-count plausibility (previously a flat "< 50 is an error"
    # check here) now lives in validate_statistics() as two graduated
    # thresholds (WARN_ACTIVE_CURRENCIES, MIN_ACTIVE_CURRENCIES), with
    # --allow-partial support for intentional partial releases. See issue #9.

    for i, currency in enumerate(active):
        code = currency.get("code", f"[index {i}]")
        prefix = f"currencies.active[{i}] ({code})"

        # Check required fields exist
        for field in ["code", "numeric", "name", "minor_units", "symbol", "entity", "central_bank", "countries", "is_independent"]:
            if field not in currency:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{prefix}.{field}",
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field}' is missing for {code}."
                ))

        # Code is 3 uppercase letters
        if not currency.get("code", "").isupper() or len(currency.get("code", "")) != 3:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field=f"{prefix}.code",
                code="INVALID_CODE_FORMAT",
                message=f"Currency code '{currency.get('code', '')}' must be exactly 3 uppercase letters."
            ))

        # Numeric code is 3 digits and matches code
        numeric = currency.get("numeric", "")
        if not numeric.isdigit() or len(numeric) != 3:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field=f"{prefix}.numeric",
                code="INVALID_NUMERIC_FORMAT",
                message=f"Numeric code '{numeric}' must be exactly 3 digits (as string)."
            ))

        # Minor units in range
        mu = currency.get("minor_units")
        if isinstance(mu, int):
            if mu < 0 or mu > MAX_MINOR_UNITS:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{prefix}.minor_units",
                    code="MINOR_UNITS_OUT_OF_RANGE",
                    message=f"minor_units={mu} is outside valid range [0, {MAX_MINOR_UNITS}]."
                ))
            # Check three-decimal currencies
            if mu == 3 and code not in THREE_DECIMAL_CURRENCIES:
                errors.append(ValidationError(
                    severity="warning",
                    category="business_logic",
                    field=f"{prefix}.minor_units",
                    code="UNEXPECTED_3_DECIMAL",
                    message=f"{code} has minor_units=3. This is unusual — verify against central bank spec.",
                    suggestion=f"Known 3-decimal currencies: {', '.join(sorted(THREE_DECIMAL_CURRENCIES))}."
                ))
            if code in THREE_DECIMAL_CURRENCIES and mu != 3:
                errors.append(ValidationError(
                    severity="error",
                    category="business_logic",
                    field=f"{prefix}.minor_units",
                    code="EXPECTED_3_DECIMAL",
                    message=f"{code} is known to have 3 minor units, but minor_units={mu}.",
                    suggestion="Verify against ISO 4217 and central bank specification."
                ))
            # Check known market conventions
            if code in KNOWN_MARKET_CONVENTIONS:
                iso_mu, market_mu, explanation = KNOWN_MARKET_CONVENTIONS[code]
                if mu == iso_mu and iso_mu != market_mu:
                    # ISO value is correct but differs from market — check for note
                    note = currency.get("note", "")
                    if not note:
                        errors.append(ValidationError(
                            severity="warning",
                            category="business_logic",
                            field=f"{prefix}.minor_units",
                            code="MISSING_MARKET_CONVENTION_NOTE",
                            message=f"{code}: {explanation}. Consider adding a 'note' field explaining this.",
                            suggestion=f"Add note: '{explanation}. This field follows the ISO standard. For display formatting, treat minor_units as {market_mu}.'"
                        ))

        # Peg consistency
        pegged_to = currency.get("pegged_to")
        is_independent = currency.get("is_independent")

        if pegged_to is not None and is_independent is True:
            errors.append(ValidationError(
                severity="error",
                category="business_logic",
                field=f"{prefix}.is_independent",
                code="PEGGED_BUT_INDEPENDENT",
                message=f"{code} is pegged to '{pegged_to}' but is_independent=true.",
                suggestion="Set is_independent=false for pegged currencies."
            ))
        if pegged_to is None and is_independent is False:
            errors.append(ValidationError(
                severity="error",
                category="business_logic",
                field=f"{prefix}.is_independent",
                code="FLOATING_BUT_NOT_INDEPENDENT",
                message=f"{code} has no peg but is_independent=false.",
                suggestion="Set is_independent=true for non-pegged currencies or specify pegged_to."
            ))

        # Peg fields completeness
        if pegged_to is not None:
            for peg_field in ["pegged_since", "peg_band_pct"]:
                if peg_field not in currency:
                    errors.append(ValidationError(
                        severity="error",
                        category="integrity",
                        field=f"{prefix}.{peg_field}",
                        code="MISSING_PEG_FIELD",
                        message=f"{code} is pegged but missing '{peg_field}' field."
                    ))

        # peg_type consistency — peg_type tells consumers how to interpret
        # pegged_to (parseable ISO code vs. free-text description). Without
        # this check, a currency could be pegged with no peg_type (leaving
        # consumers to guess), or peg_type could disagree with the actual
        # shape of pegged_to (e.g. peg_type="single" but pegged_to is a
        # basket description, or vice versa).
        peg_type = currency.get("peg_type")
        single_code_pattern = re.compile(r"^[A-Z]{3}$")

        if pegged_to is not None and peg_type is None:
            errors.append(ValidationError(
                severity="error",
                category="business_logic",
                field=f"{prefix}.peg_type",
                code="MISSING_PEG_TYPE",
                message=f"{code} is pegged to '{pegged_to}' but has no 'peg_type'.",
                suggestion="Set peg_type to 'single', 'basket', or 'undisclosed'."
            ))
        elif pegged_to is None and peg_type is not None:
            errors.append(ValidationError(
                severity="error",
                category="business_logic",
                field=f"{prefix}.peg_type",
                code="PEG_TYPE_WITHOUT_PEG",
                message=f"{code} has peg_type='{peg_type}' but pegged_to is null.",
                suggestion="Remove peg_type, or set pegged_to to describe the peg."
            ))
        elif peg_type is not None:
            if peg_type not in ("single", "basket", "undisclosed"):
                errors.append(ValidationError(
                    severity="error",
                    category="business_logic",
                    field=f"{prefix}.peg_type",
                    code="INVALID_PEG_TYPE",
                    message=f"{code} has peg_type='{peg_type}', not one of 'single', 'basket', 'undisclosed'."
                ))
            elif peg_type == "single" and not single_code_pattern.match(pegged_to):
                errors.append(ValidationError(
                    severity="error",
                    category="business_logic",
                    field=f"{prefix}.pegged_to",
                    code="PEG_TYPE_MISMATCH",
                    message=f"{code} has peg_type='single' but pegged_to='{pegged_to}' is not a bare 3-letter code.",
                    suggestion="Use peg_type='basket' or 'undisclosed' for free-text pegged_to values."
                ))
            elif peg_type in ("basket", "undisclosed") and single_code_pattern.match(pegged_to):
                errors.append(ValidationError(
                    severity="warning",
                    category="business_logic",
                    field=f"{prefix}.pegged_to",
                    code="PEG_TYPE_MISMATCH",
                    message=f"{code} has peg_type='{peg_type}' but pegged_to='{pegged_to}' looks like a bare currency code.",
                    suggestion="If this is really a single-currency peg, use peg_type='single' instead."
                ))

        # Countries validation
        countries = currency.get("countries", [])
        if not countries:
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field=f"{prefix}.countries",
                code="NO_COUNTRIES",
                message=f"{code} has no countries listed. At minimum, the issuing entity must be present."
            ))

        # Must have at least one issuing country
        has_issuer = any(c.get("relationship") == "issuing" for c in countries)
        if not has_issuer:
            errors.append(ValidationError(
                severity="error",
                category="business_logic",
                field=f"{prefix}.countries",
                code="NO_ISSUER",
                message=f"{code} has no country with relationship='issuing'.",
                suggestion="At least one country must be marked as the issuing authority."
            ))

        # Country codes and relationships
        for j, country in enumerate(countries):
            cprefix = f"{prefix}.countries[{j}]"
            country_code = country.get("code", "")

            # Country code format
            if not country_code.isupper() or len(country_code) != 2:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{cprefix}.code",
                    code="INVALID_COUNTRY_CODE",
                    message=f"Country code '{country_code}' must be exactly 2 uppercase letters (ISO 3166-1 alpha-2)."
                ))

            # Relationship type
            relationship = country.get("relationship", "")
            if relationship not in VALID_RELATIONSHIPS:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{cprefix}.relationship",
                    code="INVALID_RELATIONSHIP",
                    message=f"Relationship '{relationship}' is not valid. Must be one of: {', '.join(sorted(VALID_RELATIONSHIPS))}."
                ))

            # Name present
            if not country.get("name", "").strip():
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{cprefix}.name",
                    code="MISSING_COUNTRY_NAME",
                    message=f"Country name is empty for code '{country_code}'."
                ))

        # Symbol should be non-empty for major currencies
        symbol = currency.get("symbol", "")
        if not symbol and code not in {"USDC", "DAI"}:
            errors.append(ValidationError(
                severity="warning",
                category="business_logic",
                field=f"{prefix}.symbol",
                code="EMPTY_SYMBOL",
                message=f"{code} has an empty symbol. Is there really no display symbol?",
                suggestion="Use the currency code itself (e.g., 'CHF') if no dedicated symbol exists."
            ))

        # Entity should not be empty
        entity = currency.get("entity", "")
        if not entity.strip():
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field=f"{prefix}.entity",
                code="EMPTY_ENTITY",
                message=f"{code} has an empty entity field."
            ))

        # Central bank should not be empty
        central_bank = currency.get("central_bank", "")
        if not central_bank.strip():
            errors.append(ValidationError(
                severity="error",
                category="integrity",
                field=f"{prefix}.central_bank",
                code="EMPTY_CENTRAL_BANK",
                message=f"{code} has an empty central_bank field."
            ))

    return errors


def validate_withdrawn_currencies(withdrawn: List[Dict]) -> List[ValidationError]:
    """Validate the withdrawn currencies array."""
    errors: List[ValidationError] = []

    for i, currency in enumerate(withdrawn):
        code = currency.get("code", f"[index {i}]")
        prefix = f"currencies.withdrawn[{i}] ({code})"

        # Required fields
        for field in ["code", "numeric", "name", "minor_units", "withdrawn_date", "replaced_by", "conversion_rate"]:
            if field not in currency:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{prefix}.{field}",
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field}' is missing for withdrawn currency {code}."
                ))

        # Conversion rate is positive
        rate = currency.get("conversion_rate")
        if isinstance(rate, (int, float)):
            if rate <= 0:
                errors.append(ValidationError(
                    severity="error",
                    category="business_logic",
                    field=f"{prefix}.conversion_rate",
                    code="INVALID_CONVERSION_RATE",
                    message=f"Conversion rate for {code} is {rate}. Must be positive.",
                    suggestion="Conversion rate is units of this currency per 1 unit of replacement."
                ))

        # Withdrawn date is in the past
        wd_date = currency.get("withdrawn_date", "")
        if wd_date:
            try:
                wd = date.fromisoformat(wd_date)
                if wd > date.today():
                    errors.append(ValidationError(
                        severity="warning",
                        category="integrity",
                        field=f"{prefix}.withdrawn_date",
                        code="FUTURE_WITHDRAWAL_DATE",
                        message=f"Withdrawal date '{wd_date}' for {code} is in the future."
                    ))
            except ValueError:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{prefix}.withdrawn_date",
                    code="INVALID_DATE",
                    message=f"Withdrawal date '{wd_date}' for {code} is not valid ISO 8601."
                ))

        # Code format
        if not currency.get("code", "").isupper() or len(currency.get("code", "")) not in [3, 7]:
            errors.append(ValidationError(
                severity="warning",
                category="integrity",
                field=f"{prefix}.code",
                code="UNUSUAL_CODE_LENGTH",
                message=f"Withdrawn code '{currency.get('code', '')}' has unusual length.",
                suggestion="ISO codes are typically 3 letters. Special cases like 'MXN_OLD' should have a note."
            ))

    return errors


# Phrases that count as a valid "this is not an ISO 4217 code" disclaimer.
# Not an exhaustive NLP check — a literal substring match — so keep this list
# in sync with whatever phrasing is actually used in iso4217.json. This exists
# because "not an iso" alone missed "Not an official ISO 4217 code" (CNH's
# actual wording), silently producing a false-positive warning.
_NON_ISO_DISCLAIMER_PHRASES = (
    "not an iso",
    "not an official iso",
    "not a currency",
)


def _has_non_iso_disclaimer(note: str) -> bool:
    """True if `note` contains a recognized non-ISO-4217 disclaimer phrase."""
    lowered = note.lower()
    return any(phrase in lowered for phrase in _NON_ISO_DISCLAIMER_PHRASES)


def validate_non_iso(non_iso: Dict) -> List[ValidationError]:
    """Validate non-ISO currencies section."""
    errors: List[ValidationError] = []

    categories = ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]

    for category in categories:
        items = non_iso.get(category, [])
        for i, item in enumerate(items):
            code = item.get("code", f"[index {i}]")
            prefix = f"non_iso.{category}[{i}] ({code})"

            # Must have a type field
            item_type = item.get("type", "")
            if not item_type:
                errors.append(ValidationError(
                    severity="error",
                    category="integrity",
                    field=f"{prefix}.type",
                    code="MISSING_TYPE",
                    message=f"Non-ISO item {code} is missing 'type' field."
                ))

            # Must have note explaining non-ISO status — but ONLY for items that
            # actually are non-ISO. special_purpose is the one category that can
            # legitimately hold genuine ISO 4217 codes (XDR, XUA, XSU are all
            # real ISO fund/unit-of-account codes; they live in special_purpose
            # because they're not tradable currencies, not because they lack ISO
            # standing). cryptocurrencies, stablecoins, and commodities are never
            # ISO 4217 codes, so they keep the original text-based check.
            note = item.get("note", "")

            if category == "special_purpose":
                iso_status = item.get("iso_status")
                if iso_status is None:
                    # No ground-truth field to check against — schema validation
                    # will already flag this as missing a required field, but
                    # warn here too in case validate.py is ever run standalone
                    # against data that skipped schema validation.
                    errors.append(ValidationError(
                        severity="warning",
                        category="business_logic",
                        field=f"{prefix}.iso_status",
                        code="MISSING_ISO_STATUS",
                        message=f"special_purpose item {code} has no 'iso_status' field, so its ISO 4217 status can't be verified.",
                        suggestion="Set iso_status to 'iso_code', 'market_convention', or 'obsolete_iso'."
                    ))
                elif iso_status in ("market_convention", "obsolete_iso"):
                    if not _has_non_iso_disclaimer(note):
                        errors.append(ValidationError(
                            severity="warning",
                            category="business_logic",
                            field=f"{prefix}.note",
                            code="MISSING_NON_ISO_DISCLAIMER",
                            message=f"special_purpose item {code} has iso_status='{iso_status}' but its note doesn't clarify that it is not an ISO 4217 code.",
                            suggestion="Add note like: 'Not an ISO 4217 code. Included for [reason].'"
                        ))
                # iso_status == "iso_code": genuinely ISO-defined, no disclaimer needed.
            elif not _has_non_iso_disclaimer(note):
                errors.append(ValidationError(
                    severity="warning",
                    category="business_logic",
                    field=f"{prefix}.note",
                    code="MISSING_NON_ISO_DISCLAIMER",
                    message=f"Non-ISO item {code} should have a note clarifying it is not an ISO 4217 code.",
                    suggestion="Add note like: 'Not an ISO 4217 code. Included for [reason].'"
                ))

            # Stablecoin-specific checks
            if category == "stablecoins":
                if "pegged_to" not in item:
                    errors.append(ValidationError(
                        severity="error",
                        category="integrity",
                        field=f"{prefix}.pegged_to",
                        code="STABLECOIN_MISSING_PEG",
                        message=f"Stablecoin {code} is missing 'pegged_to' field."
                    ))
                if "peg_mechanism" not in item:
                    errors.append(ValidationError(
                        severity="error",
                        category="integrity",
                        field=f"{prefix}.peg_mechanism",
                        code="STABLECOIN_MISSING_MECHANISM",
                        message=f"Stablecoin {code} is missing 'peg_mechanism' field."
                    ))
                else:
                    mechanism = item.get("peg_mechanism", "")
                    if mechanism not in VALID_PEG_MECHANISMS:
                        errors.append(ValidationError(
                            severity="error",
                            category="integrity",
                            field=f"{prefix}.peg_mechanism",
                            code="INVALID_PEG_MECHANISM",
                            message=f"Peg mechanism '{mechanism}' is not valid. Must be one of: {', '.join(sorted(VALID_PEG_MECHANISMS))}."
                        ))

            # Commodity-specific checks
            if category == "commodities":
                if not item.get("code", "").startswith("X"):
                    errors.append(ValidationError(
                        severity="warning",
                        category="business_logic",
                        field=f"{prefix}.code",
                        code="COMMODITY_CODE_CONVENTION",
                        message=f"Commodity code '{code}' doesn't follow X-prefix convention (XAU, XAG, etc.)."
                    ))

    return errors


# ---------------------------------------------------------------------------
# Cross-reference validation (across all categories)
# ---------------------------------------------------------------------------

def validate_cross_references(registry: Dict) -> List[ValidationError]:
    """Validate references between different parts of the registry."""
    errors: List[ValidationError] = []

    active = registry.get("currencies", {}).get("active", [])
    withdrawn = registry.get("currencies", {}).get("withdrawn", [])
    non_iso = registry.get("non_iso", {})

    # Build sets of all codes
    active_codes: Dict[str, int] = {}
    for i, c in enumerate(active):
        code = c.get("code", "")
        if code in active_codes:
            errors.append(ValidationError(
                severity="error",
                category="cross_reference",
                field="currencies.active",
                code="DUPLICATE_ACTIVE_CODE",
                message=f"Duplicate active currency code '{code}' at indices {active_codes[code]} and {i}."
            ))
        active_codes[code] = i

    withdrawn_codes: Dict[str, int] = {}
    for i, c in enumerate(withdrawn):
        code = c.get("code", "")
        if code in withdrawn_codes:
            errors.append(ValidationError(
                severity="error",
                category="cross_reference",
                field="currencies.withdrawn",
                code="DUPLICATE_WITHDRAWN_CODE",
                message=f"Duplicate withdrawn currency code '{code}' at indices {withdrawn_codes[code]} and {i}."
            ))
        withdrawn_codes[code] = i

    # Active and withdrawn should not overlap
    overlap = set(active_codes.keys()) & set(withdrawn_codes.keys())
    if overlap:
        errors.append(ValidationError(
            severity="error",
            category="cross_reference",
            field="currencies",
            code="ACTIVE_WITHDRAWN_OVERLAP",
            message=f"Codes found in both active and withdrawn: {sorted(overlap)}.",
            suggestion="A currency cannot be both active and withdrawn. Check the codes."
        ))

    # Numeric code uniqueness. Unlike alphabetic codes, numeric codes CAN
    # legitimately repeat between active and withdrawn — ISO 4217 has
    # reused numeric codes after currency revaluations (e.g. MXN/MXN_OLD
    # both use 484). That reuse is allowed and only warned on. Within a
    # single category (active-only, withdrawn-only), a duplicate numeric
    # code is always a data error — two currently-circulating or two
    # historical currencies should never share one.
    active_numeric: Dict[str, List[str]] = {}
    for c in active:
        numeric = c.get("numeric")
        if numeric:
            active_numeric.setdefault(numeric, []).append(c.get("code", "?"))

    for numeric, codes in active_numeric.items():
        if len(codes) > 1:
            errors.append(ValidationError(
                severity="error",
                category="cross_reference",
                field="currencies.active[*].numeric",
                code="DUPLICATE_ACTIVE_NUMERIC",
                message=f"Numeric code '{numeric}' is used by multiple active currencies: {sorted(codes)}.",
                suggestion="Each active currency must have a unique numeric code."
            ))

    withdrawn_numeric: Dict[str, List[str]] = {}
    for c in withdrawn:
        numeric = c.get("numeric")
        if numeric:
            withdrawn_numeric.setdefault(numeric, []).append(c.get("code", "?"))

    for numeric, codes in withdrawn_numeric.items():
        if len(codes) > 1:
            errors.append(ValidationError(
                severity="error",
                category="cross_reference",
                field="currencies.withdrawn[*].numeric",
                code="DUPLICATE_WITHDRAWN_NUMERIC",
                message=f"Numeric code '{numeric}' is used by multiple withdrawn currencies: {sorted(codes)}.",
                suggestion="Each withdrawn currency must have a unique numeric code."
            ))

    numeric_overlap = set(active_numeric.keys()) & set(withdrawn_numeric.keys())
    if numeric_overlap:
        affected = []
        for numeric in sorted(numeric_overlap):
            affected.append(f"{numeric} ({'/'.join(active_numeric[numeric])} active, {'/'.join(withdrawn_numeric[numeric])} withdrawn)")
        errors.append(ValidationError(
            severity="warning",
            category="cross_reference",
            field="currencies",
            code="NUMERIC_CODE_REUSE",
            message=f"Numeric code(s) shared between active and withdrawn currencies (historical reuse): {'; '.join(affected)}.",
            suggestion="Expected for legitimate historical reuse (e.g. MXN/MXN_OLD share 484). Verify each case is intentional, and never use numeric code as a unique key spanning active + withdrawn."
        ))

    # Non-ISO codes should not overlap with ISO codes
    all_iso_codes = set(active_codes.keys()) | set(withdrawn_codes.keys())
    non_iso_categories = ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]
    for category in non_iso_categories:
        for item in non_iso.get(category, []):
            code = item.get("code", "")
            if code in all_iso_codes:
                errors.append(ValidationError(
                    severity="error",
                    category="cross_reference",
                    field=f"non_iso.{category}",
                    code="NON_ISO_OVERLAPS_ISO",
                    message=f"Non-ISO code '{code}' in '{category}' conflicts with an ISO 4217 code.",
                    suggestion="Remove from non-ISO or verify it is genuinely not an ISO code."
                ))

    # Non-ISO codes should be unique across non-ISO categories
    non_iso_codes: Dict[str, List[str]] = {}
    for category in non_iso_categories:
        for item in non_iso.get(category, []):
            code = item.get("code", "")
            if code not in non_iso_codes:
                non_iso_codes[code] = []
            non_iso_codes[code].append(category)

    for code, cats in non_iso_codes.items():
        if len(cats) > 1:
            errors.append(ValidationError(
                severity="error",
                category="cross_reference",
                field="non_iso",
                code="DUPLICATE_NON_ISO_CODE",
                message=f"Non-ISO code '{code}' appears in multiple categories: {cats}.",
                suggestion="Each non-ISO code should appear in exactly one category."
            ))

    # Validate peg targets exist in active currencies.
    # Only meaningful for peg_type='single' — 'basket'/'undisclosed' pegs
    # have a free-text pegged_to that isn't a currency reference at all.
    for c in active:
        pegged_to = c.get("pegged_to")
        peg_type = c.get("peg_type")
        if pegged_to and peg_type == "single":
            if pegged_to not in active_codes:
                errors.append(ValidationError(
                    severity="error",
                    category="cross_reference",
                    field=f"currencies.active[{c.get('code', '?')}].pegged_to",
                    code="PEG_TARGET_NOT_FOUND",
                    message=f"{c.get('code', '?')} is pegged to '{pegged_to}' which is not an active currency.",
                    suggestion="Peg targets must be active ISO 4217 codes. Add the currency or fix the reference."
                ))

    # Validate replaced_by targets exist (in active or withdrawn)
    for c in withdrawn:
        replaced_by = c.get("replaced_by", "")
        if replaced_by:
            if replaced_by not in active_codes and replaced_by not in withdrawn_codes:
                errors.append(ValidationError(
                    severity="warning",
                    category="cross_reference",
                    field=f"currencies.withdrawn[{c.get('code', '?')}].replaced_by",
                    code="REPLACEMENT_NOT_FOUND",
                    message=f"Withdrawn currency {c.get('code', '?')} replaced by '{replaced_by}' which is not in the registry.",
                    suggestion="Add the replacement currency or verify the code."
                ))

    # Validate stablecoin pegs target real currencies
    for item in non_iso.get("stablecoins", []):
        pegged_to = item.get("pegged_to", "")
        if pegged_to and pegged_to not in active_codes and pegged_to not in withdrawn_codes:
            errors.append(ValidationError(
                severity="warning",
                category="cross_reference",
                field=f"non_iso.stablecoins[{item.get('code', '?')}].pegged_to",
                code="STABLECOIN_PEG_NOT_FOUND",
                message=f"Stablecoin {item.get('code', '?')} pegged to '{pegged_to}' which is not in the ISO currency lists.",
                suggestion="Stablecoin pegs should reference ISO 4217 codes."
            ))

    return errors


# ---------------------------------------------------------------------------
# Statistical checks (anomaly detection)
# ---------------------------------------------------------------------------

def validate_statistics(registry: Dict, allow_partial: bool = False) -> Tuple[List[ValidationError], Dict[str, Any]]:
    """Run statistical checks and return errors plus stats dictionary."""
    errors: List[ValidationError] = []
    stats: Dict[str, Any] = {}

    active = registry.get("currencies", {}).get("active", [])
    withdrawn = registry.get("currencies", {}).get("withdrawn", [])
    non_iso = registry.get("non_iso", {})

    # Count statistics
    stats["active_count"] = len(active)
    stats["withdrawn_count"] = len(withdrawn)
    stats["crypto_count"] = len(non_iso.get("cryptocurrencies", []))
    stats["stablecoin_count"] = len(non_iso.get("stablecoins", []))
    stats["commodity_count"] = len(non_iso.get("commodities", []))
    stats["special_purpose_count"] = len(non_iso.get("special_purpose", []))

    # Active currency count plausibility (issue #9). A registry that claims
    # ISO 4217 coverage but has an implausibly low active count should not
    # pass validation silently — that gap is exactly what let v1.0.0 ship
    # with 61/180 currencies unnoticed. These are two independent
    # thresholds, not an if/elif: a very low count (e.g. 5) is both below
    # WARN_ACTIVE_CURRENCIES and below MIN_ACTIVE_CURRENCIES, and should
    # surface both signals rather than only the more severe one.
    active_count = stats["active_count"]

    if active_count < WARN_ACTIVE_CURRENCIES:
        errors.append(ValidationError(
            severity="warning",
            category="statistical",
            field="currencies.active",
            code="ACTIVE_COUNT_LOW",
            message=f"Only {active_count} active currencies found (below {WARN_ACTIVE_CURRENCIES}).",
            suggestion="Consider expanding coverage toward full ISO 4217."
        ))

    if active_count < MIN_ACTIVE_CURRENCIES:
        message = (
            f"Only {active_count} active currencies found. Expected at least "
            f"{MIN_ACTIVE_CURRENCIES} per ISO 4217. If this is intentional "
            f"(partial release), suppress with --allow-partial."
        )
        errors.append(ValidationError(
            severity="warning" if allow_partial else "error",
            category="statistical",
            field="currencies.active",
            code="ACTIVE_COUNT_BELOW_MINIMUM",
            message=message,
            suggestion=(
                "Add more active currencies toward full ISO 4217 coverage, "
                "or run with --allow-partial if this partial release is intentional."
            )
        ))

    # Distribution of minor_units
    mu_dist = Counter(c.get("minor_units") for c in active if "minor_units" in c)
    stats["minor_units_distribution"] = dict(sorted(mu_dist.items()))

    # Check for unexpected minor_units values
    for mu, count in mu_dist.items():
        if mu not in [0, 2, 3] and count > 0:
            errors.append(ValidationError(
                severity="warning",
                category="statistical",
                field="currencies.active[*].minor_units",
                code="UNUSUAL_MINOR_UNITS_COUNT",
                message=f"{count} active currencies have minor_units={mu}. This is unusual — most currencies use 0, 2, or 3.",
                suggestion="Verify these currencies against ISO 4217 specifications."
            ))

    # Peg distribution
    pegged_count = sum(1 for c in active if c.get("pegged_to") is not None)
    independent_count = sum(1 for c in active if c.get("is_independent") is True)
    stats["pegged_count"] = pegged_count
    stats["independent_count"] = independent_count

    # Most common peg targets (peg_type='single' only — basket/undisclosed
    # pegged_to values are descriptions, not currency codes, and shouldn't
    # be counted as "targets").
    peg_targets = Counter(
        c.get("pegged_to") for c in active
        if c.get("pegged_to") and c.get("peg_type") == "single"
    )
    stats["peg_targets"] = dict(peg_targets.most_common(10))

    # Country coverage
    all_countries: Dict[str, int] = {}
    for c in active:
        for country in c.get("countries", []):
            code = country.get("code", "")
            if code:
                all_countries[code] = all_countries.get(code, 0) + 1
    stats["unique_countries"] = len(all_countries)
    stats["total_country_references"] = sum(all_countries.values())

    # Countries claimed by multiple currencies
    multi_currency_countries = {code: count for code, count in all_countries.items() if count > 1}
    if len(multi_currency_countries) > 50:
        errors.append(ValidationError(
            severity="warning",
            category="statistical",
            field="currencies.active[*].countries",
            code="MANY_MULTI_CURRENCY_COUNTRIES",
            message=f"{len(multi_currency_countries)} countries are associated with multiple currencies. This may indicate incorrect country assignments.",
            suggestion="Review countries with >1 currency association to verify they are correct."
        ))

    stats["multi_currency_countries"] = len(multi_currency_countries)

    return errors, stats


# ---------------------------------------------------------------------------
# Main validation orchestrator
# ---------------------------------------------------------------------------

def load_registry(path: Path) -> Dict:
    """Load and parse the registry JSON file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"FATAL: Registry file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"FATAL: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def load_schema(path: Path) -> Optional[Dict]:
    """Load the JSON Schema file. Returns None if not found."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"FATAL: Invalid JSON Schema: {e}", file=sys.stderr)
        sys.exit(2)


def validate(registry_path: Path, schema_path: Optional[Path] = None, allow_partial: bool = False) -> ValidationResult:
    """Run all validations and return structured results."""
    result = ValidationResult(registry_path=str(registry_path))

    # Load files
    registry = load_registry(registry_path)
    schema = load_schema(schema_path) if schema_path else None

    if schema_path is None:
        default_schema = registry_path.parent / "schema.json"
        schema = load_schema(default_schema)

    # 1. Schema validation
    if schema:
        result.errors.extend(validate_against_schema(registry, schema))
    else:
        result.warnings.append(ValidationError(
            severity="warning",
            category="schema",
            field="(schema file)",
            code="SCHEMA_NOT_FOUND",
            message="schema.json not found. Structural validation skipped.",
            suggestion="Create schema.json or provide path with --schema."
        ))

    # 2. Meta validation
    result.errors.extend(validate_meta(registry))

    # 3. Source validation
    result.errors.extend(validate_source(registry))

    # 4. Currency validation
    currencies = registry.get("currencies", {})
    result.errors.extend(validate_active_currencies(currencies.get("active", [])))
    result.errors.extend(validate_withdrawn_currencies(currencies.get("withdrawn", [])))

    # 5. Non-ISO validation
    non_iso = registry.get("non_iso", {})
    if non_iso:
        result.errors.extend(validate_non_iso(non_iso))

    # 6. Cross-reference validation
    result.errors.extend(validate_cross_references(registry))

    # 7. Statistical checks
    stat_errors, stats = validate_statistics(registry, allow_partial=allow_partial)
    result.errors.extend(stat_errors)
    result.stats = stats

    # Separate errors and warnings
    true_errors = [e for e in result.errors if e.severity == "error"]
    warnings = [e for e in result.errors if e.severity == "warning"]
    result.errors = true_errors
    result.warnings = warnings

    return result


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_result(result: ValidationResult, quiet: bool = False, json_output: bool = False) -> str:
    """Format validation results for display."""
    if json_output:
        return json.dumps({
            "valid": result.is_valid,
            "registry": result.registry_path,
            "errors": [
                {"severity": e.severity, "category": e.category, "field": e.field,
                 "code": e.code, "message": e.message, "suggestion": e.suggestion}
                for e in result.errors
            ],
            "warnings": [
                {"severity": w.severity, "category": w.category, "field": w.field,
                 "code": w.code, "message": w.message, "suggestion": w.suggestion}
                for w in result.warnings
            ],
            "stats": result.stats
        }, indent=2)

    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("  ISO 4217 Currency Registry — Validation Report")
    lines.append("=" * 70)
    lines.append(f"  Registry: {result.registry_path}")
    lines.append(f"  Errors:   {len(result.errors)}")
    lines.append(f"  Warnings: {len(result.warnings)}")
    lines.append("=" * 70)

    # Statistics (always show, even in quiet mode stats are useful)
    if result.stats:
        lines.append("")
        lines.append("  Statistics:")
        lines.append(f"    Active currencies:     {result.stats.get('active_count', 0)}")
        lines.append(f"    Withdrawn currencies:  {result.stats.get('withdrawn_count', 0)}")
        lines.append(f"    Cryptocurrencies:      {result.stats.get('crypto_count', 0)}")
        lines.append(f"    Stablecoins:           {result.stats.get('stablecoin_count', 0)}")
        lines.append(f"    Commodities:           {result.stats.get('commodity_count', 0)}")
        lines.append(f"    Special purpose:       {result.stats.get('special_purpose_count', 0)}")
        lines.append(f"    Pegged currencies:     {result.stats.get('pegged_count', 0)}")
        lines.append(f"    Independent currencies:{result.stats.get('independent_count', 0)}")
        lines.append(f"    Unique countries:      {result.stats.get('unique_countries', 0)}")

        mu_dist = result.stats.get("minor_units_distribution", {})
        if mu_dist:
            mu_str = ", ".join(f"{mu}: {count}" for mu, count in mu_dist.items())
            lines.append(f"    Minor units dist:      {mu_str}")

    # Errors
    if result.errors:
        lines.append("")
        lines.append(f"  ❌ ERRORS ({len(result.errors)}):")
        lines.append("  " + "-" * 68)
        for i, err in enumerate(result.errors, 1):
            lines.append(f"  [{i}] [{err.code}] {err.field}")
            lines.append(f"      {err.message}")
            if err.suggestion:
                lines.append(f"      → {err.suggestion}")
            lines.append("")

    # Warnings
    if result.warnings and not quiet:
        lines.append(f"  ⚠️  WARNINGS ({len(result.warnings)}):")
        lines.append("  " + "-" * 68)
        for i, warn in enumerate(result.warnings, 1):
            lines.append(f"  [{i}] [{warn.code}] {warn.field}")
            lines.append(f"      {warn.message}")
            if warn.suggestion:
                lines.append(f"      → {warn.suggestion}")
            lines.append("")

    # Summary
    lines.append("  " + "=" * 68)
    if result.is_valid:
        lines.append("  ✅ VALIDATION PASSED")
        if result.warnings:
            lines.append(f"     ({len(result.warnings)} warning(s) — review above)")
    else:
        lines.append(f"  ❌ VALIDATION FAILED — {len(result.errors)} error(s) must be fixed")
    lines.append("  " + "=" * 68)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ISO 4217 Currency Registry — Comprehensive Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/validate.py                          # Validate default registry
  python tools/validate.py --registry custom.json   # Validate specific file
  python tools/validate.py --quiet                  # Only show errors
  python tools/validate.py --json                   # JSON output for CI/CD
  python tools/validate.py --schema custom.json     # Use custom schema
  python tools/validate.py --allow-partial          # Allow partial ISO coverage (e.g. v1.0.0)
        """
    )

    parser.add_argument(
        "--registry", "-r",
        type=Path,
        default=None,
        help="Path to iso4217.json (default: iso4217.json in project root)"
    )
    parser.add_argument(
        "--schema", "-s",
        type=Path,
        default=None,
        help="Path to schema.json (default: schema.json in same directory as registry)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress warnings, only show errors"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON (useful for CI/CD integration)"
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Downgrade the active-currency-count-below-minimum error to a "
            f"warning (still errors if below {WARN_ACTIVE_CURRENCIES} via the "
            "separate low-count warning). Use for intentional partial "
            f"releases (e.g. v1.0.0's 61 currencies, below the {MIN_ACTIVE_CURRENCIES} "
            "expected for full ISO 4217 coverage) so CI can pass while the "
            "gap is still visibly flagged rather than silently ignored."
        )
    )

    args = parser.parse_args()

    # Resolve paths
    if args.registry:
        registry_path = args.registry.resolve()
    else:
        # Default: find iso4217.json relative to this script
        script_dir = Path(__file__).resolve().parent
        registry_path = (script_dir.parent / "iso4217.json").resolve()

    if not registry_path.exists():
        print(f"FATAL: Registry not found at {registry_path}", file=sys.stderr)
        print("Use --registry to specify the path.", file=sys.stderr)
        sys.exit(2)

    # Run validation
    result = validate(registry_path, args.schema, allow_partial=args.allow_partial)

    # Output
    output = format_result(result, quiet=args.quiet, json_output=args.json)
    print(output)

    # Exit code
    if result.is_valid:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < REQUIRED_PYTHON:
        print(f"FATAL: Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required. You have {sys.version}.",
              file=sys.stderr)
        sys.exit(2)

    main()