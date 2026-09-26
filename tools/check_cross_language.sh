#!/usr/bin/env bash
#
# tools/check_cross_language.sh — one command that proves all four
# language wrappers agree on tests/cross_language_consistency.json.
#
# Each wrapper's test suite already reads that fixture. This script
# runs all four suites and reports a single pass/fail, so a divergence
# in one language surfaces without a maintainer having to remember
# that there are four places to look.
#
# Missing toolchains are reported as SKIP, not FAIL. A developer who
# has Python and Node but not Rust is not blocked; CI, which installs
# all four, runs the strict path.
#
# Usage:
#   bash tools/check_cross_language.sh
#   bash tools/check_cross_language.sh --strict    # treat SKIP as FAIL
#   bash tools/check_cross_language.sh --verbose   # stream suite output
#
# Exit codes:
#   0  every available suite passed
#   1  at least one suite failed
#   2  no suite could be run at all

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_OK=0
EXIT_FAIL=1
EXIT_FATAL=2

STRICT=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --strict)  STRICT=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h)
            sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) printf 'unknown flag: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

PASSED=0
FAILED=0
SKIPPED=0

# ---------------------------------------------------------------------------
# Reporters
# ---------------------------------------------------------------------------

report_pass() {
    printf '  %-12s \u2713 pass\n' "$1"
    PASSED=$((PASSED + 1))
}

report_fail() {
    local name="$1"
    shift
    printf '  %-12s \u2717 FAIL\n' "$name"
    printf '%s\n' "$@" | tail -20 | sed 's/^/      /'
    FAILED=$((FAILED + 1))
}

report_skip() {
    printf '  %-12s \u00b7 skipped (%s)\n' "$1" "$2"
    SKIPPED=$((SKIPPED + 1))
}

# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------

run_suite() {
    local name="$1"
    shift
    local output

    if $VERBOSE; then
        printf '  %-12s running: %s\n' "$name" "$*"
        if "$@"; then
            report_pass "$name"
        else
            report_fail "$name" "(see output above)"
        fi
        return
    fi

    if output=$("$@" 2>&1); then
        report_pass "$name"
    else
        report_fail "$name" "$output"
    fi
}

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Cross-language consistency — four wrappers, one fixture"
echo "============================================================"
echo "  Fixture: tests/cross_language_consistency.json"
echo

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

if command -v python3 >/dev/null 2>&1; then
    run_suite "Python" python3 -m pytest tests/test_wrappers.py -q
else
    report_skip "Python" "python3 not found"
fi

# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

if command -v node >/dev/null 2>&1; then
    run_suite "JavaScript" node wrappers/javascript/test.js
else
    report_skip "JavaScript" "node not found"
fi

# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

if command -v go >/dev/null 2>&1; then
    run_suite "Go" bash -c 'cd wrappers/go && go test ./... -count=1'
else
    report_skip "Go" "go not found"
fi

# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

if command -v cargo >/dev/null 2>&1; then
    run_suite "Rust" bash -c 'cd wrappers/rust && cargo test --quiet'
else
    report_skip "Rust" "cargo not found"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo

TOTAL=$((PASSED + FAILED + SKIPPED))

if [[ "$TOTAL" -eq 0 ]]; then
    echo "FATAL: no wrapper suites could be run"
    exit "$EXIT_FATAL"
fi

if [[ "$FAILED" -gt 0 ]]; then
    echo "FAIL: $FAILED of $TOTAL wrapper suite(s) failed"
    exit "$EXIT_FAIL"
fi

if $STRICT && [[ "$SKIPPED" -gt 0 ]]; then
    echo "FAIL (--strict): $SKIPPED suite(s) skipped"
    exit "$EXIT_FAIL"
fi

if [[ "$SKIPPED" -gt 0 ]]; then
    echo "OK: $PASSED wrapper suite(s) passed, $SKIPPED skipped"
else
    echo "OK: all $PASSED wrapper suites passed"
fi

exit "$EXIT_OK"