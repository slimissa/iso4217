"""
The v1.9.7 mutation sweep (hygiene rule 10: a check that cannot fail is not a check).

Every v1.9.7 item has at least one mutant here: a copy of the project with one defect put in, run against the test or check
that must notice. Killed = that command passes on the unmutated copy (the control) and fails on the mutated one.

Items 01 to 05 (the data corrections and what depends on them) stopped under the release's rule D2: no attached primary
source gives the day CUC, USS or ANG ceased to be legal tender. Their mutants therefore attack the guards that hold the
stopped state: the dated exceptions of tests/test_six_list_one_parity.py, the ISO 3166 snapshot's checksum, and the rule that
`source.verified_against` names no SIX list while a correction is blocked.

Kinds: "pytest" (a test file, optionally -k) and "shell" (a command run from the copy's root). The machinery is the v1.9.6
sweep's: the same project copy, edits in the copy only, an anchor that must match exactly once.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from test_gate_mutations import pristine, tree  # noqa: F401  (fixtures)

PY = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]


@dataclass(frozen=True)
class Mutant:
    id: str
    fix: str
    defect: str
    edits: tuple[tuple[str, str, str], ...]
    kind: str
    target: str
    expr: str = ""


def M(id, fix, defect, edits, target, expr="", kind="pytest"):
    return Mutant(id, fix, defect, tuple(edits), kind, target, expr)


PARITY = "tests/test_six_list_one_parity.py"
REG = "iso4217.json"
SNAP = "tools/iso3166_snapshot.json"
FACTS = "tests/fixtures/six_list_one_facts.json"
SIXF = "tools/six_facts.py"
PKG = "wrappers/javascript/package.json"
WF = ".github/workflows/validate.yml"
XL = "tools/check_cross_language.sh"
REL = "scripts/release.sh"
ADR15 = "docs/decisions/wrapper-lookup-contract.md"
ADR10 = "docs/decisions/country-currency-taxonomy.md"
CONTRIB = "CONTRIBUTING.md"

CW_SNAPSHOT = ('        "alpha_2": "CW",\n        "alpha_3": "CUW",\n        "borders": [],\n        "calling_codes": [\n'
               '          "599"\n        ],\n        "currency_codes": [\n          "ANG"\n        ],')

MUTANTS = [
    # -- 01, 02, 04: the stopped data corrections; the parity guard holds each code's state ---------------------------
    # X01 since the second v1.9.7 bundle: CUC landed, so its exception is gone; putting it back must fail as stale.
    M("X01-cuc-blocked-exception-put-back", "01", "CUC moved to withdrawn but its blocked exception was kept",
      [(PARITY, '    "USS": ("not_in_list_one", BLOCKED, "2027-03-31"),\n',
        '    "USS": ("not_in_list_one", BLOCKED, "2027-03-31"),\n    "CUC": ("not_in_list_one", BLOCKED, "2027-03-31"),\n')],
      PARITY, "each_is_still_needed"),
    M("X02-uss-blocked-exception-dropped", "02", "USS stays active with no exception",
      [(PARITY, '    "USS": ("not_in_list_one", BLOCKED, "2027-03-31"),\n', "")],
      PARITY, "every_active_code_is_in_list_one"),
    M("X03-snapshot-cw-edited-by-hand", "03", "the ISO 3166 snapshot is edited to list XCG for CW (never by hand: re-vendor)",
      [(SNAP, CW_SNAPSHOT, CW_SNAPSHOT.replace('"ANG"', '"XCG"'))],
      "python3 tools/vendor_iso3166.py --check", kind="shell"),
    M("X04-xcg-added-with-a-wrong-numeric", "04", "XCG appears in active with a numeric List One does not give",
      [(REG, '    "active": [\n',
        '    "active": [\n      {"code": "XCG", "numeric": "999", "minor_units": 2},\n')],
      PARITY, ""),
    M("X05-ang-blocked-exception-dropped", "04", "ANG stays active with no exception",
      [(PARITY, '    "ANG": ("not_in_list_one", BLOCKED, "2027-03-31"),\n', "")],
      PARITY, "every_active_code_is_in_list_one"),
    M("X06-xcg-blocked-exception-dropped", "04", "XCG stays absent with no exception",
      [(PARITY, '    "XCG": ("not_active", BLOCKED, "2027-03-31"),\n', "")],
      PARITY, "every_list_one_code_is_active"),
    # -- 05: the source metadata claims no more than the data ---------------------------------------------------------
    M("X07-list-one-claimed-as-verified", "05", "verified_against names SIX List One while corrections are blocked",
      [(REG, '      "SWIFT ISO 4217 public table",\n',
        '      "SWIFT ISO 4217 public table",\n      "SIX ISO 4217 List One (published 2026-09-17)",\n')],
      PARITY, "SourceMetadata"),
    # -- 06: the parity guard and its tool ----------------------------------------------------------------------------
    M("X08-a-fixture-row-altered", "06", "List One's numeric for EUR is changed in the fixture",
      [(FACTS, '      "code": "EUR",\n      "numeric": "978",', '      "code": "EUR",\n      "numeric": "979",')],
      PARITY, "numeric_code_and_minor_units_agree"),
    M("X09-an-exception-past-its-expiry", "06", "a deferred exception expired and still excuses its code",
      [(PARITY, '    "XBA": ("not_active", DEFERRED, "2027-03-31"),', '    "XBA": ("not_active", DEFERRED, "2026-01-31"),')],
      PARITY, "none_has_expired"),
    M("X10-a-stale-exception-kept", "06", "an exception for a code that already agrees (USD) is accepted",
      [(PARITY, '    "XBA": ("not_active", DEFERRED, "2027-03-31"),',
        '    "XBA": ("not_active", DEFERRED, "2027-03-31"),\n    "USD": ("not_active", DEFERRED, "2027-03-31"),')],
      PARITY, "each_is_still_needed"),
    M("X11-six-facts-writes-zero-for-na", "06", "the tool writes minor units 0 for List One's N.A.",
      [(SIXF, 'None if minor in ("", "N.A.") else int(minor)', '0 if minor in ("", "N.A.") else int(minor)')],
      "tests/test_six_facts.py", ""),
    # -- 07 to 10: coverage and harness ---------------------------------------------------------------------------------
    M("X12-npm-test-loses-a-suite", "07", "npm test stops running collection_order.test.js",
      [(PKG, " && node collection_order.test.js", "")],
      "tests/test_js_test_script.py", ""),
    M("X13-ci-cross-language-step-removed", "08", "the cross-language job no longer runs the check",
      [(WF, "      - name: Run the cross-language check\n        run: bash tools/check_cross_language.sh\n", "")],
      "tests/test_ci_topology.py", "cross_language"),
    M("X14-ci-cross-language-allows-skips", "08", "the CI job excuses missing toolchains",
      [(WF, "        run: bash tools/check_cross_language.sh\n",
        "        run: bash tools/check_cross_language.sh --allow-skip go --allow-skip rust\n")],
      "tests/test_ci_topology.py", "cross_language"),
    M("X15-the-unicode-escape-is-back", "09", "the pass mark is printf's \\u2713 again (literal under C/POSIX)",
      [(XL, "    printf '  %-12s %s pass\\n' \"$1\" \"$MARK_PASS\"", "    printf '  %-12s \\u2713 pass\\n' \"$1\"")],
      "tests/test_check_cross_language.py", "Marks"),
    M("X16-the-default-timeout-is-300-again", "10", "release.sh waits 300 s for CI by default",
      [(REL, "\nPOLL_TIMEOUT=1200\n", "\nPOLL_TIMEOUT=300\n")],
      "tests/test_release_poll_timeout.py", ""),
    # -- 11 and 12: the documents ---------------------------------------------------------------------------------------
    M("X17-adr-0015-amendment-removed", "11", "ADR 0015 no longer states the collection-order contract",
      [(ADR15, "## Amendment 1 (v1.9.6): collection order", "## Notes")],
      "tests/test_decision_records_v197.py", ""),
    M("X18-cuc-question-reopened", "11", "ADR 0010 says again that the CUC question is not decided",
      [(ADR10, "Open question, answered in v1.9.7:** whether CUC", "Open question, not decided here:** whether CUC")],
      "tests/test_decision_records_v197.py", ""),
    M("X19-the-stale-count-is-back", "12", "CONTRIBUTING states a test count again",
      [(CONTRIB, "Every test must pass and none may be skipped", "Expect **768 tests passing**. Every test must pass and none may be skipped")],
      "tests/test_contributing_counts.py", ""),
]


def _apply(tree_root: Path, m: Mutant) -> None:
    for rel, old, new in m.edits:
        path = tree_root / rel
        text = path.read_text(encoding="utf-8")
        n = text.count(old)
        assert n == 1, f"{m.id}: the anchor occurs {n} times in {rel} (must be exactly 1): {old[:80]!r}"
        assert old != new
        path.write_text(text.replace(old, new), encoding="utf-8")


def _run(m: Mutant, root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("RH_RELEASE_SH", "RH_BUMP_PY")}
    if m.kind == "pytest":
        cmd = PY + [m.target] + (["-k", m.expr] if m.expr else [])
    else:
        cmd = m.target.split()
    if shutil.which(cmd[0]) is None and not Path(cmd[0]).exists():
        pytest.fail(f"{m.id}: {cmd[0]} is not installed (hygiene rule 7)")
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env, timeout=900)


_controls: dict[tuple, int] = {}


@pytest.mark.parametrize("m", MUTANTS, ids=lambda m: m.id)
def test_every_mutant_is_killed(m: Mutant, pristine, tree):  # noqa: F811
    key = (m.kind, m.target, m.expr)
    if key not in _controls:
        control = _run(m, pristine)
        assert control.returncode == 0, f"{m.id}: the control is red:\n{(control.stdout + control.stderr)[-1500:]}"
        _controls[key] = 0
    _apply(tree, m)
    mutated = _run(m, tree)
    assert mutated.returncode != 0, f"{m.id}: SURVIVED. The guard passes with this defect: {m.defect}"
    if m.kind == "pytest":
        assert mutated.returncode == 1, f"{m.id}: pytest exited {mutated.returncode}:\n{(mutated.stdout + mutated.stderr)[-1200:]}"


def test_every_item_has_a_mutant_and_ids_are_unique():
    ids = [m.id for m in MUTANTS]
    assert len(ids) == len(set(ids))
    assert {m.fix for m in MUTANTS} >= {f"{n:02d}" for n in range(1, 13)}, "items 01 to 12 each need at least one mutant"


def test_every_target_file_exists():
    root = Path(__file__).resolve().parent.parent
    for m in MUTANTS:
        for rel, _old, _new in m.edits:
            assert (root / rel).is_file(), f"{m.id}: {rel} does not exist"
        if m.kind == "pytest":
            assert (root / m.target).is_file(), f"{m.id}: {m.target} does not exist"
