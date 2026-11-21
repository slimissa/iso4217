#!/usr/bin/env python3
"""
tools/check_doc_paths.py

Refuse a document that cites a `docs/...` file that does not exist.

The CHANGELOG entries for 1.9.1 and 1.9.2 linked to `docs/audits/third-pass.md`, a file that was named something else; two dead
links that no check noticed for two releases (v1.9.5, ADR 0017, D6). This check makes "every docs/ path a document cites
exists" a gate step.

What is scanned: tracked text files (`git ls-files`; every file under the root when it is not a git checkout), except
  - tests/ (tests build fixture trees and cite paths on purpose; a wrong path there fails its own test),
  - *.json (release_claims.json is checked by check_release_claims.py; the data files cite nothing),
  - binary files.
What counts as a citation: `docs/<path>.<md|txt|yml|yaml>`, optionally written `./docs/...`, not preceded by another path
character. Wildcards (`docs/v*-verification.md`) and placeholders (`docs/<name>.md`) are not citations. A line containing
`doc-path: example` is skipped (deliberate examples).

History cites files as they were: CHANGELOG.md and docs/v*-verification.md may name a path listed in RENAMED (an old name); a
current document may not.

Exit codes (the convention in RELEASE_PATTERN.md):
  0  every cited path exists
  1  at least one cited path does not exist
  2  usage error (the root is not a directory)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK, EXIT_DEAD, EXIT_USAGE = 0, 1, 2

# Old name -> new name. Add a line when a documented file moves; remove it never (history keeps citing the old name).
RENAMED = {
    "docs/audits/fifth-pass.md": "docs/audits/third-pass.md",  # doc-path: example
}

HISTORICAL = re.compile(r"^(CHANGELOG\.md|docs/v[0-9][0-9.]*-verification\.md)$")
SKIP_DIRS = {".git", "node_modules", "target", "__pycache__", ".pytest_cache", ".venv"}
SKIP_SUFFIXES = {".json", ".parquet", ".zip", ".png", ".jpg", ".gif", ".pdf", ".sql", ".csv", ".tsv", ".lock", ".sum", ".woff", ".woff2"}
MAX_BYTES = 2_000_000
EXAMPLE_MARKER = "doc-path: example"

CITATION = re.compile(r"(?<![\w/.\-])(?:\./)?(docs/[\w./-]*\w\.(?:md|txt|yml|yaml))\b")


def tracked_files(root: Path) -> list[str]:
    if (root / ".git").exists():
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
        if out.returncode == 0:
            return [f for f in out.stdout.splitlines() if (root / f).is_file()]
    found = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
            found.append(p.relative_to(root).as_posix())
    return found


def scan(root: Path) -> tuple[list[str], int, int]:
    """Return (problems, citations checked, files with a citation)."""
    problems: list[str] = []
    checked = 0
    files_with = 0
    for rel in tracked_files(root):
        p = root / rel
        if rel.startswith("tests/") or p.suffix in SKIP_SUFFIXES:
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        historical = bool(HISTORICAL.match(rel))
        seen_here = False
        for number, line in enumerate(text.splitlines(), 1):
            if EXAMPLE_MARKER in line:
                continue
            for m in CITATION.finditer(line):
                cited = m.group(1)
                seen_here = True
                checked += 1
                if (root / cited).is_file():
                    continue
                if historical and cited in RENAMED:
                    continue
                if cited in RENAMED:
                    problems.append(f"{rel}:{number}: {cited} was renamed to {RENAMED[cited]}")
                else:
                    problems.append(f"{rel}:{number}: {cited} does not exist")
        files_with += seen_here
    return problems, checked, files_with


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="check that every docs/ path a document cites exists")
    ap.add_argument("root", nargs="?", default=".", help="repository root")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"FATAL: {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    problems, checked, files_with = scan(root)
    if problems:
        for pr in problems:
            print(f"DEAD: {pr}")
        print(f"\n{len(problems)} dead path(s) cited.", file=sys.stderr)
        return EXIT_DEAD
    print(f"OK: {checked} path(s) cited in {files_with} file(s); all exist")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
