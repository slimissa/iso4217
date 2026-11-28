"""
CONTRIBUTING.md states no test count (v1.9.7).

It said "768 tests passing as of v1.5.0" until v1.9.6, when the suite was 2329. The number was dropped rather than put under
tools/check_readme_drift.py: the size changes with almost every release and pytest prints it. This keeps a count from coming
back unchecked.
"""

from __future__ import annotations

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_no_test_count_is_stated():
    hits = re.findall(r"\b\d[\d,]*\s+tests?\b", TEXT)
    assert not hits, hits


def test_the_suite_is_run_with_fail_on_skip():
    assert "python3 -m pytest tests/ wrappers/python/tests/ -q --fail-on-skip" in TEXT
