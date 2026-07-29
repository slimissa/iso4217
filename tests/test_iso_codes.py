"""
Tests for ISO 4217 data integrity.

Verifies specific known facts about currencies that must be true
if the data is correct. These are ground-truth assertions —
if any of these fail, the registry data is wrong.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.validate import load_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry():
    """Load the registry. Called per-test for isolation."""
    return load_registry(PROJECT_ROOT / "iso4217.json")


def _active(registry, code):
    """Get an active currency by code, or None."""
    for c in registry["currencies"]["active"]:
        if c["code"] == code:
            return c
    return None


def _withdrawn(registry, code):
    """Get a withdrawn currency by code, or None."""
    for c in registry["currencies"]["withdrawn"]:
        if c["code"] == code:
            return c
    return None


def _non_iso(registry, category, code):
    """Get a non-ISO currency by category and code, or None."""
    items = registry.get("non_iso", {}).get(category, [])
    for c in items:
        if c["code"] == code:
            return c
    return None


def _active_codes(registry):
    """Set of all active currency codes."""
    return {c["code"] for c in registry["currencies"]["active"]}


# ---------------------------------------------------------------------------
# Minor unit facts — ground truth from ISO 4217
# ---------------------------------------------------------------------------

class TestMinorUnits:
    """Currencies with specific minor unit values per ISO 4217."""

    def test_jpy_has_zero_minor_units(self):
        r = _registry()
        jpy = _active(r, "JPY")
        assert jpy is not None, "JPY not found in active currencies"
        assert jpy["minor_units"] == 0, f"JPY minor_units={jpy['minor_units']}, expected 0"

    def test_krw_has_zero_minor_units(self):
        r = _registry()
        krw = _active(r, "KRW")
        assert krw is not None, "KRW not found in active currencies"
        assert krw["minor_units"] == 0

    def test_vnd_has_zero_minor_units(self):
        r = _registry()
        vnd = _active(r, "VND")
        assert vnd is not None, "VND not found in active currencies"
        assert vnd["minor_units"] == 0

    def test_isk_has_zero_minor_units(self):
        r = _registry()
        isk = _active(r, "ISK")
        assert isk is not None, "ISK not found in active currencies"
        assert isk["minor_units"] == 0

    def test_clp_has_zero_minor_units(self):
        r = _registry()
        clp = _active(r, "CLP")
        assert clp is not None, "CLP not found in active currencies"
        assert clp["minor_units"] == 0

    # --- 3-decimal currencies (dinar subdivisions) ---

    THREE_DECIMAL = ["KWD", "BHD", "OMR", "JOD", "TND", "LYD", "IQD"]

    def test_three_decimal_currencies_exist_and_are_correct(self):
        """Every known 3-decimal currency must exist with minor_units=3."""
        r = _registry()
        for code in self.THREE_DECIMAL:
            c = _active(r, code)
            assert c is not None, f"{code} not found in active currencies"
            assert c["minor_units"] == 3, (
                f"{code} minor_units={c['minor_units']}, expected 3"
            )

    def test_no_unexpected_three_decimal_currencies(self):
        """No currency outside the known list has 3 minor units."""
        r = _registry()
        known = set(self.THREE_DECIMAL)
        for c in r["currencies"]["active"]:
            if c["minor_units"] == 3:
                assert c["code"] in known, (
                    f"Unexpected 3-decimal currency: {c['code']}. "
                    f"If this is correct, add it to THREE_DECIMAL."
                )


# ---------------------------------------------------------------------------
# Peg facts
# ---------------------------------------------------------------------------

class TestPegs:
    """Currencies with known peg relationships."""

    def test_aed_pegged_to_usd(self):
        r = _registry()
        aed = _active(r, "AED")
        assert aed is not None
        assert aed["pegged_to"] == "USD"
        assert aed["is_independent"] is False
        assert aed["peg_rate"] == 3.6725
        assert aed["peg_band_pct"] == 0.0

    def test_sar_pegged_to_usd(self):
        r = _registry()
        sar = _active(r, "SAR")
        assert sar is not None
        assert sar["pegged_to"] == "USD"
        assert sar["peg_rate"] == 3.75

    def test_qar_pegged_to_usd(self):
        r = _registry()
        qar = _active(r, "QAR")
        assert qar is not None
        assert qar["pegged_to"] == "USD"
        assert qar["peg_rate"] == 3.64

    def test_hkd_pegged_to_usd(self):
        r = _registry()
        hkd = _active(r, "HKD")
        assert hkd is not None
        assert hkd["pegged_to"] == "USD"
        assert hkd["peg_rate"] == 7.80

    def test_jod_pegged_to_usd(self):
        r = _registry()
        jod = _active(r, "JOD")
        assert jod is not None
        assert jod["pegged_to"] == "USD"

    def test_bhd_pegged_to_usd(self):
        r = _registry()
        bhd = _active(r, "BHD")
        assert bhd is not None
        assert bhd["pegged_to"] == "USD"

    def test_omr_pegged_to_usd(self):
        r = _registry()
        omr = _active(r, "OMR")
        assert omr is not None
        assert omr["pegged_to"] == "USD"

    def test_dkk_pegged_to_eur(self):
        r = _registry()
        dkk = _active(r, "DKK")
        assert dkk is not None
        assert dkk["pegged_to"] == "EUR"
        assert dkk["peg_band_pct"] == 2.25

    def test_bgn_pegged_to_eur(self):
        r = _registry()
        bgn = _active(r, "BGN")
        assert bgn is not None
        assert bgn["pegged_to"] == "EUR"
        assert bgn["peg_band_pct"] == 0.0
        assert bgn["is_independent"] is False

    def test_mad_pegged_to_basket(self):
        r = _registry()
        mad = _active(r, "MAD")
        assert mad is not None
        # MAD is pegged to EUR+USD basket
        assert mad["pegged_to"] is not None
        assert "basket" in mad["pegged_to"].lower() or "EUR" in str(mad["pegged_to"])

    def test_kwd_pegged_to_basket(self):
        r = _registry()
        kwd = _active(r, "KWD")
        assert kwd is not None
        assert kwd["pegged_to"] is not None
        assert "basket" in kwd["pegged_to"].lower()


# ---------------------------------------------------------------------------
# Independence facts
# ---------------------------------------------------------------------------

class TestIndependence:
    """Currencies that must be independent (freely floating)."""

    MAJORS = ["USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD", "SEK", "NOK"]

    def test_major_currencies_are_independent(self):
        r = _registry()
        for code in self.MAJORS:
            c = _active(r, code)
            assert c is not None, f"{code} not found in active currencies"
            assert c["is_independent"] is True, (
                f"{code} is_independent={c['is_independent']}, expected True"
            )

    def test_major_currencies_are_not_pegged(self):
        r = _registry()
        for code in self.MAJORS:
            c = _active(r, code)
            assert c is not None
            assert c["pegged_to"] is None, (
                f"{code} pegged_to={c['pegged_to']}, expected None (freely floating)"
            )

    def test_pegged_currencies_are_not_independent(self):
        """Every pegged currency must have is_independent=False."""
        r = _registry()
        for c in r["currencies"]["active"]:
            if c.get("pegged_to") is not None:
                assert c["is_independent"] is False, (
                    f"{c['code']} is pegged to {c['pegged_to']} "
                    f"but is_independent={c['is_independent']}"
                )

    def test_independent_currencies_have_no_peg(self):
        """Every independent currency must have pegged_to=None."""
        r = _registry()
        for c in r["currencies"]["active"]:
            if c.get("is_independent") is True:
                assert c.get("pegged_to") is None, (
                    f"{c['code']} is independent but pegged_to={c['pegged_to']}"
                )


# ---------------------------------------------------------------------------
# Withdrawn currency facts
# ---------------------------------------------------------------------------

class TestWithdrawn:
    """Historical currencies with known replacement data."""

    # Eurozone irrevocable conversion rates (31 Dec 1998)
    EURO_RATES = {
        "DEM": 1.95583,
        "FRF": 6.55957,
        "ITL": 1936.27,
        "ESP": 166.386,
        "NLG": 2.20371,
        "ATS": 13.7603,
        "BEF": 40.3399,
        "FIM": 5.94573,
        "IEP": 0.787564,
        "PTE": 200.482,
        "LUF": 40.3399,
        "GRD": 340.750,
    }

    def test_dem_replaced_by_eur(self):
        r = _registry()
        dem = _withdrawn(r, "DEM")
        assert dem is not None, "DEM not found in withdrawn"
        assert dem["replaced_by"] == "EUR"
        assert dem["conversion_rate"] == 1.95583

    def test_itl_replaced_by_eur(self):
        r = _registry()
        itl = _withdrawn(r, "ITL")
        assert itl is not None, "ITL not found in withdrawn"
        assert itl["replaced_by"] == "EUR"
        assert itl["minor_units"] == 0  # Lira had no subdivision

    def test_eur_conversion_rates_are_correct(self):
        """Every Eurozone withdrawn currency must have the correct irrevocable rate."""
        r = _registry()
        for code, expected_rate in self.EURO_RATES.items():
            c = _withdrawn(r, code)
            assert c is not None, (
                f"{code} not found in withdrawn currencies. "
                f"It should exist with conversion_rate={expected_rate}."
            )
            actual = c["conversion_rate"]
            assert actual == expected_rate, (
                f"{code} conversion_rate={actual}, expected {expected_rate}"
            )

    def test_all_withdrawn_have_replacement(self):
        """Every withdrawn currency must have a replaced_by field."""
        r = _registry()
        for c in r["currencies"]["withdrawn"]:
            assert c.get("replaced_by"), (
                f"{c['code']} has no replaced_by field"
            )
            assert len(c["replaced_by"]) == 3, (
                f"{c['code']} replaced_by='{c['replaced_by']}' is not a 3-letter code"
            )

    def test_all_withdrawn_have_conversion_rate(self):
        """Every withdrawn currency must have a positive conversion rate."""
        r = _registry()
        for c in r["currencies"]["withdrawn"]:
            rate = c.get("conversion_rate")
            assert rate is not None, f"{c['code']} has no conversion_rate"
            assert rate > 0, f"{c['code']} conversion_rate={rate}, must be positive"

    def test_all_withdrawn_have_withdrawal_date(self):
        """Every withdrawn currency must have a withdrawal date."""
        r = _registry()
        for c in r["currencies"]["withdrawn"]:
            assert c.get("withdrawn_date"), (
                f"{c['code']} has no withdrawn_date"
            )


# ---------------------------------------------------------------------------
# Numeric code facts
# ---------------------------------------------------------------------------

class TestNumericCodes:
    """ISO 4217 numeric codes must be correct 3-digit strings."""

    def test_usd_numeric_is_840(self):
        r = _registry()
        usd = _active(r, "USD")
        assert usd["numeric"] == "840"

    def test_eur_numeric_is_978(self):
        r = _registry()
        eur = _active(r, "EUR")
        assert eur["numeric"] == "978"

    def test_jpy_numeric_is_392(self):
        r = _registry()
        jpy = _active(r, "JPY")
        assert jpy["numeric"] == "392"

    def test_gbp_numeric_is_826(self):
        r = _registry()
        gbp = _active(r, "GBP")
        assert gbp["numeric"] == "826"

    def test_chf_numeric_is_756(self):
        r = _registry()
        chf = _active(r, "CHF")
        assert chf["numeric"] == "756"

    def test_aud_numeric_preserves_leading_zero(self):
        """AUD numeric code is '036' — string type preserves the leading zero."""
        r = _registry()
        aud = _active(r, "AUD")
        assert aud["numeric"] == "036", (
            f"AUD numeric='{aud['numeric']}' (type={type(aud['numeric']).__name__}), "
            f"expected string '036'"
        )
        assert isinstance(aud["numeric"], str), (
            f"AUD numeric is {type(aud['numeric']).__name__}, expected str"
        )

    def test_all_active_numeric_codes_are_three_digit_strings(self):
        """Every active currency must have a 3-digit string numeric code."""
        r = _registry()
        for c in r["currencies"]["active"]:
            numeric = c.get("numeric", "")
            assert isinstance(numeric, str), (
                f"{c['code']} numeric is {type(numeric).__name__}, expected str"
            )
            assert len(numeric) == 3, (
                f"{c['code']} numeric='{numeric}' has length {len(numeric)}, expected 3"
            )
            assert numeric.isdigit(), (
                f"{c['code']} numeric='{numeric}' is not all digits"
            )


# ---------------------------------------------------------------------------
# Non-ISO facts
# ---------------------------------------------------------------------------

class TestNonISO:
    """Non-ISO currencies (crypto, commodities) with known properties."""

    def test_btc_has_8_minor_units(self):
        r = _registry()
        btc = _non_iso(r, "cryptocurrencies", "BTC")
        assert btc is not None, "BTC not found in cryptocurrencies"
        assert btc["minor_units"] == 8

    def test_eth_has_18_minor_units(self):
        r = _registry()
        eth = _non_iso(r, "cryptocurrencies", "ETH")
        assert eth is not None, "ETH not found in cryptocurrencies"
        assert eth["minor_units"] == 18

    def test_usdt_is_stablecoin(self):
        r = _registry()
        usdt = _non_iso(r, "stablecoins", "USDT")
        assert usdt is not None, "USDT not found in stablecoins"
        assert usdt.get("type") == "stablecoin"
        assert usdt.get("pegged_to") == "USD"

    def test_usdc_is_stablecoin(self):
        r = _registry()
        usdc = _non_iso(r, "stablecoins", "USDC")
        assert usdc is not None, "USDC not found in stablecoins"
        assert usdc.get("pegged_to") == "USD"

    def test_xau_is_commodity(self):
        r = _registry()
        xau = _non_iso(r, "commodities", "XAU")
        assert xau is not None, "XAU not found in commodities"
        assert xau.get("type") == "commodity"

    def test_xag_is_commodity(self):
        r = _registry()
        xag = _non_iso(r, "commodities", "XAG")
        assert xag is not None, "XAG not found in commodities"

    def test_xpt_is_commodity(self):
        r = _registry()
        xpt = _non_iso(r, "commodities", "XPT")
        assert xpt is not None, "XPT not found in commodities"

    def test_xpd_is_commodity(self):
        r = _registry()
        xpd = _non_iso(r, "commodities", "XPD")
        assert xpd is not None, "XPD not found in commodities"

    def test_all_non_iso_have_type(self):
        """Every non-ISO currency must have a type field."""
        r = _registry()
        for category in ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]:
            for c in r.get("non_iso", {}).get(category, []):
                assert "type" in c, (
                    f"{c['code']} in {category} has no 'type' field"
                )

    def test_all_non_iso_have_note(self):
        """Every non-ISO currency should have a note explaining its status."""
        r = _registry()
        for category in ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]:
            for c in r.get("non_iso", {}).get(category, []):
                assert "note" in c, (
                    f"{c['code']} in {category} has no 'note' field"
                )
                assert len(c["note"]) > 10, (
                    f"{c['code']} note is too short: '{c.get('note', '')}'"
                )


# ---------------------------------------------------------------------------
# Country facts
# ---------------------------------------------------------------------------

class TestCountries:
    """Country-currency relationship ground truths."""

    def test_usd_issued_by_united_states(self):
        r = _registry()
        usd = _active(r, "USD")
        issuers = [c for c in usd.get("countries", []) if c["relationship"] == "issuing"]
        assert len(issuers) == 1, f"USD has {len(issuers)} issuing countries, expected 1"
        assert issuers[0]["code"] == "US"

    def test_chf_used_in_liechtenstein(self):
        r = _registry()
        chf = _active(r, "CHF")
        li = [c for c in chf.get("countries", []) if c["code"] == "LI"]
        assert len(li) == 1, "Liechtenstein (LI) should use CHF"

    def test_eur_has_at_least_20_countries(self):
        """Eurozone has 20 member states as of 2023 (including Croatia)."""
        r = _registry()
        eur = _active(r, "EUR")
        issuers = [c for c in eur.get("countries", []) if c["relationship"] == "issuing"]
        assert len(issuers) >= 20, (
            f"EUR has {len(issuers)} issuing countries, expected >=20"
        )

    def test_inr_used_in_bhutan(self):
        r = _registry()
        inr = _active(r, "INR")
        bt = [c for c in inr.get("countries", []) if c["code"] == "BT"]
        assert len(bt) == 1, "Bhutan (BT) should use INR"

    def test_zar_used_in_namibia(self):
        r = _registry()
        zar = _active(r, "ZAR")
        na = [c for c in zar.get("countries", []) if c["code"] == "NA"]
        assert len(na) == 1, "Namibia (NA) should use ZAR (CMA)"

    def test_all_country_codes_are_valid_format(self):
        """Every country code must be exactly 2 uppercase letters."""
        r = _registry()
        for c in r["currencies"]["active"]:
            for country in c.get("countries", []):
                code = country.get("code", "")
                assert len(code) == 2, (
                    f"{c['code']}: country code '{code}' has length {len(code)}"
                )
                assert code.isupper(), (
                    f"{c['code']}: country code '{code}' is not uppercase"
                )
                assert code.isalpha(), (
                    f"{c['code']}: country code '{code}' is not alphabetic"
                )

    def test_all_relationships_are_valid(self):
        """Every country relationship must be one of the five valid types."""
        valid = {"issuing", "adopting", "territory", "parallel", "local_issue"}
        r = _registry()
        for c in r["currencies"]["active"]:
            for country in c.get("countries", []):
                rel = country.get("relationship", "")
                assert rel in valid, (
                    f"{c['code']}: invalid relationship '{rel}' for {country.get('code')}"
                )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))