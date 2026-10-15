"""
Tests for tools/check_amendments.py (v1.7.15, finding F9).

Until v1.7.14 the monitor exited 0 whenever it could not read the SIX page --
on a network failure, and also when the page parsed to no amendment number --
and fell back to a hard-coded value. A weekly green run therefore proved
nothing. These tests pin the opposite: a run that did not read the page exits
3 (RELEASE_PATTERN.md, hygiene rule 7).

No test touches the network. An autouse fixture replaces urlopen with a
function that fails the test, and each test installs its own scripted fake.
"""

from __future__ import annotations

import json
import runpy
import sys
import urllib.error
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_amendments as ca
from tools.check_amendments import (
    EXIT_FATAL,
    EXIT_NEW_AMENDMENT,
    EXIT_OK,
    EXIT_UNDETERMINED,
    fetch_latest_amendment,
    main,
)

PAGE_179 = "<html><h2>Amendment 179</h2><p>Amendment No. 12</p></html>"
PAGE_180 = "<html><h2>Amendment 179</h2><p>AML 180</p></html>"
PAGE_EMPTY = "<html><body>Nothing numbered here.</body></html>"

FAILURE_STATUSES = ["http_error", "url_error", "timeout", "parse_failed", "unexpected_error"]


class _Response:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid/", code, "x", {}, None)


def _scripted(*outcomes):
    """A fake urlopen. Each call plays the next outcome; the last one repeats."""
    calls = []

    def fake(req, timeout=None):
        calls.append(req)
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(outcome)

    return fake, calls


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test attempted a real network request")

    monkeypatch.setattr(ca.urllib.request, "urlopen", refuse)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    def make(amendment=179):
        path = tmp_path / "iso4217.json"
        path.write_text(json.dumps({"source": {"last_amendment_applied": amendment}}), encoding="utf-8")
        monkeypatch.setattr(ca, "REGISTRY_PATH", path)
        return path

    return make


def _run(capsys, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["check_amendments.py", *argv])
    with pytest.raises(SystemExit) as exc:
        main()
    captured = capsys.readouterr()
    return exc.value.code, captured.out, captured.err


# ---------------------------------------------------------------------------
# fetch_latest_amendment: what is a failure, and what is retried
# ---------------------------------------------------------------------------

class TestFetchFailureStatuses:
    @pytest.mark.parametrize(
        "outcome, status, calls, sleeps",
        [
            (_http(404), "http_error", 1, []),
            (_http(403), "http_error", 1, []),
            (_http(503), "http_error", 3, [5, 10]),
            (_http(429), "http_error", 3, [5, 10]),
            (urllib.error.URLError("dns"), "url_error", 3, [5, 10]),
            (ConnectionResetError("reset"), "url_error", 3, [5, 10]),
            (TimeoutError("slow"), "timeout", 3, [5, 10]),
            (PAGE_EMPTY, "parse_failed", 1, []),
            (RuntimeError("boom"), "unexpected_error", 1, []),
        ],
        ids=["404", "403", "503", "429", "dns", "reset", "timeout", "parse", "boom"],
    )
    def test_status_and_retry_behaviour(self, monkeypatch, outcome, status, calls, sleeps):
        fake, seen = _scripted(outcome)
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        slept = []
        amendment, got = fetch_latest_amendment(sleep=slept.append)
        assert (amendment, got) == (0, status)
        assert len(seen) == calls
        assert slept == sleeps

    def test_a_transient_failure_then_success_returns_the_number(self, monkeypatch):
        fake, seen = _scripted(_http(503), PAGE_180)
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        slept = []
        assert fetch_latest_amendment(sleep=slept.append) == (180, "six_group_website")
        assert len(seen) == 2 and slept == [5]

    def test_success_on_the_first_try_never_sleeps(self, monkeypatch):
        fake, seen = _scripted(PAGE_179)
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        slept = []
        assert fetch_latest_amendment(sleep=slept.append) == (179, "six_group_website")
        assert len(seen) == 1 and slept == []

    def test_the_highest_number_on_the_page_wins(self, monkeypatch):
        fake, _ = _scripted("Amendment 7 ... AML 180 ... Amendment No. 12")
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        assert fetch_latest_amendment(sleep=lambda s: None) == (180, "six_group_website")

    def test_one_attempt_means_no_retry(self, monkeypatch):
        fake, seen = _scripted(_http(503))
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        assert fetch_latest_amendment(attempts=1, sleep=lambda s: None) == (0, "http_error")
        assert len(seen) == 1


# ---------------------------------------------------------------------------
# main: every failure status exits 3 and says it is undetermined
# ---------------------------------------------------------------------------

class TestUndeterminedExitsThree:
    @pytest.mark.parametrize("status", FAILURE_STATUSES)
    def test_a_failed_fetch_exits_3_and_reports_undetermined(self, status, registry, monkeypatch, capsys):
        registry(179)
        monkeypatch.setattr(ca, "fetch_latest_amendment", lambda verbose=False: (0, status))
        code, out, err = _run(capsys, monkeypatch, "--json")
        assert code == EXIT_UNDETERMINED == 3
        result = json.loads(out)
        assert result["determined"] is False
        assert result["latest_amendment"] is None
        assert result["new_amendment_detected"] is None
        assert result["fetch_status"] == status
        assert result["source"] == "undetermined"
        assert "UNDETERMINED" in err and status in err

    @pytest.mark.parametrize(
        "outcome, status",
        [
            (_http(404), "http_error"),
            (urllib.error.URLError("dns"), "url_error"),
            (TimeoutError("slow"), "timeout"),
            (PAGE_EMPTY, "parse_failed"),
            (RuntimeError("boom"), "unexpected_error"),
        ],
        ids=FAILURE_STATUSES,
    )
    def test_end_to_end_through_urlopen(self, outcome, status, registry, monkeypatch, capsys):
        registry(179)
        fake, _ = _scripted(outcome)
        monkeypatch.setattr(ca.urllib.request, "urlopen", fake)
        monkeypatch.setattr(ca.time, "sleep", lambda s: None)
        code, out, _ = _run(capsys, monkeypatch, "--json")
        assert code == EXIT_UNDETERMINED
        assert json.loads(out)["fetch_status"] == status

    def test_the_known_value_is_not_used_as_an_answer(self, registry, monkeypatch, capsys):
        # Registry behind KNOWN_LATEST_AMENDMENT: the old code reported a "new
        # amendment" from the constant after a failed fetch. Now it is undetermined.
        registry(178)
        monkeypatch.setattr(ca, "fetch_latest_amendment", lambda verbose=False: (0, "parse_failed"))
        code, out, _ = _run(capsys, monkeypatch, "--json")
        assert code == EXIT_UNDETERMINED
        assert json.loads(out)["latest_amendment"] is None


class TestDeterminedResults:
    def test_up_to_date_exits_0(self, registry, monkeypatch, capsys):
        registry(179)
        monkeypatch.setattr(ca, "fetch_latest_amendment", lambda verbose=False: (179, "six_group_website"))
        code, out, _ = _run(capsys, monkeypatch, "--json")
        result = json.loads(out)
        assert code == EXIT_OK
        assert result["determined"] is True and result["new_amendment_detected"] is False
        assert result["simulated"] is False

    def test_a_new_amendment_exits_1(self, registry, monkeypatch, capsys):
        registry(179)
        monkeypatch.setattr(ca, "fetch_latest_amendment", lambda verbose=False: (180, "six_group_website"))
        code, out, _ = _run(capsys, monkeypatch, "--json")
        result = json.loads(out)
        assert code == EXIT_NEW_AMENDMENT
        assert result["new_amendment_detected"] is True and result["latest_amendment"] == 180

    def test_offline_is_the_explicit_exception_and_does_not_fetch(self, registry, monkeypatch, capsys):
        registry(ca.KNOWN_LATEST_AMENDMENT)
        code, out, _ = _run(capsys, monkeypatch, "--json", "--offline")
        result = json.loads(out)
        assert code == EXIT_OK
        assert result["fetch_status"] == "offline_mode" and result["source"] == "known_value"

    def test_a_missing_registry_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(ca, "REGISTRY_PATH", tmp_path / "absent.json")
        code, _, _ = _run(capsys, monkeypatch, "--json", "--offline")
        assert code == EXIT_FATAL

    def test_exit_codes_are_distinct(self):
        assert [EXIT_OK, EXIT_NEW_AMENDMENT, EXIT_FATAL, EXIT_UNDETERMINED] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# A crash must not look like "new amendment"
# ---------------------------------------------------------------------------

class TestCrashesExitTwo:
    def test_an_uncaught_exception_exits_2_not_1(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(sys, "argv", ["check_amendments.py", "--offline", "--json"])
        monkeypatch.setattr(json, "dumps", boom)
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(PROJECT_ROOT / "tools" / "check_amendments.py"), run_name="__main__")
        assert exc.value.code == EXIT_FATAL


# ---------------------------------------------------------------------------
# --simulate: the workflow's way of exercising its alert paths
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_simulated_undetermined_exits_3_without_contacting_six(self, registry, monkeypatch, capsys):
        registry(179)
        code, out, err = _run(capsys, monkeypatch, "--json", "--simulate", "undetermined")
        result = json.loads(out)
        assert code == EXIT_UNDETERMINED
        assert result["simulated"] is True and result["fetch_status"] == "simulated_undetermined"
        assert "SIMULATED" in err and "UNDETERMINED" in err

    def test_simulated_new_amendment_exits_1(self, registry, monkeypatch, capsys):
        registry(179)
        code, out, err = _run(capsys, monkeypatch, "--json", "--simulate", "new-amendment")
        result = json.loads(out)
        assert code == EXIT_NEW_AMENDMENT
        assert result["simulated"] is True and result["latest_amendment"] == 180
        assert "SIMULATED" in err

    def test_simulate_and_offline_are_mutually_exclusive(self, registry, monkeypatch, capsys):
        registry(179)
        code, _, err = _run(capsys, monkeypatch, "--simulate", "undetermined", "--offline")
        assert code == 2 and "mutually exclusive" in err

    def test_a_normal_run_is_never_marked_simulated(self, registry, monkeypatch, capsys):
        registry(179)
        monkeypatch.setattr(ca, "fetch_latest_amendment", lambda verbose=False: (179, "six_group_website"))
        _, out, err = _run(capsys, monkeypatch, "--json")
        assert json.loads(out)["simulated"] is False
        assert "SIMULATED" not in err
