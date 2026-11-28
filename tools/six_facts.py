#!/usr/bin/env python3
"""
tools/six_facts.py

Derive the facts of SIX's ISO 4217 List One (one row per alphabetic code: code, numeric code, minor units, and the list's
publication date) and write them to tests/fixtures/six_list_one_facts.json, the fixture tests/test_six_list_one_parity.py
holds the registry's `active` section to.

v1.9.7: the registry claimed amendment 180 while List One no longer listed CUC, USS or ANG and listed XCG; the amendment
monitor compared only the amendment number. The parity test compares the codes themselves. Facts only: the XML is not
committed (its redistribution terms are undecided), so this tool is run by hand on a downloaded copy, and `--check` says
whether the committed fixture is what that copy gives.

Read from each <CcyNtry>: <Ccy>, <CcyNbr>, <CcyMnrUnts>. An entry without <Ccy> ("No universal currency") is skipped; a code
listed for several entities is one row, and the rows must agree (else exit 1). "N.A." minor units is written as null.

Usage:
  python3 tools/six_facts.py list-one.xml                 # write the fixture
  python3 tools/six_facts.py list-one.xml --check         # compare with the committed fixture, write nothing
  python3 tools/six_facts.py list-one.xml --out PATH      # write elsewhere

Exit codes (the convention in RELEASE_PATTERN.md):
  0  written, or --check: the committed fixture is what the XML gives
  1  --check: the fixture differs (or is missing); or the XML contradicts itself for one code
  2  usage error: the XML is missing, not List One, or not readable
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXIT_OK, EXIT_DIFF, EXIT_USAGE = 0, 1, 2
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "six_list_one_facts.json"


class ListError(Exception):
    pass


def facts(xml_path: Path) -> dict:
    """The fixture's content, from one List One XML file."""
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError) as e:
        raise ListError(f"cannot read {xml_path}: {e}") from e
    published = root.get("Pblshd")
    if root.tag != "ISO_4217" or root.find("CcyTbl") is None or not published:
        raise ListError(f"{xml_path} is not SIX List One (no <ISO_4217 Pblshd=...><CcyTbl>)")
    rows: dict[str, dict] = {}
    for entry in root.iter("CcyNtry"):
        code = (entry.findtext("Ccy") or "").strip()
        if not code:
            continue
        minor = (entry.findtext("CcyMnrUnts") or "").strip()
        row = {
            "code": code,
            "numeric": (entry.findtext("CcyNbr") or "").strip() or None,
            "minor_units": None if minor in ("", "N.A.") else int(minor),
        }
        if code in rows and rows[code] != row:
            raise ValueError(f"List One gives {code} two ways: {rows[code]} and {row}")
        rows[code] = row
    return {
        "description": "Facts derived from SIX's ISO 4217 List One by tools/six_facts.py: one row per alphabetic code. "
                       "The XML itself is not committed. Regenerate with the tool when SIX publishes a new list.",
        "source": "SIX ISO 4217 List One (List One: Current Currency & Funds), XML",
        "published": published,
        "code_count": len(rows),
        "codes": [rows[c] for c in sorted(rows)],
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="six_facts.py", description="derive the List One facts fixture")
    p.add_argument("xml", help="a downloaded copy of SIX's list-one.xml")
    p.add_argument("--check", action="store_true", help="compare with the committed fixture; write nothing")
    p.add_argument("--out", default=str(FIXTURE), help=f"where to write (default {FIXTURE.relative_to(ROOT)})")
    args = p.parse_args(argv)

    try:
        text = render(facts(Path(args.xml)))
    except ListError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return EXIT_DIFF
    out = Path(args.out)
    if args.check:
        if not out.is_file():
            print(f"FAIL: {out} does not exist; run without --check to write it")
            return EXIT_DIFF
        if out.read_text(encoding="utf-8") != text:
            print(f"FAIL: {out} is not what {args.xml} gives; run without --check to rewrite it")
            return EXIT_DIFF
        print(f"OK: {out.name} matches {Path(args.xml).name} (published {json.loads(text)['published']})")
        return EXIT_OK
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({json.loads(text)['code_count']} codes, published {json.loads(text)['published']})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
