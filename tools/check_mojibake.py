#!/usr/bin/env python3
"""
Mojibake detector for text files in the repository.

Mojibake is UTF-8 bytes reinterpreted as Latin-1/Windows-1252 and re-saved
as UTF-8. The three telltale byte prefixes are what you get when a UTF-8
em-dash, checkmark, or box-drawing character has been round-tripped
through a legacy code page:

    \xe2\x80\x9a   from — (em dash)
    \xc3\xa2\xc2\x88   from ✅ (check mark)
    \xc3\xa2\xc2\x80   from ├ ─ │ └ ┐ ┘ (box drawing)

Any hit is a real bug: the file is valid UTF-8, but a human reading it
sees garbage and downstream tools (grep, sed, diff) silently fail to
match intended strings. The fix is to re-export the file from a source
that was never corrupted.

Usage:
    python3 tools/check_mojibake.py
    python3 tools/check_mojibake.py --verbose
    python3 tools/check_mojibake.py --json
    python3 tools/check_mojibake.py --path README.md
    python3 tools/check_mojibake.py --path docs/

Exit codes:
    0 — no mojibake found
    1 — at least one file contains mojibake
    2 — fatal (path does not exist, no files matched)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_FOUND = 1
EXIT_FATAL = 2

SCAN_SUFFIXES = {
    ".md", ".txt",
    ".json", ".jsonl",
    ".py", ".sh",
    ".js", ".ts",
    ".rs", ".go",
    ".toml", ".yaml", ".yml",
    ".csv", ".tsv",
    ".cfg", ".ini",
}

SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "target", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".venv", "venv", "env", ".tox",
    ".idea", ".vscode",
}

MOJIBAKE_PATTERNS: tuple[bytes, ...] = (
    b"\xe2\x80\x9a",
    b"\xc3\xa2\xc2\x88",
    b"\xc3\xa2\xc2\x80",
)

CONTEXT_BYTES = 40


def iter_files(root: Path) -> list[Path]:
    """Yield every scannable file under `root`."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[int, bytes]]:
    """
    Return a list of (byte_offset, context_bytes) for every mojibake hit.

    The file is read as raw bytes; a hit does not require the file to be
    valid UTF-8, and context is decoded with errors='replace' so a
    preview is always printable.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return []

    hits: list[tuple[int, bytes]] = []
    for pattern in MOJIBAKE_PATTERNS:
        start = 0
        while True:
            idx = data.find(pattern, start)
            if idx == -1:
                break
            ctx_start = max(0, idx - CONTEXT_BYTES // 2)
            ctx_end = min(len(data), idx + len(pattern) + CONTEXT_BYTES // 2)
            hits.append((idx, data[ctx_start:ctx_end]))
            start = idx + len(pattern)

    hits.sort(key=lambda t: t[0])
    return hits


def report_text(
    root: Path,
    hits_by_file: dict[Path, list[tuple[int, bytes]]],
    files_scanned: int,
    verbose: bool,
) -> str:
    lines: list[str] = []
    rule = "=" * 78

    lines.append(rule)
    lines.append("  Mojibake Check - UTF-8 / Latin-1 round-trip detector")
    lines.append(rule)
    lines.append(f"  Root:  {root}")
    lines.append(f"  Files scanned: {files_scanned}")
    lines.append(rule)
    lines.append("")

    if not hits_by_file:
        lines.append(f"  OK: {files_scanned} file(s) scanned, no mojibake found.")
        lines.append(rule)
        return "\n".join(lines)

    total = sum(len(h) for h in hits_by_file.values())
    for path in sorted(hits_by_file):
        hits = hits_by_file[path]
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        lines.append(f"  {rel}: {len(hits)} hit(s)")
        for offset, ctx in hits[:5]:
            preview = ctx.decode("utf-8", errors="replace")
            lines.append(f"      byte {offset}: {preview!r}")
        if len(hits) > 5:
            lines.append(f"      ... and {len(hits) - 5} more")
        lines.append("")

    lines.append(rule)
    lines.append(
        f"  FAIL: {total} signature(s) across {len(hits_by_file)} file(s)"
    )
    lines.append(rule)
    return "\n".join(lines)


def report_json(
    root: Path,
    hits_by_file: dict[Path, list[tuple[int, bytes]]],
    files_scanned: int,
) -> str:
    payload = {
        "root": str(root),
        "files_scanned": files_scanned,
        "files_with_hits": len(hits_by_file),
        "total_hits": sum(len(h) for h in hits_by_file.values()),
        "hits": [
            {
                "file": str(path.relative_to(root))
                if path.is_relative_to(root)
                else str(path),
                "offset": offset,
                "context": ctx.decode("utf-8", errors="replace"),
            }
            for path, hits in sorted(hits_by_file.items())
            for offset, ctx in hits
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_mojibake.py",
        description="Detect UTF-8 / Latin-1 mojibake in repository files.",
        epilog=(
            "Exit codes:\n"
            "  0  clean\n"
            "  1  mojibake found\n"
            "  2  fatal (path missing, no files matched)\n"
        ),
    )
    parser.add_argument(
        "--path", type=Path, default=None,
        help="Scan only this file or directory (default: repo root)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print every scanned file, not just hits",
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Emit machine-readable JSON",
    )
    args = parser.parse_args(argv)

    if args.path is not None:
        if not args.path.exists():
            print(f"FATAL: path does not exist: {args.path}", file=sys.stderr)
            return EXIT_FATAL
        if args.path.is_file():
            root = args.path.parent
            files = [args.path]
        else:
            root = args.path
            files = iter_files(root)
    else:
        root = PROJECT_ROOT
        files = iter_files(root)

    if not files:
        print("FATAL: no files matched the scan suffixes.", file=sys.stderr)
        return EXIT_FATAL

    hits_by_file: dict[Path, list[tuple[int, bytes]]] = {}
    for path in sorted(files):
        hits = scan_file(path)
        if hits:
            hits_by_file[path] = hits
        elif args.verbose:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            print(f"  ok  {rel}")

    if args.json:
        print(report_json(root, hits_by_file, len(files)))
    else:
        print(report_text(root, hits_by_file, len(files), args.verbose))

    return EXIT_FOUND if hits_by_file else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())