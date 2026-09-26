#!/usr/bin/env python3
"""
Enrich ISO 4217 entries with the v1.6.0 fields.

Four modes, each adding one field to the appropriate entries:

  classification   Static table (11 codes) + default "circulating".
  numeric_reused   Derived: true if numeric also on a withdrawn entry.
  source_url       Derived: URL from note, or ISO OBP default.
  code_lifetime    Derived: to = withdrawn_date, from = null unless known.

Every mode is idempotent: running twice produces no diff. Formatting is
preserved via targeted string insertion, not json.dump. This matters
because a json.load/json.dump round-trip reformats the entire file and
makes the diff unreviewable.

Usage:
    python3 tools/enrich_field.py --field classification
    python3 tools/enrich_field.py --field classification --check
    python3 tools/enrich_field.py --field classification --dry-run

Exit codes:
    0  success, or --check passed (no changes pending)
    1  --check found pending changes
    2  fatal error (registry missing, invalid JSON, unknown field)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "iso4217.json"

EXIT_OK = 0
EXIT_CHANGES_PENDING = 1
EXIT_FATAL = 2

# Active currencies that are fund units, not circulating currency.
FUND_CODES: frozenset[str] = frozenset({
    "BOV", "CHE", "CHW", "CLF", "COU", "MXV", "USN", "USS", "UYI", "UYW",
})

# Active currencies that are indexation units.
INDEXATION_CODES: frozenset[str] = frozenset({"VED"})

# URL matcher for extracting a source URL from a note field.
URL_PATTERN = re.compile(r'https?://[^\s"\'<>,;]+')

# `"code": "XXX"` line in the raw JSON, with optional trailing comma.
CODE_LINE_PATTERN = re.compile(r'^(\s*)"code":\s*"([^"]+)"(,?)\s*$')

# `"note": "...."` line in the raw JSON.
NOTE_LINE_PATTERN = re.compile(r'^(\s*)"note":\s*"(.*)"(,?)\s*$')


# ---------------------------------------------------------------------------
# Derivers — one per field, taking (entry, full_registry) and returning
# the field's value (a Python object that json.dumps can serialize).
# ---------------------------------------------------------------------------

def derive_classification(entry: dict, data: dict) -> str:
    code = entry["code"]
    if code in INDEXATION_CODES:
        return "indexation"
    if code in FUND_CODES:
        return "fund"
    return "circulating"


def derive_numeric_reused(entry: dict, data: dict) -> bool:
    numeric = entry.get("numeric")
    if not numeric:
        return False
    for w in data["currencies"]["withdrawn"]:
        if w.get("numeric") == numeric:
            return True
    return False


def derive_source_url(entry: dict, data: dict) -> str:
    """
    Prefer a URL already present in the entry's note. Fall back to the
    ISO OBP page for the code when the note has none.
    """
    note = entry.get("note") or ""
    m = URL_PATTERN.search(note)
    if m:
        return m.group(0)

    code = entry["code"]
    # ISO OBP resolves 3-letter codes only. Withdrawn synthetic codes
    # like MXN_OLD use the base stem.
    stem = code.split("_", 1)[0]
    if len(stem) == 3 and stem.isalpha() and stem.isupper():
        return f"https://www.iso.org/obp/ui/#iso:code:4217:{stem}"
    return "https://www.iso.org/obp/ui/"


def derive_code_lifetime(entry: dict, data: dict) -> dict:
    """
    { from, to }. `to` mirrors withdrawn_date. `from` is null unless a
    primary source documents the assignment date — the registry does not
    have that table, so every value is null for now.
    """
    return {
        "from": None,
        "to": entry.get("withdrawn_date"),
    }


# ---------------------------------------------------------------------------
# Note cleanup — remove URLs from a note text, preserving meaningful prose
# ---------------------------------------------------------------------------

def clean_note_text(note_text: str) -> Optional[str]:
    """
    Return the note text with any URL and its leading "source:" label
    removed. Return None if nothing meaningful remains.
    """
    text = note_text

    # Drop a leading "source:" label (case-insensitive).
    text = re.sub(r'^\s*source:\s*', '', text, flags=re.IGNORECASE)

    # Remove every URL.
    text = URL_PATTERN.sub('', text)

    # Squash leftover separators at the edges.
    text = re.sub(r'^[\s\.\,\;\:]+', '', text)
    text = re.sub(r'[\s\.\,\;\:]+$', '', text)
    text = re.sub(r'\s{2,}', ' ', text)

    return text if text else None


# ---------------------------------------------------------------------------
# Text insertion — modify the raw JSON in place, preserving formatting
# ---------------------------------------------------------------------------

def insert_fields_after_code(
    text: str,
    insertions: dict[str, list[tuple[str, str]]],
) -> tuple[str, int]:
    """
    For each code in insertions, insert the given fields immediately
    after its `"code": "XXX"` line. Returns (new_text, count_entries_touched).
    """
    lines = text.split("\n")
    out: list[str] = []
    touched = 0

    for line in lines:
        m = CODE_LINE_PATTERN.match(line)
        if m and m.group(2) in insertions:
            indent, code, comma = m.group(1), m.group(2), m.group(3)
            # Ensure the code line ends with a comma before appending.
            out.append(f'{indent}"code": "{code}",' if not comma else line)
            for field_name, field_value in insertions[code]:
                out.append(f'{indent}"{field_name}": {field_value},')
            touched += 1
        else:
            out.append(line)

    return "\n".join(out), touched


def clean_notes_for_codes(text: str, codes: set[str]) -> str:
    """
    For every entry whose code is in `codes`, rewrite its note line:
      - if the note becomes empty after removing the URL, replace with null
      - otherwise replace with the cleaned text
    """
    lines = text.split("\n")
    out: list[str] = []
    in_target = False

    for line in lines:
        cm = CODE_LINE_PATTERN.match(line)
        if cm:
            in_target = cm.group(2) in codes
            out.append(line)
            continue

        if in_target:
            nm = NOTE_LINE_PATTERN.match(line)
            if nm:
                indent, note_text, comma = nm.groups()
                cleaned = clean_note_text(note_text)
                if cleaned is None:
                    out.append(f'{indent}"note": null{comma}')
                elif cleaned != note_text:
                    out.append(f'{indent}"note": {json.dumps(cleaned)}{comma}')
                else:
                    out.append(line)
                continue

        out.append(line)

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Per-mode transforms
# ---------------------------------------------------------------------------

def transform_classification(data: dict, text: str) -> str:
    insertions: dict[str, list[tuple[str, str]]] = {}
    for entry in data["currencies"]["active"]:
        if "classification" in entry:
            continue
        cls = derive_classification(entry, data)
        insertions[entry["code"]] = [("classification", json.dumps(cls))]

    if not insertions:
        return text

    new_text, _ = insert_fields_after_code(text, insertions)
    return new_text


def transform_numeric_reused(data: dict, text: str) -> str:
    insertions: dict[str, list[tuple[str, str]]] = {}
    for entry in data["currencies"]["active"]:
        if "numeric_reused" in entry:
            continue
        reused = derive_numeric_reused(entry, data)
        insertions[entry["code"]] = [("numeric_reused", json.dumps(reused))]

    if not insertions:
        return text

    new_text, _ = insert_fields_after_code(text, insertions)
    return new_text


def transform_source_url(data: dict, text: str) -> str:
    insertions: dict[str, list[tuple[str, str]]] = {}
    codes_to_clean: set[str] = set()

    for section in ("active", "withdrawn"):
        for entry in data["currencies"][section]:
            code = entry["code"]
            if "source_url" not in entry:
                url = derive_source_url(entry, data)
                insertions[code] = [("source_url", json.dumps(url))]
            # Clean the note even if source_url already exists, in case
            # an earlier run inserted source_url without cleaning.
            note = entry.get("note") or ""
            if URL_PATTERN.search(note):
                codes_to_clean.add(code)

    new_text = text
    if insertions:
        new_text, _ = insert_fields_after_code(new_text, insertions)
    if codes_to_clean:
        new_text = clean_notes_for_codes(new_text, codes_to_clean)

    return new_text


def transform_code_lifetime(data: dict, text: str) -> str:
    insertions: dict[str, list[tuple[str, str]]] = {}
    for entry in data["currencies"]["withdrawn"]:
        if "code_lifetime" in entry:
            continue
        lifetime = derive_code_lifetime(entry, data)
        # Single-line object keeps the diff minimal and readable.
        field_value = json.dumps(lifetime, ensure_ascii=False)
        insertions[entry["code"]] = [("code_lifetime", field_value)]

    if not insertions:
        return text

    new_text, _ = insert_fields_after_code(text, insertions)
    return new_text


# Registry of modes.
FIELDS: dict[str, Callable[[dict, str], str]] = {
    "classification": transform_classification,
    "numeric_reused": transform_numeric_reused,
    "source_url": transform_source_url,
    "code_lifetime": transform_code_lifetime,
}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def count_entries_with_field(data: dict, field_name: str) -> tuple[int, int]:
    """Return (count_with_field, total) across active + withdrawn."""
    with_field = 0
    total = 0
    for section in ("active", "withdrawn"):
        for entry in data["currencies"][section]:
            total += 1
            if field_name in entry:
                with_field += 1
    return with_field, total


def print_change_summary(field_name: str, before: dict, after: dict) -> None:
    """Print a human-readable summary of the enrichment."""
    before_with, total = count_entries_with_field(before, field_name)
    after_with, _ = count_entries_with_field(after, field_name)
    added = after_with - before_with

    print(f"Field:  {field_name}")
    print(f"Before: {before_with}/{total} entries have the field")
    print(f"After:  {after_with}/{total} entries have the field")
    if added > 0:
        print(f"Added:  {added} entries")
    else:
        print("Added:  0 entries (already up to date)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="enrich_field.py",
        description=(
            "Enrich ISO 4217 entries with v1.6.0 fields. One field per "
            "invocation. Preserves formatting via targeted insertion."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  success, or --check passed (nothing pending)\n"
            "  1  --check found pending changes\n"
            "  2  fatal error\n"
        ),
    )
    parser.add_argument(
        "--field",
        required=True,
        choices=sorted(FIELDS.keys()),
        help="which field to enrich",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 if changes are pending, without writing",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="print what would change, without writing",
    )
    parser.add_argument(
        "--registry", type=Path, default=REGISTRY_PATH,
        help=f"path to iso4217.json (default: {REGISTRY_PATH})",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="suppress the change summary",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.check and args.dry_run:
        print("FATAL: --check and --dry-run are mutually exclusive", file=sys.stderr)
        return EXIT_FATAL

    if not args.registry.is_file():
        print(f"FATAL: registry not found: {args.registry}", file=sys.stderr)
        return EXIT_FATAL

    original_text = args.registry.read_text(encoding="utf-8")

    try:
        data = json.loads(original_text)
    except json.JSONDecodeError as e:
        print(f"FATAL: invalid JSON in {args.registry}: {e}", file=sys.stderr)
        return EXIT_FATAL

    transform = FIELDS[args.field]

    try:
        new_text = transform(data, original_text)
    except Exception as e:  # noqa: BLE001 — surface the failure clearly
        print(f"FATAL: {args.field} transform failed: {e}", file=sys.stderr)
        return EXIT_FATAL

    changed = new_text != original_text

    if args.check:
        if changed:
            print(f"PENDING: {args.field} has changes to apply")
            return EXIT_CHANGES_PENDING
        if not args.quiet:
            print(f"OK: {args.field} is up to date")
        return EXIT_OK

    if args.dry_run:
        if not changed:
            if not args.quiet:
                print(f"NO CHANGES: {args.field} is up to date")
            return EXIT_OK
        # Parse both to print the summary counts.
        try:
            after_data = json.loads(new_text)
        except json.JSONDecodeError as e:
            print(f"FATAL: dry-run produced invalid JSON: {e}", file=sys.stderr)
            return EXIT_FATAL
        if not args.quiet:
            print_change_summary(args.field, data, after_data)
            print("DRY RUN — no changes written.")
        return EXIT_OK

    if not changed:
        if not args.quiet:
            print(f"NO CHANGES: {args.field} is up to date")
        return EXIT_OK

    # Validate the transformed text parses as JSON before writing.
    try:
        after_data = json.loads(new_text)
    except json.JSONDecodeError as e:
        print(f"FATAL: transform produced invalid JSON: {e}", file=sys.stderr)
        return EXIT_FATAL

    args.registry.write_text(new_text, encoding="utf-8")

    if not args.quiet:
        print_change_summary(args.field, data, after_data)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())