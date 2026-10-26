#!/usr/bin/env python3
"""
Check the line-ending policy (ADR 0012, v1.9.2, audit finding P5-06).

Every text file in the repository is LF. This tool fails when:

  * a text file contains a CR byte (a CRLF checkout, or a CRLF file that has
    not been through `git add` yet, which is why the gate cannot rely on git's
    normalization), or
  * .gitattributes does not carry the policy: the default rule `* text=auto
    eol=lf`, an `eol=lf` rule for each of *.sh, *.py, *.json, *.sql, and
    `*.parquet binary`.

In a git work tree it scans tracked files plus untracked files that are not
ignored; elsewhere (an exported archive, a test copy) it walks the directory
and skips build and cache directories. Binary files (a NUL byte in the first
8 KiB, or a known binary extension) are not scanned.

Exit codes:
    0  no CR byte in any text file, and .gitattributes carries the policy
    1  one or more text files contain a CR, or .gitattributes is missing a rule
    2  fatal (.gitattributes missing, root is not a directory)

Usage:
    python3 tools/check_line_endings.py
    python3 tools/check_line_endings.py --root /path/to/tree
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_FATAL = 2

BINARY_SUFFIXES = {".parquet", ".png", ".ico", ".jpg", ".jpeg", ".gif", ".zip", ".whl", ".gz", ".pyc"}
SKIP_DIRS = {".git", ".venv", "venv", "env", ".tox", ".nox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
             "node_modules", "target", "__pycache__", "dist", "build", ".eggs", "site-packages"}

# Each entry: the exact whitespace-normalised .gitattributes line that must be present.
REQUIRED_RULES = (
    "* text=auto eol=lf",
    "*.sh text eol=lf",
    "*.py text eol=lf",
    "*.json text eol=lf",
    "*.sql text eol=lf",
    "*.parquet binary",
)


def candidate_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        try:
            done = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=root, capture_output=True, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            done = None
        if done is not None and done.returncode == 0:
            return [root / n for n in done.stdout.decode("utf-8").split("\0") if n]
    found = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS):
            found.append(p)
    return found


def files_with_cr(root: Path) -> list[tuple[str, int]]:
    hits = []
    for p in candidate_files(root):
        if p.suffix.lower() in BINARY_SUFFIXES or not p.is_file():
            continue
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue
        n = data.count(b"\r")
        if n:
            hits.append((p.relative_to(root).as_posix(), n))
    return hits


def missing_rules(attributes: str) -> list[str]:
    present = {" ".join(line.split()) for line in attributes.splitlines() if not line.lstrip().startswith("#")}
    return [rule for rule in REQUIRED_RULES if rule not in present]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="check_line_endings.py", description="Enforce the LF policy (ADR 0012).")
    ap.add_argument("--root", type=Path, default=PROJECT_ROOT, help="tree to check (default: the repository)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"FATAL: {root} is not a directory", file=sys.stderr)
        return EXIT_FATAL
    attrs = root / ".gitattributes"
    if not attrs.is_file():
        print(f"FATAL: .gitattributes not found at {attrs}", file=sys.stderr)
        return EXIT_FATAL

    problems = 0
    for rule in missing_rules(attrs.read_text(encoding="utf-8")):
        problems += 1
        print(f"  \u2717 .gitattributes is missing the rule: {rule}", file=sys.stderr)
    for rel, n in files_with_cr(root):
        problems += 1
        print(f"  \u2717 {rel}: {n} CR byte(s); the policy is LF only (ADR 0012)", file=sys.stderr)

    if problems:
        print(f"check_line_endings: {problems} problem(s)", file=sys.stderr)
        return EXIT_FINDING
    print("check_line_endings: OK - no CR in any text file; .gitattributes carries the policy")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
