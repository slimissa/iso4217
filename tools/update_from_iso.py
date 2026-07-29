#!/usr/bin/env python3
"""
ISO 4217 Currency Registry — Update Tool

Semi-automated workflow for updating iso4217.json from authoritative sources.
This tool does NOT automatically apply changes — it produces a diff and a
proposed update file for human review before commit.

Sources:
  - SWIFT ISO 4217 public table (free, authoritative)
  - Wikipedia ISO 4217 page (convenient compilation, verify against SWIFT)
  - Central bank websites (manual verification per currency)
  - SIX Group amendment summaries (currency-iso.org)

Workflow:
  1. Fetch current data from sources
  2. Diff against existing registry
  3. Generate change report for human review
  4. Apply approved changes to produce updated iso4217.json

Usage:
  python tools/update_from_iso.py --check           # Check for available updates
  python tools/update_from_iso.py --fetch-sources   # Fetch source data
  python tools/update_from_iso.py --diff            # Show diff against current
  python tools/update_from_iso.py --apply           # Apply changes (with confirmation)
  python tools/update_from_iso.py --add-currency CODE [options]  # Add single currency

Requirements:
  pip install requests beautifulsoup4 lxml
"""

import json
import sys
import argparse
import hashlib
import subprocess
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

# Optional imports — graceful degradation if not installed
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "iso4217.json"
SOURCES_DIR = PROJECT_ROOT / "tools" / "sources"
DIFFS_DIR = PROJECT_ROOT / "tools" / "diffs"

# Authoritative sources
SWIFT_URL = "https://www.swift.com/standards/data-standards/iso-4217-currency-codes"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/ISO_4217"
SIX_AMENDMENTS_URL = "https://www.currency-iso.org/en/home/amendments.html"

# Central bank data sources (for minor unit verification)
CENTRAL_BANK_SOURCES = {
    "USD": "https://www.federalreserve.gov/faqs/currency_12772.htm",
    "EUR": "https://www.ecb.europa.eu/euro/html/index.en.html",
    "GBP": "https://www.bankofengland.co.uk/banknotes",
    "JPY": "https://www.boj.or.jp/en/note_tfjgs/note/",
    "CHF": "https://www.snb.ch/en/the-snb/mandates-goals/cash",
    "CNY": "http://www.pbc.gov.cn/en/3688006/index.html",
    "KWD": "https://www.cbk.gov.kw/",
    "BHD": "https://www.cbb.gov.bh/",
    "OMR": "https://cbo.gov.om/",
    "JOD": "https://www.cbj.gov.jo/",
    "TND": "https://www.bct.gov.tn/",
    "LYD": "https://cbl.gov.ly/en/",
    "IQD": "https://cbi.iq/",
}

# Known ISO 4217 amendment history (for tracking what changed when)
KNOWN_AMENDMENTS = {
    179: {"date": "2025-06-15", "summary": "Minor updates to currency names and numeric codes"},
    178: {"date": "2024-12-01", "summary": "Various administrative updates"},
    177: {"date": "2024-06-01", "summary": "Addition of new currency codes"},
}

# Currencies that ISO says have N minor_units but market uses M
MARKET_CONVENTION_OVERRIDES = {
    "IDR": {
        "iso_minor_units": 2,
        "market_minor_units": 0,
        "note": "ISO 4217 specifies 2 minor units, but in market practice IDR is quoted without decimals (effectively 0 minor units for display). This field follows the ISO standard. For display formatting, treat minor_units as 0 for IDR."
    }
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ChangeType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    WITHDRAWN = "withdrawn"
    REACTIVATED = "reactivated"


@dataclass
class FieldChange:
    """A single field-level change in a currency entry."""
    field: str
    old_value: Any
    new_value: Any

    def __str__(self) -> str:
        return f"  {self.field}: {self.old_value!r} → {self.new_value!r}"


@dataclass
class CurrencyChange:
    """A change to a single currency entry."""
    code: str
    change_type: ChangeType
    category: str  # "active", "withdrawn", "cryptocurrencies", etc.
    field_changes: List[FieldChange] = field(default_factory=list)
    source: str = ""
    note: str = ""

    def __str__(self) -> str:
        lines = [f"[{self.change_type.value.upper()}] {self.code} ({self.category})"]
        if self.source:
            lines.append(f"  Source: {self.source}")
        if self.note:
            lines.append(f"  Note: {self.note}")
        for change in self.field_changes:
            lines.append(str(change))
        return "\n".join(lines)


@dataclass
class UpdateReport:
    """Complete update report with all changes."""
    timestamp: str
    source_amendment: int
    source_date: str
    changes: List[CurrencyChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    requires_review: List[str] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.changes)

    @property
    def added_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.ADDED)

    @property
    def removed_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)

    @property
    def modified_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.MODIFIED)


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def load_registry(path: Path = REGISTRY_PATH) -> Dict:
    """Load the current registry."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_registry(data: Dict, path: Path) -> None:
    """Save registry with consistent formatting."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')  # Trailing newline


def backup_registry(path: Path = REGISTRY_PATH) -> Path:
    """Create a timestamped backup of the registry."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.parent / f"iso4217_backup_{timestamp}.json"
    save_registry(load_registry(path), backup_path)
    return backup_path


# ---------------------------------------------------------------------------
# Source data fetching
# ---------------------------------------------------------------------------

def fetch_swift_table() -> Optional[List[Dict]]:
    """
    Fetch and parse the SWIFT ISO 4217 table.
    
    The SWIFT page contains an HTML table with currency data.
    This is the most authoritative free source.
    """
    if not HAS_REQUESTS or not HAS_BS4:
        print("Warning: requests and beautifulsoup4 required for fetching.", file=sys.stderr)
        print("Install with: pip install requests beautifulsoup4 lxml", file=sys.stderr)
        return None

    try:
        response = requests.get(SWIFT_URL, timeout=30, headers={
            "User-Agent": "iso4217-registry-updater/1.0 (https://github.com/slimissa/iso4217)"
        })
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch SWIFT table: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, 'lxml')
    table = soup.find('table')

    if not table:
        print("Warning: Could not find table on SWIFT page (page structure may have changed).", file=sys.stderr)
        return None

    currencies = []
    rows = table.find_all('tr')[1:]  # Skip header row

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 4:
            continue

        try:
            code = cols[0].get_text(strip=True)
            numeric = cols[1].get_text(strip=True).zfill(3)
            name = cols[2].get_text(strip=True)
            minor_units_str = cols[3].get_text(strip=True)
            minor_units = int(minor_units_str) if minor_units_str.isdigit() else 0

            if len(code) == 3 and code.isupper() and code.isalpha():
                currencies.append({
                    "code": code,
                    "numeric": numeric,
                    "name": name,
                    "minor_units": minor_units,
                })
        except (ValueError, IndexError):
            continue

    return currencies


def fetch_wikipedia_table() -> Optional[List[Dict]]:
    """
    Fetch and parse the Wikipedia ISO 4217 active codes table.
    
    Wikipedia is convenient but must be verified against SWIFT.
    """
    if not HAS_REQUESTS or not HAS_BS4:
        return None

    try:
        response = requests.get(WIKIPEDIA_URL, timeout=30, headers={
            "User-Agent": "iso4217-registry-updater/1.0"
        })
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch Wikipedia: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, 'lxml')

    # Find the "Active codes" table — Wikipedia has multiple tables
    tables = soup.find_all('table', class_='wikitable')
    if not tables:
        print("Warning: Could not find currency tables on Wikipedia.", file=sys.stderr)
        return None

    currencies = []
    for table in tables:
        rows = table.find_all('tr')[1:]
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3:
                continue

            try:
                code = cols[0].get_text(strip=True)
                if len(code) != 3 or not code.isupper() or not code.isalpha():
                    continue

                numeric = cols[1].get_text(strip=True).zfill(3)
                minor_units_text = cols[2].get_text(strip=True)
                minor_units = int(minor_units_text) if minor_units_text.isdigit() else 0
                name = cols[3].get_text(strip=True) if len(cols) > 3 else ""

                currencies.append({
                    "code": code,
                    "numeric": numeric,
                    "name": name,
                    "minor_units": minor_units,
                })
            except (ValueError, IndexError):
                continue

    return currencies


def fetch_six_amendments() -> Optional[List[Dict]]:
    """
    Fetch SIX Group amendment summaries.
    
    This tells us what changed in each amendment without paying for ISO access.
    """
    if not HAS_REQUESTS or not HAS_BS4:
        return None

    try:
        response = requests.get(SIX_AMENDMENTS_URL, timeout=30, headers={
            "User-Agent": "iso4217-registry-updater/1.0"
        })
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch SIX amendments: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, 'lxml')
    amendments = []

    # Parse amendment entries — structure depends on the page
    # This is a best-effort parser for the typical SIX page structure
    for entry in soup.find_all(['li', 'div'], class_=lambda c: c and 'amendment' in c.lower()):
        text = entry.get_text(strip=True)
        amendments.append({"raw_text": text})

    return amendments


def save_source_data(data: Any, name: str) -> Path:
    """Save fetched source data for later comparison."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCES_DIR / f"{name}_{date.today().isoformat()}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_latest_source(name_prefix: str) -> Optional[Any]:
    """Load the most recent source data file matching the prefix."""
    if not SOURCES_DIR.exists():
        return None

    matching = sorted(
        [f for f in SOURCES_DIR.iterdir() if f.name.startswith(name_prefix)],
        reverse=True
    )
    if not matching:
        return None

    with open(matching[0], 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

def build_code_index(registry: Dict) -> Dict[str, Dict]:
    """Build a flat lookup index from the registry."""
    index: Dict[str, Dict] = {}

    # Active currencies
    for c in registry.get("currencies", {}).get("active", []):
        index[c["code"]] = {"data": c, "category": "currencies.active"}

    # Withdrawn currencies
    for c in registry.get("currencies", {}).get("withdrawn", []):
        index[c["code"]] = {"data": c, "category": "currencies.withdrawn"}

    # Non-ISO currencies
    non_iso = registry.get("non_iso", {})
    for category in ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]:
        for c in non_iso.get(category, []):
            index[c["code"]] = {"data": c, "category": f"non_iso.{category}"}

    return index


def diff_currency(old: Optional[Dict], new: Dict, code: str) -> List[FieldChange]:
    """Compare old and new currency data, return field-level changes."""
    changes: List[FieldChange] = []

    if old is None:
        return changes  # New currency, no field diff needed

    all_keys = set(old.keys()) | set(new.keys())

    for key in sorted(all_keys):
        old_val = old.get(key)
        new_val = new.get(key)

        if key == "countries" and isinstance(old_val, list) and isinstance(new_val, list):
            # Deep compare country lists
            old_countries = {(c.get("code"), c.get("relationship")) for c in old_val}
            new_countries = {(c.get("code"), c.get("relationship")) for c in new_val}
            if old_countries != new_countries:
                changes.append(FieldChange(
                    field="countries",
                    old_value=f"{len(old_val)} countries",
                    new_value=f"{len(new_val)} countries"
                ))
        elif old_val != new_val:
            changes.append(FieldChange(
                field=key,
                old_value=old_val,
                new_value=new_val
            ))

    return changes


def generate_diff(registry: Dict, source_data: Dict, field_mapping: Dict[str, str]) -> UpdateReport:
    """
    Generate a diff between the registry and source data.
    
    Args:
        registry: Current registry data
        source_data: Fetched source data (list of currency dicts)
        field_mapping: Map source field names to registry field names
    
    Returns:
        UpdateReport with all detected changes
    """
    report = UpdateReport(
        timestamp=datetime.now().isoformat(),
        source_amendment=registry.get("source", {}).get("last_amendment_applied", 0),
        source_date=str(date.today()),
    )

    # Build indices
    registry_index = build_code_index(registry)
    source_index = {c["code"]: c for c in source_data if "code" in c}

    registry_codes = set(registry_index.keys())
    source_codes = set(source_index.keys())

    # Added currencies (in source, not in registry)
    for code in sorted(source_codes - registry_codes):
        src = source_index[code]
        mapped = {field_mapping.get(k, k): v for k, v in src.items()}
        report.changes.append(CurrencyChange(
            code=code,
            change_type=ChangeType.ADDED,
            category="currencies.active",
            field_changes=[FieldChange(f, None, v) for f, v in mapped.items()],
            source="SWIFT ISO 4217 table",
        ))

    # Removed currencies (in registry, not in source)
    for code in sorted(registry_codes - source_codes):
        entry = registry_index[code]
        if entry["category"].startswith("currencies.active"):
            report.changes.append(CurrencyChange(
                code=code,
                change_type=ChangeType.WITHDRAWN,
                category=entry["category"],
                note="Currency not found in source data. May have been withdrawn.",
                source="SWIFT ISO 4217 table",
            ))
            report.requires_review.append(f"Verify withdrawal of {code}")

    # Modified currencies (in both, with differences)
    for code in sorted(source_codes & registry_codes):
        src = source_index[code]
        entry = registry_index[code]
        mapped = {field_mapping.get(k, k): v for k, v in src.items()}

        field_changes = diff_currency(entry["data"], mapped, code)
        if field_changes:
            report.changes.append(CurrencyChange(
                code=code,
                change_type=ChangeType.MODIFIED,
                category=entry["category"],
                field_changes=field_changes,
                source="SWIFT ISO 4217 table",
            ))

    return report


# ---------------------------------------------------------------------------
# Change application
# ---------------------------------------------------------------------------

def apply_changes(registry: Dict, report: UpdateReport, interactive: bool = True) -> Dict:
    """
    Apply approved changes to the registry.
    
    In interactive mode, prompts for each change.
    """
    updated = json.loads(json.dumps(registry))  # Deep copy

    for change in report.changes:
        if interactive:
            print(f"\n{'='*60}")
            print(str(change))
            response = input("Apply this change? [Y/n/skip/q]: ").strip().lower()
            if response == 'q':
                print("Aborting.")
                sys.exit(0)
            elif response == 'skip':
                continue
            elif response == 'n':
                continue

        # Apply the change
        if change.change_type == ChangeType.ADDED:
            new_entry = {}
            for fc in change.field_changes:
                if fc.new_value is not None:
                    new_entry[fc.field] = fc.new_value
            if change.category == "currencies.active":
                updated["currencies"]["active"].append(new_entry)

        elif change.change_type == ChangeType.WITHDRAWN:
            # Move from active to withdrawn
            active = updated["currencies"]["active"]
            withdrawn = updated["currencies"]["withdrawn"]
            for i, c in enumerate(active):
                if c["code"] == change.code:
                    moved = active.pop(i)
                    moved["withdrawn_date"] = str(date.today())
                    moved["replaced_by"] = ""
                    moved["conversion_rate"] = 0
                    moved["note"] = f"Withdrawn per ISO 4217 amendment. {change.note}"
                    withdrawn.append(moved)
                    break

        elif change.change_type == ChangeType.MODIFIED:
            # Update fields
            target_list = None
            if change.category == "currencies.active":
                target_list = updated["currencies"]["active"]
            elif change.category == "currencies.withdrawn":
                target_list = updated["currencies"]["withdrawn"]

            if target_list:
                for c in target_list:
                    if c["code"] == change.code:
                        for fc in change.field_changes:
                            c[fc.field] = fc.new_value
                        break

    # Update metadata
    updated["meta"]["updated"] = str(date.today())
    updated["source"]["last_verified"] = str(date.today())
    updated["source"]["last_amendment_applied"] = report.source_amendment

    return updated


# ---------------------------------------------------------------------------
# Manual currency addition
# ---------------------------------------------------------------------------

CURRENCY_TEMPLATE = {
    "code": "",
    "numeric": "",
    "name": "",
    "minor_units": 2,
    "symbol": "",
    "entity": "",
    "central_bank": "",
    "pegged_to": None,
    "pegged_since": None,
    "peg_rate": None,
    "peg_band_pct": None,
    "is_independent": True,
    "countries": []
}


def add_currency_interactive(code: str) -> Dict:
    """Interactively build a new currency entry."""
    entry = CURRENCY_TEMPLATE.copy()
    entry["code"] = code.upper()

    print(f"\nAdding new currency: {code.upper()}")
    print("Press Enter to accept defaults shown in [brackets].\n")

    entry["numeric"] = input(f"  Numeric code [{entry['numeric']}]: ").strip() or entry["numeric"]
    entry["name"] = input(f"  Currency name: ").strip()
    entry["minor_units"] = int(input(f"  Minor units [{entry['minor_units']}]: ").strip() or entry["minor_units"])
    entry["symbol"] = input(f"  Symbol [{entry['symbol']}]: ").strip() or entry["symbol"]
    entry["entity"] = input(f"  Issuing entity: ").strip()
    entry["central_bank"] = input(f"  Central bank: ").strip()

    pegged = input(f"  Pegged to (code or Enter for none): ").strip()
    if pegged:
        entry["pegged_to"] = pegged
        entry["is_independent"] = False
        entry["pegged_since"] = input(f"  Peg established date (YYYY-MM-DD): ").strip()
        try:
            entry["peg_rate"] = float(input(f"  Peg rate: ").strip())
        except ValueError:
            entry["peg_rate"] = None
        try:
            entry["peg_band_pct"] = float(input(f"  Peg band %: ").strip())
        except ValueError:
            entry["peg_band_pct"] = None
    else:
        entry["pegged_to"] = None
        entry["is_independent"] = True

    # Countries
    print("\n  Add countries (ISO 3166-1 alpha-2 codes). Enter blank code to finish.")
    while True:
        ccode = input(f"    Country code: ").strip().upper()
        if not ccode:
            break
        cname = input(f"    Country name: ").strip()
        crel = input(f"    Relationship [issuing]: ").strip() or "issuing"
        entry["countries"].append({
            "code": ccode,
            "name": cname,
            "relationship": crel
        })

    return entry


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_report(report: UpdateReport) -> str:
    """Format an update report for display."""
    lines = []
    lines.append("=" * 70)
    lines.append("  ISO 4217 Registry — Update Report")
    lines.append("=" * 70)
    lines.append(f"  Generated:    {report.timestamp}")
    lines.append(f"  Source amend: {report.source_amendment}")
    lines.append(f"  Source date:  {report.source_date}")
    lines.append(f"  Total changes: {report.total_changes}")
    lines.append(f"    Added:      {report.added_count}")
    lines.append(f"    Modified:   {report.modified_count}")
    lines.append(f"    Withdrawn:  {report.removed_count}")
    lines.append("=" * 70)

    if not report.changes:
        lines.append("\n  ✅ No changes detected. Registry is up to date.")
        return "\n".join(lines)

    lines.append(f"\n  Changes ({report.total_changes}):")
    lines.append("  " + "-" * 68)

    for change in report.changes:
        symbol = {
            ChangeType.ADDED: "+",
            ChangeType.REMOVED: "-",
            ChangeType.WITHDRAWN: "↓",
            ChangeType.MODIFIED: "~",
            ChangeType.REACTIVATED: "↑",
        }.get(change.change_type, "?")
        lines.append(f"  {symbol} {change.code} — {change.change_type.value.upper()}")
        if change.note:
            lines.append(f"    Note: {change.note}")
        for fc in change.field_changes:
            old_str = str(fc.old_value)[:60]
            new_str = str(fc.new_value)[:60]
            lines.append(f"    {fc.field}: {old_str} → {new_str}")
        lines.append("")

    if report.warnings:
        lines.append("  ⚠️  Warnings:")
        for w in report.warnings:
            lines.append(f"    - {w}")
        lines.append("")

    if report.requires_review:
        lines.append("  🔍 Requires Human Review:")
        for r in report.requires_review:
            lines.append(f"    - {r}")
        lines.append("")

    lines.append("  " + "=" * 68)
    lines.append("  Run with --apply to apply these changes interactively.")
    lines.append("  " + "=" * 68)

    return "\n".join(lines)


def save_report(report: UpdateReport) -> Path:
    """Save the update report for record-keeping."""
    DIFFS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DIFFS_DIR / f"update_report_{timestamp}.json"

    report_data = {
        "timestamp": report.timestamp,
        "source_amendment": report.source_amendment,
        "source_date": report.source_date,
        "changes": [
            {
                "code": c.code,
                "change_type": c.change_type.value,
                "category": c.category,
                "source": c.source,
                "note": c.note,
                "field_changes": [
                    {"field": fc.field, "old": fc.old_value, "new": fc.new_value}
                    for fc in c.field_changes
                ]
            }
            for c in report.changes
        ],
        "warnings": report.warnings,
        "requires_review": report.requires_review
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ISO 4217 Currency Registry — Update Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow Examples:

  # Check what's available from authoritative sources
  python tools/update_from_iso.py --fetch-sources
  
  # Diff against current registry
  python tools/update_from_iso.py --diff
  
  # Apply changes interactively (with confirmation for each)
  python tools/update_from_iso.py --apply
  
  # Add a single currency manually
  python tools/update_from_iso.py --add-currency NEW
  
  # Full pipeline: fetch, diff, apply
  python tools/update_from_iso.py --fetch-sources --diff --apply
        """
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Quick check for available updates (no fetch)"
    )
    parser.add_argument(
        "--fetch-sources",
        action="store_true",
        help="Fetch latest data from SWIFT, Wikipedia, and SIX Group"
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Diff fetched source data against current registry"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (interactive mode with confirmation)"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Apply all changes without confirmation (use with --apply)"
    )
    parser.add_argument(
        "--add-currency",
        type=str,
        metavar="CODE",
        help="Interactively add a single currency by ISO code"
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Use a specific source file instead of fetching"
    )
    parser.add_argument(
        "--verify-minor-units",
        type=str,
        metavar="CODE",
        help="Verify minor_units for a specific currency against central bank source"
    )

    args = parser.parse_args()

    # Check dependencies
    if not HAS_REQUESTS:
        print("Warning: 'requests' not installed. Fetching disabled.", file=sys.stderr)
        print("Install with: pip install requests beautifulsoup4 lxml", file=sys.stderr)
    if not HAS_BS4:
        print("Warning: 'beautifulsoup4' not installed. HTML parsing disabled.", file=sys.stderr)

    # --add-currency: Manual addition workflow
    if args.add_currency:
        code = args.add_currency.upper()
        registry = load_registry()

        # Check if already exists
        index = build_code_index(registry)
        if code in index:
            print(f"Error: Currency '{code}' already exists in '{index[code]['category']}'.")
            sys.exit(1)

        new_entry = add_currency_interactive(code)

        print(f"\nNew entry for {code}:")
        print(json.dumps(new_entry, indent=2, ensure_ascii=False))

        confirm = input("\nAdd this currency to the active list? [y/N]: ").strip().lower()
        if confirm == 'y':
            registry["currencies"]["active"].append(new_entry)
            registry["meta"]["updated"] = str(date.today())
            backup_path = backup_registry()
            print(f"Backup saved to: {backup_path}")
            save_registry(registry)
            print(f"Added {code} to registry.")
        else:
            print("Aborted.")

        sys.exit(0)

    # --verify-minor-units: Check specific currency
    if args.verify_minor_units:
        code = args.verify_minor_units.upper()
        registry = load_registry()
        index = build_code_index(registry)

        if code not in index:
            print(f"Error: Currency '{code}' not found in registry.")
            sys.exit(1)

        entry = index[code]
        print(f"Current data for {code}:")
        print(f"  minor_units: {entry['data'].get('minor_units')}")
        print(f"  name:        {entry['data'].get('name')}")
        print(f"  category:    {entry['category']}")

        if code in CENTRAL_BANK_SOURCES:
            print(f"\n  Central bank source: {CENTRAL_BANK_SOURCES[code]}")
            print(f"  (Manual verification required — visit the URL to confirm)")
        else:
            print(f"\n  No central bank URL configured for {code}.")
            print(f"  Add it to CENTRAL_BANK_SOURCES in this script.")

        if code in MARKET_CONVENTION_OVERRIDES:
            override = MARKET_CONVENTION_OVERRIDES[code]
            print(f"\n  Market convention note: {override['note']}")

        sys.exit(0)

    # --fetch-sources: Download source data
    if args.fetch_sources:
        print("Fetching source data...")

        swift_data = fetch_swift_table()
        if swift_data:
            path = save_source_data(swift_data, "swift")
            print(f"  SWIFT data saved: {path} ({len(swift_data)} currencies)")
        else:
            print("  SWIFT fetch failed or no data returned.")

        wiki_data = fetch_wikipedia_table()
        if wiki_data:
            path = save_source_data(wiki_data, "wikipedia")
            print(f"  Wikipedia data saved: {path} ({len(wiki_data)} currencies)")
        else:
            print("  Wikipedia fetch failed or no data returned.")

        amendments = fetch_six_amendments()
        if amendments:
            path = save_source_data(amendments, "amendments")
            print(f"  SIX amendments saved: {path} ({len(amendments)} entries)")
        else:
            print("  SIX amendments fetch failed.")

        if not args.diff and not args.apply:
            sys.exit(0)

    # --diff: Compare against current
    if args.diff or args.apply:
        registry = load_registry()

        # Load source data (either from file or latest fetch)
        source_data = None
        if args.source_file:
            with open(args.source_file, 'r', encoding='utf-8') as f:
                source_data = json.load(f)
        else:
            source_data = load_latest_source("swift") or load_latest_source("wikipedia")

        if not source_data:
            print("Error: No source data available. Run --fetch-sources first.", file=sys.stderr)
            sys.exit(1)

        # Field mapping: source field names → registry field names
        field_mapping = {
            "code": "code",
            "numeric": "numeric",
            "name": "name",
            "minor_units": "minor_units",
        }

        report = generate_diff(registry, source_data, field_mapping)

        # Save report
        report_path = save_report(report)
        print(f"\nReport saved: {report_path}")

        # Display report
        print("\n" + format_report(report))

        # --apply: Apply changes
        if args.apply:
            if not report.changes:
                print("No changes to apply.")
                sys.exit(0)

            interactive = not args.yes
            if not interactive:
                print("\n⚠️  Non-interactive mode: applying ALL changes without confirmation.")

            updated = apply_changes(registry, report, interactive=interactive)

            # Save backup
            backup_path = backup_registry()
            print(f"\nBackup saved: {backup_path}")

            # Save updated registry
            save_registry(updated)
            print(f"Registry updated: {REGISTRY_PATH}")

            # Update amendment number
            print(f"\nRemember to update source.last_amendment_applied in iso4217.json")
            print(f"and add an entry to CHANGELOG.md.")

    # --check: Quick status
    if args.check and not args.diff and not args.apply:
        registry = load_registry()
        verified = registry.get("source", {}).get("last_verified", "unknown")
        amendment = registry.get("source", {}).get("last_amendment_applied", "unknown")

        print(f"Registry status:")
        print(f"  Last verified: {verified}")
        print(f"  Amendment:     {amendment}")
        print(f"  Active:        {len(registry['currencies']['active'])}")
        print(f"  Withdrawn:     {len(registry['currencies']['withdrawn'])}")

        # Check if sources are available
        latest_swift = load_latest_source("swift")
        if latest_swift:
            print(f"  Source data:   Available ({len(latest_swift)} currencies)")
            print(f"  Run --diff to compare.")
        else:
            print(f"  Source data:   Not available")
            print(f"  Run --fetch-sources to download.")


if __name__ == "__main__":
    main()