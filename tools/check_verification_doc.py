#!/usr/bin/env python3
"""
tools/check_verification_doc.py

Refuse to accept a verification doc that contains a placeholder.

The v1.7.11 release shipped three commits named "Fill CI proof" that
did not fill the proof, because a template wrote the description of
the content to insert instead of the content. This check makes that
class of mistake impossible to land on main: it fails on TODO, on
angle-bracket placeholders like <the real line>, and on documents
shorter than the minimum line count.

Exit codes:
  0  every doc checked is clean
  1  at least one doc contains a placeholder
  3  no docs found (probably the wrong directory)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_DIRTY, EXIT_FATAL = 0, 1, 3

MIN_LINES = 80

# Patterns that only appear in a doc that was not finished.
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\bTODO\b"), "TODO marker"),
    (re.compile(r"\bFIXME\b"), "FIXME marker"),
    (re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE), "PLACEHOLDER marker"),
    (re.compile(r"<the real line"), "<the real line>"),
    (re.compile(r"<the proof line"), "<the proof line>"),
    (re.compile(r"<paste\s+\w", re.IGNORECASE), "<paste ...>"),
    (re.compile(r"<insert\s+\w", re.IGNORECASE), "<insert ...>"),
    (re.compile(r"<replace\s+\w", re.IGNORECASE), "<replace ...>"),
    (re.compile(r"<version>"), "<version>"),
    (re.compile(r"<X\.Y\.Z>"), "<X.Y.Z>"),
    (re.compile(r"<target>"), "<target>"),
]


def _version_key(path: Path) -> tuple[int, ...]:
    m = re.match(r"v(\d+(?:\.\d+)*)", path.name)
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def check_doc(path: Path) -> list[str]:
    if not path.is_file():
        return [f"{path}: not a file"]

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors: list[str] = []

    if len(lines) < MIN_LINES:
        errors.append(
            f"{path}: only {len(lines)} lines; a real verification doc is "
            f"at least {MIN_LINES}. This is probably the release script's stub."
        )

    for pattern, label in PLACEHOLDER_PATTERNS:
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:80]
            errors.append(f"{path}:{line_no}: {label}: {snippet}")

    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="check verification docs for placeholders")
    p.add_argument("root", nargs="?", default=".", help="repository root")
    p.add_argument(
        "--all",
        action="store_true",
        help="check every docs/v*-verification.md (default: only the latest)",
    )
    args = p.parse_args(argv)

    root = Path(args.root).resolve()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        print(f"FATAL: {docs_dir} not found", file=sys.stderr)
        return EXIT_FATAL

    docs = sorted(docs_dir.glob("v*-verification.md"), key=_version_key)
    if not docs:
        print(f"FATAL: no docs/v*-verification.md under {root}", file=sys.stderr)
        return EXIT_FATAL

    if not args.all:
        docs = docs[-1:]

    errors: list[str] = []
    for doc in docs:
        errors.extend(check_doc(doc))

    if errors:
        for e in errors:
            print(f"DIRTY: {e}")
        print(f"\n{len(errors)} placeholder(s) in {len(docs)} doc(s).", file=sys.stderr)
        return EXIT_DIRTY

    print(f"OK: {len(docs)} verification doc(s) clean")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
