"""
Tests for tools/refresh_market_caps.py.

Covers:
  - Data classes (Change, RefreshResult)
  - Logger (verbose, quiet, all levels)
  - Network layer (retry, backoff, error classification, pagination)
  - Registry I/O (load, backup, restore)
  - Diff engine (build_fresh_ranks, compute_changes)
  - Text patcher (apply_changes_to_text — the trickiest part)
  - Validator (validate_result)
  - Orchestration (refresh end-to-end)
  - CLI (parse_args, main, exit codes)

Network is always mocked — no real HTTP calls in tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

# Make tools importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.refresh_market_caps import (
    APIError,
    Change,
    CODE_TO_COINGECKO_ID,
    EXIT_CHANGES_PENDING,
    EXIT_FATAL,
    EXIT_NETWORK_ERROR,
    EXIT_OK,
    Logger,
    NetworkError,
    PatchError,
    RefreshResult,
    ValidationError,
    apply_changes_to_text,
    backup_registry,
    build_fresh_ranks,
    compute_changes,
    fetch_coingecko_markets,
    find_ranked_entries,
    load_registry,
    main,
    parse_args,
    refresh,
    restore_backup,
    validate_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def quiet_logger() -> Logger:
    """A logger that produces no output — for tests that don't check output."""
    return Logger(verbose=False, quiet=True)


@pytest.fixture
def sample_registry() -> dict:
    """A minimal registry matching the real schema shape."""
    return {
        "meta": {"version": "1.4.0", "updated": "2026-09-14"},
        "currencies": {"active": [], "withdrawn": []},
        "non_iso": {
            "cryptocurrencies": [
                {
                    "code": "BTC",
                    "name": "Bitcoin",
                    "minor_units": 8,
                    "symbol": "₿",
                    "type": "cryptocurrency",
                    "entity": "Decentralized",
                    "introduced": "2009-01-03",
                    "market_cap_rank": 1,
                    "note": "Not an ISO 4217 code.",
                },
                {
                    "code": "ETH",
                    "name": "Ethereum",
                    "minor_units": 18,
                    "symbol": "Ξ",
                    "type": "cryptocurrency",
                    "entity": "Decentralized",
                    "introduced": "2015-07-30",
                    "market_cap_rank": 2,
                    "note": "Not an ISO 4217 code.",
                },
                {
                    "code": "XRP",
                    "name": "XRP",
                    "minor_units": 6,
                    "symbol": "XRP",
                    "type": "cryptocurrency",
                    "entity": "Ripple Labs",
                    "introduced": "2012-06-01",
                    "market_cap_rank": 5,
                    "note": "Not an ISO 4217 code.",
                },
            ],
            "stablecoins": [
                {
                    "code": "USDT",
                    "name": "Tether USD",
                    "minor_units": 6,
                    "symbol": "₮",
                    "type": "stablecoin",
                    "entity": "Tether Limited",
                    "introduced": "2014-10-06",
                    "market_cap_rank": 3,
                    "pegged_to": "USD",
                    "peg_mechanism": "Fiat-collateralized",
                    "note": "Not an ISO 4217 code.",
                },
            ],
            "commodities": [],
            "special_purpose": [],
        },
    }


@pytest.fixture
def sample_markets() -> list[dict]:
    """Minimal CoinGecko /coins/markets response."""
    return [
        {"id": "bitcoin", "market_cap_rank": 1, "market_cap": 1_200_000_000_000},
        {"id": "ethereum", "market_cap_rank": 2, "market_cap": 400_000_000_000},
        {"id": "tether", "market_cap_rank": 3, "market_cap": 100_000_000_000},
        {"id": "ripple", "market_cap_rank": 4, "market_cap": 80_000_000_000},
    ]


@pytest.fixture
def registry_file(tmp_path: Path, sample_registry: dict) -> Path:
    """Write the sample registry to a temp file and return its path."""
    path = tmp_path / "iso4217.json"
    path.write_text(json.dumps(sample_registry, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class TestLogger:
    def test_quiet_suppresses_info_and_success(self, capsys):
        log = Logger(quiet=True)
        log.info("info message")
        log.success("success message")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_quiet_still_shows_warn_and_error(self, capsys):
        log = Logger(quiet=True)
        log.warn("warning")
        log.error("error")
        captured = capsys.readouterr()
        assert "warning" in captured.err
        assert "error" in captured.err

    def test_verbose_shows_debug(self, capsys):
        log = Logger(verbose=True)
        log.debug("debug info")
        captured = capsys.readouterr()
        assert "debug" in captured.err

    def test_non_verbose_hides_debug(self, capsys):
        log = Logger(verbose=False)
        log.debug("debug info")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_all_output_goes_to_stderr(self, capsys):
        """Stdout is reserved for JSON output — logger always uses stderr."""
        log = Logger(verbose=True)
        log.info("a")
        log.warn("b")
        log.error("c")
        log.success("d")
        log.debug("e")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "a" in captured.err
        assert "b" in captured.err
        assert "c" in captured.err
        assert "d" in captured.err
        assert "e" in captured.err


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class TestChange:
    def test_direction_improved(self):
        assert Change("BTC", "cryptocurrencies", 5, 3).direction == "↑"

    def test_direction_worsened(self):
        assert Change("BTC", "cryptocurrencies", 3, 5).direction == "↓"

    def test_direction_unchanged(self):
        assert Change("BTC", "cryptocurrencies", 3, 3).direction == "="

    def test_to_dict(self):
        c = Change("BTC", "cryptocurrencies", 1, 2, 1e12)
        d = c.to_dict()
        assert d["code"] == "BTC"
        assert d["category"] == "cryptocurrencies"
        assert d["old_rank"] == 1
        assert d["new_rank"] == 2
        assert d["new_market_cap_usd"] == 1e12


class TestRefreshResult:
    def test_to_dict_empty(self):
        r = RefreshResult(status="no_changes", timestamp="2026-09-14T12:00:00+00:00")
        d = r.to_dict()
        assert d["status"] == "no_changes"
        assert d["changes"] == []
        assert d["missing"] == []

    def test_to_dict_with_changes(self):
        r = RefreshResult(
            status="updated",
            changes=[Change("BTC", "cryptocurrencies", 1, 2)],
            timestamp="2026-09-14T12:00:00+00:00",
        )
        d = r.to_dict()
        assert len(d["changes"]) == 1
        assert d["changes"][0]["code"] == "BTC"

    def test_to_json_round_trips(self):
        r = RefreshResult(status="no_changes", timestamp="2026-09-14T12:00:00+00:00")
        parsed = json.loads(r.to_json())
        assert parsed["status"] == "no_changes"


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

class TestLoadRegistry:
    def test_loads_valid_file(self, registry_file: Path, sample_registry: dict):
        assert load_registry(registry_file) == sample_registry

    def test_missing_file_exits_fatal(self, tmp_path: Path):
        with pytest.raises(SystemExit) as exc_info:
            load_registry(tmp_path / "missing.json")
        assert exc_info.value.code == EXIT_FATAL

    def test_invalid_json_exits_fatal(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(SystemExit) as exc_info:
            load_registry(bad)
        assert exc_info.value.code == EXIT_FATAL


class TestFindRankedEntries:
    def test_extracts_all_ranked(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        assert set(entries.keys()) == {"BTC", "ETH", "USDT", "XRP"}

    def test_attaches_category(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        assert entries["BTC"]["_category"] == "cryptocurrencies"
        assert entries["USDT"]["_category"] == "stablecoins"

    def test_empty_registry(self):
        assert find_ranked_entries({}) == {}

    def test_ignores_entries_without_code(self):
        registry = {
            "non_iso": {
                "cryptocurrencies": [
                    {"code": "BTC", "market_cap_rank": 1},
                    {"market_cap_rank": 2},  # no code — skipped
                ],
                "stablecoins": [],
            }
        }
        entries = find_ranked_entries(registry)
        assert "BTC" in entries
        assert len(entries) == 1


class TestBackupRestore:
    def test_backup_creates_bak(self, registry_file: Path):
        backup = backup_registry(registry_file)
        assert backup.exists()
        assert backup.name == "iso4217.json.bak"
        assert backup.read_bytes() == registry_file.read_bytes()

    def test_restore_overwrites_original(self, registry_file: Path, quiet_logger: Logger):
        original_content = registry_file.read_text()
        backup = backup_registry(registry_file)
        registry_file.write_text('{"modified": true}')
        restore_backup(backup, registry_file, quiet_logger)
        assert registry_file.read_text() == original_content


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

class TestFetchCoingeckoMarkets:
    def test_success_single_page(self, quiet_logger: Logger):
        payload = [{"id": "bitcoin", "market_cap_rank": 1}]
        with patch("tools.refresh_market_caps._http_get_json", return_value=payload):
            result = fetch_coingecko_markets(top_n=10, log=quiet_logger)
        assert result == payload

    def test_pagination_multiple_pages(self, quiet_logger: Logger):
        """When a page returns exactly per_page items, we fetch the next page."""
        page1 = [{"id": f"coin{i}", "market_cap_rank": i} for i in range(1, 251)]
        page2 = [{"id": f"coin{i}", "market_cap_rank": i} for i in range(251, 261)]

        with patch("tools.refresh_market_caps._http_get_json") as mock_get:
            mock_get.side_effect = [page1, page2]
            result = fetch_coingecko_markets(top_n=260, log=quiet_logger)

        assert len(result) == 260
        assert mock_get.call_count == 2

    def test_top_n_limits_result(self, quiet_logger: Logger):
        page = [{"id": f"coin{i}", "market_cap_rank": i} for i in range(1, 251)]
        with patch("tools.refresh_market_caps._http_get_json", return_value=page):
            result = fetch_coingecko_markets(top_n=10, log=quiet_logger)
        assert len(result) == 10

    def test_retry_on_5xx(self, quiet_logger: Logger):
        """A 500 error on attempt 1, success on attempt 2."""
        payload = [{"id": "bitcoin", "market_cap_rank": 1}]
        http_500 = HTTPError("http://x", 500, "Server Error", {}, None)

        with patch("tools.refresh_market_caps._http_get_json") as mock_get, \
             patch("tools.refresh_market_caps.time.sleep"):
            mock_get.side_effect = [http_500, payload]
            result = fetch_coingecko_markets(
                top_n=10, log=quiet_logger, retries=3
            )

        assert result == payload
        assert mock_get.call_count == 2

    def test_retry_on_429_rate_limit(self, quiet_logger: Logger):
        payload = [{"id": "bitcoin", "market_cap_rank": 1}]
        http_429 = HTTPError("http://x", 429, "Rate Limited", {}, None)

        with patch("tools.refresh_market_caps._http_get_json") as mock_get, \
             patch("tools.refresh_market_caps.time.sleep"):
            mock_get.side_effect = [http_429, payload]
            result = fetch_coingecko_markets(top_n=10, log=quiet_logger)
        assert result == payload

    def test_fail_fast_on_404(self, quiet_logger: Logger):
        """4xx (except 429) is permanent — no retry."""
        http_404 = HTTPError("http://x", 404, "Not Found", {}, None)

        with patch("tools.refresh_market_caps._http_get_json") as mock_get:
            mock_get.side_effect = http_404
            with pytest.raises(APIError):
                fetch_coingecko_markets(top_n=10, log=quiet_logger)
            assert mock_get.call_count == 1  # no retry

    def test_fail_fast_on_403(self, quiet_logger: Logger):
        http_403 = HTTPError("http://x", 403, "Forbidden", {}, None)
        with patch("tools.refresh_market_caps._http_get_json") as mock_get:
            mock_get.side_effect = http_403
            with pytest.raises(APIError):
                fetch_coingecko_markets(top_n=10, log=quiet_logger)
            assert mock_get.call_count == 1

    def test_retry_on_url_error(self, quiet_logger: Logger):
        payload = [{"id": "bitcoin", "market_cap_rank": 1}]
        with patch("tools.refresh_market_caps._http_get_json") as mock_get, \
             patch("tools.refresh_market_caps.time.sleep"):
            mock_get.side_effect = [URLError("connection reset"), payload]
            result = fetch_coingecko_markets(top_n=10, log=quiet_logger)
        assert result == payload

    def test_retry_on_timeout(self, quiet_logger: Logger):
        payload = [{"id": "bitcoin", "market_cap_rank": 1}]
        with patch("tools.refresh_market_caps._http_get_json") as mock_get, \
             patch("tools.refresh_market_caps.time.sleep"):
            mock_get.side_effect = [TimeoutError("timed out"), payload]
            result = fetch_coingecko_markets(top_n=10, log=quiet_logger)
        assert result == payload

    def test_exhausted_retries_raises_network_error(self, quiet_logger: Logger):
        with patch("tools.refresh_market_caps._http_get_json") as mock_get, \
             patch("tools.refresh_market_caps.time.sleep"):
            mock_get.side_effect = URLError("persistent failure")
            with pytest.raises(NetworkError):
                fetch_coingecko_markets(top_n=10, log=quiet_logger, retries=3)
            assert mock_get.call_count == 3

    def test_unexpected_response_type_raises_api_error(self, quiet_logger: Logger):
        """
        CoinGecko returning a dict instead of a list indicates an API-level
        problem (rate limit message, error object), not a network failure.
        The tool raises APIError, not NetworkError — this distinction matters
        because APIError is a permanent-class failure that shouldn't be retried
        silently for hours.
        """
        with patch("tools.refresh_market_caps._http_get_json",
                   return_value={"error": "rate limited"}):
            with pytest.raises(APIError, match="Unexpected response type"):
                fetch_coingecko_markets(top_n=10, log=quiet_logger, retries=1)

    def test_empty_first_page_stops_pagination(self, quiet_logger: Logger):
        with patch("tools.refresh_market_caps._http_get_json", return_value=[]):
            result = fetch_coingecko_markets(top_n=500, log=quiet_logger)
        assert result == []


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

class TestBuildFreshRanks:
    def test_maps_ids_to_codes(self, sample_markets, quiet_logger: Logger):
        result = build_fresh_ranks(sample_markets, CODE_TO_COINGECKO_ID, quiet_logger)
        assert result["BTC"]["rank"] == 1
        assert result["ETH"]["rank"] == 2
        assert result["USDT"]["rank"] == 3
        assert result["XRP"]["rank"] == 4

    def test_preserves_market_cap(self, sample_markets, quiet_logger: Logger):
        result = build_fresh_ranks(sample_markets, CODE_TO_COINGECKO_ID, quiet_logger)
        assert result["BTC"]["market_cap_usd"] == 1_200_000_000_000

    def test_missing_coins_warned_not_fatal(self, quiet_logger: Logger, capsys):
        markets = [{"id": "bitcoin", "market_cap_rank": 1, "market_cap": 1e12}]
        result = build_fresh_ranks(markets, CODE_TO_COINGECKO_ID, quiet_logger)
        # Only BTC mapped
        assert set(result.keys()) == {"BTC"}
        # Warning was emitted for the missing coins (via logger to stderr)
        # Note: quiet_logger suppresses info but NOT warn
        captured = capsys.readouterr()
        assert "SOL" in captured.err or "not found" in captured.err

    def test_skips_coins_without_rank(self, quiet_logger: Logger):
        markets = [{"id": "bitcoin", "market_cap_rank": None, "market_cap": None}]
        result = build_fresh_ranks(markets, CODE_TO_COINGECKO_ID, quiet_logger)
        assert "BTC" not in result

    def test_skips_unmapped_ids(self, quiet_logger: Logger):
        markets = [{"id": "unknown-coin", "market_cap_rank": 1, "market_cap": 1e12}]
        result = build_fresh_ranks(markets, CODE_TO_COINGECKO_ID, quiet_logger)
        assert result == {}


class TestComputeChanges:
    def test_no_changes(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        fresh = {
            "BTC": {"rank": 1},
            "ETH": {"rank": 2},
            "USDT": {"rank": 3},
            "XRP": {"rank": 5},
        }
        assert compute_changes(entries, fresh) == []

    def test_detects_changes(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        fresh = {
            "BTC": {"rank": 1},
            "ETH": {"rank": 2},
            "USDT": {"rank": 3},
            "XRP": {"rank": 8},  # changed from 5 → 8
        }
        changes = compute_changes(entries, fresh)
        assert len(changes) == 1
        assert changes[0].code == "XRP"
        assert changes[0].old_rank == 5
        assert changes[0].new_rank == 8

    def test_skips_fresh_codes_not_in_registry(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        fresh = {
            "BTC": {"rank": 1},
            "NEWCOIN": {"rank": 99},
        }
        changes = compute_changes(entries, fresh)
        assert all(c.code != "NEWCOIN" for c in changes)

    def test_result_is_sorted_by_code(self, sample_registry: dict):
        entries = find_ranked_entries(sample_registry)
        fresh = {
            "XRP": {"rank": 99},
            "BTC": {"rank": 99},
            "USDT": {"rank": 99},
            "ETH": {"rank": 99},
        }
        changes = compute_changes(entries, fresh)
        codes = [c.code for c in changes]
        assert codes == sorted(codes)


# ---------------------------------------------------------------------------
# Text patcher
# ---------------------------------------------------------------------------

class TestApplyChangesToText:
    def _make_text(self, registry: dict) -> str:
        return json.dumps(registry, indent=2)

    def test_single_change(self, sample_registry: dict, quiet_logger: Logger):
        text = self._make_text(sample_registry)
        changes = [Change("XRP", "cryptocurrencies", 5, 8)]
        new_text, applied = apply_changes_to_text(text, changes, quiet_logger)
        assert applied == 1
        assert '"market_cap_rank": 8' in new_text
        # Verify only XRP changed
        parsed = json.loads(new_text)
        xrp = next(c for c in parsed["non_iso"]["cryptocurrencies"] if c["code"] == "XRP")
        assert xrp["market_cap_rank"] == 8
        btc = next(c for c in parsed["non_iso"]["cryptocurrencies"] if c["code"] == "BTC")
        assert btc["market_cap_rank"] == 1

    def test_multiple_changes(self, sample_registry: dict, quiet_logger: Logger):
        text = self._make_text(sample_registry)
        changes = [
            Change("BTC", "cryptocurrencies", 1, 2),
            Change("ETH", "cryptocurrencies", 2, 1),
        ]
        new_text, applied = apply_changes_to_text(text, changes, quiet_logger)
        assert applied == 2
        parsed = json.loads(new_text)
        assert next(c for c in parsed["non_iso"]["cryptocurrencies"]
                    if c["code"] == "BTC")["market_cap_rank"] == 2
        assert next(c for c in parsed["non_iso"]["cryptocurrencies"]
                    if c["code"] == "ETH")["market_cap_rank"] == 1

    def test_preserves_formatting(self, sample_registry: dict, quiet_logger: Logger):
        """The patched text should differ only where we intended."""
        text = self._make_text(sample_registry)
        changes = [Change("XRP", "cryptocurrencies", 5, 8)]
        new_text, _ = apply_changes_to_text(text, changes, quiet_logger)

        # Line count should be identical
        assert text.count("\n") == new_text.count("\n")

        # Character count should differ by exactly the length difference
        # of "5" (1 char) → "8" (1 char) = 0
        # Actually old=5, new=8, both 1 char, so identical length
        # Let's test with different-length ranks instead
        changes = [Change("XRP", "cryptocurrencies", 5, 99)]
        new_text, _ = apply_changes_to_text(text, changes, quiet_logger)
        assert len(new_text) == len(text) + 1  # 5 → 99 adds 1 char

    def test_missing_code_raises(self, sample_registry: dict, quiet_logger: Logger):
        text = self._make_text(sample_registry)
        changes = [Change("NOTREAL", "cryptocurrencies", 1, 2)]
        with pytest.raises(PatchError, match="NOTREAL"):
            apply_changes_to_text(text, changes, quiet_logger)

    def test_drifted_rank_raises(self, sample_registry: dict, quiet_logger: Logger):
        """If the old rank doesn't match what's in the file, refuse to patch."""
        text = self._make_text(sample_registry)
        # Claim XRP is 99 in the file (it's actually 5)
        changes = [Change("XRP", "cryptocurrencies", 99, 8)]
        with pytest.raises(PatchError, match="drifted"):
            apply_changes_to_text(text, changes, quiet_logger)

    def test_idempotent(self, sample_registry: dict, quiet_logger: Logger):
        """Applying the same change twice: second call should raise (drift)."""
        text = self._make_text(sample_registry)
        changes = [Change("XRP", "cryptocurrencies", 5, 8)]
        new_text, _ = apply_changes_to_text(text, changes, quiet_logger)
        # Second application — the old rank 5 is no longer there
        with pytest.raises(PatchError):
            apply_changes_to_text(new_text, changes, quiet_logger)

    def test_does_not_patch_across_entries(self, sample_registry: dict, quiet_logger: Logger):
        """A rank value that appears in another entry shouldn't be touched."""
        # BTC has rank 1. Change USDT to 1 — ensure BTC's rank stays 1.
        text = self._make_text(sample_registry)
        changes = [Change("USDT", "stablecoins", 3, 1)]
        new_text, _ = apply_changes_to_text(text, changes, quiet_logger)
        parsed = json.loads(new_text)
        btc = next(c for c in parsed["non_iso"]["cryptocurrencies"] if c["code"] == "BTC")
        usdt = next(c for c in parsed["non_iso"]["stablecoins"] if c["code"] == "USDT")
        assert btc["market_cap_rank"] == 1  # unchanged
        assert usdt["market_cap_rank"] == 1  # changed to 1


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class TestValidateResult:
    def test_valid_result(self, sample_registry: dict, quiet_logger: Logger):
        new_text = json.dumps(sample_registry, indent=2).replace(
            '"market_cap_rank": 5', '"market_cap_rank": 8'
        )
        changes = [Change("XRP", "cryptocurrencies", 5, 8)]
        validate_result(new_text, sample_registry, changes, quiet_logger)

    def test_invalid_json_raises(self, sample_registry: dict, quiet_logger: Logger):
        with pytest.raises(ValidationError, match="not valid JSON"):
            validate_result("{not json", sample_registry, [], quiet_logger)

    def test_missing_expected_change_raises(self, sample_registry: dict, quiet_logger: Logger):
        """Claim a change happened when it didn't."""
        new_text = json.dumps(sample_registry, indent=2)  # unchanged
        changes = [Change("XRP", "cryptocurrencies", 5, 8)]
        with pytest.raises(ValidationError, match="expected rank 8"):
            validate_result(new_text, sample_registry, changes, quiet_logger)

    def test_side_effect_raises(self, sample_registry: dict, quiet_logger: Logger):
        """A patch that modifies an unrelated field should be rejected."""
        mutated = json.loads(json.dumps(sample_registry))
        mutated["non_iso"]["cryptocurrencies"][0]["name"] = "Not Bitcoin"
        mutated["non_iso"]["cryptocurrencies"][0]["market_cap_rank"] = 8

        new_text = json.dumps(mutated, indent=2)
        changes = [Change("BTC", "cryptocurrencies", 1, 8)]
        with pytest.raises(ValidationError, match="unrelated fields"):
            validate_result(new_text, sample_registry, changes, quiet_logger)

    def test_changed_entry_set_raises(self, sample_registry: dict, quiet_logger: Logger):
        """Adding/removing an entry should be rejected."""
        mutated = json.loads(json.dumps(sample_registry))
        mutated["non_iso"]["cryptocurrencies"].pop()  # remove XRP

        new_text = json.dumps(mutated, indent=2)
        with pytest.raises(ValidationError):
            validate_result(new_text, sample_registry, [], quiet_logger)


# ---------------------------------------------------------------------------
# Orchestration (refresh)
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_dry_run_no_write(
        self, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        original = registry_file.read_text()
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=True,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "dry_run"
        assert registry_file.read_text() == original

    def test_check_mode_clean(
        self, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        """Ranks match — no changes."""
        # The sample_markets rank for ripple is 4, but registry has XRP=5 → changes exist
        # Adjust markets to match registry
        markets = [
            {"id": "bitcoin", "market_cap_rank": 1, "market_cap": 1e12},
            {"id": "ethereum", "market_cap_rank": 2, "market_cap": 4e11},
            {"id": "tether", "market_cap_rank": 3, "market_cap": 1e11},
            {"id": "ripple", "market_cap_rank": 5, "market_cap": 8e10},
        ]
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=markets):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=True,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "check_clean"

    def test_check_mode_dirty(
        self, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        """Ranks differ — changes pending."""
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=True,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "check_dirty"
        assert len(result.changes) > 0

    def test_apply_writes_changes(
        self, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "updated"
        # Verify written
        written = json.loads(registry_file.read_text())
        xrp = next(c for c in written["non_iso"]["cryptocurrencies"]
                   if c["code"] == "XRP")
        assert xrp["market_cap_rank"] == 4  # was 5 in registry

    def test_no_changes_status(
        self, registry_file: Path, quiet_logger: Logger
    ):
        """When nothing changed, status is no_changes and file untouched."""
        markets = [
            {"id": "bitcoin", "market_cap_rank": 1, "market_cap": 1e12},
            {"id": "ethereum", "market_cap_rank": 2, "market_cap": 4e11},
            {"id": "tether", "market_cap_rank": 3, "market_cap": 1e11},
            {"id": "ripple", "market_cap_rank": 5, "market_cap": 8e10},
        ]
        original = registry_file.read_text()
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=markets):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "no_changes"
        assert registry_file.read_text() == original

    def test_network_error_returns_error_status(
        self, registry_file: Path, quiet_logger: Logger
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   side_effect=NetworkError("connection refused")):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "error"
        assert "Network failure" in result.message

    def test_api_error_returns_error_status(
        self, registry_file: Path, quiet_logger: Logger
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   side_effect=APIError("HTTP 403 Forbidden")):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "error"
        assert "API error" in result.message

    def test_snapshot_replay(
        self, tmp_path: Path, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        snapshot = tmp_path / "cg.json"
        snapshot.write_text(json.dumps(sample_markets))
        result = refresh(
            registry_path=registry_file,
            top_n=250,
            dry_run=True,
            check_mode=False,
            snapshot_path=snapshot,
            log=quiet_logger,
        )
        assert result.status == "dry_run"
        assert "snapshot" in result.source

    def test_rollback_on_validation_failure(
        self, registry_file: Path, quiet_logger: Logger, sample_markets
    ):
        """If validation fails mid-patch, the file is unchanged."""
        original = registry_file.read_text()
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets), \
             patch("tools.refresh_market_caps.validate_result",
                   side_effect=ValidationError("simulated")):
            result = refresh(
                registry_path=registry_file,
                top_n=250,
                dry_run=False,
                check_mode=False,
                snapshot_path=None,
                log=quiet_logger,
            )
        assert result.status == "error"
        assert "rolled back" in result.message
        assert registry_file.read_text() == original


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        """
        Default registry path must match the module's own constant, not a
        hardcoded absolute path — the test has to pass on any machine
        (developer laptop, CI runner, container).
        """
        from tools.refresh_market_caps import DEFAULT_REGISTRY_PATH
        args = parse_args([])
        assert args.registry == DEFAULT_REGISTRY_PATH
        assert args.top_n == 250
        assert args.dry_run is False
        assert args.check is False
        assert args.json is False
        assert args.verbose is False
        assert args.quiet is False

    def test_dry_run_flag(self):
        assert parse_args(["--dry-run"]).dry_run is True
        assert parse_args(["-n"]).dry_run is True

    def test_check_flag(self):
        assert parse_args(["--check"]).check is True
        assert parse_args(["-c"]).check is True

    def test_registry_override(self):
        args = parse_args(["--registry", "/tmp/x.json"])
        assert args.registry == Path("/tmp/x.json")

    def test_top_n_override(self):
        assert parse_args(["--top-n", "50"]).top_n == 50

    def test_json_flag(self):
        assert parse_args(["--json"]).json is True

    def test_snapshot(self):
        args = parse_args(["--snapshot", "/tmp/cg.json"])
        assert args.snapshot == Path("/tmp/cg.json")


class TestMain:
    def test_missing_registry_exits_fatal(self, tmp_path: Path):
        code = main(["--registry", str(tmp_path / "missing.json"), "--dry-run"])
        assert code == EXIT_FATAL

    def test_dry_run_and_check_mutually_exclusive(
        self, registry_file: Path, capsys
    ):
        code = main([
            "--registry", str(registry_file),
            "--dry-run",
            "--check",
        ])
        assert code == EXIT_FATAL
        captured = capsys.readouterr()
        assert "mutually exclusive" in captured.err

    def test_network_error_exit_code_1(
        self, registry_file: Path
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   side_effect=NetworkError("connection refused")):
            code = main(["--registry", str(registry_file), "--dry-run", "--quiet"])
        assert code == EXIT_NETWORK_ERROR

    def test_check_dirty_exit_code_3(
        self, registry_file: Path, sample_markets
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            code = main(["--registry", str(registry_file), "--check", "--quiet"])
        assert code == EXIT_CHANGES_PENDING

    def test_check_clean_exit_code_0(
        self, registry_file: Path
    ):
        markets = [
            {"id": "bitcoin", "market_cap_rank": 1, "market_cap": 1e12},
            {"id": "ethereum", "market_cap_rank": 2, "market_cap": 4e11},
            {"id": "tether", "market_cap_rank": 3, "market_cap": 1e11},
            {"id": "ripple", "market_cap_rank": 5, "market_cap": 8e10},
        ]
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=markets):
            code = main(["--registry", str(registry_file), "--check", "--quiet"])
        assert code == EXIT_OK

    def test_dry_run_exit_code_0(
        self, registry_file: Path, sample_markets
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            code = main(["--registry", str(registry_file), "--dry-run", "--quiet"])
        assert code == EXIT_OK

    def test_json_output_to_stdout(
        self, registry_file: Path, sample_markets, capsys
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            main(["--registry", str(registry_file), "--dry-run",
                  "--json", "--quiet"])
        captured = capsys.readouterr()
        # Stdout should be valid JSON
        parsed = json.loads(captured.out)
        assert parsed["status"] == "dry_run"
        assert len(parsed["changes"]) > 0

    def test_human_output_goes_to_stderr(
        self, registry_file: Path, sample_markets, capsys
    ):
        with patch("tools.refresh_market_caps.fetch_coingecko_markets",
                   return_value=sample_markets):
            main(["--registry", str(registry_file), "--dry-run"])
        captured = capsys.readouterr()
        assert captured.out == ""  # nothing on stdout
        assert "changes" in captured.err.lower()
        