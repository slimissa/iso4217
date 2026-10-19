"""
ADR citations in tools/*.py.

Two citations in tools/validate.py named the wrong ADR for a release (v1.8.3, F16). Both numbers
resolved, so "does it exist" cannot catch that; each citation is pinned to the ADR it means.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = PROJECT_ROOT / "docs" / "decisions"

# (file, a phrase in the sentence that carries the citation, the ADR file that sentence is about)
CITATIONS = [
    ("tools/validate.py", "second source of truth that drifts on every schema bump", "schema-version-consistency.md"),
    ("tools/validate.py", "complementary treatment of numeric-code reuse", "numeric-code-reuse.md"),
    ("tools/export_countries_parquet.py", "has eleven columns", "parquet-schema.md"),
    ("tools/export_countries_parquet.py", "CSV/Parquet column parity", "parquet-schema.md"),
    ("tools/export_parquet.py", "synthetic identifier convention", "withdrawn-codes.md"),
    ("tools/check_version_consistency.py", "deliberately not sites", "aggregated-layer-0007.md"),
    ("tools/export_aggregated.py", "single sanctioned exception", "aggregated-layer-0007.md"),
]


def _adr_numbers() -> dict[str, int]:
    out = {}
    for p in DECISIONS.glob("*.md"):
        m = re.match(r"# ADR (\d{4}) ", p.read_text(encoding="utf-8"))
        if m:
            out[p.name] = int(m.group(1))
    return out


def _flat(text: str) -> str:
    """Comment markers and line breaks are formatting, not meaning."""
    return " ".join(re.sub(r"(?m)^\s*#", " ", text).split())


def test_every_adr_cited_in_tools_exists():
    known = set(_adr_numbers().values())
    for p in sorted((PROJECT_ROOT / "tools").glob("*.py")):
        for n in re.findall(r"ADR (\d{4})", p.read_text(encoding="utf-8")):
            assert int(n) in known, f"{p.name} cites ADR {n}, which does not exist"


@pytest.mark.parametrize("rel,phrase,adr_file", CITATIONS, ids=[f"{c[0]}:{c[1][:28]}" for c in CITATIONS])
def test_each_citation_names_the_adr_it_means(rel, phrase, adr_file):
    text = _flat((PROJECT_ROOT / rel).read_text(encoding="utf-8"))
    assert phrase in text, f"{rel}: the sentence {phrase!r} moved; update CITATIONS"
    at = text.index(phrase)
    window = text[max(0, at - 260): at + len(phrase) + 260]
    cited = {int(n) for n in re.findall(r"ADR (\d{4})", window)}
    want = _adr_numbers()[adr_file]
    assert want in cited, f"{rel}: near {phrase!r} the ADRs cited are {sorted(cited)}, expected {want:04d} ({adr_file})"
    assert cited <= {want}, f"{rel}: near {phrase!r} an unrelated ADR is cited: {sorted(cited - {want})}"
