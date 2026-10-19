"""
The versioning policy is written in two places (CONTRIBUTING.md's table, README.md's bullets). Both must carry
the amendment rule: an ISO amendment that changes which currencies are active is a Minor release (v1.8.3).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _flat(rel: str) -> str:
    return " ".join((PROJECT_ROOT / rel).read_text(encoding="utf-8").split())


def test_contributing_says_an_amendment_that_changes_active_currencies_is_minor():
    text = _flat("CONTRIBUTING.md")
    assert "An ISO amendment" in text
    row = text.split("An ISO amendment", 1)[1][:400]
    assert "Minor" in row and "not Patch" in row


def test_readme_agrees():
    assert "an ISO amendment that changes which currencies are active" in _flat("README.md")
