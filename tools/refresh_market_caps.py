#!/usr/bin/env python3
"""
Refresh market_cap_rank for crypto/stablecoin entries in iso4217.json.

Fetches the current top-N cryptocurrencies by market cap from CoinGecko (free
tier, no API key required), maps each to its ISO 4217 registry code, and updates
the `market_cap_rank` field in place.

This is a MANUAL maintenance tool. Market cap ranks change daily; running this
automatically in CI would create daily commits for a field that is inherently
a snapshot. Recommended cadence: weekly, or before each registry release.

Design principles
-----------------
- **Preserves file formatting.** Uses targeted string replacement, not a full
  json.load/json.dump round-trip. A round-trip would reformat ~3,000 lines and
  produce a diff nobody can review.
- **Idempotent.** Running twice with the same CoinGecko data produces no diff.
- **Never partially writes.** Any validation failure restores the backup.
- **Network-resilient.** Retries transient failures; exits 0 with a clear
  message on persistent failure. Never leaves the registry in an inconsistent
  state.
- **Only updates existing entries.** Adding or removing coins requires a
  schema-checked decision (see CHANGELOG v1.4.0) — not something a refresh
  tool should decide unilaterally.
- **Only fetches the top N by market cap (default 250).** Entries that have
  dropped below top N won't be refreshed — the tool warns about them by name
  but doesn't fetch their individual rank. In that case, update the rank
  manually using CoinGecko's `/coins/{id}` endpoint, which returns the exact
  current rank regardless of global position. Learned the hard way with USDP
  (rank 700, well below the default fetch window).
- **Idempotent-by-default.** `--check` mode exits 3 (not 0) if changes are
  needed, without writing. Useful for CI monitoring.

Usage
-----
    # See what would change (safe — writes nothing)
    python3 tools/refresh_market_caps.py --dry-run

    # Apply changes
    python3 tools/refresh_market_caps.py

    # Exit 3 if stale (CI gate)
    python3 tools/refresh_market_caps.py --check

    # Machine-readable output
    python3 tools/refresh_market_caps.py --json

    # Diagnose network issues
    python3 tools/refresh_market_caps.py --verbose --dry-run

    # Test against a saved CoinGecko response
    python3 tools/refresh_market_caps.py --snapshot /tmp/cg.json

    # Custom registry (for testing)
    python3 tools/refresh_market_caps.py --registry /tmp/test.json --dry-run

Exit codes
----------
    0 — Success: changes applied, or no changes needed
    1 — Network/API failure (no changes made)
    2 — Fatal error (missing file, invalid JSON, patch failure)
    3 — `--check` mode: changes are pending

Module structure
----------------
    Constants        — URLs, code map, defaults
    Logger           — structured, leveled, stream-aware output
    Data classes     — Change, RefreshResult (all serializable)
    Network layer    — fetch_coingecko_markets() with retry/backoff
    Registry I/O     — load, find, backup, restore
    Diff engine      — build_fresh_ranks(), compute_changes()
    Text patcher     — apply_changes_to_text()
    Validator        — validate_result()
    Output           — print_human(), print_json()
    CLI              — parse_args(), main()
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH: Path = PROJECT_ROOT / "iso4217.json"

COINGECKO_MARKETS_URL: str = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd"
    "&order=market_cap_desc"
    "&per_page={per_page}"
    "&page={page}"
    "&sparkline=false"
    "&price_change_percentage=24h"
)

DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_RETRIES: int = 3
DEFAULT_RETRY_BACKOFF: float = 2.0
DEFAULT_TOP_N: int = 250

USER_AGENT: str = (
    "iso4217-registry-market-cap-refresh/1.0 "
    "(https://github.com/slimissa/iso4217)"
)

# Mapping from ISO 4217 registry code to CoinGecko coin ID.
# CoinGecko uses slug IDs (e.g., "bitcoin"), not tickers — so this map is
# required. Add new codes here when the registry gains new non-ISO entries.
CODE_TO_COINGECKO_ID: dict[str, str] = {
    # Cryptocurrencies
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "XRP": "ripple",
    "SOL": "solana",
    "BNB": "binancecoin",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    # Stablecoins
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "USDP": "paxos-standard",
    "FRAX": "frax",
    "TUSD": "true-usd",
}

# Non-ISO categories whose entries carry a market_cap_rank.
RANKED_CATEGORIES: tuple[str, ...] = ("cryptocurrencies", "stablecoins")

# Exit codes (documented in the module docstring).
EXIT_OK: int = 0
EXIT_NETWORK_ERROR: int = 1
EXIT_FATAL: int = 2
EXIT_CHANGES_PENDING: int = 3


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class Logger:
    """
    Small leveled logger. Deliberately minimal — no dependency on the logging
    module, so this tool stays stdlib-only. Quiet mode suppresses info/debug;
    verbose mode enables debug.
    """

    def __init__(self, verbose: bool = False, quiet: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet

    def debug(self, msg: str) -> None:
        if self.verbose and not self.quiet:
            print(f"[debug] {msg}", file=sys.stderr)

    def info(self, msg: str) -> None:
        if not self.quiet:
            print(msg, file=sys.stderr)

    def warn(self, msg: str) -> None:
        print(f"⚠️  {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"❌ {msg}", file=sys.stderr)

    def success(self, msg: str) -> None:
        if not self.quiet:
            print(f"✅ {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Change:
    """A single market_cap_rank update."""
    code: str
    category: str
    old_rank: int
    new_rank: int
    new_market_cap_usd: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "old_rank": self.old_rank,
            "new_rank": self.new_rank,
            "new_market_cap_usd": self.new_market_cap_usd,
        }

    @property
    def direction(self) -> str:
        if self.new_rank < self.old_rank:
            return "↑"  # rank improved
        if self.new_rank > self.old_rank:
            return "↓"  # rank worsened
        return "="


@dataclass
class RefreshResult:
    """Aggregate result of a refresh run, serializable for CI."""
    status: str
    source: str = "coingecko"
    checked: int = 0
    changes: list[Change] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    timestamp: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "checked": self.checked,
            "changes": [c.to_dict() for c in self.changes],
            "missing": self.missing,
            "timestamp": self.timestamp,
            "message": self.message,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

class NetworkError(Exception):
    """Raised on unrecoverable network failure after all retries."""


class APIError(Exception):
    """Raised on CoinGecko API error (HTTP 4xx/5xx after retries)."""


def _http_get_json(url: str, timeout: int, log: Logger) -> Any:
    """
    Single HTTP GET returning parsed JSON.

    Raises urllib.error.HTTPError / URLError / TimeoutError on failure.
    Caller handles retry.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def fetch_coingecko_markets(
    top_n: int,
    log: Logger,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> list[dict[str, Any]]:
    """
    Fetch up to `top_n` coins by market cap from CoinGecko.

    Handles pagination (CoinGecko max 250 per page), retries transient
    failures with exponential backoff, and never partially returns — either
    you get a full list or an exception.

    Raises:
        NetworkError — after all retries exhausted
        APIError    — HTTP 4xx/5xx that retrying won't fix (e.g., 401, 403, 404)
    """
    per_page = min(250, top_n)
    pages_needed = (top_n + per_page - 1) // per_page

    all_markets: list[dict[str, Any]] = []

    for page in range(1, pages_needed + 1):
        url = COINGECKO_MARKETS_URL.format(per_page=per_page, page=page)
        log.debug(f"Fetching page {page}/{pages_needed}: {url}")

        page_data = _fetch_with_retry(url, timeout, retries, log)
        if not page_data:
            break

        all_markets.extend(page_data)
        if len(page_data) < per_page:
            break  # no more pages

    return all_markets[:top_n]


def _fetch_with_retry(
    url: str,
    timeout: int,
    retries: int,
    log: Logger,
) -> list[dict[str, Any]]:
    """Fetch a single URL with exponential backoff on transient failures."""
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            data = _http_get_json(url, timeout, log)
            if isinstance(data, list):
                return data
            raise APIError(f"Unexpected response type: {type(data).__name__}")

        except urllib.error.HTTPError as e:
            last_error = e
            # 4xx (except 429) is a permanent error — retry won't help
            if 400 <= e.code < 500 and e.code != 429:
                raise APIError(f"HTTP {e.code} {e.reason}") from e
            log.warn(f"HTTP {e.code} on attempt {attempt}/{retries}")
            # 429 (rate limit) or 5xx — retry with backoff
            if attempt < retries:
                backoff = DEFAULT_RETRY_BACKOFF ** attempt
                log.debug(f"Backing off {backoff:.1f}s before retry")
                time.sleep(backoff)

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            log.warn(f"Network error on attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                backoff = DEFAULT_RETRY_BACKOFF ** attempt
                log.debug(f"Backing off {backoff:.1f}s before retry")
                time.sleep(backoff)

    raise NetworkError(
        f"Failed after {retries} attempts: {last_error}"
    ) from last_error


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def load_registry(path: Path) -> dict[str, Any]:
    """Load and parse the registry. Exits with EXIT_FATAL on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"FATAL: Registry not found: {path}", file=sys.stderr)
        sys.exit(EXIT_FATAL)
    except json.JSONDecodeError as e:
        print(f"FATAL: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_FATAL)


def find_ranked_entries(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Return {code: entry_dict} for all non-ISO entries that carry a
    market_cap_rank. Codes are unique across categories in the schema, so no
    collision risk.
    """
    entries: dict[str, dict[str, Any]] = {}
    for category in RANKED_CATEGORIES:
        for entry in registry.get("non_iso", {}).get(category, []):
            code = entry.get("code")
            if code:
                entries[code] = {**entry, "_category": category}
    return entries


def backup_registry(path: Path) -> Path:
    """Create a .bak copy. Returns the backup path."""
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy(path, backup)
    return backup


def restore_backup(backup: Path, path: Path, log: Logger) -> None:
    """Restore the backup over the registry, logging the action."""
    shutil.copy(backup, path)
    log.warn(f"Restored from backup: {backup}")


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

def build_fresh_ranks(
    markets: list[dict[str, Any]],
    code_map: dict[str, str],
    log: Logger,
) -> dict[str, dict[str, Any]]:
    """
    Map CoinGecko results to registry codes.

    Returns {registry_code: {"rank": int, "market_cap_usd": float}}.
    Logs a warning for codes in `code_map` that weren't in the response —
    a coin might be delisted, or dropped out of the top N.
    """
    # Reverse the map: CoinGecko ID → registry code
    id_to_code = {v: k for k, v in code_map.items()}

    results: dict[str, dict[str, Any]] = {}
    for coin in markets:
        coin_id = coin.get("id")
        if coin_id in id_to_code:
            code = id_to_code[coin_id]
            rank = coin.get("market_cap_rank")
            if rank is not None:
                results[code] = {
                    "rank": int(rank),
                    "market_cap_usd": coin.get("market_cap"),
                }

    # Warn about codes we didn't find
    missing = set(code_map.keys()) - set(results.keys())
    for code in sorted(missing):
        log.warn(
            f"{code} not found in CoinGecko response "
            f"(delisted, or dropped below top {len(markets)})"
        )

    return results


def compute_changes(
    entries: dict[str, dict[str, Any]],
    fresh: dict[str, dict[str, Any]],
) -> list[Change]:
    """
    Compute the list of changes. Stable-sorted by code so diffs are
    deterministic across runs.
    """
    changes: list[Change] = []
    for code in sorted(fresh.keys()):
        entry = entries.get(code)
        if entry is None:
            continue  # not in registry — skip
        old_rank = entry.get("market_cap_rank")
        new_rank = fresh[code]["rank"]
        if old_rank is None or old_rank != new_rank:
            changes.append(Change(
                code=code,
                category=entry["_category"],
                old_rank=old_rank if old_rank is not None else -1,
                new_rank=new_rank,
                new_market_cap_usd=fresh[code].get("market_cap_usd"),
            ))
    return changes


# ---------------------------------------------------------------------------
# Text patcher (preserves formatting)
# ---------------------------------------------------------------------------

# Pattern for the entry header — used to find the start of each entry.
# Matches:  "code": "BTC"
_CODE_PATTERN_TEMPLATE = '"code": "{code}"'

# Pattern for the rank field we're replacing.
_RANK_PATTERN_TEMPLATE = '"market_cap_rank": {rank}'


class PatchError(Exception):
    """Raised when a change can't be applied to the raw text."""


def apply_changes_to_text(
    text: str,
    changes: list[Change],
    log: Logger,
) -> tuple[str, int]:
    """
    Apply changes via targeted string replacement. Preserves all formatting.

    For each change:
      1. Locate the entry by its `"code": "XXX"` line.
      2. Search forward for `"market_cap_rank": <old>` within a bounded window.
      3. Replace it with `"market_cap_rank": <new>`.

    Returns (patched_text, applied_count). Raises PatchError if the expected
    old rank isn't found — that indicates the file drifted from what we loaded,
    or the change was already applied by a concurrent run.
    """
    applied = 0
    for change in changes:
        code_pos = text.find(_CODE_PATTERN_TEMPLATE.format(code=change.code))
        if code_pos == -1:
            raise PatchError(
                f"Could not find entry for {change.code} in registry text"
            )

        # Bound the search window so we don't accidentally patch a later entry.
        # 2000 chars comfortably covers any current entry, even with long notes.
        window_end = min(len(text), code_pos + 2000)
        window = text[code_pos:window_end]

        old_pattern = _RANK_PATTERN_TEMPLATE.format(rank=change.old_rank)
        rank_pos = window.find(old_pattern)
        if rank_pos == -1:
            raise PatchError(
                f"Could not find '\"market_cap_rank\": {change.old_rank}' "
                f"in {change.code}'s entry. The file may have drifted."
            )

        absolute_pos = code_pos + rank_pos
        new_pattern = _RANK_PATTERN_TEMPLATE.format(rank=change.new_rank)
        text = (
            text[:absolute_pos]
            + new_pattern
            + text[absolute_pos + len(old_pattern):]
        )
        applied += 1
        log.debug(f"Patched {change.code}: {change.old_rank} → {change.new_rank}")

    return text, applied


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when the patched result fails integrity checks."""


def validate_result(
    new_text: str,
    original_registry: dict[str, Any],
    expected_changes: list[Change],
    log: Logger,
) -> dict[str, Any]:
    """
    Verify the patched text:
      1. Parses as valid JSON.
      2. Every expected change is present.
      3. No unexpected changes to other fields.

    Returns the parsed registry on success. Raises ValidationError otherwise.
    """
    # 1. Parses
    try:
        new_registry = json.loads(new_text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Patched text is not valid JSON: {e}") from e

    # 2. Expected changes present
    new_entries = find_ranked_entries(new_registry)
    for change in expected_changes:
        entry = new_entries.get(change.code)
        if entry is None:
            raise ValidationError(
                f"{change.code} missing from patched registry"
            )
        actual = entry.get("market_cap_rank")
        if actual != change.new_rank:
            raise ValidationError(
                f"{change.code}: expected rank {change.new_rank}, got {actual}"
            )

    # 3. No unintended side effects — compare everything except market_cap_rank
    original_entries = find_ranked_entries(original_registry)
    if set(original_entries.keys()) != set(new_entries.keys()):
        raise ValidationError("Patch changed the set of ranked entries")
    for code in original_entries:
        orig = {k: v for k, v in original_entries[code].items()
                if k != "market_cap_rank" and k != "_category"}
        new = {k: v for k, v in new_entries[code].items()
               if k != "market_cap_rank" and k != "_category"}
        if orig != new:
            raise ValidationError(
                f"Patch changed unrelated fields in {code}"
            )

    log.debug("Validation passed")
    return new_registry


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_human(result: RefreshResult, log: Logger) -> None:
    """Human-readable summary. Uses stderr via Logger for consistent CI logs."""
    if result.status == "no_changes":
        log.success(
            f"No changes — all {result.checked} ranks match {result.source}"
        )
        return

    if result.status == "error":
        log.error(result.message)
        return

    if result.changes:
        log.info(f"\nMarket cap rank changes ({len(result.changes)}):")
        for c in result.changes:
            log.info(
                f"  {c.code:6} {c.old_rank:3} → {c.new_rank:3}  {c.direction}"
            )

    if result.missing:
        log.warn(
            f"{len(result.missing)} code(s) not found in {result.source}: "
            f"{', '.join(result.missing)}"
        )

    if result.status == "dry_run":
        log.info("\n[dry-run] No changes written.")
    elif result.status == "updated":
        log.success(f"\nUpdated {len(result.changes)} entries")
        log.info("   Next steps:")
        log.info("     python3 tools/sync_wrappers.py")
        log.info("     python3 tools/validate.py")
        log.info("     python3 -m pytest tests/ -v")
    elif result.status == "check_dirty":
        log.warn(f"\n{len(result.changes)} change(s) pending. Exit code 3.")
    elif result.status == "check_clean":
        log.success("Registry is up to date (check mode)")


def print_json(result: RefreshResult) -> None:
    """Machine-readable JSON to stdout. Logger output goes to stderr."""
    print(result.to_json())


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    registry_path: Path,
    top_n: int,
    dry_run: bool,
    check_mode: bool,
    snapshot_path: Optional[Path],
    log: Logger,
) -> RefreshResult:
    """
    End-to-end refresh. Never writes unless dry_run and check_mode are both
    False, and only after all validation passes.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = RefreshResult(
        status="no_changes",
        timestamp=timestamp,
        source="coingecko",
    )

    # 1. Fetch (or load snapshot)
    try:
        if snapshot_path:
            log.info(f"Loading snapshot: {snapshot_path}")
            with open(snapshot_path, "r", encoding="utf-8") as f:
                markets = json.load(f)
            result.source = f"snapshot:{snapshot_path.name}"
        else:
            log.info(f"Fetching top {top_n} from CoinGecko...")
            markets = fetch_coingecko_markets(top_n, log)
            log.info(f"  Received {len(markets)} coins")
    except NetworkError as e:
        return RefreshResult(
            status="error",
            source=result.source,
            timestamp=timestamp,
            message=f"Network failure: {e}",
        )
    except APIError as e:
        return RefreshResult(
            status="error",
            source=result.source,
            timestamp=timestamp,
            message=f"API error: {e}",
        )

    # 2. Load current registry
    original_registry = load_registry(registry_path)
    entries = find_ranked_entries(original_registry)
    result.checked = len(entries)

    # 3. Map to registry codes
    fresh = build_fresh_ranks(markets, CODE_TO_COINGECKO_ID, log)
    result.missing = sorted(set(CODE_TO_COINGECKO_ID.keys()) - set(fresh.keys()))

    # 4. Compute changes
    changes = compute_changes(entries, fresh)
    result.changes = changes

    if not changes:
        result.status = "check_clean" if check_mode else "no_changes"
        return result

    if check_mode:
        result.status = "check_dirty"
        return result

    if dry_run:
        result.status = "dry_run"
        return result

    # 5. Apply changes — with backup and rollback
    raw_text = registry_path.read_text(encoding="utf-8")
    backup_path = backup_registry(registry_path)
    log.debug(f"Backup created: {backup_path}")

    try:
        patched_text, applied = apply_changes_to_text(raw_text, changes, log)
        if applied != len(changes):
            raise PatchError(
                f"Applied {applied} changes, expected {len(changes)}"
            )
        validate_result(patched_text, original_registry, changes, log)
    except (PatchError, ValidationError) as e:
        restore_backup(backup_path, registry_path, log)
        result.status = "error"
        result.message = f"Patch failed and rolled back: {e}"
        return result

    # 6. Write
    registry_path.write_text(patched_text, encoding="utf-8")
    backup_path.unlink()  # success — remove backup
    result.status = "updated"
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh market_cap_rank for non-ISO entries from CoinGecko.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                       Preview changes, write nothing
  %(prog)s                                 Apply changes
  %(prog)s --check                         CI gate: exit 3 if stale
  %(prog)s --json                          Machine-readable output
  %(prog)s --snapshot /tmp/cg.json         Replay a saved response
  %(prog)s --registry /tmp/test.json       Use alternate registry
        """,
    )
    parser.add_argument(
        "--registry", "-r",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help=f"Path to iso4217.json (default: {DEFAULT_REGISTRY_PATH})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Fetch top N coins from CoinGecko (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show changes without writing",
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Exit 3 if changes are pending, without writing",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Read a saved CoinGecko response instead of fetching",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result as JSON to stdout",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose diagnostic output to stderr",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all non-error output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    log = Logger(verbose=args.verbose, quiet=args.quiet)

    if args.dry_run and args.check:
        log.error("--dry-run and --check are mutually exclusive")
        return EXIT_FATAL

    if not args.registry.exists():
        log.error(f"Registry not found: {args.registry}")
        return EXIT_FATAL

    result = refresh(
        registry_path=args.registry,
        top_n=args.top_n,
        dry_run=args.dry_run,
        check_mode=args.check,
        snapshot_path=args.snapshot,
        log=log,
    )

    if args.json:
        print_json(result)
    else:
        print_human(result, log)

    # Exit code mapping
    if result.status == "error":
        # Distinguish network from fatal — network errors are transient
        if "Network failure" in result.message or "API error" in result.message:
            return EXIT_NETWORK_ERROR
        return EXIT_FATAL

    if result.status == "check_dirty":
        return EXIT_CHANGES_PENDING

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())