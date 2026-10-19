#!/usr/bin/env python3
"""
tools/check_provenance.py

Fail when docs/PROVENANCE.md does not account for a field of iso4217.json.

README promises "per-field sourcing". Before v1.8.3 the document named 19 of the 46 fields in
passing and described the rest only by category, so a new field could ship with no provenance at all.
This check keeps that from coming back: every field in the data has exactly one row in the per-field
table, and every row says where the value comes from, when it is refreshed and what checks it.

What counts as a field: a key name in any of the six kinds of object the registry holds: `meta`,
`source`, the entries of `currencies.active`, the entries of `currencies.withdrawn`, the `countries[]`
objects inside them, and the entries of every `non_iso` section. The same name in several kinds
(`code`, `name`, `note`, ...) is one field with one row whose "Where" column lists the kinds. The
four root keys, and the `from` / `to` keys inside `code_lifetime`, are structure, not fields.

The table is the one under the heading "Per-field provenance" in docs/PROVENANCE.md, with the columns
Field | Where | Source | Refresh trigger | Checked by. A name that appears only in prose does not count.

Findings (exit 1):
  - a field in iso4217.json with no row
  - a row for a field that is not in iso4217.json
  - two rows for one field
  - an empty cell, or a cell that says TODO / TBD
  - a "Checked by" cell that names no file in backticks and does not say `none`, or names a file that does
    not exist in the repository (so "checked by" cannot outlive the check)

Exit codes (the convention in RELEASE_PATTERN.md):
  0  every field has a complete row
  1  at least one finding
  2  fatal: the registry or the document is missing or malformed, or the document has no per-field table

Usage:
    python3 tools/check_provenance.py
    python3 tools/check_provenance.py --json
    python3 tools/check_provenance.py --root /path/to/checkout
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_REL = "iso4217.json"
DOC_REL = "docs/PROVENANCE.md"

EXIT_OK, EXIT_FINDING, EXIT_FATAL = 0, 1, 2

COLUMNS = ["Field", "Where", "Source", "Refresh trigger", "Checked by"]
HEADING = re.compile(r"(?m)^##\s+(?:\d+\.\s+)?Per-field provenance\s*$")
PATHLIKE = re.compile(r"[/]|\.(?:py|sh|json|md|yml|yaml)$")
EMPTY = {"", "todo", "tbd", "?", "-", "n/a"}


class Fatal(Exception):
    pass


def data_fields(registry: dict) -> dict[str, set[str]]:
    """Field name -> the kinds of object it appears in."""
    found: dict[str, set[str]] = {}

    def add(kind: str, obj: object) -> None:
        if isinstance(obj, dict):
            for key in obj:
                found.setdefault(key, set()).add(kind)

    add("meta", registry.get("meta"))
    add("source", registry.get("source"))
    currencies = registry.get("currencies") or {}
    for status in ("active", "withdrawn"):
        for entry in currencies.get(status) or []:
            add(status, entry)
            if isinstance(entry, dict):
                for country in entry.get("countries") or []:
                    add("countries[]", country)
    for section in (registry.get("non_iso") or {}).values():
        for entry in section or []:
            add("non_iso", entry)
    return found


def parse_table(doc: str) -> list[dict[str, str]]:
    m = HEADING.search(doc)
    if not m:
        raise Fatal(f"{DOC_REL} has no 'Per-field provenance' section")
    rest = doc[m.end():]
    nxt = re.search(r"(?m)^##\s", rest)
    section = rest[:nxt.start()] if nxt else rest
    rows: list[dict[str, str]] = []
    header_seen = False
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header_seen:
            if [c.strip("` ") for c in cells] != COLUMNS:
                raise Fatal(f"the per-field table header is {cells}, expected {COLUMNS}")
            header_seen = True
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        if len(cells) != len(COLUMNS):
            raise Fatal(f"a per-field row has {len(cells)} cells, expected {len(COLUMNS)}: {line[:80]}")
        rows.append(dict(zip(COLUMNS, cells)))
    if not header_seen:
        raise Fatal(f"the 'Per-field provenance' section of {DOC_REL} has no table")
    return rows


def _name(cell: str) -> str:
    return cell.strip().strip("`").strip()


def findings(registry: dict, doc: str, root: Path) -> list[str]:
    fields = data_fields(registry)
    rows = parse_table(doc)
    out: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        name = _name(row["Field"])
        seen[name] = seen.get(name, 0) + 1
    for name in sorted(fields):
        if name not in seen:
            out.append(f"field `{name}` ({', '.join(sorted(fields[name]))}) has no row in the per-field table")
    for name in sorted(seen):
        if name not in fields:
            out.append(f"the table has a row for `{name}`, which is not a field of {REGISTRY_REL}")
        if seen[name] > 1:
            out.append(f"the table has {seen[name]} rows for `{name}`")
    for row in rows:
        name = _name(row["Field"])
        for col in COLUMNS[1:]:
            if row[col].strip().lower() in EMPTY:
                out.append(f"`{name}`: the {col!r} cell is empty")
        checked = row["Checked by"]
        spans = re.findall(r"`([^`]+)`", checked)
        paths = [s.split()[0] for s in spans if PATHLIKE.search(s.split()[0])]
        if not paths and "none" not in checked.lower():
            out.append(f"`{name}`: 'Checked by' names no file and does not say `none`")
        for rel in paths:
            if not (root / rel).exists():
                out.append(f"`{name}`: 'Checked by' names {rel}, which does not exist")
    return out


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check that PROVENANCE.md names every field of iso4217.json.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", help="repository root (default: this checkout)")
    args = ap.parse_args(argv)
    base = Path(args.root).resolve() if args.root else (root or PROJECT_ROOT)
    try:
        try:
            registry = json.loads((base / REGISTRY_REL).read_text(encoding="utf-8"))
            doc = (base / DOC_REL).read_text(encoding="utf-8")
        except OSError as exc:
            raise Fatal(f"cannot read {exc.filename}: {exc.strerror}") from exc
        except ValueError as exc:
            raise Fatal(f"{REGISTRY_REL} is not valid JSON: {exc}") from exc
        if not isinstance(registry, dict):
            raise Fatal(f"{REGISTRY_REL} is not a JSON object")
        fields = data_fields(registry)
        problems = findings(registry, doc, base)
    except Fatal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FATAL
    if args.json:
        print(json.dumps({"root": str(base), "fields": len(fields), "findings": problems}, indent=2))
    elif problems:
        for p in problems:
            print(f"FINDING: {p}")
        print(f"\n{len(problems)} finding(s) in {base / DOC_REL}", file=sys.stderr)
    else:
        print(f"OK: {len(fields)} fields in {REGISTRY_REL}, each with a complete row in {DOC_REL} (under {base})")
    return EXIT_FINDING if problems else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
