#!/usr/bin/env python3
"""
Bump one version site of the ISO 4217 Currency Registry (ADR 0014, D8).

This replaces the four inline Python heredocs and the two `sed -i` calls that scripts/release.sh used to carry. One site
per call. The script never reads the clock: a date is always passed in (release.sh computes it once, in UTC).

    usage: bump_version.py [--root ROOT] --from OLD --to NEW SITE
    SITE in version | changelog | iso_json_version | iso_json_updated
          | readme_badge | setup_py | package_json | cargo_toml

What OLD and NEW are:
    version, iso_json_version, readme_badge, setup_py, package_json, cargo_toml    versions, X.Y.Z
    iso_json_updated        OLD is a date, or the literal DATE meaning "any YYYY-MM-DD currently there";
                            NEW is a date
    changelog               OLD and NEW are the exact heading lines, e.g.
                            "## [1.0.1] \u2014 Unreleased"  and  "## [1.0.1] \u2014 2026-10-28"

Behavior, the same for every site:
    idempotent      a site already holding NEW is left byte for byte as it is (exit 0, "already at")
    fails loudly    a site holding neither OLD nor NEW, or without its pattern at all, exits 1 and names the site
                    and the file; nothing is written
    read-back       after writing, the site is read again and must hold NEW (exit 1 otherwise)
    format kept     only the one value changes; the rest of the file is byte for byte as it was

Exit codes (RELEASE_PATTERN.md convention):
    0  the site holds NEW (changed, or already)
    1  the site does not hold OLD or NEW, has no pattern, or the read-back failed
    2  usage error, unknown site, or the site's file is missing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_SITE, EXIT_USAGE = 0, 1, 2

SITES = {
    "version": "VERSION",
    "changelog": "CHANGELOG.md",
    "iso_json_version": "iso4217.json",
    "iso_json_updated": "iso4217.json",
    "readme_badge": "README.md",
    "setup_py": "wrappers/python/setup.py",
    "package_json": "wrappers/javascript/package.json",
    "cargo_toml": "wrappers/rust/Cargo.toml",
}
SEMVER = r"\d+\.\d+\.\d+"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SiteError(Exception):
    """The site does not hold what the caller said it would."""


# ---------------------------------------------------------------------------
# Readers: text -> the value currently at the site (SiteError when the pattern is absent)
# Writers: (text, current, new) -> new text, replacing only that value
# ---------------------------------------------------------------------------

def _only(matches: list, what: str):
    if not matches:
        raise SiteError(f"no {what} found")
    if len(matches) > 1:
        raise SiteError(f"{len(matches)} {what} found; expected exactly one")
    return matches[0]


def read_version(text: str) -> str:
    value = text.strip()
    if not re.fullmatch(SEMVER, value):
        raise SiteError(f"VERSION does not hold an X.Y.Z version (found {value[:40]!r})")
    return value


def write_version(text: str, current: str, new: str) -> str:
    return new + "\n"


_BADGE = re.compile(rf"badge/registry-({SEMVER})-orange")


def read_readme_badge(text: str) -> str:
    return _only(_BADGE.findall(text), "registry badge")


def write_readme_badge(text: str, current: str, new: str) -> str:
    return _BADGE.sub(f"badge/registry-{new}-orange", text, count=1)


_SETUP = re.compile(rf"""^(VERSION\s*=\s*)(["'])({SEMVER})(["'])""", re.MULTILINE)


def read_setup_py(text: str) -> str:
    return _only(_SETUP.findall(text), "VERSION assignment")[2]


def write_setup_py(text: str, current: str, new: str) -> str:
    return _SETUP.sub(lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(4)}", text, count=1)


def _cargo_lines(text: str):
    """Yield (index, line, in_package) for every line, section-aware."""
    in_pkg = False
    for i, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_pkg = stripped == "[package]"
        yield i, line, in_pkg


_CARGO_VER = re.compile(rf"""^(version\s*=\s*)(["'])({SEMVER})(["'])""")


def read_cargo_toml(text: str) -> str:
    found = [m.group(3) for _i, line, in_pkg in _cargo_lines(text) if in_pkg and (m := _CARGO_VER.match(line.strip()))]
    return _only(found, "[package] version")


def write_cargo_toml(text: str, current: str, new: str) -> str:
    lines = text.splitlines(keepends=True)
    for i, line, in_pkg in _cargo_lines(text):
        if in_pkg and _CARGO_VER.match(line.strip()):
            ending = line[len(line.rstrip("\r\n")):]
            lines[i] = f'version = "{new}"{ending}'
            break
    return "".join(lines)


def _json_object_span(text: str, key: str | None) -> tuple[int, int]:
    """Span of the object that holds the site: the top-level object (key None) or the object under top-level `key`."""
    start = 0
    if key is not None:
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*\{', text)
        if not m:
            raise SiteError(f'no "{key}" object found')
        start = m.end() - 1
    elif not text.lstrip().startswith("{"):
        raise SiteError("the file is not a JSON object")
    else:
        start = text.index("{")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SiteError("unbalanced braces in the JSON text")


def _json_load(text: str):
    try:
        return json.loads(text)
    except ValueError as e:
        raise SiteError(f"not valid JSON: {e}") from e


def _json_value(text: str, path: tuple[str, ...]) -> str:
    node = _json_load(text)
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise SiteError(f'no "{".".join(path)}" found')
        node = node[key]
    if not isinstance(node, str):
        raise SiteError(f'"{".".join(path)}" is not a string')
    return node


def _json_replace(text: str, container: str | None, field: str, current: str, new: str) -> str:
    """Replace `"field": "current"` inside the container object only, so a same-named key elsewhere is never touched."""
    lo, hi = _json_object_span(text, container)
    body = text[lo:hi]
    pat = re.compile(r'("' + re.escape(field) + r'"\s*:\s*)"' + re.escape(current) + '"')
    # Only the container's own keys count: blank out nested objects when looking for the key.
    depth, first = 0, None
    in_str, esc = False, False
    for m in pat.finditer(body):
        depth, in_str, esc = 0, False, False
        for c in body[: m.start()]:
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
        if depth == 1:
            first = m
            break
    if first is None:
        raise SiteError(f'could not locate "{field}" in the text of its object')
    new_body = body[: first.start()] + first.group(1) + '"' + new + '"' + body[first.end():]
    return text[:lo] + new_body + text[hi:]


def read_iso_version(text: str) -> str:
    return _json_value(text, ("meta", "version"))


def write_iso_version(text: str, current: str, new: str) -> str:
    return _json_replace(text, "meta", "version", current, new)


def read_iso_updated(text: str) -> str:
    value = _json_value(text, ("meta", "updated"))
    if not DATE_RE.match(value):
        raise SiteError(f'meta.updated is not a YYYY-MM-DD date (found {value[:40]!r})')
    return value


def write_iso_updated(text: str, current: str, new: str) -> str:
    return _json_replace(text, "meta", "updated", current, new)


def read_package_json(text: str) -> str:
    return _json_value(text, ("version",))


def write_package_json(text: str, current: str, new: str) -> str:
    return _json_replace(text, None, "version", current, new)


READERS = {
    "version": (read_version, write_version),
    "readme_badge": (read_readme_badge, write_readme_badge),
    "setup_py": (read_setup_py, write_setup_py),
    "cargo_toml": (read_cargo_toml, write_cargo_toml),
    "iso_json_version": (read_iso_version, write_iso_version),
    "iso_json_updated": (read_iso_updated, write_iso_updated),
    "package_json": (read_package_json, write_package_json),
}


# ---------------------------------------------------------------------------
# The changelog site works on exact heading lines, not on versions
# ---------------------------------------------------------------------------

def bump_changelog(text: str, old: str, new: str) -> tuple[str, str]:
    """Return (new_text, state) with state in {"changed", "already"}; SiteError otherwise."""
    old_n = len(re.findall(r"^" + re.escape(old) + r"$", text, re.MULTILINE))
    new_n = len(re.findall(r"^" + re.escape(new) + r"$", text, re.MULTILINE))
    if old == new:
        if new_n == 1:
            return text, "already"
        raise SiteError(f"heading {new!r} found {new_n} times; expected exactly one")
    if new_n == 1 and old_n == 0:
        return text, "already"
    if old_n == 1 and new_n == 0:
        return re.sub(r"^" + re.escape(old) + r"$", lambda _m: new, text, count=1, flags=re.MULTILINE), "changed"
    raise SiteError(f"holds neither {old!r} nor {new!r} exactly once (found {old_n} and {new_n})")


# ---------------------------------------------------------------------------

def run(root: Path, site: str, old: str, new: str) -> tuple[int, str]:
    rel = SITES[site]
    path = root / rel
    if not path.is_file():
        return EXIT_USAGE, f"{site}: {rel} is missing"
    text = path.read_bytes().decode("utf-8")
    try:
        if site == "changelog":
            new_text, state = bump_changelog(text, old, new)
            if state == "changed":
                _write(path, new_text)
                if bump_changelog(path.read_bytes().decode("utf-8"), old, new)[1] != "already":
                    raise SiteError("read-back: the heading was not written")
            return EXIT_OK, f"{site}: {'already at' if state == 'already' else 'bumped to'} {new!r} ({rel})"

        reader, writer = READERS[site]
        current = reader(text)
        if current == new:
            return EXIT_OK, f"{site}: already at {new} ({rel})"
        any_date = site == "iso_json_updated" and old == "DATE"
        if current != old and not any_date:
            raise SiteError(f"holds {current!r}, expected {old!r} or {new!r}")
        new_text = writer(text, current, new)
        if new_text == text:
            raise SiteError("the write changed nothing")
        _check_only_that_value_changed(site, text, new_text)
        _write(path, new_text)
        if reader(path.read_bytes().decode("utf-8")) != new:
            raise SiteError(f"read-back: the site does not hold {new} after the write")
        return EXIT_OK, f"{site}: {current} -> {new} ({rel})"
    except SiteError as e:
        return EXIT_SITE, f"{site}: {rel}: {e}"


def _check_only_that_value_changed(site: str, before: str, after: str) -> None:
    """For the JSON sites, the parsed documents must be equal apart from the one field."""
    if site not in ("iso_json_version", "iso_json_updated", "package_json"):
        return
    a, b = _json_load(before), _json_load(after)
    path = {"iso_json_version": ("meta", "version"), "iso_json_updated": ("meta", "updated"),
            "package_json": ("version",)}[site]
    for doc in (a, b):
        node = doc
        for key in path[:-1]:
            node = node[key]
        node.pop(path[-1])
    if a != b:
        raise SiteError("the edit would change more than the one field; nothing written")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="bump one version site", add_help=True)
    p.add_argument("--root", default=".", help="repository root (default: the current directory)")
    p.add_argument("--from", dest="old", help="the value the site holds now")
    p.add_argument("--to", dest="new", help="the value the site must hold")
    p.add_argument("site", choices=sorted(SITES), help="which site")
    args = p.parse_args(argv)
    if args.old is None or args.new is None:
        p.error("--from and --to are both required")
    code, message = run(Path(args.root), args.site, args.old, args.new)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
