#!/usr/bin/env python3
"""
tools/check_rules_refs.py

Keep this repository's side of the release-rule numbering true (v1.9.5, ADR 0016; audit findings P5-10 and EC).

`docs/rules.md` is a numbering authority: one row per rule with an ID (E1..E8 for the essential eight, H1..H10 with H6b, H6c and
H6d for operator hygiene), the section and heading it indexes in RELEASE_PATTERN.md, and its aliases. It never restates a rule's
text. This tool fails when

  a. an ID is duplicated or malformed;
  b. a row's heading is not found under its section in RELEASE_PATTERN.md, or a rule heading in RELEASE_PATTERN.md has no row
     (the table and the document index each other);
  c. a qualified citation in a current Markdown document names a rule that does not exist: `invariant N`, `hygiene rule N`,
     `operator-hygiene rule N`, an alias such as `R10`, or a repository-prefixed ID (`4217/H7`; the prefixes 3166, 10383 and
     ec are accepted by shape only: this tool never reads another repository);
  d. a bare "rule N" citation appears in a file that is not in docs/rules-legacy-bare.json, or more often than recorded there.
     An entry that is higher than the file's count, or whose file is gone, is stale and also fails ("every entry is current").

Not scanned: CHANGELOG.md and docs/v*-verification.md (history cites rules as they were numbered), docs/rules.md itself, and
everything that is not Markdown. Cross-repository verification and any --strict mode are the fourth audit's work.

Exit codes (the convention in RELEASE_PATTERN.md):
  0  the table, the document and every checked citation agree
  1  at least one problem
  2  usage error, or docs/rules.md or RELEASE_PATTERN.md is missing, or a malformed docs/rules-legacy-bare.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK, EXIT_PROBLEM, EXIT_USAGE = 0, 1, 2

SECTIONS = {"E": "The essential eight", "H": "Operator hygiene"}
ID_RE = re.compile(r"^[EH][0-9]+[a-d]?$")
HEADING_NUMBER = re.compile(r"^(\d+[a-d]?)\.\s")
HISTORICAL = re.compile(r"^(CHANGELOG\.md|docs/v[0-9][0-9.]*-verification\.md)$")
SKIP_DIRS = {".git", "node_modules", "target", "__pycache__", ".pytest_cache", ".venv"}
SELF = "docs/rules.md"

# Files that cite a rule by a bare "rule N" today, and how often, are recorded in docs/rules-legacy-bare.json ({path: count}) of
# the root being checked; an absent file means none. Frozen: a new bare citation elsewhere fails, and so does a count that
# drifts either way. Shrink it by qualifying the citations, never by growing it. `--print-legacy` prints the current counts.
LEGACY_FILE = "docs/rules-legacy-bare.json"

QUALIFIED = [
    (re.compile(r"\binvariant (\d+)\b", re.I), lambda g: "E" + g, "invariant"),
    (re.compile(r"\b(?:operator-)?hygiene rules? (\d+[a-d]?)\b", re.I), lambda g: "H" + g, "hygiene rule"),
]
PREFIXED = re.compile(r"\b(4217|3166|10383|ec)/([EH][0-9]+[a-d]?)\b")
ALIAS_TOKEN = re.compile(r"\bR(\d{1,2}[a-d]?)\b")
BARE = re.compile(r"\b[Rr]ules? (\d+[a-d]?)\b")
QUALIFIERS = ("hygiene ", "operator-hygiene ", "operator hygiene ", "essential ", "invariant ")


def headings(text: str) -> dict[str, list[str]]:
    """{section title: [heading text after '### ']} for the two rule sections only."""
    out: dict[str, list[str]] = {t: [] for t in SECTIONS.values()}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            current = title if title in out else None
        elif line.startswith("### ") and current:
            h = line[4:].strip()
            if HEADING_NUMBER.match(h):
                out[current].append(h)
    return out


def parse_table(text: str) -> list[dict]:
    rows: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\|\s*ID\s*\|\s*Meaning\s*\|", line):
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if len(cells) >= 5:
                    rows.append({"id": cells[0], "meaning": cells[1], "section": cells[2], "heading": cells[3], "aliases": cells[4]})
            break
    return rows


def tracked_markdown(root: Path) -> list[str]:
    if (root / ".git").exists():
        out = subprocess.run(["git", "ls-files", "*.md"], cwd=root, capture_output=True, text=True)
        if out.returncode == 0:
            return [f for f in out.stdout.splitlines() if (root / f).is_file()]
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.md")
                  if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS))


def load_legacy(root: Path) -> dict[str, int]:
    f = root / LEGACY_FILE
    if not f.is_file():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in data.items()):
        raise ValueError(f"{LEGACY_FILE}: expected an object of {{path: positive count}}")
    return data


def run(root: Path, legacy: dict[str, int] | None = None) -> tuple[list[str], str]:
    legacy = load_legacy(root) if legacy is None else legacy
    errors: list[str] = []
    rules_text = (root / SELF).read_text(encoding="utf-8")
    pattern_text = (root / "RELEASE_PATTERN.md").read_text(encoding="utf-8")
    rows = parse_table(rules_text)
    doc_headings = headings(pattern_text)

    seen: set[str] = set()
    ids: set[str] = set()
    aliases: dict[str, str] = {}
    indexed: dict[str, set[str]] = {t: set() for t in SECTIONS.values()}
    for r in rows:
        rid = r["id"]
        if not ID_RE.match(rid):
            errors.append(f"{SELF}: malformed ID {rid} (expected E or H followed by a number and an optional a to d)")
            continue
        if rid in seen:
            errors.append(f"{SELF}: duplicate ID {rid}")
            continue
        seen.add(rid)
        ids.add(rid)
        title = SECTIONS[rid[0]]
        if r["section"] != title or r["heading"] not in doc_headings[title]:
            errors.append(f"{SELF}: {rid}: heading '{r['heading']}' not found under '{title}' in RELEASE_PATTERN.md")
        else:
            indexed[title].add(r["heading"])
        for a in re.findall(r"\bR\d{1,2}[a-d]?\b", r["aliases"]):
            aliases[a] = rid
    for title, hs in doc_headings.items():
        for h in hs:
            if h not in indexed[title]:
                errors.append(f"RELEASE_PATTERN.md: heading '{h}' under '{title}' has no row in {SELF}")

    checked = 0
    bare_counts: dict[str, int] = {}
    for rel in tracked_markdown(root):
        if rel == SELF or HISTORICAL.match(rel):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for pattern, to_id, word in QUALIFIED:
                for m in pattern.finditer(line):
                    checked += 1
                    if to_id(m.group(1)) not in ids:
                        errors.append(f"{rel}:{number}: {m.group(0)} does not resolve (no {to_id(m.group(1))} in {SELF})")
            for m in PREFIXED.finditer(line):
                checked += 1
                if m.group(1) == "4217" and m.group(2) not in ids:
                    errors.append(f"{rel}:{number}: {m.group(0)} does not resolve (no {m.group(2)} in {SELF})")
            for m in ALIAS_TOKEN.finditer(line):
                if "R" + m.group(1) in aliases:
                    checked += 1
            for m in BARE.finditer(line):
                before = line[: m.start()].lower()
                if any(before.endswith(q) for q in QUALIFIERS):
                    continue
                checked += 1
                bare_counts[rel] = bare_counts.get(rel, 0) + 1
                if rel not in legacy:
                    errors.append(f"{rel}:{number}: bare rule citation '{m.group(0)}' (qualify it: invariant N, hygiene rule N, "
                                  f"or <repo>/<ID>); bare citations are frozen in {LEGACY_FILE}")
    for rel, count in sorted(bare_counts.items()):
        if rel in legacy and count > legacy[rel]:
            errors.append(f"{rel}: {count} bare rule citation(s), {legacy[rel]} recorded in {LEGACY_FILE}")
    for rel, recorded in sorted(legacy.items()):
        have = bare_counts.get(rel, 0)
        if have < recorded:
            reason = "does not exist or has no bare citation" if have == 0 else f"has {have}, {recorded} recorded"
            errors.append(f"STALE: {rel} in {LEGACY_FILE} {reason}; update the entry")
    summary = f"OK: {len(ids)} rule(s) in {SELF} match RELEASE_PATTERN.md; {checked} citation(s) checked"
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="keep docs/rules.md and the citations of release rules true")
    ap.add_argument("root", nargs="?", default=".", help="repository root")
    ap.add_argument("--print-legacy", action="store_true", help="print the bare-citation counts per file and exit")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    for need in (SELF, "RELEASE_PATTERN.md"):
        if not (root / need).is_file():
            print(f"FATAL: {root / need} not found", file=sys.stderr)
            return EXIT_USAGE
    if args.print_legacy:
        _errors, _ = run(root, legacy={})
        counts: dict[str, int] = {}
        for e in _errors:
            m = re.match(r"^(.+?):\d+: bare rule citation", e)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        for rel, n in sorted(counts.items()):
            print(f'    "{rel}": {n},')
        return EXIT_OK
    try:
        errors, summary = run(root)
    except ValueError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return EXIT_USAGE
    if errors:
        for e in errors:
            print(e if e.startswith(("STALE", "RELEASE_PATTERN.md", SELF)) else f"DIRTY: {e}")
        print(f"\n{len(errors)} problem(s).", file=sys.stderr)
        return EXIT_PROBLEM
    print(summary)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
