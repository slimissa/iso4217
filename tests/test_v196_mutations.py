"""
The v1.9.6 mutation sweep (hygiene rule 10: a check that cannot fail is not a check).

Every fix in v1.9.6 has at least one mutant here: a copy of the project with one defect put back (usually the v1.9.5 behaviour),
run against the tests or the check that is supposed to notice. A mutant is *killed* when that command succeeds on the unmutated
copy (the control) and fails on the mutated one. A survivor means the guard is decoration; it is fixed in the tests or the code,
never accepted.

Kinds: "pytest" (a test file, optionally -k), "go" (go test -run in wrappers/go), "cargo" (cargo test with a name filter in
wrappers/rust) and "shell" (a command run from the copy's root: the formatting mutants are killed by the gate's own check,
because a formatting defect is exactly what that check exists to see). The machinery is the v1.9.5 sweep's
(tests/test_v195_mutations.py): the same project copy, edits in the copy only, an anchor that must match exactly once. Go, Rust
and the formatting cases need those toolchains; a case that cannot run fails (hygiene rule 7) rather than being skipped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from test_gate_mutations import pristine, tree  # noqa: F401  (fixtures)

PY = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
_CARGO_TARGET = Path(tempfile.gettempdir()) / "iso4217-v196-mutation-cargo-target"


@dataclass(frozen=True)
class Mutant:
    id: str
    fix: str                                     # the v1.9.6 patch the mutant puts back
    defect: str
    edits: tuple[tuple[str, str, str], ...]      # (relative path, text that must occur exactly once, replacement)
    kind: str                                    # "pytest", "go", "cargo" or "shell"
    target: str                                  # pytest file; go -run regexp; cargo test filter; shell command
    expr: str = ""                               # pytest -k expression


def M(id, fix, defect, edits, target, expr="", kind="pytest"):
    return Mutant(id, fix, defect, tuple(edits), kind, target, expr)


RS = "wrappers/rust/src/lib.rs"
GO = "wrappers/go/iso4217.go"
GO_CO = "wrappers/go/collection_order_test.go"
PYW = "wrappers/python/iso4217.py"
JS = "wrappers/javascript/index.js"
JS_LC = "wrappers/javascript/lookup_contract.test.js"
JS_CO = "wrappers/javascript/collection_order.test.js"
XL = "tools/check_cross_language.sh"
FMT = "tools/check_formatting.sh"
REL = "scripts/release.sh"
TRG = "scripts/workflow_triggers.py"
CHK = "tools/check_verification_doc.py"
WF = ".github/workflows/validate.yml"
FIX = "tests/cross_language_consistency.json"

T_CO = "tests/test_wrapper_collection_order.py"
T_LC = "tests/test_wrapper_lookup_contract.py"
T_FMT = "tests/test_check_formatting.py"
T_TRG = "tests/test_workflow_triggers.py"
T_H = "tests/test_release_harness.py"
T_VER = "tests/test_check_verification_doc.py"

GO_ORDER_TESTS = "TestCollectionOrderFixture|TestCollectionsAreInFileOrder|TestEveryFilterKeepsFileOrder|TestARepeatedCode"
MAP_WALK = "res := []*Currency{{}}\n\tfor _, c := range {m} {{\n\t\tres = append(res, c)\n\t}}\n\treturn res"
QUOTE_GUARD = ('    masked, unclosed = _mask_code(block)\n    if unclosed is not None or masked.strip():\n'
               '        raise AssertionError("quote_block produced a block its own content can escape")  # unreachable by construction\n')
V195_FENCE = ("            printf '### %s %s\\n\\n```\\n' \"$mark\" \"$name\"\n"
              "            printf '%s\\n' \"$output\" | tail -20 | sed -e 's/^```/    ```/' -e 's/^~~~/    ~~~/'\n"
              "            printf '```\\n\\n'")
V196_FENCE = ("            printf '### %s %s\\n\\n' \"$mark\" \"$name\"\n"
              "            printf '%s\\n' \"$output\" | tail -20 | python3 tools/check_verification_doc.py --quote\n"
              "            printf '\\n'")
V195_COVERED = ('''    actual="$(python3 scripts/workflow_triggers.py --polled .github/workflows 2>&1)" || rc=$?''',
                '''    actual="$(find .github/workflows -maxdepth 1 \\( -name '*.yml' -o -name '*.yaml' \\) -exec basename {} \\; '''
                '''| grep -v -E '^(monitor|fetch|refresh|update|schedule)' || true)"''')

MUTANTS = [
    # -- 01: Rust and Go return file order ------------------------------------------------------------------------------
    M("W01-rust-all-active-in-hash-order", "01", "all_active() walks the HashMap",
      [(RS, "        self.active_in_order().collect()", "        self.active.values().collect()")],
      "collection_order", kind="cargo"),
    M("W02-rust-all-currencies-in-hash-order", "01", "all_currencies() walks the HashMap",
      [(RS, "        self.all_order.iter().map(|code| &self.all[code]).collect()", "        self.all.values().collect()")],
      "collection_order", kind="cargo"),
    M("W03-rust-filters-in-hash-order", "01", "pegged_to() and every filter walk the HashMap",
      [(RS, "        self.active_order.iter().map(move |code| &self.active[code])", "        self.active.values()")],
      "collection_order", kind="cargo"),
    M("W04-rust-a-repeated-code-is-listed-twice", "01", "the order index records a code each time it is seen",
      [(RS, "    if !map.contains_key(&code) {\n        order.push(code.clone());\n    }", "    order.push(code.clone());")],
      "collection_order", kind="cargo"),
    M("W05-go-all-active-in-map-order", "01", "AllActive() ranges over the Go map (random order)",
      [(GO, "\treturn inOrder(r.active, r.activeOrder)", "\t" + MAP_WALK.format(m="r.active"))],
      GO_ORDER_TESTS, kind="go"),
    M("W06-go-all-currencies-in-map-order", "01", "AllCurrencies() ranges over the Go map",
      [(GO, "\treturn inOrder(r.all, r.allOrder)", "\t" + MAP_WALK.format(m="r.all"))],
      GO_ORDER_TESTS, kind="go"),
    # -- 02: the collection_order group, read by every runner ---------------------------------------------------------
    M("W07-the-javascript-runner-skips-the-group", "02", "check_cross_language.sh does not run the JS order suite",
      [(XL, " && node collection_order.test.js'", "'")],
      T_CO, "every_suite_that_reads_the_group"),
    M("W08-the-python-runner-skips-the-group", "02", "check_cross_language.sh does not run the Python order tests",
      [(XL, " tests/test_wrapper_collection_order.py -q", " -q")],
      T_CO, "every_suite_that_reads_the_group"),
    M("W09-the-javascript-suite-skips-pegged-to", "02", "the JS suite compares the collections only",
      [(JS_CO, "  for (const [anchor, codes] of Object.entries(c.pegged_to)) {",
        "  for (const [anchor, codes] of Object.entries({})) {")],
      T_CO, "JavaScriptWrapper"),
    M("W10-the-go-suite-skips-pegged-to", "02", "the Go suite compares the collections only",
      [(GO_CO, "\t\tfor anchor, want := range c.PeggedTo {", "\t\tfor anchor, want := range map[string][]string{} {")],
      "TestCollectionOrderFixture", kind="go"),
    M("W11-the-rust-suite-skips-pegged-to", "02", "the Rust suite compares the collections only",
      [(RS, 'for (anchor, expected) in case["pegged_to"].as_object().unwrap() {',
        "for (anchor, expected) in serde_json::Map::new().iter() {")],
      "collection_order_fixture", kind="cargo"),
    M("W12-the-fixture-loses-an-anchor-xaf", "02", "the audit's anchor XAF is not pinned",
      [(FIX, '        "XAF": [],\n', "")],
      T_CO, "required_anchors or declared_count"),
    # -- 03: Python TypeError for country and anchor codes --------------------------------------------------------------
    M("W13-python-pegged-to-takes-a-non-string", "03", "pegged_to(None) is an AttributeError again",
      [(PYW, "        anchor = _require_code(anchor_code)", "        anchor = anchor_code.upper()")],
      T_LC, "TestPythonWrapper and (pegged_to or module_level)"),
    M("W14-python-issued-by-takes-a-non-string", "03", "issued_by(None) is an AttributeError again",
      [(PYW, "            List of Currency objects issued by that country.\n\n        Raises:\n"
             "            TypeError: if `country_code` is not a string (None included).\n        \"\"\"\n"
             "        code = _require_code(country_code)",
        "            List of Currency objects issued by that country.\n\n        Raises:\n"
        "            TypeError: if `country_code` is not a string (None included).\n        \"\"\"\n"
        "        code = country_code.upper()")],
      T_LC, "TestPythonWrapper and issued_by"),
    M("W15-python-used-in-takes-a-non-string", "03", "used_in(None) is an AttributeError again",
      [(PYW, "            List of Currency objects used in that country.\n\n        Raises:\n"
             "            TypeError: if `country_code` is not a string (None included).\n        \"\"\"\n"
             "        code = _require_code(country_code)",
        "            List of Currency objects used in that country.\n\n        Raises:\n"
        "            TypeError: if `country_code` is not a string (None included).\n        \"\"\"\n"
        "        code = country_code.upper()")],
      T_LC, "TestPythonWrapper and used_in"),
    M("W16-the-invalid-input-set-loses-pegged-to", "03", "the shared vectors stop covering pegged_to",
      [(FIX, '        "contains",\n        "pegged_to",\n', '        "contains",\n')],
      T_LC, "TestTheFixture"),
    # -- 04: JavaScript TypeError for country and anchor codes ----------------------------------------------------------
    M("W17-javascript-pegged-to-takes-a-non-string", "04", "peggedTo(null) is an incidental TypeError again",
      [(JS, "    const anchor = requireCode(anchorCode);", "    const anchor = anchorCode.toUpperCase();")],
      T_LC, "JavaScriptWrapper"),
    M("W18-javascript-issued-by-takes-a-non-string", "04", "issuedBy(null) is an incidental TypeError again",
      [(JS, "  issuedBy(countryCode) {\n    const code = requireCode(countryCode);",
        "  issuedBy(countryCode) {\n    const code = countryCode.toUpperCase();")],
      T_LC, "JavaScriptWrapper"),
    M("W19-javascript-used-in-takes-a-non-string", "04", "usedIn(null) is an incidental TypeError again",
      [(JS, "  usedIn(countryCode) {\n    const code = requireCode(countryCode);",
        "  usedIn(countryCode) {\n    const code = countryCode.toUpperCase();")],
      T_LC, "JavaScriptWrapper"),
    M("W20-the-javascript-suite-ignores-the-new-methods", "04", "the JS suite skips the methods it cannot map",
      [(JS_LC, "  pegged_to: 'peggedTo', issued_by: 'issuedBy', used_in: 'usedIn',\n", "")],
      T_LC, "JavaScriptWrapper"),
    # -- 05 and 06: the formatting itself (killed by the gate's check, run for real) -------------------------------------
    M("W21-a-go-file-is-not-gofmt-formatted", "05", "a Go source drifts from gofmt",
      [(GO, "func inOrder(m map[string]*Currency, order []string) []*Currency {",
        "func inOrder(m map[string]*Currency,  order []string) []*Currency {")],
      "bash tools/check_formatting.sh go", kind="shell"),
    M("W22-a-rust-file-is-not-rustfmt-formatted", "06", "a Rust source drifts from rustfmt",
      [(RS, "    if !map.contains_key(&code) {\n", "    if !map.contains_key(&code)  {\n")],
      "bash tools/check_formatting.sh rust", kind="shell"),
    # -- 07: the formatting gate ----------------------------------------------------------------------------------------
    M("W23-the-gate-drops-the-format-step", "07", "CI checks formatting and the release gate does not",
      [(REL, '    run_gate_step "check_formatting.sh"             bash tools/check_formatting.sh\n', "")],
      "tests/test_ci_parity.py", "every_tool_a_workflow_runs"),
    M("W24-ci-does-not-install-rustfmt", "07", "CI's Rust leg cannot run cargo fmt",
      [(WF, "        with:\n          components: rustfmt\n", "")],
      T_FMT, "installs_rustfmt"),
    M("W25-an-unformatted-go-file-passes", "07", "gofmt -l output is ignored",
      [(FMT, '    elif [[ -n "$out" ]]; then', "    elif false; then")],
      T_FMT, "TestNotFormatted"),
    M("W26-could-not-run-passes", "07", "a missing toolchain is reported as formatted",
      [(FMT, 'if [[ "$NOT_RUN" -gt 0 ]]; then\n    exit 3', "if false; then\n    exit 3")],
      T_FMT, "TestCouldNotRun"),
    # -- 08: polling decided by trigger ---------------------------------------------------------------------------------
    M("W27-the-name-prefix-exemption-is-back", "08", "a push-triggered update-docs.yml is not polled",
      [(REL, *V195_COVERED)],
      T_H, "workflows_covered"),
    M("W28-a-polled-workflow-no-push-runs-is-accepted", "08", "only one direction of 'polled iff push' is checked",
      [(REL, '        if ! printf \'%s\\n\' "$actual" | grep -qxF -- "$d"; then', "        if false; then")],
      T_H, "workflows_covered"),
    M("W29-the-yaml-1-1-on-trap", "08", "an unquoted on: key is not read (a YAML 1.1 loader's True)",
      [(TRG, '''_ON_KEY = re.compile(r"""^(?:on|"on"|'on')[ \\t]*:(?:[ \\t]+(.*))?$""")''',
        '''_ON_KEY = re.compile(r"""^(?:"on"|'on')[ \\t]*:(?:[ \\t]+(.*))?$""")''')],
      T_TRG, ""),
    M("W30-an-unreadable-workflow-is-skipped", "08", "the helper fails open on a workflow it cannot read",
      [(TRG, '            print(f"UNREADABLE: {e}", file=sys.stderr)\n        return EXIT_UNREADABLE\n',
        '            print(f"UNREADABLE: {e}", file=sys.stderr)\n')],
      T_TRG, "unreadable or missing"),
    M("W31-a-trigger-setting-counts-as-a-trigger", "08", "a nested key named push (an input) makes a workflow polled",
      [(TRG, "        if len(c) - len(c.lstrip()) != indent:\n            continue", "        if False:\n            continue")],
      T_TRG, "TestTheFormsGitHubAccepts"),
    # -- 09: quoted gate output stays fenced ----------------------------------------------------------------------------
    M("W32-the-v195-sed-fence-is-back", "09", "an indented or form-fed fence line closes the quoted block",
      [(REL, V196_FENCE, V195_FENCE)],
      T_H, "banned_word_in_a_claim_output_line"),
    M("W33-the-fence-is-always-three-backticks", "09", "a fence line in the output closes the block",
      [(CHK, '    fence = "`" * max(3, longest + 1)', '    fence = "```"'), (CHK, QUOTE_GUARD, "")],
      T_VER, "QuotedGateOutput"),
    M("W34-the-quote-splits-on-newline-only", "09", "a form feed or a line separator starts a hidden line",
      [(CHK, "    lines = text.splitlines()\n    longest", '    lines = text.split("\\n")\n    longest'), (CHK, QUOTE_GUARD, "")],
      T_VER, "QuotedGateOutput"),
    M("W35-one-banned-word-is-left-unfenced", "09", "a line holding FIXME is written after the closing fence",
      [(CHK, '    block = fence + "\\n" + "".join(line + "\\n" for line in lines) + fence + "\\n"',
        '    block = (fence + "\\n" + "".join(line + "\\n" for line in lines if "FIXME" not in line) + fence + "\\n"\n'
        '             + "".join(line + "\\n" for line in lines if "FIXME" in line))'),
       (CHK, QUOTE_GUARD, "")],
      T_VER, "QuotedGateOutput"),
]


def _apply(tree_root: Path, m: Mutant) -> None:
    for rel, old, new in m.edits:
        path = tree_root / rel
        text = path.read_text(encoding="utf-8")
        n = text.count(old)
        assert n == 1, f"{m.id}: the anchor occurs {n} times in {rel} (must be exactly 1): {old[:80]!r}"
        assert old != new
        path.write_text(text.replace(old, new), encoding="utf-8")


def _command(m: Mutant, root: Path) -> tuple[list[str], Path, dict]:
    env = {k: v for k, v in os.environ.items() if k not in ("RH_RELEASE_SH", "RH_BUMP_PY")}
    if m.kind == "pytest":
        return PY + [m.target] + (["-k", m.expr] if m.expr else []), root, env
    if m.kind == "shell":
        return m.target.split(), root, env
    if m.kind == "go":
        env.update(GOFLAGS="-mod=mod")
        return ["go", "test", "-run", m.target, "-count=1", "."], root / "wrappers" / "go", env
    env.update(CARGO_TARGET_DIR=str(_CARGO_TARGET))
    # A shared target directory plus mtimes preserved by the copy let cargo reuse a binary built from another copy. Touch the
    # crate's sources so it is always rebuilt; the dependencies stay cached.
    for src in (root / "wrappers" / "rust").rglob("*.rs"):
        os.utime(src, None)
    return ["cargo", "test", "--lib", m.target, "--quiet"], root / "wrappers" / "rust", env


def _run(m: Mutant, root: Path) -> subprocess.CompletedProcess:
    cmd, cwd, env = _command(m, root)
    needed = {"go": ["go"], "cargo": ["cargo"], "shell": ["gofmt", "cargo"]}.get(m.kind, [cmd[0]])
    for tool in needed:
        if shutil.which(tool) is None:
            pytest.fail(f"{m.id}: {tool} is not installed; a mutant that cannot run is not a pass (hygiene rule 7)")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, timeout=1500)


_controls: dict[tuple, int] = {}


@pytest.mark.parametrize("m", MUTANTS, ids=lambda m: m.id)
def test_every_mutant_is_killed(m: Mutant, pristine, tree):  # noqa: F811
    key = (m.kind, m.target, m.expr)
    if key not in _controls:
        control = _run(m, pristine)
        assert control.returncode == 0, f"{m.id}: the control is red on the unmutated copy:\n{(control.stdout + control.stderr)[-1500:]}"
        _controls[key] = control.returncode
    _apply(tree, m)
    mutated = _run(m, tree)
    assert mutated.returncode != 0, f"{m.id}: SURVIVED. The guard passes with this defect put back: {m.defect}"
    if m.kind == "pytest":
        assert mutated.returncode == 1, (
            f"{m.id}: pytest exited {mutated.returncode} (not a test failure):\n{(mutated.stdout + mutated.stderr)[-1200:]}")


def test_every_fix_has_a_mutant_and_ids_are_unique():
    ids = [m.id for m in MUTANTS]
    assert len(ids) == len(set(ids))
    assert {m.fix for m in MUTANTS} >= {f"{n:02d}" for n in range(1, 10)}, "fixes 01 to 09 each need at least one mutant"


def test_every_target_file_exists():
    root = Path(__file__).resolve().parent.parent
    for m in MUTANTS:
        for rel, _old, _new in m.edits:
            assert (root / rel).is_file(), f"{m.id}: {rel} does not exist"
        if m.kind == "pytest":
            assert (root / m.target).is_file(), f"{m.id}: {m.target} does not exist"
