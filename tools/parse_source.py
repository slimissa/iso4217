#!/usr/bin/env python3
"""
Parse downloaded source data into structured, diffable format.
v1 — properly separates active from withdrawn ISO 4217 codes.

Usage:
  python tools/parse_source.py                          # Parse latest source
  python tools/parse_source.py --source wikipedia       # Specific source
  python tools/parse_source.py --output parsed.json     # Custom output path
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import date
from typing import Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = PROJECT_ROOT / "tools" / "sources"

# ---------------------------------------------------------------------------
# Known classifications — ground truth that Wikipedia's table doesn't encode
# ---------------------------------------------------------------------------

# Currently active ISO 4217 currency codes (per amendment 179)
# This list is manually curated against the ISO standard.
# When ISO publishes an amendment, update this list.
ACTIVE_ISO_CODES: Set[str] = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
    "BRL", "BSD", "BTN", "BWP", "BYN", "BZD",
    "CAD", "CDF", "CHE", "CHF", "CHW", "CLF", "CLP", "CNY", "COP", "COU",
    "CRC", "CUC", "CUP", "CVE", "CZK",
    "DJF", "DKK", "DOP", "DZD",
    "EGP", "ERN", "ETB", "EUR",
    "FJD", "FKP",
    "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD",
    "HKD", "HNL", "HTG", "HUF",
    "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
    "JMD", "JOD", "JPY",
    "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT",
    "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR",
    "MWK", "MXN", "MXV", "MYR", "MZN",
    "NAD", "NGN", "NIO", "NOK", "NPR", "NZD",
    "OMR",
    "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR",
    "RON", "RSD", "RUB", "RWF",
    "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SOS",
    "SRD", "SSP", "STN", "SVC", "SYP", "SZL",
    "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS",
    "UAH", "UGX", "USD", "USN", "UYI", "UYU", "UYW", "UZS",
    "VED", "VES", "VND", "VUV",
    "WST",
    "XAF", "XCD", "XOF", "XPF",
    "YER",
    "ZAR", "ZMW", "ZWG", "USS",
}

# Known withdrawn codes — these appear in Wikipedia's table but are not active
WITHDRAWN_ISO_CODES: Set[str] = {
    "ADF", "ADP", "AFA", "ALK", "AOK", "AON", "AOR", "ARA", "ARL", "ARP",
    "ARY", "ATS", "AZM",
    "BAD", "BEC", "BEF", "BEL", "BGJ", "BGK", "BGL", "BOP", "BRB", "BRC",
    "BRE", "BRN", "BRR", "BUK", "BYB", "BYR",
    "CHC", "CSD", "CSJ", "CSK", "CYP",
    "DDM", "DEM",
    "ECS", "ECV", "EEK", "ESA", "ESB", "ESP",
    "FIM", "FRF",
    "GEK", "GHC", "GHP", "GNE", "GNS", "GQE", "GRD", "GWE", "GWP",
    "HRD", "HRK",
    "IEP", "ILP", "ILR", "ISJ", "ITL",
    "LAJ", "LSM", "LTL", "LTT", "LUC", "LUF", "LUL", "LVL", "LVR",
    "MCF", "MGF", "MKN", "MLF", "MRO", "MTL", "MTP", "MVQ", "MXP", "MZE", "MZM",
    "NIC", "NLG",
    "PEH", "PEI", "PES", "PLZ", "PTE",
    "RHD", "ROK", "ROL", "RUR",
    "SDD", "SDP", "SIT", "SKK", "SLL", "SML", "SRG", "STD", "SUR",
    "TJR", "TMM", "TPE", "TRL",
    "UAK", "UGS", "UGW", "UYN", "UYP",
    "VAL", "VEB", "VEF", "VNC",
    "YDD", "YUD", "YUG", "YUM", "YUN", "YUO", "YUR",
    "ZAL", "ZMK", "ZRN", "ZRZ", "ZWC", "ZWD", "ZWL", "ZWN", "ZWR",
}

# Special non-currency ISO codes
SPECIAL_ISO_CODES: Set[str] = {
    "XDR",  # Special Drawing Rights
    "XSU",  # SUCRE
    "XUA",  # ADB Unit of Account
    "XBA", "XBB", "XBC", "XBD",  # European bond market units
    "XTS",  # Testing
    "XXX",  # No currency
}

# Commodity/precious metal codes
COMMODITY_CODES: Set[str] = {
    "XAG", "XAU", "XPD", "XPT",
}

# Obsolete/withdrawn special codes
OBSOLETE_SPECIAL: Set[str] = {
    "XEU", "XFO", "XFU", "XRE",
}

# Codes that Wikipedia lists but aren't actually ISO 4217
NON_ISO_MARKET_CODES: Set[str] = {
    "RMB",  # CNH is the market code; RMB is not an ISO code
    "XCG",  # Caribbean guilder — proposed, not yet active
}


def classify_currency(code: str, name: str) -> str:
    """
    Classify a currency code as active, withdrawn, commodity, special_purpose, or non_iso.
    
    Uses the known sets above as ground truth, with heuristics as fallback.
    """
    if code in ACTIVE_ISO_CODES:
        return "active"
    if code in WITHDRAWN_ISO_CODES:
        return "withdrawn"
    if code in SPECIAL_ISO_CODES:
        return "special_purpose"
    if code in COMMODITY_CODES:
        return "commodity"
    if code in OBSOLETE_SPECIAL:
        return "withdrawn"
    if code in NON_ISO_MARKET_CODES:
        return "non_iso"

    # Heuristics for codes not in any known set
    if code.startswith("X"):
        # X-codes are special — check name for clues
        name_lower = name.lower()
        if "gold" in name_lower or "silver" in name_lower or "palladium" in name_lower or "platinum" in name_lower:
            return "commodity"
        if "funds code" in name_lower or "bond market" in name_lower or "testing" in name_lower:
            return "special_purpose"
        return "commodity"  # Default for unknown X-codes

    # If we don't know, mark as unclassified for human review
    return "unclassified"


def load_latest_source(name_prefix: str) -> Optional[Dict]:
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


def parse_wikipedia_data(raw_data: List[Dict]) -> Dict:
    """Parse raw Wikipedia data into structured format with proper active/withdrawn separation."""
    parsed = {
        "active": [],
        "withdrawn": [],
        "commodity": [],
        "special_purpose": [],
        "non_iso": [],
        "unclassified": [],
        "parse_notes": [],
        "classification_stats": {},
    }

    for entry in raw_data:
        code = entry.get("code", "")

        # Skip entries without valid codes
        if not code or len(code) != 3 or not code.isupper():
            continue

        # Skip rows that are actually table headers or notes
        if code in ["CODE", "NUM", "DIGITS"]:
            continue

        # Build a normalized entry
        normalized = {
            "code": code,
            "numeric": entry.get("numeric", "").strip().zfill(3),
            "name": entry.get("name", "").strip(),
            "minor_units": entry.get("minor_units", 0),
        }

        # Validate numeric code
        if not normalized["numeric"].isdigit() or len(normalized["numeric"]) != 3:
            parsed["parse_notes"].append(
                f"Invalid numeric code for {code}: '{entry.get('numeric', '')}' "
                f"(name: {normalized['name'][:40]})"
            )
            normalized["numeric"] = "000"

        # Validate minor_units
        if not isinstance(normalized["minor_units"], int):
            parsed["parse_notes"].append(
                f"Invalid minor_units for {code}: {entry.get('minor_units')}"
            )
            normalized["minor_units"] = 0

        # Classify using ground truth sets
        category = classify_currency(code, normalized["name"])
        parsed[category].append(normalized)

    # Sort each category by code
    for cat in ["active", "withdrawn", "commodity", "special_purpose", "non_iso", "unclassified"]:
        parsed[cat].sort(key=lambda x: x["code"])

    # Stats
    parsed["classification_stats"] = {
        cat: len(parsed[cat])
        for cat in ["active", "withdrawn", "commodity", "special_purpose", "non_iso", "unclassified"]
    }

    return parsed


def generate_summary(parsed: Dict) -> str:
    """Generate a human-readable summary of parsed data."""
    lines = []
    lines.append("=" * 60)
    lines.append("  Source Data Parse Summary (v1 — classified)")
    lines.append("=" * 60)

    labels = {
        "active": "Active ISO 4217",
        "withdrawn": "Withdrawn ISO 4217",
        "commodity": "Commodity codes",
        "special_purpose": "Special purpose",
        "non_iso": "Non-ISO market codes",
        "unclassified": "⚠️  Unclassified (needs review)",
    }

    total = 0
    for cat in ["active", "withdrawn", "commodity", "special_purpose", "non_iso", "unclassified"]:
        count = len(parsed.get(cat, []))
        total += count
        marker = "⚠️  " if cat == "unclassified" and count > 0 else "    "
        lines.append(f"  {marker}{labels[cat]:<30} {count:>4}")

    lines.append(f"  {'Total':<30} {total:>4}")
    lines.append("=" * 60)

    if parsed.get("parse_notes"):
        lines.append(f"\n  ⚠️  Parse Notes ({len(parsed['parse_notes'])}):")
        for note in parsed["parse_notes"][:10]:
            lines.append(f"    - {note}")
        if len(parsed["parse_notes"]) > 10:
            lines.append(f"    ... and {len(parsed['parse_notes']) - 10} more")

    # Show unclassified codes (these need human attention)
    unclassified = parsed.get("unclassified", [])
    if unclassified:
        lines.append(f"\n  🔍 UNCLASSIFIED CODES ({len(unclassified)}) — NEED HUMAN REVIEW:")
        for item in unclassified:
            lines.append(f"    {item['code']}: {item['name'][:50]} (minor_units={item['minor_units']})")

    return "\n".join(lines)


def cross_reference_with_registry(parsed: Dict, registry_path: Path) -> Dict:
    """Cross-reference parsed source data with the current registry."""
    with open(registry_path, 'r', encoding='utf-8') as f:
        registry = json.load(f)

    registry_active = {c["code"] for c in registry.get("currencies", {}).get("active", [])}
    registry_withdrawn = {c["code"] for c in registry.get("currencies", {}).get("withdrawn", [])}
    registry_all_iso = registry_active | registry_withdrawn

    source_active = {c["code"] for c in parsed.get("active", [])}
    source_withdrawn = {c["code"] for c in parsed.get("withdrawn", [])}
    source_all_iso = source_active | source_withdrawn

    # Missing from registry: codes that ISO says are active but we don't have
    missing_active = sorted(source_active - registry_active)

    # In registry but withdrawn: codes we list as active but ISO says are withdrawn
    wrongly_active = sorted(registry_active & source_withdrawn)

    # In registry but not in source at all: possible data errors or very new codes
    not_in_source = sorted(registry_all_iso - source_all_iso)

    # Active codes in source that would expand the registry
    new_active_candidates = sorted(source_active - registry_active)

    return {
        "registry_active_count": len(registry_active),
        "registry_withdrawn_count": len(registry_withdrawn),
        "source_active_count": len(source_active),
        "source_withdrawn_count": len(source_withdrawn),
        "missing_from_registry": missing_active,
        "missing_count": len(missing_active),
        "wrongly_active": wrongly_active,
        "wrongly_active_count": len(wrongly_active),
        "not_in_source": not_in_source,
        "not_in_source_count": len(not_in_source),
        "new_active_candidates": new_active_candidates,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse downloaded ISO 4217 source data (v1 — classified)")
    parser.add_argument("--source", "-s", default=None, help="Source prefix (default: latest)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output path for parsed JSON")
    parser.add_argument("--summary-only", action="store_true", help="Only print summary")

    args = parser.parse_args()

    # Load source data
    if args.source:
        source_data = load_latest_source(args.source)
    else:
        source_data = load_latest_source("wikipedia")

    if not source_data:
        print("Error: No source data found. Run update_from_iso.py --fetch-sources first.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {len(source_data)} raw entries with ground-truth classification...")

    # Parse
    parsed = parse_wikipedia_data(source_data)

    # Summary
    print("\n" + generate_summary(parsed))

    # Cross-reference with registry
    registry_path = PROJECT_ROOT / "iso4217.json"
    if registry_path.exists():
        cross_ref = cross_reference_with_registry(parsed, registry_path)
        print(f"\n  Cross-reference with current registry:")
        print(f"    Registry active:     {cross_ref['registry_active_count']}")
        print(f"    Source active:       {cross_ref['source_active_count']}")
        print(f"    Source withdrawn:    {cross_ref['source_withdrawn_count']}")
        print(f"    Missing from registry: {cross_ref['missing_count']}")
        if cross_ref['missing_from_registry']:
            print(f"      Add these active codes:")
            for code in cross_ref['missing_from_registry'][:30]:
                print(f"        {code}")
            if len(cross_ref['missing_from_registry']) > 30:
                print(f"        ... and {len(cross_ref['missing_from_registry']) - 30} more")
        if cross_ref['wrongly_active']:
            print(f"\n    ⚠️  Listed as active but ISO says withdrawn:")
            for code in cross_ref['wrongly_active']:
                print(f"        {code}")

    # Save
    if not args.summary_only:
        output_path = args.output or (SOURCES_DIR / f"parsed_{date.today().isoformat()}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        print(f"\nParsed data saved to: {output_path}")


if __name__ == "__main__":
    main()