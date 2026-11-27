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

v1.9.5 (audit finding P5-11, ADR 0017):
  - PLACEHOLDER is a marker only in upper case: the prose word is not an unfinished document.
  - The OK line names the artifact it checked and, under --all, what it set aside.
  - --all honours docs/verification-grandfathered.json: {path: reason} for historical records that are genuinely short or
    never completed. An entry is held to "every entry is current": a listed doc that became clean, or whose file is gone, is an
    error, and so is an unlisted doc that is dirty. The latest doc is never grandfathered.
  - Fenced code is tracked exactly (marker character and length; a tilde line does not close a backtick fence) and an
    unterminated fence is an error, so a fence cannot hide the rest of a document.

v1.9.6 (the third audit pass, open item 7): `--quote` is how scripts/release.sh puts a gate step's output into the generated
document. It reads text on stdin and writes it as a fenced block that the text itself cannot close: the lines are the lines
this checker sees (str.splitlines, which also breaks on \r, \f, \x1c-\x1e, \x85, \u2028 and \u2029), and the fence is one
backtick longer than the longest run of backticks anywhere in the text (at least three). A banned word in quoted gate output is
therefore always evidence, never prose, whatever else the output prints. Before v1.9.6 the script only indented lines that
began with a fence in column 0, so a fence line with one to three leading spaces, or behind a \f, closed the block early.

Usage:
  python3 tools/check_verification_doc.py [ROOT]          # the latest docs/v*-verification.md
  python3 tools/check_verification_doc.py --all [ROOT]    # every one, honouring the grandfather list
  ... | python3 tools/check_verification_doc.py --quote   # stdin as a fenced block its content cannot close

Exit codes (the convention in RELEASE_PATTERN.md):
  0  every doc checked is clean (--quote: the block was written)
  1  at least one doc contains a placeholder, or a grandfather entry is stale
  2  usage error, or nothing to check: no docs/ directory or no docs/v*-verification.md
     (probably the wrong directory), or a malformed docs/verification-grandfathered.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_DIRTY, EXIT_FATAL = 0, 1, 2

MIN_LINES = 80
GRANDFATHER_FILE = "docs/verification-grandfathered.json"

# Patterns that only appear in a doc that was not finished.
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\bTODO\b"), "TODO marker"),
    (re.compile(r"\bFIXME\b"), "FIXME marker"),
    (re.compile(r"\bPLACEHOLDER\b"), "PLACEHOLDER marker"),
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


# ---------------------------------------------------------------------------
# Fenced code and inline code are *evidence*, not prose. A TODO inside them is a
# quoted tool output or a claim's wording, not a placeholder. The v1.9.4 doc's
# evidence section quotes `scripts/release.sh does not contain 'TODO'`, which the
# pre-fix scanner reported as a marker. Mask it before scanning, and map a match
# back to its original line number.
# ---------------------------------------------------------------------------

_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _mask_code(text: str) -> tuple[str, int | None]:
    """Return (masked, unclosed_line): `text` with fenced code blocks and inline `code` spans blanked out, preserving line
    structure so line numbers match the original, and the 1-based line where a fence was opened and never closed (else None).

    A fence closes only on a line made of the same character, at least as long as the opener (CommonMark); anything else
    inside it, including a tilde line in a backtick fence, is content."""
    out = []
    fence: tuple[str, int, int] | None = None   # (char, length, opening line)
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        blank = "\n" if line.endswith("\n") else ""
        if fence is None:
            m = _FENCE_OPEN_RE.match(line)
            if m:
                fence = (m.group(1)[0], len(m.group(1)), number)
                out.append(blank)
                continue
            out.append(re.sub(r"`[^`\n]+`", lambda x: " " * len(x.group(0)), line))
        else:
            m = _FENCE_OPEN_RE.match(line)
            closes = bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and line.strip() == m.group(1)
            if closes:
                fence = None
            out.append(blank)
    return "".join(out), (fence[2] if fence else None)


def quote_block(text: str) -> str:
    """`text` as a fenced code block that no line of `text` can close or escape, by this module's own reading.

    The content lines are exactly the lines `check_doc` will see (str.splitlines), rejoined with "\n", so no character that
    Python treats as a line break can start a hidden line. The fence is backticks, one longer than the longest run of
    backticks in the text and at least three: a closing fence must be a line made only of at least that many backticks
    (CommonMark, and `_mask_code`), and no line of the text holds that many."""
    lines = text.splitlines()
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    block = fence + "\n" + "".join(line + "\n" for line in lines) + fence + "\n"
    masked, unclosed = _mask_code(block)
    if unclosed is not None or masked.strip():
        raise AssertionError("quote_block produced a block its own content can escape")  # unreachable by construction
    return block


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

    # Scan prose only: fenced code and inline code are evidence. An unterminated fence is an error, not a hiding place.
    prose, unclosed = _mask_code(text)
    if unclosed is not None:
        errors.append(f"{path}:{unclosed}: unclosed code fence opened at line {unclosed}; the rest of the document is not checked")
    for pattern, label in PLACEHOLDER_PATTERNS:
        for m in pattern.finditer(prose):
            line_no = prose[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:80]
            errors.append(f"{path}:{line_no}: {label}: {snippet}")

    return errors


def _load_grandfathered(root: Path) -> dict[str, str] | None:
    """{relative path: reason}, or None when the file is malformed (already reported)."""
    f = root / GRANDFATHER_FILE
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError("expected an object of {path: reason}")
        for path, reason in data.items():
            if not reason.strip():
                raise ValueError(f"{path} has no reason")
    except (ValueError, OSError) as e:
        print(f"FATAL: {GRANDFATHER_FILE}: {e} (every entry needs a reason)", file=sys.stderr)
        return None
    return data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="check verification docs for placeholders")
    p.add_argument("root", nargs="?", default=".", help="repository root")
    p.add_argument(
        "--all",
        action="store_true",
        help="check every docs/v*-verification.md (default: only the latest); honours " + GRANDFATHER_FILE,
    )
    p.add_argument(
        "--quote",
        action="store_true",
        help="read text on stdin and write it as a fenced block that the text cannot close (used by scripts/release.sh)",
    )
    args = p.parse_args(argv)

    if args.quote:
        if args.all:
            p.error("--quote takes no other option")
        data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        sys.stdout.buffer.write(quote_block(data).encode("utf-8"))
        sys.stdout.flush()
        return EXIT_OK

    root = Path(args.root).resolve()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        print(f"FATAL: {docs_dir} not found", file=sys.stderr)
        return EXIT_FATAL

    docs = sorted(docs_dir.glob("v*-verification.md"), key=_version_key)
    if not docs:
        print(f"FATAL: no docs/v*-verification.md under {root}", file=sys.stderr)
        return EXIT_FATAL

    grandfathered: dict[str, str] = {}
    if args.all:
        loaded = _load_grandfathered(root)
        if loaded is None:
            return EXIT_FATAL
        grandfathered = loaded
    else:
        docs = docs[-1:]

    latest = sorted(docs_dir.glob("v*-verification.md"), key=_version_key)[-1]
    errors: list[str] = []
    set_aside: list[str] = []
    for doc in docs:
        rel = doc.relative_to(root).as_posix()
        found = check_doc(doc)
        if rel in grandfathered and doc != latest:
            if found:
                set_aside.append(rel)
            else:
                errors.append(f"STALE: {rel} is grandfathered but clean; remove it from {GRANDFATHER_FILE}")
        else:
            errors.extend(found)
    for rel in grandfathered:
        if not (root / rel).is_file():
            errors.append(f"{GRANDFATHER_FILE}: {rel} does not exist; remove the entry")

    if errors:
        for e in errors:
            print(f"DIRTY: {e}" if not e.startswith(("STALE", GRANDFATHER_FILE)) else e)
        print(f"\n{len(errors)} problem(s) in {len(docs)} doc(s).", file=sys.stderr)
        return EXIT_DIRTY

    if args.all:
        listed = f": {', '.join(set_aside)}" if set_aside else ""
        print(f"OK: {len(docs)} verification doc(s) clean, {len(set_aside)} grandfathered{listed}")
    else:
        rel = docs[0].relative_to(root).as_posix()
        print(f"OK: {rel} clean ({len(docs[0].read_text(encoding='utf-8').splitlines())} lines)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
