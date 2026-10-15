#!/usr/bin/env python3
"""
Check for new ISO 4217 amendments from SIX Group.

Fetches the SIX amendment page, extracts the latest amendment number,
compares against the registry's source.last_amendment_applied field.

Exit codes:
  0 — Registry is up to date: the latest amendment was read and is not newer
  1 — New amendment detected (alert mode)
  2 — Fatal error (registry file not found, invalid JSON, crash)
  3 — Undetermined: the SIX page could not be fetched or parsed, so this run
      could not tell whether a new amendment exists

Usage:
  python3 tools/check_amendments.py               # Check against default registry
  python3 tools/check_amendments.py --json        # JSON output for CI
  python3 tools/check_amendments.py --offline     # Skip network, use known value only
  python3 tools/check_amendments.py --verbose     # Show detailed progress
  python3 tools/check_amendments.py --simulate undetermined|new-amendment
                                                  # Exercise an alert path without
                                                  # contacting SIX (workflow test only)

Exit code philosophy (RELEASE_PATTERN.md, hygiene rule 7):
  A check that cannot run must fail, not pass. Until v1.7.14 every fetch
  failure -- HTTP error, DNS error, timeout, and a page that parsed to no
  amendment number -- returned 0 with source "known_value_fallback", so a
  change to SIX's page made the monitor report success every week while it
  saw nothing. Now a run that did not read the page exits 3.
  Transient failures (timeouts, connection errors, HTTP 429 and 5xx) are
  retried, 3 attempts in all; a parse failure and other HTTP errors are not,
  because repeating the request will not change them.
  The one way to exit 0 without reading the page is --offline, an explicit
  flag whose output says "offline_mode".
  Exit 1 is reserved for a detected amendment. An uncaught exception would
  also exit 1 under Python's defaults, so unexpected exceptions exit 2.
"""

import argparse
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "iso4217.json"
SIX_AMENDMENTS_URL = "https://www.currency-iso.org/en/home/amendments.html"

EXIT_OK = 0
EXIT_NEW_AMENDMENT = 1
EXIT_FATAL = 2
EXIT_UNDETERMINED = 3

# A fetch is repeated only when the failure can pass by itself.
FETCH_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5  # doubles after each failed attempt: 5 s, then 10 s

# ---------------------------------------------------------------------------
# Known amendment history
# ---------------------------------------------------------------------------

# Update this when ISO publishes a new amendment.
# The value here is the highest amendment number we believe exists.
# It serves as a fallback when the SIX website cannot be fetched.
KNOWN_LATEST_AMENDMENT = 180

# Known amendment details (for issue body generation).
# Update manually as new amendments are confirmed.
AMENDMENT_HISTORY: dict[int, dict] = {
    179: {
        "date": "2025-05-02",
        "summary": "Arab Accounting Dinar (XAD, 396) added, effective 2025-05-12",
        "changes": [
            "XAD added: Arab Monetary Fund, minor unit 2",
        ],
    },
    180: {
        "date": "2025-09-22",
        "summary": "Bulgaria adopts the euro, effective 2026-01-01",
        "changes": [
            "EUR now also listed for Bulgaria",
            "BGN moves to the historic list; fixed rate EUR 1 = BGN 1.95583",
            "BGN and EUR in parallel circulation 2026-01-01 to 2026-01-31",
        ],
    },
    # Future entries:
    # 181: {
    #     "date": "YYYY-MM-DD",   # the date printed on the amendment PDF
    #     "summary": "Description of changes",
    #     "changes": ["Currency XXX added", "Currency YYY withdrawn"],
    # },
}

# ---------------------------------------------------------------------------
# Known currencies by amendment (for detailed issue body)
# ---------------------------------------------------------------------------

# When an amendment adds or withdraws currencies, update this map.
# Format: amendment_number -> list of change descriptions.
KNOWN_AMENDMENT_CHANGES: dict[int, list[str]] = {
    179: [
        "XAD (Arab Accounting Dinar, 396) added",
    ],
    180: [
        "BGN withdrawn, replaced by EUR at 1.95583, effective 2026-01-01",
        "Bulgaria added to the EUR countries",
    ],
}

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_registry_amendment(verbose: bool = False) -> int:
    """
    Read source.last_amendment_applied from iso4217.json.
    
    Returns 0 if the field is missing or invalid, with a warning.
    """
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"FATAL: Registry file not found: {REGISTRY_PATH}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"FATAL: Invalid JSON in registry: {e}", file=sys.stderr)
        sys.exit(2)

    amendment = data.get("source", {}).get("last_amendment_applied")

    if amendment is None:
        if verbose:
            print("Warning: source.last_amendment_applied is missing from registry")
        return 0

    if not isinstance(amendment, int) or amendment < 1 or amendment > 999:
        if verbose:
            print(f"Warning: invalid amendment number: {amendment}")
        return 0

    return amendment


def _is_retryable_http(code: int) -> bool:
    """Rate limiting and server-side errors can pass; other 4xx will not."""
    return code == 429 or code >= 500


def _fetch_once(verbose: bool = False) -> tuple[int, str, bool]:
    """
    One attempt at reading the SIX amendments page.

    Returns (amendment_number, status, retryable). An amendment_number of 0
    means "could not read it"; retryable says whether repeating the same
    request could succeed.
    """
    try:
        req = urllib.request.Request(
            SIX_AMENDMENTS_URL,
            headers={
                "User-Agent": "iso4217-registry-amendment-checker/1.0 "
                              "(https://github.com/slimissa/iso4217)"
            },
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")

        if verbose:
            print(f"Fetched {len(html)} bytes from SIX Group")

        # Parse amendment numbers from the page.
        # SIX pages reference amendments in various formats:
        #   "Amendment 179", "AML 179", "Amendment No. 179", "Amendment Number 179",
        # and, since the page was redesigned, ONLY in the download link's file name:
        #   dl-currency-iso-amendment-180.pdf   (older files: dl_currency_iso_amendment_160.pdf)
        patterns = [
            re.compile(r'(?:Amendment|AML)\s+(?:No\.?\s+|Number\s+)?(\d{1,3})', re.IGNORECASE),
            re.compile(r'Amendment\s+(\d{1,3})', re.IGNORECASE),
            re.compile(r'amendment[-_](\d{1,3})\.pdf', re.IGNORECASE),
        ]

        all_matches = []
        for pattern in patterns:
            all_matches.extend(pattern.findall(html))

        if not all_matches:
            if verbose:
                print("Warning: No amendment numbers found on SIX page")
            return 0, "parse_failed", False

        return max(int(m) for m in all_matches), "six_group_website", False

    except urllib.error.HTTPError as e:
        if verbose:
            print(f"HTTP error from SIX: {e.code} {e.reason}")
        return 0, "http_error", _is_retryable_http(e.code)
    except urllib.error.URLError as e:
        if verbose:
            print(f"URL error from SIX: {e.reason}")
        return 0, "url_error", True
    except (TimeoutError, socket.timeout):
        if verbose:
            print("Timeout fetching SIX page")
        return 0, "timeout", True
    except OSError as e:
        # A connection reset while reading the body, and similar.
        if verbose:
            print(f"Connection error reading SIX page: {e}")
        return 0, "url_error", True
    except Exception as e:
        if verbose:
            print(f"Unexpected error fetching SIX page: {e}")
        return 0, "unexpected_error", False


def fetch_latest_amendment(verbose: bool = False, attempts: int = FETCH_ATTEMPTS,
                           sleep=None) -> tuple[int, str]:
    """
    Fetch the SIX Group amendments page and extract the highest amendment number.

    Returns:
        (amendment_number, status)
        status is "six_group_website" on success, otherwise one of
        "http_error", "url_error", "timeout", "parse_failed", "unexpected_error".

    An amendment_number of 0 means "unknown". The caller must treat that as
    undetermined (exit 3), never as "nothing new".
    """
    if sleep is None:
        sleep = time.sleep
    delay = RETRY_DELAY_SECONDS
    for attempt in range(1, attempts + 1):
        amendment, status, retryable = _fetch_once(verbose=verbose)
        if amendment > 0 or not retryable or attempt == attempts:
            return amendment, status
        if verbose:
            print(f"Attempt {attempt} of {attempts} failed ({status}); retrying in {delay} s")
        sleep(delay)
        delay *= 2
    return 0, "unexpected_error"  # attempts < 1: nothing was tried


def get_amendment_details(amendment: int) -> dict:
    """Get known details for an amendment, or a default if unknown."""
    return AMENDMENT_HISTORY.get(amendment, {
        "date": "unknown",
        "summary": "Details not yet documented. Review the SIX amendment page.",
        "changes": [],
    })


def format_issue_body(current: int, latest: int, source: str,
                      fetch_status: str) -> str:
    """Generate the issue body for a new amendment alert."""
    details = get_amendment_details(latest)

    lines = [
        f"## ISO 4217 Amendment {latest} Detected",
        "",
        f"- **Registry has:** Amendment {current}",
        f"- **Latest known:** Amendment {latest}",
        f"- **Detection source:** {source}",
        f"- **Fetch status:** {fetch_status}",
        f"- **Amendment date:** {details.get('date', 'unknown')}",
        f"- **Summary:** {details.get('summary', 'unknown')}",
        "",
        "### Known Changes",
        "",
    ]

    if details.get("changes"):
        for change in details["changes"]:
            lines.append(f"- {change}")
    else:
        lines.append("- _No detailed changes documented yet_")

    lines.extend([
        "",
        "### Action Required",
        "",
        "1. Review the SIX Group amendment page:",
        f"   {SIX_AMENDMENTS_URL}",
        "2. Run the update tool:",
        "   ```bash",
        "   python3 tools/update_from_iso.py --fetch-sources",
        "   python3 tools/parse_source.py",
        "   ```",
        "3. Apply changes to `iso4217.json`",
        "4. Run validation:",
        "   ```bash",
        "   python3 tools/validate.py",
        "   python3 -m pytest tests/ -v",
        "   ```",
        "5. Update `source.last_amendment_applied` and `source.last_amendment_date`",
        "6. Update `KNOWN_LATEST_AMENDMENT` in `tools/check_amendments.py`",
        "7. Commit, bump version, tag",
        "",
        "### Notes",
        "",
        "- This issue was auto-generated by `tools/check_amendments.py`",
        "- Detection source: " + source,
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check for new ISO 4217 amendments from SIX Group",
        epilog="""
Exit codes:
  0 — Registry up to date (the SIX page was read)
  1 — New amendment detected
  2 — Fatal error
  3 — Undetermined: the SIX page could not be fetched or parsed
        """,
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Output as JSON (for CI/CD integration)"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Skip network fetch, use known value only"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed progress"
    )
    parser.add_argument(
        "--issue-body", action="store_true",
        help="Print the issue body for the new amendment (if any)"
    )
    parser.add_argument(
        "--simulate", choices=("undetermined", "new-amendment"),
        help="Test only: do not contact SIX; behave as if the check came back undetermined (exit 3) or found an amendment (exit 1). Output says simulated."
    )
    args = parser.parse_args()
    if args.simulate and args.offline:
        parser.error("--simulate and --offline are mutually exclusive")

    # Load current amendment from registry
    current = load_registry_amendment(verbose=args.verbose)

    if args.verbose:
        print(f"Registry amendment: {current}")

    if args.simulate:
        print(f"SIMULATED RUN (--simulate {args.simulate}): SIX is not contacted "
              "and this result is not real.", file=sys.stderr)

    # Fetch latest amendment. `latest` is None when this run could not tell.
    if args.simulate == "undetermined":
        latest, source, fetch_status = None, "undetermined", "simulated_undetermined"
    elif args.simulate == "new-amendment":
        latest, source, fetch_status = current + 1, "simulated", "simulated_new_amendment"
    elif args.offline:
        latest, source, fetch_status = KNOWN_LATEST_AMENDMENT, "known_value", "offline_mode"
    else:
        fetched, fetch_status = fetch_latest_amendment(verbose=args.verbose)
        if fetched > 0:
            latest, source = fetched, "six_group_website"
        else:
            # KNOWN_LATEST_AMENDMENT is deliberately not used here. It is the
            # --offline answer, not evidence about what SIX says today.
            latest, source = None, "undetermined"
            if args.verbose:
                print(f"Could not read the SIX page ({fetch_status}); result undetermined")

    determined = latest is not None

    # Compare
    is_new = determined and latest > current

    # Build result
    result = {
        "current_amendment": current,
        "latest_amendment": latest,
        "source": source,
        "fetch_status": fetch_status,
        "determined": determined,
        "new_amendment_detected": is_new if determined else None,
        "simulated": args.simulate is not None,
        "date_checked": str(date.today()),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.verbose:
        if determined:
            print(f"Latest amendment: {latest} (source: {source})")
            print(f"New amendment detected: {is_new}")
        else:
            print(f"Latest amendment: undetermined (fetch status: {fetch_status})")

    # Generate issue body if requested
    if args.issue_body and is_new:
        body = format_issue_body(current, latest, source, fetch_status)
        print("\n" + body)

    # Exit code
    if not determined:
        print(f"UNDETERMINED: could not read the latest amendment from SIX "
              f"(fetch_status={fetch_status}). This run verified nothing; "
              f"it is not a pass.", file=sys.stderr)
        sys.exit(EXIT_UNDETERMINED)

    if is_new:
        if not args.json and not args.verbose:
            print(f"⚠️  New ISO 4217 amendment {latest} detected (registry has {current})")
            print(f"    Source: {source}")
            print(f"    Review at: {SIX_AMENDMENTS_URL}")
        sys.exit(EXIT_NEW_AMENDMENT)
    else:
        if not args.json and not args.verbose:
            print(f"✅ Registry up to date (amendment {current})")
            print(f"    Latest known: {latest} (source: {source})")
        sys.exit(EXIT_OK)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Python exits 1 on an uncaught exception, and 1 means "new amendment".
        import traceback
        traceback.print_exc()
        sys.exit(EXIT_FATAL)
