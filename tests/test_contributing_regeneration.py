"""
CONTRIBUTING.md step 3 and release.sh's regenerate_artifacts must name the same generators in the same order.

A contributor who follows a shorter list gets a red `--check` in CI for the generator it left out
(v1.8.3, F5: the list omitted export_countries_parquet.py and export_aggregated.py).
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _contributing_generators() -> list[str]:
    text = (PROJECT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    start = text.index("Regenerate every derived artifact")
    block = text[start:text.index("```", text.index("```", start) + 3)]
    return re.findall(r"python3 tools/(\w+)\.py", block)


def _release_generators() -> list[str]:
    text = (PROJECT_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    start = text.index("regenerate_artifacts() {")
    body = text[start:text.index("\n}\n", start)]
    return re.findall(r"python3 tools/(\w+)\.py", body)


def test_release_sh_regenerates_the_expected_set():
    assert len(_release_generators()) >= 6


def test_contributing_names_every_generator_release_sh_runs_in_the_same_order():
    assert _contributing_generators() == _release_generators()
