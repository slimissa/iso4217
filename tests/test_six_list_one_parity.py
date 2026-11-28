"""
The registry's active section against SIX's ISO 4217 List One (v1.9.7).

v1.9.6 claimed amendment 180 while List One (published 2026-09-17) no longer listed CUC, USS or ANG and listed XCG. The
amendment monitor (tools/check_amendments.py) compares only the amendment number, so it said "up to date". This test compares
the codes: tests/fixtures/six_list_one_facts.json holds one row per List One code (written by tools/six_facts.py from SIX's
XML, which is not committed), and

  - every `active` code is in the fixture, with the same numeric code and minor units;
  - every fixture code is `active`;

except the codes named in EXCEPTIONS, each with a reason and an expiry date. After its expiry an exception fails the test,
and an exception that is no longer needed (the code now agrees) fails it too, so the list can only shrink.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "six_list_one_facts.json"
FACTS = json.loads(FIXTURE.read_text(encoding="utf-8"))
REGISTRY = json.loads((PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8"))
ACTIVE = {c["code"]: c for c in REGISTRY["currencies"]["active"]}
LIST_ONE = {row["code"]: row for row in FACTS["codes"]}

DEFERRED = "deferred to v1.10.0"
BLOCKED = ("blocked in v1.9.7: no attached primary source gives the day the currency ceased to be legal tender "
           "(D2 stop; List Three gives only the month)")

# code -> (direction, reason, expiry). "not_active": in List One, not in `active`. "not_in_list_one": in `active`, not in
# List One. Dated and named one by one; never a pattern.
EXCEPTIONS = {
    # Not ISO-active in this registry by design until v1.10.0 decides the X-codes (bond units, testing, no currency).
    "XBA": ("not_active", DEFERRED, "2027-03-31"),
    "XBB": ("not_active", DEFERRED, "2027-03-31"),
    "XBC": ("not_active", DEFERRED, "2027-03-31"),
    "XBD": ("not_active", DEFERRED, "2027-03-31"),
    "XTS": ("not_active", DEFERRED, "2027-03-31"),
    "XXX": ("not_active", DEFERRED, "2027-03-31"),
    # Kept in non_iso (commodities, special purpose) until v1.10.0.
    "XAU": ("not_active", DEFERRED, "2027-03-31"),
    "XAG": ("not_active", DEFERRED, "2027-03-31"),
    "XPT": ("not_active", DEFERRED, "2027-03-31"),
    "XPD": ("not_active", DEFERRED, "2027-03-31"),
    "XDR": ("not_active", DEFERRED, "2027-03-31"),
    "XUA": ("not_active", DEFERRED, "2027-03-31"),
    "XSU": ("not_active", DEFERRED, "2027-03-31"),
    "XAD": ("not_active", DEFERRED, "2027-03-31"),
    # The v1.9.7 data corrections that stopped under D2: List Three lists USS (2014-03) and ANG (2025-03) as withdrawn and List
    # One lists XCG, but no attached source gives the day. CUC landed in v1.9.7 (amendment 178 gives 30 June 2021); each
    # data patch removes its own code's exception.
    "USS": ("not_in_list_one", BLOCKED, "2027-03-31"),
    "ANG": ("not_in_list_one", BLOCKED, "2027-03-31"),
    "XCG": ("not_active", BLOCKED, "2027-03-31"),
}


def _excused(code: str, direction: str) -> bool:
    entry = EXCEPTIONS.get(code)
    return entry is not None and entry[0] == direction


class TestTheFixture:
    def test_it_is_list_one_with_a_publication_date(self):
        assert "List One" in FACTS["source"]
        dt.date.fromisoformat(FACTS["published"])

    def test_the_declared_count_is_the_row_count_and_codes_are_unique_and_sorted(self):
        codes = [row["code"] for row in FACTS["codes"]]
        assert FACTS["code_count"] == len(codes) == len(set(codes))
        assert codes == sorted(codes)

    def test_every_row_is_well_formed(self):
        for row in FACTS["codes"]:
            assert set(row) == {"code", "numeric", "minor_units"}, row
            assert len(row["code"]) == 3 and row["code"].isupper(), row
            assert row["numeric"] is None or (len(row["numeric"]) == 3 and row["numeric"].isdigit()), row
            assert row["minor_units"] is None or isinstance(row["minor_units"], int), row


class TestActiveAgainstListOne:
    def test_every_active_code_is_in_list_one(self):
        missing = sorted(c for c in ACTIVE if c not in LIST_ONE and not _excused(c, "not_in_list_one"))
        assert not missing, f"active in iso4217.json but not in List One ({FACTS['published']}): {missing}"

    def test_every_list_one_code_is_active(self):
        missing = sorted(c for c in LIST_ONE if c not in ACTIVE and not _excused(c, "not_active"))
        assert not missing, f"in List One ({FACTS['published']}) but not active in iso4217.json: {missing}"

    @pytest.mark.parametrize("field", ["numeric", "minor_units"])
    def test_numeric_code_and_minor_units_agree(self, field):
        bad = {c: (ACTIVE[c].get(field), LIST_ONE[c][field]) for c in sorted(set(ACTIVE) & set(LIST_ONE))
               if ACTIVE[c].get(field) != LIST_ONE[c][field]}
        assert not bad, f"{field} differs from List One (registry, List One): {bad}"


class TestTheExceptions:
    def test_each_has_a_known_direction_a_reason_and_a_date(self):
        for code, (direction, reason, expiry) in EXCEPTIONS.items():
            assert direction in ("not_active", "not_in_list_one"), code
            assert reason in (DEFERRED, BLOCKED), code
            dt.date.fromisoformat(expiry)

    @pytest.mark.parametrize("code", sorted(EXCEPTIONS))
    def test_none_has_expired(self, code):
        expiry = dt.date.fromisoformat(EXCEPTIONS[code][2])
        assert dt.date.today() <= expiry, f"the exception for {code} expired on {expiry}: {EXCEPTIONS[code][1]}"

    @pytest.mark.parametrize("code", sorted(EXCEPTIONS))
    def test_each_is_still_needed(self, code):
        direction = EXCEPTIONS[code][0]
        if direction == "not_active":
            assert code in LIST_ONE and code not in ACTIVE, f"{code} no longer needs its exception: remove it"
        else:
            assert code in ACTIVE and code not in LIST_ONE, f"{code} no longer needs its exception: remove it"

    def test_the_deferred_set_is_exactly_the_fourteen_x_codes(self):
        deferred = {c for c, (_d, reason, _e) in EXCEPTIONS.items() if reason == DEFERRED}
        assert deferred == {"XBA", "XBB", "XBC", "XBD", "XTS", "XXX", "XAU", "XAG", "XPT", "XPD", "XDR", "XUA", "XSU", "XAD"}


class TestTheSourceMetadataClaimsNoMoreThanTheData:
    def test_list_one_is_not_named_as_verified_while_a_correction_is_blocked(self):
        # v1.9.7, patch 05 (stopped with the data patches it depends on): `source.verified_against` and `last_verified` say the
        # data matches what they name. While a BLOCKED exception stands, the registry knowingly differs from List One.
        blocked = sorted(c for c, (_d, reason, _e) in EXCEPTIONS.items() if reason == BLOCKED)
        named = [s for s in REGISTRY["source"]["verified_against"] if "List One" in s or "List Three" in s]
        assert not (blocked and named), f"verified_against names {named} while {blocked} still differ from List One"
