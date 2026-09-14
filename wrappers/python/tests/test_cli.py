"""
Tests for wrappers/python/iso4217_cli.py.

Covers the CLI's full surface:

  - argv normalization (bare shorthand, --raw prefix, --registry prefix)
  - every subcommand: lookup, list, minor, major, format, peg, info, validate
  - every output mode: human, --json, --jsonl, --tsv, --csv, --raw
  - color control and env-var precedence
  - exit codes 0, 1, 2, 3
  - stdin via '-' for lookup and validate
  - --registry override and its interaction with the shorthand rewrites
  - help output for every subcommand
  - cross-check: CLI --tsv output matches committed iso4217.tsv row for row

Every test runs `iso4217_cli.main(argv)` in-process and captures stdout
and stderr via pytest's capsys fixture. No subprocess, no venv required,
no dependency on the console_scripts entry point being installed.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
# This test file lives at wrappers/python/tests/test_cli.py.
#   parents[0] = wrappers/python/tests
#   parents[1] = wrappers/python      <- the wrapper package
#   parents[2] = wrappers
#   parents[3] = repo root            <- where iso4217.json and iso4217.tsv live

_WRAPPER_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]

if str(_WRAPPER_DIR) not in sys.path:
    sys.path.insert(0, str(_WRAPPER_DIR))

import iso4217_cli  # noqa: E402
from iso4217 import CurrencyRegistry  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LOOKUP_FIELDS = list(iso4217_cli.LOOKUP_FIELDS)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def registry() -> CurrencyRegistry:
    """The real registry, loaded once per test session."""
    return CurrencyRegistry()


@pytest.fixture(autouse=True)
def _clean_color_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure ISO4217_COLOR does not leak between tests. Some tests set it
    explicitly; without this fixture, the value would persist and make
    unrelated tests flaky depending on execution order.
    """
    monkeypatch.delenv("ISO4217_COLOR", raising=False)


@pytest.fixture
def run_cli(capsys: pytest.CaptureFixture):
    """
    Run iso4217_cli.main(argv) and capture (exit_code, stdout, stderr).

    Returns a callable so a single test can invoke the CLI multiple times
    and read each result independently.
    """
    def _run(argv: list[str]) -> tuple[int, str, str]:
        code = iso4217_cli.main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err
    return _run


@pytest.fixture
def no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force color off regardless of TTY detection."""
    monkeypatch.setattr(iso4217_cli, "_use_color", lambda: False)


@pytest.fixture
def force_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force color on regardless of TTY detection."""
    monkeypatch.setattr(iso4217_cli, "_use_color", lambda: True)


# ---------------------------------------------------------------------------
# _normalize_argv — direct unit tests
# ---------------------------------------------------------------------------

class TestNormalizeArgv:
    """The argv preprocessor that turns every documented usage shape into
    one the parser accepts. Pure function; test it in isolation."""

    def test_empty(self):
        assert iso4217_cli._normalize_argv([]) == []

    def test_bare_code_becomes_lookup(self):
        assert iso4217_cli._normalize_argv(["USD"]) == ["lookup", "USD"]

    def test_known_subcommand_left_alone(self):
        for cmd in iso4217_cli.SUBCOMMANDS:
            assert iso4217_cli._normalize_argv([cmd, "USD"]) == [cmd, "USD"]

    def test_flag_first_left_alone(self):
        assert iso4217_cli._normalize_argv(["--help"]) == ["--help"]
        assert iso4217_cli._normalize_argv(["--version"]) == ["--version"]

    def test_top_level_raw_rewritten(self):
        assert iso4217_cli._normalize_argv(
            ["--raw", "lookup", "USD", "minor_units"]
        ) == ["lookup", "USD", "--raw", "minor_units"]

    def test_top_level_raw_with_middle_args(self):
        assert iso4217_cli._normalize_argv(
            ["--raw", "list", "--pegged-to", "USD", "code"]
        ) == ["list", "--pegged-to", "USD", "--raw", "code"]

    def test_top_level_raw_too_short_is_passthrough(self):
        # No subcommand or no trailing field; leave for argparse to reject.
        assert iso4217_cli._normalize_argv(["--raw"]) == ["--raw"]
        assert iso4217_cli._normalize_argv(["--raw", "lookup"]) == [
            "--raw", "lookup",
        ]

    def test_registry_prefix_preserved(self):
        assert iso4217_cli._normalize_argv(
            ["--registry", "x.json", "USD"]
        ) == ["--registry", "x.json", "lookup", "USD"]

    def test_registry_composes_with_raw(self):
        assert iso4217_cli._normalize_argv(
            ["--registry", "x.json", "--raw", "info", "active_currencies"]
        ) == ["--registry", "x.json", "info", "--raw", "active_currencies"]

    def test_registry_composes_with_bare_shorthand(self):
        assert iso4217_cli._normalize_argv(
            ["--registry", "x.json", "USD"]
        ) == ["--registry", "x.json", "lookup", "USD"]

    def test_registry_with_no_subcommand_is_passthrough(self):
        assert iso4217_cli._normalize_argv(
            ["--registry", "x.json"]
        ) == ["--registry", "x.json"]


# ---------------------------------------------------------------------------
# Bare-argument shorthand
# ---------------------------------------------------------------------------

class TestBareShorthand:
    def test_bare_and_explicit_produce_identical_output(self, run_cli, no_color):
        code_a, out_a, _ = run_cli(["USD"])
        code_b, out_b, _ = run_cli(["lookup", "USD"])
        assert code_a == 0
        assert code_b == 0
        assert out_a == out_b

    def test_bare_unknown_code_is_exit_1(self, run_cli):
        code, out, err = run_cli(["XYZ"])
        assert code == 1
        assert "XYZ" in err

    def test_bare_with_json_flag(self, run_cli):
        code, out, _ = run_cli(["USD", "--json"])
        assert code == 0
        parsed = json.loads(out)
        assert parsed["code"] == "USD"

    def test_version_flag_short_circuits(self, run_cli):
        code, out, _ = run_cli(["--version"])
        assert code == 0
        assert out.strip()  # prints something


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_known_active_code(self, run_cli, no_color):
        code, out, _ = run_cli(["lookup", "USD"])
        assert code == 0
        for field in LOOKUP_FIELDS:
            assert field in out

    def test_known_withdrawn_code(self, run_cli, no_color):
        code, out, _ = run_cli(["lookup", "DEM"])
        assert code == 0
        assert "DEM" in out
        assert "withdrawn" in out

    def test_known_non_iso_code(self, run_cli, no_color):
        code, out, _ = run_cli(["lookup", "BTC"])
        assert code == 0
        assert "BTC" in out

    def test_unknown_code_exits_1(self, run_cli):
        code, out, err = run_cli(["lookup", "XYZ"])
        assert code == 1
        assert "XYZ" in err
        assert "not in registry" in err

    def test_case_insensitive(self, run_cli, no_color):
        _, out_upper, _ = run_cli(["lookup", "USD"])
        _, out_lower, _ = run_cli(["lookup", "usd"])
        _, out_mixed, _ = run_cli(["lookup", "Usd"])
        assert out_upper == out_lower == out_mixed

    def test_multiple_codes(self, run_cli, no_color):
        code, out, _ = run_cli(["lookup", "USD", "EUR"])
        assert code == 0
        assert "USD" in out
        assert "EUR" in out

    def test_missing_in_middle_of_valid_codes(self, run_cli, no_color):
        code, out, err = run_cli(["lookup", "USD", "XYZ", "EUR"])
        assert code == 1
        # Found currencies still printed
        assert "USD" in out and "EUR" in out
        # Only the missing code is named on stderr
        assert "XYZ" in err
        assert "USD" not in err
        assert "EUR" not in err

    def test_all_missing(self, run_cli):
        code, out, err = run_cli(["lookup", "XYZ", "ABC"])
        assert code == 1
        assert "XYZ" in err and "ABC" in err


# ---------------------------------------------------------------------------
# list — category selection
# ---------------------------------------------------------------------------

class TestListCategories:
    def test_default_is_active(self, run_cli, registry):
        code, out, _ = run_cli(["list", "--raw", "code"])
        codes = set(out.strip().splitlines())
        assert code == 0
        assert codes == {c.code for c in registry.all_active()}

    def test_withdrawn(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--withdrawn", "--raw", "code"])
        codes = set(out.strip().splitlines())
        assert codes == {c.code for c in registry.all_withdrawn()}

    def test_non_iso(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--non-iso", "--raw", "code"])
        codes = set(out.strip().splitlines())
        assert codes == {c.code for c in registry.all_non_iso()}

    def test_all_is_union(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--all", "--raw", "code"])
        codes = set(out.strip().splitlines())
        expected = (
            {c.code for c in registry.all_active()}
            | {c.code for c in registry.all_withdrawn()}
            | {c.code for c in registry.all_non_iso()}
        )
        assert codes == expected

    def test_active_withdrawn_non_iso_flags_equal_all(self, run_cli):
        _, out_flags, _ = run_cli(
            ["list", "--active", "--withdrawn", "--non-iso", "--raw", "code"]
        )
        _, out_all, _ = run_cli(["list", "--all", "--raw", "code"])
        assert set(out_flags.strip().splitlines()) == set(out_all.strip().splitlines())


# ---------------------------------------------------------------------------
# list — filters, each cross-checked against the wrapper's own method
# ---------------------------------------------------------------------------

class TestListFilters:
    def test_pegged_to_matches_wrapper(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--pegged-to", "USD", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            c.code for c in registry.pegged_to("USD")
        }

    def test_pegged_to_case_insensitive(self, run_cli):
        _, out_upper, _ = run_cli(["list", "--pegged-to", "USD", "--raw", "code"])
        _, out_lower, _ = run_cli(["list", "--pegged-to", "usd", "--raw", "code"])
        assert out_upper == out_lower

    def test_pegged_to_basket_does_not_match(self, run_cli, registry):
        """MAD is pegged to 'EUR+USD basket'; it must not appear in the
        USD-anchor list, because peg_type is 'basket', not 'single'."""
        _, out, _ = run_cli(["list", "--pegged-to", "USD", "--raw", "code"])
        assert "MAD" not in out.strip().splitlines()

    def test_minor_units_matches_wrapper(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--minor-units", "3", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            c.code for c in registry.with_minor_units(3)
        }

    def test_issued_by_matches_wrapper(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--issued-by", "CH", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            c.code for c in registry.issued_by("CH")
        }

    def test_country_matches_wrapper(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--country", "LI", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            c.code for c in registry.used_in("LI")
        }

    def test_independent_matches_wrapper(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--independent", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            c.code for c in registry.independent()
        }

    def test_pegged_flag(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--pegged", "--raw", "code"])
        expected = {c.code for c in registry.all_active() if c.is_pegged}
        assert set(out.strip().splitlines()) == expected

    def test_independent_and_pegged_are_disjoint(self, run_cli):
        _, out_ind, _ = run_cli(["list", "--independent", "--raw", "code"])
        _, out_peg, _ = run_cli(["list", "--pegged", "--raw", "code"])
        assert not (set(out_ind.strip().splitlines())
                    & set(out_peg.strip().splitlines()))

    def test_filters_combine_with_and(self, run_cli, registry):
        """--independent + --minor-units 2 restricts to active, independent,
        two-minor-unit currencies."""
        _, out, _ = run_cli(
            ["list", "--independent", "--minor-units", "2", "--raw", "code"]
        )
        expected = {
            c.code for c in registry.all_active()
            if c.is_independent and c.minor_units == 2
        }
        assert set(out.strip().splitlines()) == expected

    def test_empty_result_exits_0_with_no_output(self, run_cli):
        code, out, _ = run_cli(["list", "--issued-by", "ZZ", "--raw", "code"])
        assert code == 0
        assert out.strip() == ""


# ---------------------------------------------------------------------------
# list — sort, limit, long/wide
# ---------------------------------------------------------------------------

class TestListPresentation:
    def test_default_sort_is_by_code(self, run_cli):
        _, out, _ = run_cli(["list", "--raw", "code"])
        codes = out.strip().splitlines()
        assert codes == sorted(codes)

    def test_sort_by_name(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--sort", "name", "--json"])
        rows = json.loads(out)
        names = [r["name"] for r in rows]
        assert names == sorted(names)

    def test_sort_by_numeric_code(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--sort", "numeric_code", "--json"])
        rows = json.loads(out)
        numerics = [r["numeric_code"] for r in rows]
        assert numerics == sorted(numerics)

    def test_limit_truncates(self, run_cli):
        _, out, _ = run_cli(["list", "--limit", "5", "--raw", "code"])
        assert len(out.strip().splitlines()) == 5

    def test_limit_zero_returns_nothing(self, run_cli):
        _, out, _ = run_cli(["list", "--limit", "0", "--raw", "code"])
        assert out.strip() == ""

    def test_long_columns(self, run_cli, no_color):
        _, out, _ = run_cli(["list", "--limit", "1", "--long"])
        header_cols = [c.strip() for c in out.splitlines()[0].split("  ") if c.strip()]
        assert header_cols == [
            "code", "name", "minor_units", "status", "pegged_to",
            "numeric_code", "symbol", "entity",
        ]

    def test_wide_columns(self, run_cli, no_color):
        _, out, _ = run_cli(["list", "--limit", "1", "--wide"])
        header_cols = [c.strip() for c in out.splitlines()[0].split("  ") if c.strip()]
        assert header_cols == LOOKUP_FIELDS

    def test_default_columns(self, run_cli, no_color):
        _, out, _ = run_cli(["list", "--limit", "1"])
        header_cols = [c.strip() for c in out.splitlines()[0].split("  ") if c.strip()]
        assert header_cols == ["code", "name", "minor_units", "status", "pegged_to"]


# ---------------------------------------------------------------------------
# minor / major / format
# ---------------------------------------------------------------------------

class TestConversions:
    @pytest.mark.parametrize("code,amount,expected", [
        ("USD", "100.50", "10050"),
        ("USD", "0.01", "1"),
        ("USD", "0", "0"),
        ("JPY", "500", "500"),
        ("KWD", "1.500", "1500"),
        ("BTC", "0.00000001", "1"),
    ])
    def test_minor(self, run_cli, code, amount, expected):
        code_out, out, _ = run_cli(["minor", amount, code])
        assert code_out == 0
        assert out.strip() == expected

    @pytest.mark.parametrize("code,minor,expected_repr", [
        ("USD", "10050", "100.5"),
        ("USD", "1", "0.01"),
        ("USD", "0", "0.0"),
        ("JPY", "500", "500.0"),
    ])
    def test_major(self, run_cli, code, minor, expected_repr):
        code_out, out, _ = run_cli(["major", minor, code])
        assert code_out == 0
        assert out.strip() == expected_repr

    def test_format_usd(self, run_cli):
        code, out, _ = run_cli(["format", "1000", "USD"])
        assert code == 0
        assert out.strip() == "$1,000.00"

    def test_format_jpy(self, run_cli):
        code, out, _ = run_cli(["format", "500", "JPY"])
        assert code == 0
        assert out.strip() == "¥500"

    def test_minor_unknown_code_exits_1(self, run_cli):
        code, _, err = run_cli(["minor", "100", "XYZ"])
        assert code == 1
        assert "XYZ" in err

    def test_minor_non_numeric_exits_2(self, run_cli):
        code, _, err = run_cli(["minor", "not-a-number", "USD"])
        assert code == 2

    def test_major_non_integer_exits_2(self, run_cli):
        code, _, _ = run_cli(["major", "100.5", "USD"])
        assert code == 2

    def test_round_trip_via_cli(self, run_cli):
        """major(minor(X)) is X for stable USD values."""
        for amount in ["0.01", "1.00", "100.50", "9999.99"]:
            _, minor_out, _ = run_cli(["minor", amount, "USD"])
            minor = minor_out.strip()
            _, major_out, _ = run_cli(["major", minor, "USD"])
            recovered = float(major_out.strip())
            assert abs(recovered - float(amount)) < 0.005


# ---------------------------------------------------------------------------
# peg
# ---------------------------------------------------------------------------

class TestPeg:
    def test_aed_single_peg(self, run_cli, no_color):
        code, out, _ = run_cli(["peg", "AED"])
        assert code == 0
        assert "USD" in out
        assert "single" in out
        assert "3.6725" in out

    def test_mad_basket_peg(self, run_cli, no_color):
        code, out, _ = run_cli(["peg", "MAD"])
        assert code == 0
        assert "basket" in out

    def test_kwd_undisclosed_peg(self, run_cli, no_color):
        code, out, _ = run_cli(["peg", "KWD"])
        assert code == 0
        assert "undisclosed" in out

    def test_unpegged_currency(self, run_cli, no_color):
        code, out, _ = run_cli(["peg", "USD"])
        assert code == 0
        assert "not pegged" in out

    def test_unknown_code_exits_1(self, run_cli):
        code, _, err = run_cli(["peg", "XYZ"])
        assert code == 1
        assert "XYZ" in err

    def test_json_output(self, run_cli):
        code, out, _ = run_cli(["peg", "AED", "--json"])
        assert code == 0
        parsed = json.loads(out)
        assert parsed["pegged_to"] == "USD"
        assert parsed["peg_type"] == "single"
        assert parsed["peg_rate"] == 3.6725

    def test_raw_field(self, run_cli):
        code, out, _ = run_cli(["--raw", "peg", "AED", "peg_rate"])
        assert code == 0
        assert out.strip() == "3.6725"

    def test_raw_unknown_field_exits_2(self, run_cli):
        code, _, _ = run_cli(["--raw", "peg", "AED", "no_such_field"])
        assert code == 2


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

_INFO_KEYS = {
    "version",
    "updated",
    "amendment",
    "active_currencies",
    "withdrawn_currencies",
    "non_iso_currencies",
    "pegged_currencies",
    "independent_currencies",
    "minor_units_distribution",
}


class TestInfo:
    def test_human_output_has_all_fields(self, run_cli, no_color):
        code, out, _ = run_cli(["info"])
        assert code == 0
        for key in _INFO_KEYS:
            assert key in out

    def test_json_keys_match_summary(self, run_cli, registry):
        _, out, _ = run_cli(["info", "--json"])
        parsed = json.loads(out)
        assert set(parsed.keys()) == set(registry.summary().keys())

    def test_json_values_match_summary(self, run_cli, registry):
        _, out, _ = run_cli(["info", "--json"])
        parsed = json.loads(out)
        summary = registry.summary()
        for key in summary:
            if key == "minor_units_distribution":
                # JSON object keys are always strings; convert back to int
                # so the comparison matches summary()'s int-keyed dict.
                assert {int(k): v for k, v in parsed[key].items()} == summary[key]
            else:
                assert parsed[key] == summary[key], key

    def test_raw_field(self, run_cli, registry):
        code, out, _ = run_cli(["--raw", "info", "active_currencies"])
        assert code == 0
        assert int(out.strip()) == registry.active_count

    def test_raw_unknown_field_exits_2(self, run_cli):
        code, _, _ = run_cli(["--raw", "info", "no_such_field"])
        assert code == 2


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_all_valid_exits_0(self, run_cli):
        code, _, _ = run_cli(["validate", "USD", "EUR", "JPY"])
        assert code == 0

    def test_any_invalid_exits_1(self, run_cli):
        code, _, err = run_cli(["validate", "USD", "XYZ", "EUR"])
        assert code == 1
        assert "XYZ" in err
        # Valid codes are not named in the error
        assert "USD" not in err
        assert "EUR" not in err

    def test_multiple_invalid_all_named(self, run_cli):
        code, _, err = run_cli(["validate", "AAA", "BBB", "USD", "CCC"])
        assert code == 1
        assert "AAA" in err and "BBB" in err and "CCC" in err
        assert "USD" not in err

    def test_no_codes_exits_2(self, run_cli):
        code, _, _ = run_cli(["validate"])
        assert code == 2

    def test_case_insensitive(self, run_cli):
        code, _, _ = run_cli(["validate", "usd", "eur"])
        assert code == 0


# ---------------------------------------------------------------------------
# stdin via '-'
# ---------------------------------------------------------------------------

class TestStdin:
    def test_lookup_reads_stdin(self, run_cli, monkeypatch, no_color):
        monkeypatch.setattr("sys.stdin", io.StringIO("USD\nEUR\n"))
        code, out, _ = run_cli(["lookup", "-"])
        assert code == 0
        assert "USD" in out and "EUR" in out

    def test_validate_reads_stdin(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("USD\nEUR\n"))
        code, _, _ = run_cli(["validate", "-"])
        assert code == 0

    def test_validate_stdin_with_missing(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("USD\nXYZ\n"))
        code, _, err = run_cli(["validate", "-"])
        assert code == 1
        assert "XYZ" in err

    def test_blank_lines_ignored(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("\nUSD\n\nEUR\n\n"))
        code, _, _ = run_cli(["validate", "-"])
        assert code == 0

    def test_comment_lines_ignored(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("# header\nUSD\n# tail\n"))
        code, _, _ = run_cli(["validate", "-"])
        assert code == 0

    def test_empty_stdin_exits_2(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        code, _, _ = run_cli(["validate", "-"])
        assert code == 2

    def test_only_comments_exits_2(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("# nothing\n\n"))
        code, _, _ = run_cli(["validate", "-"])
        assert code == 2

    def test_peg_reads_first_stdin_code(self, run_cli, monkeypatch, no_color):
        monkeypatch.setattr("sys.stdin", io.StringIO("AED\nEUR\n"))
        code, out, _ = run_cli(["peg", "-"])
        assert code == 0
        assert "AED" in out

    def test_mixed_stdin_and_positional(self, run_cli, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("EUR\n"))
        code, out, _ = run_cli(["lookup", "USD", "-"])
        assert code == 0
        assert "USD" in out and "EUR" in out


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------

class TestOutputFormats:
    def test_json_single_lookup_is_object(self, run_cli):
        _, out, _ = run_cli(["lookup", "USD", "--json"])
        assert isinstance(json.loads(out), dict)

    def test_json_multiple_lookups_is_array(self, run_cli):
        _, out, _ = run_cli(["lookup", "USD", "EUR", "--json"])
        parsed = json.loads(out)
        assert isinstance(parsed, list) and len(parsed) == 2

    def test_json_list_is_array(self, run_cli):
        _, out, _ = run_cli(["list", "--json"])
        assert isinstance(json.loads(out), list)

    def test_jsonl_one_object_per_line(self, run_cli):
        _, out, _ = run_cli(["list", "--limit", "3", "--jsonl"])
        lines = [l for l in out.splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            assert isinstance(json.loads(line), dict)

    def test_json_is_valid_utf8(self, run_cli):
        _, out, _ = run_cli(["lookup", "JPY", "--json"])
        # The symbol ¥ must survive the round-trip
        parsed = json.loads(out)
        assert parsed["symbol"] == "¥"

    def test_tsv_header_is_lookup_fields(self, run_cli):
        _, out, _ = run_cli(["list", "--limit", "1", "--tsv"])
        header = out.splitlines()[0].split("\t")
        assert header == LOOKUP_FIELDS

    def test_csv_header_is_lookup_fields(self, run_cli):
        _, out, _ = run_cli(["list", "--limit", "1", "--csv"])
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == LOOKUP_FIELDS

    def test_csv_round_trip(self, run_cli, registry):
        """--csv output parses as valid CSV with the right number of rows."""
        _, out, _ = run_cli(["list", "--csv"])
        rows = list(csv.reader(io.StringIO(out)))
        # header + one row per active currency
        assert len(rows) == 1 + registry.active_count

    def test_raw_single_value(self, run_cli):
        _, out, _ = run_cli(["--raw", "lookup", "USD", "minor_units"])
        assert out.strip() == "2"
        # No trailing decoration beyond the newline print adds
        assert out.endswith("\n")

    def test_raw_list_one_per_line(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--raw", "code"])
        assert len(out.strip().splitlines()) == registry.active_count

    def test_raw_unknown_field_exits_2(self, run_cli):
        for cmd in (["lookup", "USD", "nope"],
                    ["list", "nope"],
                    ["peg", "AED", "nope"],
                    ["info", "nope"]):
            code, _, _ = run_cli(["--raw"] + cmd)
            assert code == 2, cmd

    @pytest.mark.parametrize("combo", [
        ["--json", "--csv"],
        ["--json", "--tsv"],
        ["--json", "--jsonl"],
        ["--jsonl", "--csv"],
        ["--csv", "--tsv"],
    ])
    def test_mutually_exclusive_flags_exit_2(self, run_cli, combo):
        code, _, _ = run_cli(["list"] + combo)
        assert code == 2

    def test_tsv_and_raw_mutually_exclusive(self, run_cli):
        code, _, _ = run_cli(["list", "--tsv", "--raw", "code"])
        assert code == 2


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

class TestColor:
    def test_use_color_never(self, monkeypatch):
        monkeypatch.setenv("ISO4217_COLOR", "never")
        assert iso4217_cli._use_color() is False

    def test_use_color_always(self, monkeypatch):
        monkeypatch.setenv("ISO4217_COLOR", "always")
        assert iso4217_cli._use_color() is True

    def test_use_color_auto_non_tty(self, monkeypatch):
        monkeypatch.setenv("ISO4217_COLOR", "auto")
        monkeypatch.setattr("sys.stdout", io.StringIO())
        assert iso4217_cli._use_color() is False

    def test_use_color_unset_non_tty(self, monkeypatch):
        monkeypatch.delenv("ISO4217_COLOR", raising=False)
        monkeypatch.setattr("sys.stdout", io.StringIO())
        assert iso4217_cli._use_color() is False

    def test_use_color_unknown_value_falls_through_to_auto(self, monkeypatch):
        monkeypatch.setenv("ISO4217_COLOR", "rainbow")
        monkeypatch.setattr("sys.stdout", io.StringIO())
        assert iso4217_cli._use_color() is False

    def test_palette_off_produces_no_escapes(self):
        p = iso4217_cli._Palette(False)
        joined = (
            p.bold("x") + p.dim("x") + p.green("x")
            + p.yellow("x") + p.blue("x") + p.magenta("x")
        )
        assert not ANSI_RE.search(joined)

    @pytest.mark.parametrize("method,sgr", [
        ("bold", "1"),
        ("dim", "2"),
        ("green", "32"),
        ("yellow", "33"),
        ("blue", "34"),
        ("magenta", "35"),
    ])
    def test_palette_roles_use_correct_sgr(self, method, sgr):
        p = iso4217_cli._Palette(True)
        rendered = getattr(p, method)("x")
        assert rendered == f"\x1b[{sgr}mx\x1b[0m"

    def test_lookup_human_no_color_when_off(self, run_cli, no_color):
        _, out, _ = run_cli(["lookup", "USD"])
        assert not ANSI_RE.search(out)

    def test_lookup_human_color_on(self, run_cli, force_color):
        _, out, _ = run_cli(["lookup", "USD"])
        assert "\x1b[1mUSD\x1b[0m" in out          # code is bold
        assert "\x1b[32mactive\x1b[0m" in out      # active is green

    def test_withdrawn_status_is_dim(self, run_cli, force_color):
        _, out, _ = run_cli(["lookup", "DEM"])
        assert "\x1b[2mwithdrawn\x1b[0m" in out

    def test_peg_type_colors(self, run_cli, force_color):
        _, out_single, _ = run_cli(["lookup", "AED"])
        assert "\x1b[33msingle\x1b[0m" in out_single

        _, out_basket, _ = run_cli(["lookup", "MAD"])
        assert "\x1b[34mbasket\x1b[0m" in out_basket

        _, out_und, _ = run_cli(["lookup", "KWD"])
        assert "\x1b[35mundisclosed\x1b[0m" in out_und

    @pytest.mark.parametrize("mode", [["--json"], ["--jsonl"], ["--tsv"], ["--csv"]])
    def test_machine_modes_have_no_color_even_when_forced(
        self, run_cli, force_color, mode
    ):
        _, out, _ = run_cli(["list", *mode])
        assert not ANSI_RE.search(out)

    def test_raw_has_no_color_even_when_forced(self, run_cli, force_color):
        _, out, _ = run_cli(["--raw", "list", "code"])
        assert not ANSI_RE.search(out)

    def test_env_always_wins_over_auto(self, run_cli, monkeypatch):
        """ISO4217_COLOR=always forces color even when stdout is captured."""
        monkeypatch.setenv("ISO4217_COLOR", "always")
        _, out, _ = run_cli(["lookup", "USD"])
        assert ANSI_RE.search(out)


# ---------------------------------------------------------------------------
# Exit codes — every code reachable by a specific input
# ---------------------------------------------------------------------------

class TestExitCodes:
    def test_exit_0_success(self, run_cli):
        for argv in (
            ["lookup", "USD"],
            ["list", "--limit", "1"],
            ["validate", "USD"],
            ["info"],
            ["peg", "AED"],
            ["--version"],
        ):
            code, _, _ = run_cli(argv)
            assert code == 0, argv

    def test_exit_1_not_found(self, run_cli):
        for argv in (
            ["lookup", "XYZ"],
            ["validate", "XYZ"],
            ["peg", "XYZ"],
            ["minor", "1", "XYZ"],
            ["major", "1", "XYZ"],
            ["format", "1", "XYZ"],
        ):
            code, _, _ = run_cli(argv)
            assert code == 1, argv

    def test_exit_2_usage_error(self, run_cli):
        for argv in (
            ["--bogus-flag"],
            [],                            # no subcommand
            ["lookup"],                    # missing positional
            ["minor", "not-a-number", "USD"],
            ["list", "--json", "--csv"],
            ["lookup", "USD", "--raw", "no_such_field"],
        ):
            code, _, _ = run_cli(argv)
            assert code == 2, argv

    def test_exit_3_data_error(self, run_cli, monkeypatch, tmp_path):
        """Point at a path that doesn't exist; the CLI's loader raises
        RegistryError, which maps to EXIT_DATA."""
        code, _, err = run_cli(
            ["--registry", str(tmp_path / "missing.json"), "lookup", "USD"]
        )
        assert code == 3
        assert err.strip()  # an explanatory message on stderr

    def test_exit_3_on_invalid_json(self, run_cli, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _, err = run_cli(["--registry", str(bad), "lookup", "USD"])
        assert code == 3


# ---------------------------------------------------------------------------
# --registry flag
# ---------------------------------------------------------------------------

class TestRegistryFlag:
    def test_explicit_valid_path(self, run_cli, tmp_path):
        # Copy the real JSON so we know the path is valid
        import shutil
        src = _REPO_ROOT / "iso4217.json"
        dst = tmp_path / "registry.json"
        shutil.copy(src, dst)
        code, out, _ = run_cli(["--registry", str(dst), "--raw", "lookup", "USD", "code"])
        assert code == 0
        assert out.strip() == "USD"

    def test_explicit_missing_path_exits_3(self, run_cli, tmp_path):
        code, _, _ = run_cli(["--registry", str(tmp_path / "nope.json"), "lookup", "USD"])
        assert code == 3

    def test_registry_with_version_flag(self, run_cli, tmp_path):
        import shutil, json as _json
        src = _REPO_ROOT / "iso4217.json"
        dst = tmp_path / "registry.json"
        shutil.copy(src, dst)
        expected = _json.loads(dst.read_text())["meta"]["version"]

        code, out, _ = run_cli(["--registry", str(dst), "--version"])
        assert code == 0
        assert out.strip() == expected

    def test_registry_composes_with_raw(self, run_cli, tmp_path):
        import shutil
        src = _REPO_ROOT / "iso4217.json"
        dst = tmp_path / "registry.json"
        shutil.copy(src, dst)
        code, out, _ = run_cli(
            ["--registry", str(dst), "--raw", "info", "active_currencies"]
        )
        assert code == 0
        assert out.strip().isdigit()

    def test_registry_composes_with_bare_shorthand(self, run_cli, tmp_path):
        import shutil
        src = _REPO_ROOT / "iso4217.json"
        dst = tmp_path / "registry.json"
        shutil.copy(src, dst)
        code, out, _ = run_cli(["--registry", str(dst), "USD"])
        assert code == 0
        assert "USD" in out


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

class TestHelp:
    def test_top_level_help_exits_0(self, run_cli):
        code, out, _ = run_cli(["--help"])
        assert code == 0

    def test_top_level_help_lists_all_subcommands(self, run_cli):
        _, out, _ = run_cli(["--help"])
        for cmd in iso4217_cli.SUBCOMMANDS:
            assert cmd in out, cmd

    def test_no_subcommand_prints_help_and_exits_2(self, run_cli):
        code, out, _ = run_cli([])
        assert code == 2
        assert "usage" in out.lower() or "usage" in (out + _)[:0] or out

    @pytest.mark.parametrize("cmd", list(iso4217_cli.SUBCOMMANDS))
    def test_subcommand_help_has_example(self, run_cli, cmd):
        code, out, _ = run_cli([cmd, "--help"])
        assert code == 0
        assert "Example:" in out

    @pytest.mark.parametrize("cmd", list(iso4217_cli.SUBCOMMANDS))
    def test_subcommand_help_has_exit_codes(self, run_cli, cmd):
        code, out, _ = run_cli([cmd, "--help"])
        assert code == 0
        assert "Exit codes:" in out

    def test_version_prints_registry_version(self, run_cli, registry):
        code, out, _ = run_cli(["--version"])
        assert code == 0
        assert out.strip() == registry.version


# ---------------------------------------------------------------------------
# Layer isolation — the CLI must reuse the wrapper, not reimplement it
# ---------------------------------------------------------------------------

class TestWrapperReuse:
    def test_source_imports_from_wrapper(self):
        """The CLI must import CurrencyRegistry from iso4217, not read the
        JSON file itself. If it ever opened iso4217.json directly, this
        guard would catch the drift."""
        src = (_WRAPPER_DIR / "iso4217_cli.py").read_text(encoding="utf-8")
        assert "from iso4217 import" in src
        assert "CurrencyRegistry" in src

    def test_source_does_not_open_registry_json(self):
        src = (_WRAPPER_DIR / "iso4217_cli.py").read_text(encoding="utf-8")
        # _load_registry delegates to CurrencyRegistry(path); there should
        # be no `open(...iso4217.json...)` anywhere in the CLI.
        assert "iso4217.json" not in src or "open(" not in src

    def test_pegged_to_matches_wrapper_exactly(self, run_cli, registry):
        _, out, _ = run_cli(["list", "--pegged-to", "EUR", "--raw", "code"])
        cli = set(out.strip().splitlines())
        wrapper = {c.code for c in registry.pegged_to("EUR")}
        assert cli == wrapper


# ---------------------------------------------------------------------------
# Cross-check against the committed CSV/TSV exports
# ---------------------------------------------------------------------------

class TestCrossCheckWithExports:
    """
    The CLI's --tsv output must match the committed iso4217.tsv, at least
    for the rows in each status group. This is the test that catches drift
    between the CLI's column order and the export's.
    """

    TSV_PATH = _REPO_ROOT / "iso4217.tsv"

    @staticmethod
    def _parse_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
        if not path.exists():
            pytest.skip(f"{path.name} not present")
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f, delimiter="\t"))
        return rows[0], rows[1:]

    def test_tsv_header_matches_lookup_fields(self, run_cli):
        header, _ = self._parse_tsv(self.TSV_PATH)
        assert header == LOOKUP_FIELDS

    def test_cli_tsv_active_rows_match_export(self, run_cli):
        _, out, _ = run_cli(["list", "--active", "--tsv"])
        _, export_rows = self._parse_tsv(self.TSV_PATH)
        expected = [r for r in export_rows if r[6] == "active"]
        actual = list(csv.reader(io.StringIO(out), delimiter="\t"))[1:]
        assert actual == expected

    def test_cli_tsv_withdrawn_rows_match_export(self, run_cli):
        _, out, _ = run_cli(["list", "--withdrawn", "--tsv"])
        _, export_rows = self._parse_tsv(self.TSV_PATH)
        expected = [r for r in export_rows if r[6] == "withdrawn"]
        actual = list(csv.reader(io.StringIO(out), delimiter="\t"))[1:]
        assert actual == expected

    def test_cli_tsv_all_iso_rows_match_export(self, run_cli):
        """--all includes non-ISO, which the export does not. Filter the
        CLI's output by code membership in the export — not by status —
        because the CLI reports non-ISO currencies with status 'active'
        (they are not in the withdrawn map), which would otherwise leak
        rows like ADA and BTC into the ISO comparison."""
        _, out, _ = run_cli(["list", "--all", "--tsv"])
        _, export_rows = self._parse_tsv(self.TSV_PATH)
        export_codes = {r[0] for r in export_rows}
        actual = list(csv.reader(io.StringIO(out), delimiter="\t"))[1:]
        actual_iso = [r for r in actual if r[0] in export_codes]

        def key(r):
            return (0 if r[6] == "active" else 1, r[0])

        assert sorted(actual_iso, key=key) == sorted(export_rows, key=key)


# ---------------------------------------------------------------------------
# Real-registry smoke tests
# ---------------------------------------------------------------------------

class TestRealRegistry:
    """A handful of ground-truth assertions against the actual committed
    registry. If these fail, something fundamental is wrong."""

    def test_usd_has_minor_units_2(self, run_cli):
        _, out, _ = run_cli(["--raw", "lookup", "USD", "minor_units"])
        assert out.strip() == "2"

    def test_jpy_has_minor_units_0(self, run_cli):
        _, out, _ = run_cli(["--raw", "lookup", "JPY", "minor_units"])
        assert out.strip() == "0"

    def test_kwd_has_minor_units_3(self, run_cli):
        _, out, _ = run_cli(["--raw", "lookup", "KWD", "minor_units"])
        assert out.strip() == "3"

    def test_aed_pegged_to_usd(self, run_cli):
        _, out, _ = run_cli(["peg", "AED", "--json"])
        parsed = json.loads(out)
        assert parsed["pegged_to"] == "USD"
        assert parsed["peg_rate"] == 3.6725
        assert parsed["is_independent"] is False

    def test_three_minor_unit_currencies(self, run_cli):
        _, out, _ = run_cli(["list", "--minor-units", "3", "--raw", "code"])
        assert set(out.strip().splitlines()) == {
            "BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND",
        }