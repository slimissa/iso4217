"""
The v1.9.7 data corrections, held to their primary sources.

Each record moved to `withdrawn` is pinned to what its source states, quoted in SPEC.md of the v1.9.7 bundles:

  CUC  ISO 4217 amendment 178 (SIX, 4 February 2025): "The withdrawal process was completed within 180 days, ending on
       June 30, 2021". Resolución 177/2020 of the Banco Central de Cuba (Gaceta Oficial No. 73 Extraordinaria, 10 December
       2020), artículo TERCERO: "la tasa de cambio de veinticuatro (24) pesos cubanos por un (1) peso convertible".
       conversion_rate is "units of this currency per 1 unit of replacement" (schema.json; BGN 1.95583 per EUR), so 1/24.

USS and ANG/XCG did not land in v1.9.7 (no attached source gives the day); tests/test_six_list_one_parity.py holds them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = json.loads((PROJECT_ROOT / "iso4217.json").read_text(encoding="utf-8"))
ACTIVE = {c["code"]: c for c in REGISTRY["currencies"]["active"]}
WITHDRAWN = {c["code"]: c for c in REGISTRY["currencies"]["withdrawn"]}
LIST_THREE_PUBLISHED = "2026-01-01"


class TestCUC:
    def test_it_is_withdrawn_and_no_longer_active(self):
        assert "CUC" in WITHDRAWN and "CUC" not in ACTIVE

    def test_the_day_is_the_one_amendment_178_states(self):
        cuc = WITHDRAWN["CUC"]
        assert cuc["withdrawn_date"] == "2021-06-30"
        assert cuc["code_lifetime"] == {"from": None, "to": "2021-06-30"}

    def test_replaced_by_cup_at_the_rate_of_resolucion_177(self):
        cuc = WITHDRAWN["CUC"]
        assert cuc["replaced_by"] == "CUP"
        assert cuc["conversion_rate"] == pytest.approx(1 / 24, rel=1e-12), "CUC per CUP: 24 CUP for 1 CUC"
        assert cuc["conversion_rate"] * 24 == pytest.approx(1.0)

    def test_the_identity_fields_are_those_it_had_as_active(self):
        cuc = WITHDRAWN["CUC"]
        assert (cuc["numeric"], cuc["minor_units"], cuc["name"]) == ("931", 2, "Cuban Convertible Peso")

    def test_the_note_quotes_list_three_and_cites_both_sources(self):
        note = WITHDRAWN["CUC"]["note"]
        assert note.startswith(f"ISO List Three (SIX, published {LIST_THREE_PUBLISHED}): WthdrwlDt 2021-06.")
        assert "amendment 178 (SIX, 4 February 2025)" in note and "Resolución 177/2020" in note
        assert "veinticuatro (24) pesos cubanos por un (1) peso convertible" in note
        assert "still ISO-listed as active" not in note

    def test_the_source_is_the_resolution_not_the_unread_iso_page(self):
        url = WITHDRAWN["CUC"]["source_url"]
        assert url.endswith("/goc-2020-ex73.pdf") and "iso.org/obp" not in url


class TestReadmeCounts:
    """Every count the README states about the registry, held to iso4217.json (v1.9.7). tools/check_readme_drift.py reads
    only the summary sentence ("N active currencies ..."); the table rows, the schema sketch, the statistics table and the
    Parquet row count were unchecked, and a data patch must move them all."""

    README = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    def _expect(self, phrase: str):
        assert phrase in self.README, f"README.md does not say: {phrase!r}"

    def test_every_stated_count_matches_the_registry(self):
        a, w = len(ACTIVE), len(WITHDRAWN)
        cls = [c["classification"] for c in ACTIVE.values()]
        pegged = [c for c in ACTIVE.values() if c.get("pegged_to")]
        single = [c for c in pegged if c.get("peg_type") == "single"]
        for phrase in (
            f"| **Active ISO 4217 currencies** | {a} —",
            f"| **Withdrawn ISO 4217 currencies** | {w} —",
            f"active[]    {a} entries",
            f"withdrawn[] {w} entries",
            f"| Active ISO currencies | {a} | {cls.count('circulating')} circulating, {cls.count('fund')} fund, "
            f"{cls.count('indexation')} indexation |",
            f"| Withdrawn ISO currencies | {w} |",
            f"| Pegged active currencies | {len(pegged)} | {len(single)} single-anchor",
            f"{a + w} rows: {a} active and {w} withdrawn.",
            f"is null for all {w} withdrawn entries.",
        ):
            self._expect(phrase)


def test_conversion_rate_has_one_direction_everywhere():
    # Revaluations store old units per new unit (SLL 1000 per SLE; BGN 1.95583 per EUR). A rate below 1 is legitimate only
    # where the old unit was worth more than the new one; CUC is the one such record v1.9.7 adds.
    assert WITHDRAWN["SLL"]["conversion_rate"] == 1000.0 and WITHDRAWN["BGN"]["conversion_rate"] == 1.95583
