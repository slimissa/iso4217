"""
Tests for the SIX page parser in tools/check_amendments.py (v1.7.15, A2b).

The monitor went blind because it looked for "Amendment 179" in the page text, while the
redesigned SIX page shows no amendment number in its text at all: the number is only in the
download link, `dl-currency-iso-amendment-180.pdf`. These tests feed that page shape through
the real fetch path and through main(), so the next redesign that hides the number fails
here and exits 3 in production rather than passing silently.

No test touches the network (urlopen is replaced in every test).
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_amendments as ca
from tools.check_amendments import EXIT_NEW_AMENDMENT, fetch_latest_amendment, main

BASE = "https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/amendments/"

# The page as fetched on 2026-10-13: the visible text names no amendment number.
PAGE_TODAY = (
    "<h3>Amendments</h3>"
    "<p>Effective from 1st of January 2026, the following change will be made to "
    "List One: Bulgaria, Euro, EUR, 978, 2.</p>"
    f'<a href="{BASE}dl-currency-iso-amendment-180.pdf">Download</a>'
    "<p>Changes to the currency codes lists occur if a currency is created, withdrawn or parts thereof altered.</p>"
    f'<a href="{BASE}lists/overview-amendments.xlsx">All Past Amendments</a>'
)


class _Response:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, page: str):
    monkeypatch.setattr(ca.urllib.request, "urlopen", lambda req, timeout=None: _Response(page))
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test attempted a real network request")

    monkeypatch.setattr(ca.urllib.request, "urlopen", refuse)


class TestThePageShapes:
    def test_the_page_as_it_is_today_yields_the_number_from_the_link(self, monkeypatch):
        _serve(monkeypatch, PAGE_TODAY)
        assert fetch_latest_amendment() == (180, "six_group_website")

    def test_the_older_underscore_file_name_still_parses(self, monkeypatch):
        _serve(monkeypatch, f'<a href="{BASE}dl_currency_iso_amendment_160.pdf">Download</a>')
        assert fetch_latest_amendment() == (160, "six_group_website")

    def test_the_highest_linked_number_wins(self, monkeypatch):
        _serve(monkeypatch, f'<a href="{BASE}dl-currency-iso-amendment-179.pdf">a</a><a href="{BASE}dl-currency-iso-amendment-180.pdf">b</a>')
        assert fetch_latest_amendment() == (180, "six_group_website")

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("ISO 4217 AMENDMENT NUMBER 181", 181),
            ("Amendment 179", 179),
            ("AML 180", 180),
            ("Amendment No. 12 ... Amendment 179", 179),
        ],
    )
    def test_the_text_forms_still_parse(self, monkeypatch, text, expected):
        _serve(monkeypatch, f"<p>{text}</p>")
        assert fetch_latest_amendment() == (expected, "six_group_website")


class TestDoesNotOverMatch:
    def test_the_archive_overview_link_alone_is_not_an_amendment(self, monkeypatch):
        _serve(monkeypatch, f'<a href="{BASE}lists/overview-amendments.xlsx">All Past Amendments</a>')
        assert fetch_latest_amendment() == (0, "parse_failed")

    def test_a_year_in_a_file_name_is_not_an_amendment_number(self, monkeypatch):
        _serve(monkeypatch, f'<a href="{BASE}dl-currency-iso-amendment-2025.pdf">x</a>')
        assert fetch_latest_amendment() == (0, "parse_failed")


class TestEndToEnd:
    def test_the_repaired_monitor_raises_amendment_180_against_a_registry_at_179(self, tmp_path, monkeypatch, capsys):
        registry = tmp_path / "iso4217.json"
        registry.write_text(json.dumps({"source": {"last_amendment_applied": 179}}), encoding="utf-8")
        monkeypatch.setattr(ca, "REGISTRY_PATH", registry)
        _serve(monkeypatch, PAGE_TODAY)
        monkeypatch.setattr(sys, "argv", ["check_amendments.py", "--json"])
        with pytest.raises(SystemExit) as exc:
            main()
        result = json.loads(capsys.readouterr().out)
        assert exc.value.code == EXIT_NEW_AMENDMENT
        assert result["latest_amendment"] == 180 and result["new_amendment_detected"] is True
        assert result["source"] == "six_group_website" and result["determined"] is True
