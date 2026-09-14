#!/usr/bin/env python3
"""
Command-line interface for the ISO 4217 Currency Registry.

Eight subcommands over the Python wrapper's CurrencyRegistry:

    lookup CODE...      all fields for one or more currencies
    list                filter across the registry
    minor AMOUNT CODE   major units -> minor units (integer)
    major AMOUNT CODE   minor units -> major units (decimal)
    format AMOUNT CODE  symbol + thousands separators
    peg CODE            peg details only
    info                registry metadata
    validate CODE...    exit 0 if all codes exist, 1 otherwise

Bare-argument shorthand: `iso4217 USD` is `iso4217 lookup USD`.

Output modes (mutually exclusive):
    (default)           human-readable, aligned columns
    --json              JSON object (single lookup/peg/info) or array (list, multi-lookup)
    --jsonl             newline-delimited JSON, one object per line
    --tsv               tab-separated, columns match iso4217.tsv, header included
    --csv               comma-separated, columns match iso4217.csv, header included
    --raw FIELD         bare value only, one per line for lists

Color is on when stdout is a TTY, off when piped. Override with
ISO4217_COLOR=never|auto|always. Machine modes always disable color.

Exit codes (aligned with export_sql.py, export_csv.py, and the other tools):
    0  success
    1  not found, or validation failed
    2  usage error (unknown flag, missing argument, bad combination)
    3  data error (registry missing, invalid JSON)

Read-only. No command writes to the registry or to any file. No network.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from typing import Any, Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# Wrapper import
# ---------------------------------------------------------------------------
# The CLI ships inside the same directory as the wrapper. Add that directory
# to sys.path before importing, so `python -m iso4217_cli` and the installed
# console_script both resolve the wrapper the same way.

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from iso4217 import Currency, CurrencyRegistry  # noqa: E402


__all__ = ["main"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_USAGE = 2
EXIT_DATA = 3

SUBCOMMANDS = (
    "lookup",
    "list",
    "minor",
    "major",
    "format",
    "peg",
    "info",
    "validate",
)

# Column order for --tsv and --csv, and field order for human `lookup` output.
# Identical to tools/export_csv.py's COLUMNS tuple and to the header row in
# iso4217.csv / iso4217.tsv, so a `diff` between the CLI and the export is
# meaningful.
LOOKUP_FIELDS: tuple[str, ...] = (
    "code",
    "numeric_code",
    "name",
    "minor_units",
    "symbol",
    "entity",
    "status",
    "is_independent",
    "pegged_to",
    "peg_type",
    "peg_rate",
)

LIST_DEFAULT_COLUMNS: tuple[str, ...] = (
    "code",
    "name",
    "minor_units",
    "status",
    "pegged_to",
)
LIST_LONG_COLUMNS: tuple[str, ...] = LIST_DEFAULT_COLUMNS + (
    "numeric_code",
    "symbol",
    "entity",
)
LIST_WIDE_COLUMNS: tuple[str, ...] = LOOKUP_FIELDS


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

def _use_color() -> bool:
    """
    True if ANSI color should be emitted.

    Precedence:
      1. ISO4217_COLOR=never   -> always False
      2. ISO4217_COLOR=always  -> always True
      3. ISO4217_COLOR=auto (default) -> True only when stdout is a TTY

    Unrecognized values fall through to auto, so an unset or misspelled
    environment variable behaves the same as auto.
    """
    mode = os.environ.get("ISO4217_COLOR", "auto").strip().lower()
    if mode == "never":
        return False
    if mode == "always":
        return True
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        # A StringIO or similar non-fd stream — treat as non-TTY.
        return False


class _Palette:
    """Tiny wrapper for the handful of ANSI sequences the CLI uses."""

    def __init__(self, on: bool) -> None:
        self.on = on

    def _wrap(self, code: str, s: str) -> str:
        return f"\x1b[{code}m{s}\x1b[0m" if self.on else s

    def bold(self, s: str) -> str: return self._wrap("1", s)
    def dim(self, s: str) -> str: return self._wrap("2", s)
    def green(self, s: str) -> str: return self._wrap("32", s)
    def yellow(self, s: str) -> str: return self._wrap("33", s)
    def blue(self, s: str) -> str: return self._wrap("34", s)
    def magenta(self, s: str) -> str: return self._wrap("35", s)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

class RegistryError(Exception):
    """Raised when the registry cannot be loaded. Maps to EXIT_DATA."""


def _load_registry(path: Optional[str] = None) -> CurrencyRegistry:
    try:
        if path:
            return CurrencyRegistry(path)
        return CurrencyRegistry()
    except FileNotFoundError as e:
        raise RegistryError(str(e)) from e
    except json.JSONDecodeError as e:
        raise RegistryError(f"invalid registry JSON: {e}") from e


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def _field_value(c: Currency, field: str, registry: CurrencyRegistry) -> Any:
    """
    Extract one of LOOKUP_FIELDS from a Currency.

    Return types are native Python values so JSON serialization is correct:
    booleans stay bool, numbers stay int/float, absent values become ''.

    'status' is derived by asking the registry whether the code is withdrawn.
    A code can be in exactly one of the two maps, so this is unambiguous.
    """
    if field == "code":
        return c.code
    if field == "numeric_code":
        return c.numeric
    if field == "name":
        return c.name
    if field == "minor_units":
        return c.minor_units
    if field == "symbol":
        return c.symbol
    if field == "entity":
        return c.entity
    if field == "status":
        return "withdrawn" if registry.withdrawn(c.code) else "active"
    if field == "is_independent":
        return bool(c.is_independent)
    if field == "pegged_to":
        return c.pegged_to or ""
    if field == "peg_type":
        return c.peg_type or ""
    if field == "peg_rate":
        # Keep the float for JSON; text formatters turn None into ''.
        return c.peg_rate if c.peg_rate is not None else ""
    raise KeyError(field)


def _cell_str(value: Any) -> str:
    """
    Render a field value as text for human, --tsv, --csv, and --raw output.

    Booleans become lowercase 'true'/'false' to match the CSV/TSV exports
    and the JSON wire format. None becomes the empty string. Everything else
    is str().
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def _row_tuple(
    c: Currency, registry: CurrencyRegistry, columns: Iterable[str]
) -> tuple[str, ...]:
    """Render a currency as a tuple of text cells for --tsv/--csv."""
    return tuple(_cell_str(_field_value(c, f, registry)) for f in columns)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_human_lookup(
    c: Currency, registry: CurrencyRegistry, palette: _Palette
) -> str:
    """
    Two-column, aligned field/value block for one currency.

    Field order matches LOOKUP_FIELDS so a user comparing human output
    against iso4217.csv sees the same fields in the same sequence.
    """
    rows: list[tuple[str, str]] = []
    for field in LOOKUP_FIELDS:
        raw = _field_value(c, field, registry)
        text = _cell_str(raw)

        if field == "code":
            rendered = palette.bold(text)
        elif field == "status":
            rendered = palette.green(text) if text == "active" else palette.dim(text)
        elif field == "peg_type":
            if not text:
                rendered = ""
            else:
                colors = {
                    "single": palette.yellow,
                    "basket": palette.blue,
                    "undisclosed": palette.magenta,
                }
                rendered = colors.get(text, lambda s: s)(text)
        else:
            rendered = text

        rows.append((field, rendered))

    width = max(len(f) for f, _ in rows) if rows else 0
    return "\n".join(f"{field:<{width}}  {value}" for field, value in rows)


def _fmt_human_list(
    rows: list[Currency],
    registry: CurrencyRegistry,
    palette: _Palette,
    columns: tuple[str, ...],
) -> str:
    """
    Aligned table of currencies. Empty input produces an empty string so the
    caller can decide whether to print a 'no matches' notice.
    """
    if not rows:
        return ""

    data = [tuple(_cell_str(_field_value(c, f, registry)) for f in columns) for c in rows]
    widths = [
        max(
            len(str(columns[i])),
            max((len(row[i]) for row in data), default=0),
        )
        for i in range(len(columns))
    ]
    header = "  ".join(
        palette.bold(str(columns[i]).ljust(widths[i])) for i in range(len(columns))
    )
    lines = [header]
    for row in data:
        lines.append("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))))
    return "\n".join(lines)


def _fmt_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _fmt_jsonl(objs: Iterable[Any]) -> str:
    return "\n".join(json.dumps(o, ensure_ascii=False) for o in objs)


def _fmt_tsv(header: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    """
    RFC 4180-style TSV with a header row. lineterminator='\\n' matches
    iso4217.tsv; quoting is delegated to csv.writer.
    """
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().rstrip("\n")


def _fmt_csv(header: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    """RFC 4180 CSV with a header row. lineterminator='\\n' matches iso4217.csv."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().rstrip("\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_stdin_codes() -> list[str]:
    """
    Read codes from stdin, one per line. Blank lines and lines beginning
    with '#' are ignored, so a commented file pipes cleanly.
    """
    codes: list[str] = []
    for line in sys.stdin.read().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        codes.append(stripped)
    return codes


def _resolve_codes(raw: list[str]) -> list[str]:
    """
    Expand '-' in a positional argument list by reading from stdin. Any
    other argument is passed through unchanged. The result is a flat list
    of codes in the order they were encountered.
    """
    out: list[str] = []
    for a in raw:
        if a == "-":
            out.extend(_read_stdin_codes())
        else:
            out.append(a)
    return out


def _output_mode(args: argparse.Namespace) -> tuple[str, Optional[str]]:
    """
    Collapse the mutually-exclusive output flags into a single (mode, field)
    pair. argparse already rejected combinations of two or more flags, so at
    most one branch fires.
    """
    if args.json:
        return "json", None
    if args.jsonl:
        return "jsonl", None
    if args.tsv:
        return "tsv", None
    if args.csv:
        return "csv", None
    if args.raw is not None:
        return "raw", args.raw
    return "human", None


def _add_output_flags(p: argparse.ArgumentParser) -> None:
    """
    Attach the five mutually-exclusive output-mode flags to a subparser.

    --raw takes a FIELD argument; the others are bare flags. A user who
    passes two of them gets an argparse error with exit code 2, which the
    CLI's main() catches and returns as EXIT_USAGE.
    """
    group = p.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="JSON output")
    group.add_argument("--jsonl", action="store_true", help="newline-delimited JSON")
    group.add_argument("--tsv", action="store_true", help="tab-separated, header included")
    group.add_argument("--csv", action="store_true", help="comma-separated, header included")
    group.add_argument(
        "--raw",
        metavar="FIELD",
        default=None,
        help="print only FIELD, one value per line for lists",
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_lookup(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    codes = _resolve_codes(args.codes)
    if not codes:
        print("error: no codes provided", file=sys.stderr)
        return EXIT_USAGE

    mode, field = _output_mode(args)

    found: list[Currency] = []
    missing: list[str] = []
    for code in codes:
        c = registry.currency(code)
        if c is None:
            missing.append(code)
        else:
            found.append(c)

    # Emit whatever was found, even if some codes were missing. A caller
    # who wants all-or-nothing behavior should use `validate` instead.
    if mode == "json":
        if len(found) == 1:
            print(_fmt_json({f: _field_value(found[0], f, registry) for f in LOOKUP_FIELDS}))
        else:
            print(_fmt_json([
                {f: _field_value(c, f, registry) for f in LOOKUP_FIELDS} for c in found
            ]))
    elif mode == "jsonl":
        print(_fmt_jsonl([
            {f: _field_value(c, f, registry) for f in LOOKUP_FIELDS} for c in found
        ]))
    elif mode == "tsv":
        print(_fmt_tsv(
            LOOKUP_FIELDS,
            [_row_tuple(c, registry, LOOKUP_FIELDS) for c in found],
        ))
    elif mode == "csv":
        print(_fmt_csv(
            LOOKUP_FIELDS,
            [_row_tuple(c, registry, LOOKUP_FIELDS) for c in found],
        ))
    elif mode == "raw":
        assert field is not None  # guaranteed by _output_mode
        if field not in LOOKUP_FIELDS:
            print(f"error: unknown field '{field}'", file=sys.stderr)
            return EXIT_USAGE
        for c in found:
            print(_cell_str(_field_value(c, field, registry)))
    else:
        palette = _Palette(_use_color())
        blocks = [_fmt_human_lookup(c, registry, palette) for c in found]
        if blocks:
            print("\n\n".join(blocks))

    if missing:
        for code in missing:
            print(f"error: {code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND
    return EXIT_OK


def _cmd_list(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    # Category selection. --all is equivalent to --active --withdrawn --non-iso;
    # otherwise the union of whichever category flags were set. With none set,
    # default to active (the most common query).
    if args.all:
        pool = registry.all_active() + registry.all_withdrawn() + registry.all_non_iso()
    else:
        pool = []
        if args.withdrawn:
            pool += registry.all_withdrawn()
        if args.non_iso:
            pool += registry.all_non_iso()
        if args.active or not pool:
            pool += registry.all_active()

    # De-duplicate by code in case a category flag was passed twice, then
    # apply the non-category filters.
    seen: set[str] = set()
    unique_pool: list[Currency] = []
    for c in pool:
        if c.code not in seen:
            seen.add(c.code)
            unique_pool.append(c)

    def keep(c: Currency) -> bool:
        if args.pegged_to is not None:
            if c.peg_type != "single":
                return False
            if (c.pegged_to or "").upper() != args.pegged_to.upper():
                return False
        if args.minor_units is not None and c.minor_units != args.minor_units:
            return False
        if args.issued_by is not None:
            target = args.issued_by.upper()
            if not any(
                ct.get("code") == target and ct.get("relationship") == "issuing"
                for ct in c.countries
            ):
                return False
        if args.country is not None:
            target = args.country.upper()
            if not any(ct.get("code") == target for ct in c.countries):
                return False
        if args.independent and not c.is_independent:
            return False
        if args.pegged and not c.is_pegged:
            return False
        return True

    rows = [c for c in unique_pool if keep(c)]

    if args.sort == "name":
        rows.sort(key=lambda c: (c.name, c.code))
    elif args.sort == "numeric_code":
        rows.sort(key=lambda c: (c.numeric, c.code))
    else:
        rows.sort(key=lambda c: c.code)

    if args.limit is not None and args.limit >= 0:
        rows = rows[: args.limit]

    mode, field = _output_mode(args)

    if mode == "json":
        print(_fmt_json([
            {f: _field_value(c, f, registry) for f in LOOKUP_FIELDS} for c in rows
        ]))
    elif mode == "jsonl":
        print(_fmt_jsonl([
            {f: _field_value(c, f, registry) for f in LOOKUP_FIELDS} for c in rows
        ]))
    elif mode == "tsv":
        print(_fmt_tsv(
            LOOKUP_FIELDS,
            [_row_tuple(c, registry, LOOKUP_FIELDS) for c in rows],
        ))
    elif mode == "csv":
        print(_fmt_csv(
            LOOKUP_FIELDS,
            [_row_tuple(c, registry, LOOKUP_FIELDS) for c in rows],
        ))
    elif mode == "raw":
        assert field is not None
        if field not in LOOKUP_FIELDS:
            print(f"error: unknown field '{field}'", file=sys.stderr)
            return EXIT_USAGE
        for c in rows:
            print(_cell_str(_field_value(c, field, registry)))
    else:
        if not rows:
            # Nothing to show; still exit 0 — an empty result is a successful
            # query with no matches, not an error.
            return EXIT_OK
        palette = _Palette(_use_color())
        if args.wide:
            columns = LIST_WIDE_COLUMNS
        elif args.long:
            columns = LIST_LONG_COLUMNS
        else:
            columns = LIST_DEFAULT_COLUMNS
        print(_fmt_human_list(rows, registry, palette, columns))

    return EXIT_OK


def _cmd_minor(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    c = registry.currency(args.code)
    if c is None:
        print(f"error: {args.code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND
    try:
        amount = float(args.amount)
    except ValueError:
        print(f"error: '{args.amount}' is not a number", file=sys.stderr)
        return EXIT_USAGE
    try:
        result = c.to_minor(amount)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(result)
    return EXIT_OK


def _cmd_major(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    c = registry.currency(args.code)
    if c is None:
        print(f"error: {args.code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND
    try:
        minor = int(args.amount)
    except ValueError:
        print(f"error: '{args.amount}' is not an integer", file=sys.stderr)
        return EXIT_USAGE
    print(repr(c.from_minor(minor)))
    return EXIT_OK


def _cmd_format(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    c = registry.currency(args.code)
    if c is None:
        print(f"error: {args.code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND
    try:
        amount = float(args.amount)
    except ValueError:
        print(f"error: '{args.amount}' is not a number", file=sys.stderr)
        return EXIT_USAGE
    print(c.format(amount))
    return EXIT_OK


def _cmd_peg(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    # peg takes exactly one code. '-' reads the first non-blank, non-comment
    # line from stdin; additional lines are ignored.
    code = args.code
    if code == "-":
        stdin_codes = _read_stdin_codes()
        if not stdin_codes:
            print("error: no code on stdin", file=sys.stderr)
            return EXIT_USAGE
        code = stdin_codes[0]

    c = registry.currency(code)
    if c is None:
        print(f"error: {code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND

    peg_fields: tuple[str, ...] = (
        "code",
        "is_independent",
        "pegged_to",
        "peg_type",
        "peg_rate",
    )
    mode, field = _output_mode(args)

    if mode == "json":
        print(_fmt_json({f: _field_value(c, f, registry) for f in peg_fields}))
    elif mode == "jsonl":
        print(_fmt_jsonl([{f: _field_value(c, f, registry) for f in peg_fields}]))
    elif mode in ("tsv", "csv"):
        data = [_row_tuple(c, registry, peg_fields)]
        if mode == "tsv":
            print(_fmt_tsv(peg_fields, data))
        else:
            print(_fmt_csv(peg_fields, data))
    elif mode == "raw":
        assert field is not None
        if field not in peg_fields:
            print(f"error: unknown field '{field}'", file=sys.stderr)
            return EXIT_USAGE
        print(_cell_str(_field_value(c, field, registry)))
    else:
        palette = _Palette(_use_color())
        if not c.is_pegged:
            print(f"{palette.bold(c.code)} is not pegged")
            return EXIT_OK
        width = max(len(f) for f in peg_fields)
        for f in peg_fields:
            v = _cell_str(_field_value(c, f, registry))
            if f == "code":
                v = palette.bold(v)
            elif f == "peg_type" and v:
                colors = {
                    "single": palette.yellow,
                    "basket": palette.blue,
                    "undisclosed": palette.magenta,
                }
                v = colors.get(v, lambda s: s)(v)
            print(f"{f:<{width}}  {v}")

    return EXIT_OK


def _cmd_info(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    summary = registry.summary()
    mode, field = _output_mode(args)

    if mode == "json":
        print(_fmt_json(summary))
    elif mode == "jsonl":
        print(_fmt_jsonl([summary]))
    elif mode == "raw":
        assert field is not None
        if field not in summary:
            print(f"error: unknown field '{field}'", file=sys.stderr)
            return EXIT_USAGE
        print(_cell_str(summary[field]))
    elif mode in ("tsv", "csv"):
        # Two-column key/value table. Not the same shape as the currencies
        # exports — info is metadata, not rows. Header is ('field', 'value').
        header = ("field", "value")
        data = [(k, _cell_str(v)) for k, v in summary.items()]
        if mode == "tsv":
            print(_fmt_tsv(header, data))
        else:
            print(_fmt_csv(header, data))
    else:
        width = max(len(k) for k in summary)
        for k, v in summary.items():
            print(f"{k:<{width}}  {_cell_str(v)}")

    return EXIT_OK


def _cmd_validate(args: argparse.Namespace, registry: CurrencyRegistry) -> int:
    codes = _resolve_codes(args.codes)
    if not codes:
        print("error: no codes provided", file=sys.stderr)
        return EXIT_USAGE

    missing = [code for code in codes if registry.currency(code) is None]
    if missing:
        for code in missing:
            print(f"error: {code} not in registry", file=sys.stderr)
        return EXIT_NOT_FOUND
    return EXIT_OK


_HANDLERS: dict[str, Callable[[argparse.Namespace, CurrencyRegistry], int]] = {
    "lookup": _cmd_lookup,
    "list": _cmd_list,
    "minor": _cmd_minor,
    "major": _cmd_major,
    "format": _cmd_format,
    "peg": _cmd_peg,
    "info": _cmd_info,
    "validate": _cmd_validate,
}


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iso4217",
        description="Query the ISO 4217 Currency Registry.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the registry version and exit",
    )

    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")

    # lookup
    p = sub.add_parser("lookup", help="all fields for one or more currencies")
    p.add_argument(
        "codes",
        nargs="+",
        metavar="CODE",
        help="currency code(s); use '-' to read from stdin, one per line",
    )
    _add_output_flags(p)

    # list
    p = sub.add_parser("list", help="filter across the registry")
    p.add_argument("--active", action="store_true", help="only active (default)")
    p.add_argument("--withdrawn", action="store_true", help="only withdrawn")
    p.add_argument("--non-iso", action="store_true", help="include non-ISO instruments")
    p.add_argument(
        "--all",
        action="store_true",
        help="active + withdrawn + non-ISO (equivalent to all three category flags)",
    )
    p.add_argument("--pegged-to", metavar="CODE", default=None, help="peg anchor (single pegs only)")
    p.add_argument("--minor-units", type=int, metavar="N", default=None, help="exactly N minor units")
    p.add_argument("--country", metavar="CC", default=None, help="used in country CC (ISO 3166-1 alpha-2)")
    p.add_argument("--issued-by", metavar="CC", default=None, help="issued by country CC")
    p.add_argument("--independent", action="store_true", help="only independent currencies")
    p.add_argument("--pegged", action="store_true", help="only pegged currencies")
    p.add_argument("--limit", type=int, metavar="N", default=None, help="truncate to N rows")
    p.add_argument(
        "--sort",
        choices=("code", "name", "numeric_code"),
        default="code",
        help="sort order (default: code)",
    )
    p.add_argument("--long", action="store_true", help="add numeric_code, symbol, entity")
    p.add_argument("--wide", action="store_true", help="all 11 columns")
    _add_output_flags(p)

    # minor / major / format — same shape
    for name, helptext in (
        ("minor", "convert major units to minor units"),
        ("major", "convert minor units to major units"),
        ("format", "format an amount with the currency symbol"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("amount", metavar="AMOUNT")
        p.add_argument("code", metavar="CODE")

    # peg
    p = sub.add_parser("peg", help="peg details only")
    p.add_argument("code", metavar="CODE", help="currency code, or '-' to read one from stdin")
    _add_output_flags(p)

    # info
    p = sub.add_parser("info", help="registry metadata")
    _add_output_flags(p)

    # validate
    p = sub.add_parser("validate", help="exit 0 if all codes exist, 1 otherwise")
    p.add_argument(
        "codes",
        nargs="+",
        metavar="CODE",
        help="currency code(s); use '-' to read from stdin, one per line",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point. Returns the process exit code.

    Accepts argv for testability; when None, uses sys.argv[1:].
    Bare-argument shorthand: if the first token is neither a known
    subcommand nor a flag, prepend 'lookup' so `iso4217 USD` works.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    # Bare-argument shorthand. Any leading token that starts with '-' is a
    # top-level flag (--version, --help, -h); argparse handles those. A token
    # that is a known subcommand is left alone. Anything else becomes the
    # first argument to `lookup`.
    if argv and not argv[0].startswith("-") and argv[0] not in SUBCOMMANDS:
        argv = ["lookup"] + argv

    parser = _build_parser()

    # argparse calls sys.exit() on usage errors and on -h/--help. Catch the
    # SystemExit so main() always returns an int; the help/error text has
    # already been written to stdout/stderr by then.
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        if code is None:
            return EXIT_USAGE
        if isinstance(code, int):
            return code
        return EXIT_USAGE

    # --version short-circuits before any subcommand runs.
    if getattr(args, "version", False):
        try:
            registry = _load_registry(None)
        except RegistryError as e:
            print(f"error: {e}", file=sys.stderr)
            return EXIT_DATA
        print(registry.version)
        return EXIT_OK

    # No subcommand given: print help and exit with a usage code.
    if not getattr(args, "cmd", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        registry = _load_registry(None)
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_DATA

    handler = _HANDLERS[args.cmd]
    return handler(args, registry)


if __name__ == "__main__":
    sys.exit(main())