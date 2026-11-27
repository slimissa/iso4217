#!/usr/bin/env python3
"""
scripts/workflow_triggers.py -- which GitHub Actions workflows does a push to main run?

scripts/release.sh polls CI for the release commit before it tags (invariant 7). It must poll every workflow a push runs,
and only those: a push-triggered workflow left out of POLLED_WORKFLOWS could fail after the tag, and a workflow with no push
trigger never gets a run for the release commit, so polling it can only time out. Until v1.9.6 `check_workflows_covered`
guessed from the file name (any name starting with monitor, fetch, refresh, update or schedule was exempt), so a
push-triggered `update-docs.yml` went unpolled (the third audit pass, open item 6). The trigger decides now: a workflow is
polled if and only if its `on:` key has a `push` trigger.

Only the `on:` key is read, and only the forms GitHub accepts for it:

    on: push                          on: [push, pull_request]         on: {push: {branches: [main]}}
    on:                               on:
      push:                             - push
        branches: [main]                - workflow_dispatch

The key may be written `on`, `"on"` or `'on'`. A YAML 1.1 parser (PyYAML's safe_load, for one) reads an unquoted `on` as the
boolean True, so a lookup of "on" finds nothing and every workflow looks trigger-less, which is the failure that exempts
everything. This reader is not a YAML 1.1 parser: `on` is the key. It needs nothing outside the standard library
(requirements-ci.txt has no YAML package).

Anything it cannot read for certain (no `on:` key, two of them, an anchor, an alias, a tag, an unbalanced flow collection) is
an error, never a guess: the release stops rather than polling the wrong set.

Usage:
    python3 scripts/workflow_triggers.py --polled [DIR]    # one file name per line: the workflows to poll
    python3 scripts/workflow_triggers.py --explain [DIR]   # every workflow: polled or exempt, and why
    DIR defaults to .github/workflows

Exit codes:
    0  every workflow file was read
    2  a workflow file could not be read for certain (each is named), DIR does not exist, or a usage error (argparse)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_UNREADABLE = 0, 2

_ON_KEY = re.compile(r"""^(?:on|"on"|'on')[ \t]*:(?:[ \t]+(.*))?$""")
_TOP_KEY = re.compile(r"""^(?:[A-Za-z_][\w-]*|"[^"]*"|'[^']*')[ \t]*:""")


class Unreadable(Exception):
    """The `on:` key is not in a form this reader can be certain about."""


def _strip_comment(line: str) -> str:
    """Drop a trailing `# comment` that is outside quotes (YAML: `#` starts a comment after whitespace or at the start)."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _check_plain(token: str) -> str:
    """A trigger name, or Unreadable for YAML features this reader does not follow."""
    t = token.strip()
    if not t:
        raise Unreadable("an empty trigger name")
    if t[0] in "&*!|>%@`":
        raise Unreadable(f"unsupported YAML in the on: key ({t[:30]!r}): anchors, aliases, tags and block scalars are not read")
    return _unquote(t)


def _split_top(body: str) -> list[str]:
    """Split the inside of a flow collection on the commas at its own depth."""
    parts, depth, quote, cur = [], 0, None, []
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if quote or depth:
        raise Unreadable("an unbalanced flow collection in the on: key")
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _flow(value: str) -> list[str]:
    """Trigger names from `[a, b]` or `{a: ..., b: ...}`."""
    opener, closer = value[0], {"[": "]", "{": "}"}[value[0]]
    if not value.endswith(closer):
        raise Unreadable(f"the flow collection in the on: key does not end with {closer!r}")
    items = _split_top(value[1:-1])
    if opener == "[":
        return [_check_plain(i) for i in items]
    names = []
    for item in items:
        key = _split_key(item)
        names.append(_check_plain(key))
    return names


def _split_key(item: str) -> str:
    """The key of `key: value` (or of a bare `key`) in a flow mapping, honouring quotes."""
    quote = None
    for i, ch in enumerate(item):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ":" and (i + 1 == len(item) or item[i + 1] in " \t"):
            return item[:i]
    return item


def triggers(text: str) -> list[str]:
    """The trigger names in a workflow's top-level `on:` key, in the order written."""
    lines = [_strip_comment(raw) for raw in text.splitlines()]
    found = [i for i, line in enumerate(lines) if _ON_KEY.match(line)]
    if not found:
        raise Unreadable("no top-level on: key")
    if len(found) > 1:
        raise Unreadable(f"{len(found)} top-level on: keys (lines {', '.join(str(i + 1) for i in found)})")
    at = found[0]
    inline = (_ON_KEY.match(lines[at]).group(1) or "").strip()

    if inline:
        if inline[0] in "[{":
            # A flow collection may continue on the following, more indented lines.
            value, j = inline, at + 1
            while _depth_open(value) and j < len(lines):
                if lines[j].strip():
                    if not lines[j][:1].isspace():
                        break
                    value += " " + lines[j].strip()
                j += 1
            return _flow(value)
        return [_check_plain(inline)]

    # Block form: the children are the following lines indented more than column 0, up to the next top-level line.
    children = []
    for line in lines[at + 1:]:
        if not line.strip() or line.strip() == "---":
            continue
        if not line[:1].isspace():
            break
        children.append(line)
    if not children:
        raise Unreadable("an empty on: key")
    indent = min(len(c) - len(c.lstrip()) for c in children)
    names: list[str] = []
    for c in children:
        if len(c) - len(c.lstrip()) != indent:
            continue                                  # deeper: a trigger's own settings
        item = c.strip()
        if item.startswith("- ") or item == "-":
            names.append(_check_plain(item[1:]))
        else:
            key = _split_key(item)
            if key == item and not item.endswith(":"):
                raise Unreadable(f"a line under on: that is neither 'name:' nor '- name': {item[:40]!r}")
            names.append(_check_plain(key))
    return names


def _depth_open(value: str) -> bool:
    depth, quote = 0, None
    for ch in value:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    return depth > 0


def verdict(path: Path) -> tuple[bool, str]:
    """(polled, reason). Raises Unreadable."""
    names = triggers(path.read_text(encoding="utf-8"))
    listed = ", ".join(names)
    if "push" in names:
        return True, f"has a push trigger (on: {listed})"
    return False, f"no push trigger (on: {listed})"


def workflow_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="list the workflows a push runs (the ones release.sh must poll)")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--polled", action="store_true", help="print the file name of every push-triggered workflow")
    mode.add_argument("--explain", action="store_true", help="print every workflow with its verdict and the reason")
    p.add_argument("dir", nargs="?", default=".github/workflows")
    args = p.parse_args(argv)

    folder = Path(args.dir)
    if not folder.is_dir():
        print(f"FATAL: {folder} is not a directory", file=sys.stderr)
        return EXIT_UNREADABLE
    errors, rows = [], []
    for path in workflow_files(folder):
        try:
            polled, reason = verdict(path)
        except (Unreadable, UnicodeDecodeError, OSError) as e:
            errors.append(f"{path.name}: cannot read its triggers for certain: {e}")
            continue
        rows.append((path.name, polled, reason))
    if errors:
        for e in errors:
            print(f"UNREADABLE: {e}", file=sys.stderr)
        return EXIT_UNREADABLE
    for name, polled, reason in rows:
        if args.polled:
            if polled:
                print(name)
        else:
            print(f"{name}: {'polled' if polled else 'exempt'} ({reason})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
