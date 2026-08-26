#!/usr/bin/env python3
"""
Generate v1.3.0 skeleton entries for missing withdrawn ISO 4217 currencies.

Reads the curated withdrawn-code set from tools/parse_source.py, finds which
codes are missing from the current registry's withdrawn array, and generates
skeleton JSON entries with fields populated from parsed Wikipedia data where
available.

Eurozone currencies (irrevocably fixed conversion rates) are auto-filled
completely — no manual research needed. Non-Eurozone currencies get TODO
placeholders for withdrawn_date, replaced_by, and conversion_rate.

Usage:
  python3 tools/generate_v1_3_skeletons.py --summary
  python3 tools/generate_v1_3_skeletons.py --output /tmp/skeletons.json
  python3 tools/generate_v1_3_skeletons.py --auto-fill-eurozone
  python3 tools/generate_v1_3_skeletons.py --all-auto-fill

Exit codes:
  0 — success
  1 — no missing currencies found (nothing to generate)
  2 — fatal error (missing files, invalid JSON, etc.)
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.parse_source import WITHDRAWN_ISO_CODES


# ---------------------------------------------------------------------------
# Eurozone data — irrevocably fixed, verified against ECB
# ---------------------------------------------------------------------------

# Irrevocable conversion rates: units of old currency per 1 EUR
# Source: ECB Council Regulation (EC) No 2866/98 of 31 December 1998
EUROZONE_RATES: dict[str, float] = {
    "ADF": 5.58674,    # Andorran franc (aligned with French franc)
    "ADP": 166.386,    # Andorran peseta (aligned with Spanish peseta)
    "ATS": 13.7603,    # Austrian schilling
    "BEF": 40.3399,    # Belgian franc
    "CYP": 0.585274,   # Cypriot pound
    "DEM": 1.95583,    # German mark
    "EEK": 15.6466,    # Estonian kroon
    "ESP": 166.386,    # Spanish peseta
    "FIM": 5.94573,    # Finnish markka
    "FRF": 6.55957,    # French franc
    "GRD": 340.750,    # Greek drachma
    "HRK": 7.53450,    # Croatian kuna
    "IEP": 0.787564,   # Irish pound
    "ITL": 1936.27,    # Italian lira
    "LUF": 40.3399,    # Luxembourg franc
    "LVL": 0.702804,   # Latvian lats
    "LTL": 3.4528,     # Lithuanian litas
    "MTL": 0.4293,     # Maltese lira
    "NLG": 2.20371,    # Dutch guilder
    "PTE": 200.482,    # Portuguese escudo
    "SIT": 239.640,    # Slovenian tolar
    "SKK": 30.1260,    # Slovak koruna
    "VAL": 1936.27,    # Vatican lira (aligned with Italian lira)
    "SML": 1936.27,    # San Marinese lira (aligned with Italian lira)
    "MCF": 6.55957,    # Monégasque franc (aligned with French franc)
}

# Withdrawal dates for Eurozone currencies
# Most joined on 1999-01-01; later joiners have their own dates
EURO_WITHDRAWAL_DATES: dict[str, str] = {
    "GRD": "2001-01-01",  # Greece joined Eurozone
    "SIT": "2007-01-01",  # Slovenia joined
    "CYP": "2008-01-01",  # Cyprus joined
    "MTL": "2008-01-01",  # Malta joined
    "SKK": "2009-01-01",  # Slovakia joined
    "EEK": "2011-01-01",  # Estonia joined
    "LVL": "2014-01-01",  # Latvia joined
    "LTL": "2015-01-01",  # Lithuania joined
    "HRK": "2023-01-01",  # Croatia joined
}

# Default withdrawal date for the original 1999 Eurozone members
EURO_DEFAULT_WITHDRAWAL_DATE = "1999-01-01"

# Entities and central banks for Eurozone predecessor currencies
# (auto-filled where the data is unambiguous)
EUROZONE_ENTITIES: dict[str, str] = {
    "ADF": "Andorra",
    "ADP": "Andorra",
    "ATS": "Austria",
    "BEF": "Belgium",
    "CYP": "Cyprus",
    "DEM": "Germany",
    "EEK": "Estonia",
    "ESP": "Spain",
    "FIM": "Finland",
    "FRF": "France",
    "GRD": "Greece",
    "HRK": "Croatia",
    "IEP": "Ireland",
    "ITL": "Italy",
    "LUF": "Luxembourg",
    "LVL": "Latvia",
    "LTL": "Lithuania",
    "MTL": "Malta",
    "NLG": "Netherlands",
    "PTE": "Portugal",
    "SIT": "Slovenia",
    "SKK": "Slovakia",
    "VAL": "Vatican City",
    "SML": "San Marino",
    "MCF": "Monaco",
}

EUROZONE_SYMBOLS: dict[str, str] = {
    "ADF": "F", "ADP": "Pts", "ATS": "S", "BEF": "fr.",
    "CYP": "£", "DEM": "DM", "EEK": "kr", "ESP": "Pts",
    "FIM": "mk", "FRF": "F", "GRD": "Δρχ", "HRK": "kn",
    "IEP": "£", "ITL": "₤", "LUF": "F", "LVL": "Ls",
    "LTL": "Lt", "MTL": "Lm", "NLG": "ƒ", "PTE": "$",
    "SIT": "SIT", "SKK": "Sk", "VAL": "₤", "SML": "₤", "MCF": "F",
}

# ---------------------------------------------------------------------------
# Non-Eurozone known data (verified, commonly documented)
# ---------------------------------------------------------------------------

# Known revaluation currencies with documented successors and rates
KNOWN_REVALUATIONS: dict[str, dict] = {
    "AFA": {"replaced_by": "AFN", "rate": 1000.0, "date": "2003-01-01",
             "entity": "Afghanistan", "symbol": "؋"},
    "AZM": {"replaced_by": "AZN", "rate": 5000.0, "date": "2006-01-01",
             "entity": "Azerbaijan", "symbol": "₼"},
    "BYR": {"replaced_by": "BYN", "rate": 10000.0, "date": "2016-07-01",
             "entity": "Belarus", "symbol": "Br"},
    "GHC": {"replaced_by": "GHS", "rate": 10000.0, "date": "2007-07-01",
             "entity": "Ghana", "symbol": "GH₵"},
    "MRO": {"replaced_by": "MRU", "rate": 10.0, "date": "2018-01-01",
             "entity": "Mauritania", "symbol": "UM"},
    "ROL": {"replaced_by": "RON", "rate": 10000.0, "date": "2005-07-01",
             "entity": "Romania", "symbol": "lei"},
    "RUR": {"replaced_by": "RUB", "rate": 1000.0, "date": "1998-01-01",
             "entity": "Russia", "symbol": "₽"},
    "SDP": {"replaced_by": "SDG", "rate": 10.0, "date": "2007-01-01",
             "entity": "Sudan", "symbol": "ج.س"},
    "SRG": {"replaced_by": "SRD", "rate": 1000.0, "date": "2004-01-01",
             "entity": "Suriname", "symbol": "$"},
    "STD": {"replaced_by": "STN", "rate": 1000.0, "date": "2018-01-01",
             "entity": "São Tomé and Príncipe", "symbol": "Db"},
    "TRL": {"replaced_by": "TRY", "rate": 1000000.0, "date": "2005-01-01",
             "entity": "Turkey", "symbol": "₺"},
    "ZMK": {"replaced_by": "ZMW", "rate": 1000.0, "date": "2013-01-01",
             "entity": "Zambia", "symbol": "ZK"},
}


def load_parsed_source() -> dict:
    """Load the most recent parsed source data file."""
    sources_dir = PROJECT_ROOT / "tools" / "sources"

    # Try to find any parsed file
    parsed_files = sorted(sources_dir.glob("parsed_*.json"), reverse=True)
    if not parsed_files:
        return {}

    with open(parsed_files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def build_withdrawn_lookup(parsed: dict) -> dict:
    """Build a code → source data lookup from parsed Wikipedia data."""
    lookup = {}
    for entry in parsed.get("withdrawn", []):
        code = entry.get("code", "")
        if code:
            lookup[code] = entry
    return lookup


def get_missing(curated_codes: set, current_codes: set) -> list:
    """Return sorted list of codes in curated but not in current registry."""
    return sorted(curated_codes - current_codes)


def generate_skeleton(code: str, source_lookup: dict,
                      auto_fill_eurozone: bool = False,
                      auto_fill_revaluations: bool = False) -> dict:
    """
    Generate a skeleton entry for a single withdrawn currency code.

    Auto-fills Eurozone data (locked rates, no research needed) and known
    revaluations if the corresponding flags are set.
    """
    source = source_lookup.get(code, {})

    skeleton = {
        "code": code,
        "numeric": source.get("numeric", "000").strip().zfill(3),
        "name": source.get("name", f"TODO: name for {code}").strip(),
        "minor_units": source.get("minor_units", 2),
        "symbol": "TODO",
        "entity": "TODO",
        "withdrawn_date": "TODO",
        "replaced_by": "TODO",
        "conversion_rate": None,
        "note": None,
    }

    # Auto-fill Eurozone data
    if auto_fill_eurozone and code in EUROZONE_RATES:
        skeleton["symbol"] = EUROZONE_SYMBOLS.get(code, "TODO")
        skeleton["entity"] = EUROZONE_ENTITIES.get(code, "TODO")
        skeleton["withdrawn_date"] = EURO_WITHDRAWAL_DATES.get(
            code, EURO_DEFAULT_WITHDRAWAL_DATE
        )
        skeleton["replaced_by"] = "EUR"
        skeleton["conversion_rate"] = EUROZONE_RATES[code]
        skeleton["note"] = (
            f"Irrevocably fixed conversion rate to EUR per ECB "
            f"Council Regulation (EC) No 2866/98."
        )

    # Auto-fill known revaluations
    if auto_fill_revaluations and code in KNOWN_REVALUATIONS:
        known = KNOWN_REVALUATIONS[code]
        skeleton["symbol"] = known.get("symbol", "TODO")
        skeleton["entity"] = known.get("entity", "TODO")
        skeleton["withdrawn_date"] = known["date"]
        skeleton["replaced_by"] = known["replaced_by"]
        skeleton["conversion_rate"] = known["rate"]
        skeleton["note"] = (
            f"Revalued at {known['rate']:g}:1 into {known['replaced_by']} "
            f"on {known['date']}."
        )

    return skeleton


def main():
    parser = argparse.ArgumentParser(
        description="Generate v1.3.0 skeletons for missing withdrawn currencies"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write skeletons to a file (default: stdout)"
    )
    parser.add_argument(
        "--summary", "-s", action="store_true",
        help="Only show summary, don't output skeletons"
    )
    parser.add_argument(
        "--auto-fill-eurozone", action="store_true",
        help="Auto-fill Eurozone currencies with locked rates (no TODO)"
    )
    parser.add_argument(
        "--auto-fill-revaluations", action="store_true",
        help="Auto-fill known revaluations with documented rates"
    )
    parser.add_argument(
        "--all-auto-fill", action="store_true",
        help="Enable both --auto-fill-eurozone and --auto-fill-revaluations"
    )

    args = parser.parse_args()

    # Resolve flags
    auto_euro = args.auto_fill_eurozone or args.all_auto_fill
    auto_reval = args.auto_fill_revaluations or args.all_auto_fill

    # Load current registry
    registry_path = PROJECT_ROOT / "iso4217.json"
    if not registry_path.exists():
        print(f"FATAL: Registry not found: {registry_path}", file=sys.stderr)
        sys.exit(2)

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    current_codes = {
        c["code"] for c in registry.get("currencies", {}).get("withdrawn", [])
    }

    # Load parsed source
    parsed = load_parsed_source()
    source_lookup = build_withdrawn_lookup(parsed)

    # Find missing
    missing = get_missing(WITHDRAWN_ISO_CODES, current_codes)

    if not missing:
        print("No missing withdrawn currencies — registry is up to date.")
        sys.exit(1)

    # Count auto-fill vs research
    euro_count = sum(1 for c in missing if c in EUROZONE_RATES)
    reval_count = sum(1 for c in missing if c in KNOWN_REVALUATIONS)
    overlap = sum(1 for c in missing if c in EUROZONE_RATES and c in KNOWN_REVALUATIONS)
    research_count = len(missing) - euro_count - reval_count + overlap

    print("=" * 60)
    print("  v1.3.0 Withdrawn Currency Skeleton Summary")
    print("=" * 60)
    print(f"  Total missing:          {len(missing)}")
    print(f"  Eurozone (locked rates): {euro_count}")
    print(f"  Known revaluations:      {reval_count}")
    print(f"  Needs research:          {research_count}")
    print("=" * 60)

    # Show first 30 codes
    print("\n  First 30 codes:")
    for code in missing[:30]:
        markers = []
        if code in EUROZONE_RATES:
            markers.append("EUR")
        if code in KNOWN_REVALUATIONS:
            markers.append("REVAL")
        marker_str = f" [{', '.join(markers)}]" if markers else ""
        print(f"    {code}{marker_str}")

    if len(missing) > 30:
        print(f"    ... and {len(missing) - 30} more")

    if args.summary:
        sys.exit(0)

    # Generate skeletons
    skeletons = []
    for code in missing:
        skeletons.append(generate_skeleton(
            code, source_lookup,
            auto_fill_eurozone=auto_euro,
            auto_fill_revaluations=auto_reval,
        ))

    output = json.dumps(skeletons, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"\nSkeletons written to: {args.output}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()