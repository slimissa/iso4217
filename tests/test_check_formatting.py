"""
Tests for tools/check_formatting.sh (v1.9.6, the third audit pass's open item 7).

The script is driven with stub `gofmt` and `cargo` first on a PATH that holds nothing else of either toolchain, so every
exit code is tested without Go or Rust installed. The real toolchains run the same script in the release gate and in CI's
Go and Rust legs.

0 formatted, 1 not formatted (or gofmt cannot read a file), 2 usage error or missing wrapper directory, 3 could not run.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "tools" / "check_formatting.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required")

# STUB_GOFMT_OUT: lines gofmt -l prints; STUB_GOFMT_RC: its exit code.
GOFMT = """#!/bin/sh
[ "$1" = "-l" ] || exit 99
[ -n "$STUB_GOFMT_OUT" ] && printf '%s\\n' "$STUB_GOFMT_OUT"
exit ${STUB_GOFMT_RC:-0}
"""
# STUB_FMT_MISSING=1: `cargo fmt` is not installed. STUB_FMT_RC: the exit code of `cargo fmt --check`.
CARGO = """#!/bin/sh
[ "$1" = "fmt" ] || exit 99
if [ "$2" = "--version" ]; then [ -n "$STUB_FMT_MISSING" ] && exit 1; echo "rustfmt stub"; exit 0; fi
[ "$2" = "--check" ] || exit 98
if [ "${STUB_FMT_RC:-0}" != "0" ]; then echo "Diff in $PWD/src/lib.rs:12:"; echo "-    let x=1;"; fi
exit ${STUB_FMT_RC:-0}
"""


def build(tmp_path: Path, go: bool = True, rust: bool = True) -> Path:
    root = tmp_path / "proj"
    (root / "tools").mkdir(parents=True)
    if go:
        (root / "wrappers" / "go").mkdir(parents=True)
    if rust:
        (root / "wrappers" / "rust").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools" / "check_formatting.sh")
    return root


def tool_path(tmp_path: Path, gofmt: bool = True, cargo: bool = True) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("dirname", "tail", "sed", "grep", "sort", "head", "wc", "tr"):
        found = shutil.which(name)
        if found and not (bin_dir / name).exists():
            (bin_dir / name).symlink_to(found)
    for name, src, wanted in (("gofmt", GOFMT, gofmt), ("cargo", CARGO, cargo)):
        if wanted:
            p = bin_dir / name
            p.write_text(src, encoding="utf-8")
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(bin_dir)


def run(root: Path, path: str, *args: str, **env) -> tuple[int, str]:
    done = subprocess.run([BASH, str(root / "tools" / "check_formatting.sh"), *args], capture_output=True, text=True,
                          env={"PATH": path, **env}, timeout=60)
    return done.returncode, done.stdout + done.stderr


class TestFormatted:
    def test_both_formatted_exits_0(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path))
        assert code == 0, out
        assert "OK: gofmt -l wrappers/go prints nothing" in out and "OK: cargo fmt --check exits 0" in out

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_one_language_checks_only_that_language(self, tmp_path, lang):
        code, out = run(build(tmp_path), tool_path(tmp_path), lang)
        assert code == 0, out
        assert ("gofmt" in out) == (lang == "go") and ("cargo fmt" in out) == (lang == "rust")


class TestNotFormatted:
    def test_a_file_gofmt_lists_exits_1_and_is_named(self, tmp_path):
        root = build(tmp_path)
        code, out = run(root, tool_path(tmp_path), STUB_GOFMT_OUT=f"{root}/wrappers/go/iso4217.go")
        assert code == 1, out
        assert "not gofmt-formatted: wrappers/go/iso4217.go" in out

    def test_a_file_gofmt_cannot_parse_exits_1(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path), "go", STUB_GOFMT_RC="2", STUB_GOFMT_OUT="x.go:1:1: expected 'package'")
        assert code == 1, out
        assert "could not read" in out

    def test_a_rustfmt_difference_exits_1_and_names_the_file(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path), "rust", STUB_FMT_RC="1")
        assert code == 1, out
        assert "Diff in wrappers/rust/src/lib.rs" in out

    def test_go_unformatted_and_rust_missing_is_1_not_3(self, tmp_path):
        root = build(tmp_path)
        code, out = run(root, tool_path(tmp_path, cargo=False), STUB_GOFMT_OUT=f"{root}/wrappers/go/a.go")
        assert code == 1, out
        assert "NOT RUN: cargo" in out, "the language that could not run is still reported"


class TestCouldNotRun:
    def test_gofmt_missing_exits_3(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path, gofmt=False), "go")
        assert code == 3, out
        assert "NOT RUN: gofmt is not installed" in out

    def test_cargo_missing_exits_3(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path, cargo=False), "rust")
        assert code == 3, out

    def test_rustfmt_component_missing_exits_3_and_says_how_to_install_it(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path), "rust", STUB_FMT_MISSING="1")
        assert code == 3, out
        assert "rustup component add rustfmt" in out

    def test_could_not_run_is_never_reported_as_formatted(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path, gofmt=False, cargo=False))
        assert code == 3 and "OK:" not in out, out


class TestUsage:
    def test_an_unknown_argument_exits_2(self, tmp_path):
        code, out = run(build(tmp_path), tool_path(tmp_path), "python")
        assert code == 2 and "unknown argument" in out, out

    @pytest.mark.parametrize("missing", ["go", "rust"])
    def test_a_missing_wrapper_directory_exits_2(self, tmp_path, missing):
        code, out = run(build(tmp_path, **{missing: False}), tool_path(tmp_path), missing)
        assert code == 2 and "FATAL" in out, out


class TestWiring:
    """The gate, the plan and CI call the same script."""

    def test_the_gate_and_the_plan_run_it(self):
        text = (PROJECT_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
        assert 'run_gate_step "check_formatting.sh"             bash tools/check_formatting.sh\n' in text
        assert 'echo "  bash tools/check_formatting.sh"' in text

    def test_ci_checks_go_and_rust_and_installs_rustfmt(self):
        text = (PROJECT_ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        assert "run: bash tools/check_formatting.sh ${{ matrix.language }}" in text
        assert "if: matrix.language == 'go' || matrix.language == 'rust'" in text
        toolchain = text.split("dtolnay/rust-toolchain@", 1)[1].split("\n      - ", 1)[0]
        assert "components: rustfmt" in toolchain, "the Rust leg must install rustfmt or the check cannot run there"
