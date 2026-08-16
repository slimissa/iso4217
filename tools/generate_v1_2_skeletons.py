#!/usr/bin/env python3
"""
Generate v1.2.0 skeleton entries for the ISO 4217 Currency Registry.

Reads the curated active-code set from tools/parse_source.py, finds which
of those 167 codes are missing from the current registry, and generates
skeleton JSON entries for each missing code with all fields populated
except those requiring manual research.

Skeleton fields:
- code: from the curated set
- numeric: from the parsed source data (if available, else "000")
- name: from the parsed source data (if available, else placeholder)
- minor_units: from the parsed source data (if available, else 2)
- symbol: placeholder "TODO"
- entity: placeholder "TODO"
- central_bank: placeholder "TODO"
- pegged_to: null (to be researched)
- peg_type: null (to be researched)
- is_independent: true (default assumption, to be corrected)
- countries: [] (to be researched)
- note: null (to be added for special cases)

Output: writes to stdout as pretty JSON, or to a file with --output.

Usage:
  python3 tools/generate_v1_2_skeletons.py                 # Print to stdout
  python3 tools/generate_v1_2_skeletons.py --output FILE   # Write to file
  python3 tools/generate_v1_2_skeletons.py --summary       # Just show counts
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.parse_source import ACTIVE_ISO_CODES

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Codes that are fund codes or indexation units, NOT tradable currencies.
# These get a note explaining their special status.
FUND_CODES = {
    "BOV": "Bolivian Mvdol — funds code maintained by the Central Bank of Bolivia for indexation purposes. Not a circulating currency.",
    "CHE": "WIR Euro — complementary currency used by the WIR Bank in Switzerland. Not a tradable ISO currency.",
    "CHW": "WIR Franc — complementary currency used by the WIR Bank in Switzerland. Not a tradable ISO currency.",
    "CLF": "Unidad de Fomento — Chilean indexation unit maintained by the Central Bank of Chile. Not a circulating currency.",
    "COU": "Unidad de Valor Real — Colombian indexation unit maintained by the Banco de la República. Not a circulating currency.",
    "MXV": "Mexican Unidad de Inversion (UDI) — indexation unit maintained by Banco de México. Not a circulating currency.",
    "USN": "US Dollar (next day) — funds code for settlement purposes. Not a separate currency.",
    "USS": "US Dollar (same day) — funds code for settlement purposes. Not a separate currency.",
    "UYI": "Uruguay Peso en Unidades Indexadas — indexation unit maintained by the Central Bank of Uruguay. Not a circulating currency.",
    "UYW": "Unidad Previsional — Uruguayan pension indexation unit. Not a circulating currency.",
    "VED": "Venezuelan Digital Bolívar — digital representation of VES. ISO-listed as a separate code; market usage varies.",
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_current_registry() -> dict:
    """Load the current iso4217.json."""
    path = PROJECT_ROOT / "iso4217.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_parsed_source() -> dict:
    """Try to load parsed source data. Returns empty dict if not found."""
    parsed_path = PROJECT_ROOT / "tools" / "sources" / "parsed_2026-07-29.json"
    if not parsed_path.exists():
        # Try to find any parsed file
        sources_dir = PROJECT_ROOT / "tools" / "sources"
        if sources_dir.exists():
            parsed_files = sorted(sources_dir.glob("parsed_*.json"), reverse=True)
            if parsed_files:
                parsed_path = parsed_files[0]
            else:
                return {}
        else:
            return {}

    with open(parsed_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_source_lookup(parsed: dict) -> dict:
    """Build a code → source data lookup from parsed Wikipedia data."""
    lookup = {}
    for category in ["active", "withdrawn", "commodity", "special_purpose"]:
        for entry in parsed.get(category, []):
            code = entry.get("code", "")
            if code:
                lookup[code] = entry
    return lookup


def get_missing_codes(current_codes: set, curated_codes: set) -> list:
    """Return sorted list of codes in curated but not in current registry."""
    return sorted(curated_codes - current_codes)


def generate_skeleton(code: str, source_lookup: dict) -> dict:
    """Generate a skeleton entry for a single currency code."""
    source = source_lookup.get(code, {})

    entry = {
        "code": code,
        "numeric": source.get("numeric", "000").strip().zfill(3),
        "name": source.get("name", f"TODO: name for {code}").strip(),
        "minor_units": source.get("minor_units", 2),
        "symbol": "TODO",
        "entity": "TODO",
        "central_bank": "TODO",
        "pegged_to": None,
        "peg_type": None,
        "is_independent": True,
        "countries": [],
    }

    # Special handling for fund codes
    if code in FUND_CODES:
        entry["note"] = FUND_CODES[code]
        entry["is_independent"] = True  # Fund codes aren't pegged in the traditional sense
    else:
        entry["note"] = None

    return entry


def generate_all_skeletons(missing_codes: list, source_lookup: dict) -> list:
    """Generate skeleton entries for all missing codes."""
    skeletons = []
    for code in missing_codes:
        skeletons.append(generate_skeleton(code, source_lookup))
    return skeletons


def format_json(entries: list) -> str:
    """Format skeleton entries as pretty JSON."""
    return json.dumps(entries, indent=2, ensure_ascii=False)


def print_summary(missing_codes: list, skeletons: list) -> None:
    """Print a summary of what will be generated."""
    print("=" * 60)
    print("  v1.2.0 Skeleton Generation Summary")
    print("=" * 60)
    print(f"  Total missing: {len(missing_codes)}")
    print(f"  Fund codes:    {sum(1 for c in missing_codes if c in FUND_CODES)}")
    print(f"  Regular:       {sum(1 for c in missing_codes if c not in FUND_CODES)}")
    print("=" * 60)

    # Show first 20 codes
    print("\n  First 20 codes:")
    for code in missing_codes[:20]:
        marker = " [FUND]" if code in FUND_CODES else ""
        print(f"    {code}{marker}")

    if len(missing_codes) > 20:
        print(f"    ... and {len(missing_codes) - 20} more")


def main():
    parser = argparse.ArgumentParser(
        description="Generate v1.2.0 skeleton entries for missing ISO 4217 currencies"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Write skeletons to a file (default: stdout)"
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Only show summary, don't output skeletons"
    )

    args = parser.parse_args()

    # Load current registry
    current = load_current_registry()
    current_codes = {c["code"] for c in current.get("currencies", {}).get("active", [])}

    # Load parsed source
    parsed = load_parsed_source()
    source_lookup = build_source_lookup(parsed)

    # Find missing codes
    missing = get_missing_codes(current_codes, ACTIVE_ISO_CODES)

    if not missing:
        print("No missing codes — registry is already at full coverage.")
        sys.exit(0)

    # Generate skeletons
    skeletons = generate_all_skeletons(missing, source_lookup)

    # Print summary
    print_summary(missing, skeletons)

    if args.summary:
        sys.exit(0)

    # Output skeletons
    output = format_json(skeletons)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"\nSkeletons written to: {args.output}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()