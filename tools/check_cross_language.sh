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
# All four suites are required. A suite whose toolchain is missing is
# reported as NOT RUN and fails the check: "could not check" is not
# "passed". The one way to excuse a suite is to name it, so the exception
# is visible in the command line and in the output:
#
#   bash tools/check_cross_language.sh --allow-skip go --allow-skip rust
#
# Usage:
#   bash tools/check_cross_language.sh
#   bash tools/check_cross_language.sh --allow-skip LANG   # repeatable
#   bash tools/check_cross_language.sh --verbose           # stream suite output
#
#   LANG is one of: python, javascript, go, rust (any case).
#
# Exit codes:
#   0  every required suite ran and passed
#   1  at least one suite that ran failed
#   2  usage error, or no suite ran at all
#   3  no suite failed, but a required suite did not run (toolchain missing
#      and not named in --allow-skip)

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_OK=0
EXIT_FAIL=1
EXIT_FATAL=2
EXIT_NOT_RUN=3

VERBOSE=false
ALLOWED=""        # lowercase language keys named by --allow-skip

usage() {
    cat <<'USAGE'
Usage: bash tools/check_cross_language.sh [--allow-skip LANG]... [--verbose]

Runs the Python, JavaScript, Go, and Rust wrapper suites against
tests/cross_language_consistency.json. All four are required: a suite whose
toolchain is missing is reported as NOT RUN and fails the check.

  --allow-skip LANG  excuse one suite (python, javascript, go, or rust);
                     repeatable; the exception is printed
  --verbose, -v      stream suite output

Exit codes:
  0  every required suite ran and passed
  1  at least one suite that ran failed
  2  usage error, or no suite ran at all
  3  a required suite did not run
USAGE
}

usage_error() {
    printf 'error: %s\n' "$1" >&2
    exit "$EXIT_FATAL"
}

add_allowed() {
    local key
    key="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    case "$key" in
        python|javascript|go|rust) ALLOWED="$ALLOWED $key" ;;
        *) usage_error "unknown language '$1' (expected python, javascript, go, or rust)" ;;
    esac
}

is_allowed() {
    case " $ALLOWED " in
        *" $1 "*) return 0 ;;
    esac
    return 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --allow-skip)
            if [[ $# -lt 2 ]]; then
                usage_error "--allow-skip needs a language (python, javascript, go, or rust)"
            fi
            add_allowed "$2"; shift 2 ;;
        --allow-skip=*) add_allowed "${1#--allow-skip=}"; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --strict)
            usage_error "--strict was removed: a suite that does not run now fails by default (use --allow-skip LANG to excuse one)" ;;
        --help|-h) usage; exit 0 ;;
        *) usage_error "unknown flag: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

PASSED=0
FAILED=0
NOT_RUN=0
NOT_RUN_NAMES=""      # display names of required suites that did not run
NOT_RUN_KEYS=""       # their --allow-skip keys, for the hint
ALLOWED_NAMES=""      # display names of suites excused by --allow-skip

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

# A suite that could not run. Excused only if --allow-skip named it.
report_not_run() {
    local name="$1" key="$2" reason="$3"
    if is_allowed "$key"; then
        printf '  %-12s - allowed skip (%s)\n' "$name" "$reason"
        ALLOWED_NAMES="$ALLOWED_NAMES $name"
    else
        printf '  %-12s ! NOT RUN (%s)\n' "$name" "$reason"
        NOT_RUN=$((NOT_RUN + 1))
        NOT_RUN_NAMES="$NOT_RUN_NAMES $name"
        NOT_RUN_KEYS="$NOT_RUN_KEYS $key"
    fi
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
    report_not_run "Python" python "python3 not found"
fi

# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

if command -v node >/dev/null 2>&1; then
    run_suite "JavaScript" node wrappers/javascript/test.js
else
    report_not_run "JavaScript" javascript "node not found"
fi

# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

if command -v go >/dev/null 2>&1; then
    run_suite "Go" bash -c 'cd wrappers/go && go test ./... -count=1'
else
    report_not_run "Go" go "go not found"
fi

# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

if command -v cargo >/dev/null 2>&1; then
    run_suite "Rust" bash -c 'cd wrappers/rust && cargo test --quiet'
else
    report_not_run "Rust" rust "cargo not found"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo

RAN=$((PASSED + FAILED))

# "Go Rust" -> "Go, Rust"
not_run_list="${NOT_RUN_NAMES# }"; not_run_list="${not_run_list// /, }"
allowed_list="${ALLOWED_NAMES# }"; allowed_list="${allowed_list// /, }"

if [[ "$FAILED" -gt 0 ]]; then
    echo "FAIL: $FAILED of $RAN wrapper suite(s) that ran failed"
    if [[ "$NOT_RUN" -gt 0 ]]; then
        echo "FAIL: $NOT_RUN required suite(s) did not run: $not_run_list"
    fi
    exit "$EXIT_FAIL"
fi

if [[ "$RAN" -eq 0 ]]; then
    echo "FATAL: no wrapper suite ran"
    exit "$EXIT_FATAL"
fi

if [[ "$NOT_RUN" -gt 0 ]]; then
    echo "FAIL: $NOT_RUN required suite(s) did not run: $not_run_list"
    hint=""
    for key in $NOT_RUN_KEYS; do
        hint="$hint --allow-skip $key"
    done
    echo "      To skip on purpose: bash tools/check_cross_language.sh${hint}"
    exit "$EXIT_NOT_RUN"
fi

if [[ -n "$ALLOWED_NAMES" ]]; then
    echo "OK: $PASSED wrapper suite(s) passed; allowed to skip: $allowed_list"
else
    echo "OK: all $PASSED wrapper suites passed"
fi

exit "$EXIT_OK"
