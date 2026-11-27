#!/usr/bin/env bash
#
# tools/check_formatting.sh -- fail when the Go or Rust wrapper sources are not formatted.
#
# The third audit pass (open item 7) found `gofmt -l` listing two files and `rustfmt` reporting 45 differences, with no
# gate step and no CI step looking. v1.9.6 formatted both wrappers; this script keeps them formatted. It is the one
# command the release gate and CI both call (RELEASE_PATTERN.md, hygiene rule 7).
#
#   go    `gofmt -l wrappers/go` must print nothing
#   rust  `cargo fmt --check` in wrappers/rust must exit 0
#
# It reports and never rewrites: to fix a failure run `gofmt -w wrappers/go` or `cd wrappers/rust && cargo fmt`.
#
# Usage:
#   bash tools/check_formatting.sh             # Go and Rust (the release gate)
#   bash tools/check_formatting.sh go          # one language (each CI wrapper leg checks its own)
#   bash tools/check_formatting.sh rust
#
# Exit codes:
#   0  every language checked is formatted
#   1  at least one source file is not formatted (each is listed)
#   2  usage error, or a wrapper directory is missing
#   3  could not run: gofmt, cargo or the rustfmt component is not installed. "Could not check" is not "formatted";
#      the gate fails on 3 like on 1.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GO_DIR="$REPO_ROOT/wrappers/go"
RUST_DIR="$REPO_ROOT/wrappers/rust"

LANGS=()
for arg in "$@"; do
    case "$arg" in
        go|rust) LANGS+=("$arg") ;;
        -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "error: unknown argument '$arg' (expected go, rust, or nothing for both)" >&2; exit 2 ;;
    esac
done
if [[ ${#LANGS[@]} -eq 0 ]]; then
    LANGS=(go rust)
fi

FAILED=0
NOT_RUN=0

check_go() {
    if [[ ! -d "$GO_DIR" ]]; then
        echo "FATAL: $GO_DIR not found" >&2
        exit 2
    fi
    if ! command -v gofmt >/dev/null 2>&1; then
        echo "NOT RUN: gofmt is not installed; the Go wrapper cannot be checked" >&2
        NOT_RUN=$((NOT_RUN + 1))
        return
    fi
    local out rc=0
    out="$(gofmt -l "$GO_DIR" 2>&1)" || rc=$?
    if [[ "$rc" -ne 0 ]]; then
        # gofmt exits non-zero when a file does not parse: a file gofmt cannot read is not formatted.
        printf '%s\n' "$out" | tail -20
        echo "FAIL: gofmt could not read wrappers/go (exit $rc)"
        FAILED=$((FAILED + 1))
    elif [[ -n "$out" ]]; then
        printf '%s\n' "$out" | sed "s#^$REPO_ROOT/##; s#^#  not gofmt-formatted: #"
        echo "FAIL: gofmt -l lists $(printf '%s\n' "$out" | wc -l | tr -d ' ') file(s); run: gofmt -w wrappers/go"
        FAILED=$((FAILED + 1))
    else
        echo "OK: gofmt -l wrappers/go prints nothing"
    fi
}

check_rust() {
    if [[ ! -d "$RUST_DIR" ]]; then
        echo "FATAL: $RUST_DIR not found" >&2
        exit 2
    fi
    if ! command -v cargo >/dev/null 2>&1; then
        echo "NOT RUN: cargo is not installed; the Rust wrapper cannot be checked" >&2
        NOT_RUN=$((NOT_RUN + 1))
        return
    fi
    if ! (cd "$RUST_DIR" && cargo fmt --version) >/dev/null 2>&1; then
        echo "NOT RUN: cargo fmt is not available; install it with: rustup component add rustfmt" >&2
        NOT_RUN=$((NOT_RUN + 1))
        return
    fi
    local out rc=0
    out="$(cd "$RUST_DIR" && cargo fmt --check 2>&1)" || rc=$?
    if [[ "$rc" -ne 0 ]]; then
        printf '%s\n' "$out" | grep -E '^Diff in ' | sed "s#$REPO_ROOT/##; s#^#  #" | sort -u | head -40
        printf '%s\n' "$out" | grep -vE '^Diff in ' | tail -10
        echo "FAIL: cargo fmt --check exited $rc in wrappers/rust; run: cd wrappers/rust && cargo fmt"
        FAILED=$((FAILED + 1))
    else
        echo "OK: cargo fmt --check exits 0 in wrappers/rust"
    fi
}

for lang in "${LANGS[@]}"; do
    "check_$lang"
done

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
if [[ "$NOT_RUN" -gt 0 ]]; then
    exit 3
fi
exit 0
