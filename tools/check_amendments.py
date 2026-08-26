#!/usr/bin/env python3
"""
Check for new ISO 4217 amendments from SIX Group.

Fetches the SIX amendment page, extracts the latest amendment number,
compares against the registry's source.last_amendment_applied field.

Exit codes:
  0 — Registry is up to date (or check skipped due to network failure)
  1 — New amendment detected (alert mode)
  2 — Fatal error (registry file not found, invalid JSON, etc.)

Usage:
  python3 tools/check_amendments.py               # Check against default registry
  python3 tools/check_amendments.py --json        # JSON output for CI
  python3 tools/check_amendments.py --offline     # Skip network, use known value only
  python3 tools/check_amendments.py --verbose     # Show detailed progress

Exit code philosophy:
  Network failures (rate limits, DNS errors, timeouts, HTTP errors) exit 0
  with a clear "skipped" status — we do NOT want CI to fail because SIX's
  website was briefly down. The known-value fallback still runs and reports
  what we last knew. A genuine new amendment is the ONLY thing that exits 1.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "iso4217.json"
SIX_AMENDMENTS_URL = "https://www.currency-iso.org/en/home/amendments.html"

# ---------------------------------------------------------------------------
# Known amendment history
# ---------------------------------------------------------------------------

# Update this when ISO publishes a new amendment.
# The value here is the highest amendment number we believe exists.
# It serves as a fallback when the SIX website cannot be fetched.
KNOWN_LATEST_AMENDMENT = 179

# Known amendment details (for issue body generation).
# Update manually as new amendments are confirmed.
AMENDMENT_HISTORY: dict[int, dict] = {
    179: {
        "date": "2025-06-15",
        "summary": "Minor updates to currency names and numeric codes",
        "changes": [
            "No currency additions or removals",
            "Minor corrections to entity names",
        ],
    },
    # Future entries:
    # 180: {
    #     "date": "2026-XX-XX",
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
        "No currency additions",
        "No currency removals",
        "Corrected entity names for several currencies",
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


def fetch_latest_amendment(verbose: bool = False) -> tuple[int, str]:
    """
    Fetch the SIX Group amendments page and extract the highest amendment number.
    
    Returns:
        (amendment_number, source_string)
        where source_string is "six_group_website" or "network_failed"
        
    A returned amendment of 0 means "unknown" — the caller should use
    the known fallback value.
    """
    try:
        import urllib.request
        import urllib.error

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
        #   "Amendment 179", "AML 179", "Amendment No. 179", etc.
        patterns = [
            re.compile(r'(?:Amendment|AML)\s+(?:No\.?\s+)?(\d{1,3})', re.IGNORECASE),
            re.compile(r'Amendment\s+(\d{1,3})', re.IGNORECASE),
        ]

        all_matches = []
        for pattern in patterns:
            all_matches.extend(pattern.findall(html))

        if not all_matches:
            if verbose:
                print("Warning: No amendment numbers found on SIX page")
            return 0, "parse_failed"

        latest = max(int(m) for m in all_matches)
        return latest, "six_group_website"

    except urllib.error.HTTPError as e:
        if verbose:
            print(f"HTTP error from SIX: {e.code} {e.reason}")
        return 0, "http_error"
    except urllib.error.URLError as e:
        if verbose:
            print(f"URL error from SIX: {e.reason}")
        return 0, "url_error"
    except TimeoutError:
        if verbose:
            print("Timeout fetching SIX page")
        return 0, "timeout"
    except Exception as e:
        if verbose:
            print(f"Unexpected error fetching SIX page: {e}")
        return 0, "unexpected_error"


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
  0 — Registry up to date, or check skipped due to network failure
  1 — New amendment detected
  2 — Fatal error
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
    args = parser.parse_args()

    # Load current amendment from registry
    current = load_registry_amendment(verbose=args.verbose)

    if args.verbose:
        print(f"Registry amendment: {current}")

    # Fetch latest amendment
    if args.offline:
        latest = KNOWN_LATEST_AMENDMENT
        source = "known_value"
        fetch_status = "offline_mode"
    else:
        fetched, fetch_status = fetch_latest_amendment(verbose=args.verbose)
        if fetched > 0:
            latest = fetched
            source = "six_group_website"
        else:
            latest = KNOWN_LATEST_AMENDMENT
            source = "known_value_fallback"
            if args.verbose:
                print(f"Network fetch failed ({fetch_status}), using known value: {latest}")

    # Compare
    is_new = latest > current

    # Build result
    result = {
        "current_amendment": current,
        "latest_amendment": latest,
        "source": source,
        "fetch_status": fetch_status,
        "new_amendment_detected": is_new,
        "date_checked": str(date.today()),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.verbose:
        print(f"Latest amendment: {latest} (source: {source})")
        print(f"New amendment detected: {is_new}")

    # Generate issue body if requested
    if args.issue_body and is_new:
        body = format_issue_body(current, latest, source, fetch_status)
        print("\n" + body)

    # Exit code
    if is_new:
        if not args.json and not args.verbose:
            print(f"⚠️  New ISO 4217 amendment {latest} detected (registry has {current})")
            print(f"    Source: {source}")
            print(f"    Review at: {SIX_AMENDMENTS_URL}")
        sys.exit(1)
    else:
        if not args.json and not args.verbose:
            print(f"✅ Registry up to date (amendment {current})")
            print(f"    Latest known: {latest} (source: {source})")
        sys.exit(0)


if __name__ == "__main__":
    main()