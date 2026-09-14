#!/usr/bin/env python3
"""
Insert new crypto/stablecoin entries into iso4217.json without reformatting.

This script appends entries to the correct arrays using text insertion at the
exact closing bracket position — it does NOT do a json.load/json.dump round-trip,
which would reformat the entire file and produce a 3000+ line diff.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

REGISTRY_PATH = Path("iso4217.json")

# ---------------------------------------------------------------------------
# Entries to insert — replace with your verified data
# ---------------------------------------------------------------------------

NEW_CRYPTOCURRENCIES = [
    {
        "code": "XRP",
        "name": "XRP",
        "minor_units": 6,
        "symbol": "XRP",
        "type": "cryptocurrency",
        "entity": "Ripple Labs",
        "introduced": "2012-06-01",
        "market_cap_rank": 5,
        "note": "Not an ISO 4217 code. Included due to widespread financial market usage."
    },
    {
        "code": "SOL",
        "name": "Solana",
        "minor_units": 9,
        "symbol": "SOL",
        "type": "cryptocurrency",
        "entity": "Solana Foundation",
        "introduced": "2020-03-16",
        "market_cap_rank": 6,
        "note": "Not an ISO 4217 code. Included due to widespread financial market usage."
    },
    {
        "code": "BNB",
        "name": "BNB",
        "minor_units": 18,
        "symbol": "BNB",
        "type": "cryptocurrency",
        "entity": "Binance",
        "introduced": "2017-07-14",
        "market_cap_rank": 4,
        "note": "Not an ISO 4217 code. 18 minor units follows the BEP20 (BSC) convention; the BEP2 (Binance Chain) variant uses 8."
    },
    {
        "code": "ADA",
        "name": "Cardano",
        "minor_units": 6,
        "symbol": "ADA",
        "type": "cryptocurrency",
        "entity": "Cardano Foundation",
        "introduced": "2017-09-29",
        "market_cap_rank": 10,
        "note": "Not an ISO 4217 code. Included due to widespread financial market usage."
    },
    {
        "code": "DOGE",
        "name": "Dogecoin",
        "minor_units": 8,
        "symbol": "Ð",
        "type": "cryptocurrency",
        "entity": "Decentralized",
        "introduced": "2013-12-06",
        "market_cap_rank": 8,
        "note": "Not an ISO 4217 code. Included due to widespread financial market usage."
    }
]

NEW_STABLECOINS = [
    {
        "code": "USDP",
        "name": "Pax Dollar",
        "minor_units": 18,
        "symbol": "USDP",
        "type": "stablecoin",
        "entity": "Paxos Trust Company",
        "introduced": "2018-09-10",
        "market_cap_rank": 50,
        "pegged_to": "USD",
        "peg_mechanism": "Fiat-collateralized",
        "note": "Not an ISO 4217 code. Regulated US dollar stablecoin issued by Paxos."
    },
    {
        "code": "FRAX",
        "name": "Frax",
        "minor_units": 18,
        "symbol": "FRAX",
        "type": "stablecoin",
        "entity": "Frax Finance",
        "introduced": "2020-12-21",
        "market_cap_rank": 30,
        "pegged_to": "USD",
        "peg_mechanism": "Hybrid",
        "note": "Not an ISO 4217 code. Partially algorithmic stablecoin."
    },
    {
        "code": "TUSD",
        "name": "TrueUSD",
        "minor_units": 18,
        "symbol": "TUSD",
        "type": "stablecoin",
        "entity": "Archblock (formerly TrustToken)",
        "introduced": "2018-03-05",
        "market_cap_rank": 40,
        "pegged_to": "USD",
        "peg_mechanism": "Fiat-collateralized",
        "note": "Not an ISO 4217 code. Regulated US dollar stablecoin."
    }
]


def find_array_close(text: str, key: str) -> int:
    """
    Find the position of the closing ']' for the array following `"key": [`.

    Uses bracket-depth counting to handle nested objects and arrays correctly.
    Returns the index of the closing ']'.
    """
    # Find the key
    key_pattern = f'"{key}": ['
    key_pos = text.find(key_pattern)
    if key_pos == -1:
        raise ValueError(f"Key not found: {key}")

    # Position of the opening '['
    open_pos = key_pos + len(key_pattern) - 1

    # Count bracket depth from the opening bracket
    depth = 0
    in_string = False
    escape = False

    for i in range(open_pos, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == '\\':
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return i

    raise ValueError(f"Unmatched bracket for key: {key}")


def format_entry(entry: dict, indent: int = 6) -> str:
    """Format a single entry as JSON with the specified indentation."""
    lines = json.dumps(entry, indent=2, ensure_ascii=False).split('\n')
    prefix = ' ' * indent
    # First line stays at indent, subsequent lines get prefixed
    formatted = [prefix + lines[0]]
    for line in lines[1:]:
        formatted.append(prefix + line)
    return '\n'.join(formatted)


def insert_entries(text: str, key: str, entries: list[dict]) -> str:
    """
    Insert entries at the end of the array following `"key": [`.

    The insertion preserves the existing closing bracket and adds a comma
    after the last existing entry.
    """
    close_pos = find_array_close(text, key)

    # Walk backwards from close_pos to find the last non-whitespace char
    # to determine if we need a trailing comma
    i = close_pos - 1
    while i > 0 and text[i] in ' \t\n\r':
        i -= 1

    # If the array is empty (previous non-ws char is '['), no comma needed
    last_char = text[i]
    needs_leading_comma = last_char != '['

    # Build the insertion text
    indented_entries = []
    for entry in entries:
        indented_entries.append(format_entry(entry, indent=6))

    # If we need a leading comma (existing entries), add it before the first new entry
    if needs_leading_comma:
        insertion = ',\n' + ',\n'.join(indented_entries) + '\n    '
    else:
        insertion = '\n' + ',\n'.join(indented_entries) + '\n    '

    # Insert before the closing bracket
    return text[:close_pos] + insertion + text[close_pos:]


def main():
    # Backup
    backup = REGISTRY_PATH.with_suffix('.json.bak')
    shutil.copy(REGISTRY_PATH, backup)
    print(f"Backup created: {backup}")

    # Read raw text
    text = REGISTRY_PATH.read_text(encoding='utf-8')

    # Verify the JSON parses before we start
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Existing file is not valid JSON: {e}")
        return 1

    # Insert cryptocurrencies
    text = insert_entries(text, "cryptocurrencies", NEW_CRYPTOCURRENCIES)

    # Insert stablecoins
    text = insert_entries(text, "stablecoins", NEW_STABLECOINS)

    # Verify the result parses
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Result is not valid JSON: {e}")
        print("Restoring backup...")
        shutil.copy(backup, REGISTRY_PATH)
        return 1

    # Verify counts
    crypto_count = len(parsed["non_iso"]["cryptocurrencies"])
    stable_count = len(parsed["non_iso"]["stablecoins"])

    if crypto_count != 7 or stable_count != 6:
        print(f"ERROR: Unexpected counts — crypto={crypto_count}, stablecoin={stable_count}")
        print("Expected: crypto=7, stablecoin=6")
        print("Restoring backup...")
        shutil.copy(backup, REGISTRY_PATH)
        return 1

    # Write
    REGISTRY_PATH.write_text(text, encoding='utf-8')

    print(f"✅ Inserted {len(NEW_CRYPTOCURRENCIES)} cryptocurrencies (total: {crypto_count})")
    print(f"✅ Inserted {len(NEW_STABLECOINS)} stablecoins (total: {stable_count})")
    print(f"Backup: {backup}")

    return 0


if __name__ == "__main__":
    exit(main())