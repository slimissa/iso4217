"""
What v1.9.7 wrote into two decision records (both Proposed) is still there.

ADR 0015 (docs/decisions/wrapper-lookup-contract.md) carries Amendment 1, the collection-order contract v1.9.6 enforced. ADR 0010
(docs/decisions/country-currency-taxonomy.md) answers the CUC question with List Three and says why the move did not land.
"""

from __future__ import annotations

from pathlib import Path

DECISIONS = Path(__file__).resolve().parent.parent / "docs" / "decisions"
ADR_0015 = (DECISIONS / "wrapper-lookup-contract.md").read_text(encoding="utf-8")
ADR_0010 = (DECISIONS / "country-currency-taxonomy.md").read_text(encoding="utf-8")


def test_adr_0015_records_the_collection_order_contract():
    amendment = ADR_0015.split("## Amendment 1 (v1.9.6): collection order", 1)[1].split("\n## ", 1)[0]
    assert "**Status:** Proposed" in amendment
    for phrase in ("**file order** in all four languages", "section by section, one entry per code", "`collection_order` group"):
        assert phrase in amendment, phrase
    assert "was wrong for Go" in amendment


def test_adr_0010_answers_the_cuc_question_and_records_the_move():
    # v1.9.7 second bundle: the move landed (it said "did **not** land" while the first bundle's patch 01 was stopped).
    assert "Open question, not decided here:** whether CUC" not in ADR_0010
    assert "Open question, answered in v1.9.7:** whether CUC" in ADR_0010
    assert "<WthdrwlDt>2021-06</WthdrwlDt>" in ADR_0010 and "The move landed in v1.9.7" in ADR_0010
    assert "did **not** land in v1.9.7" not in ADR_0010
    assert "amendment 178 (4 February 2025)" in ADR_0010 and "Resolución 177/2020" in ADR_0010
