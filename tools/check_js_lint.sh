#!/usr/bin/env bash
#
# tools/check_js_lint.sh -- run ESLint on the JavaScript wrapper.
#
# `npm run lint` existed since v1.9.0 (F27 added eslint as a pinned devDependency)
# but nothing invoked it, in CI or in the release gate: a lint error could reach a
# tag. This script is the one command both call (v1.9.1, P5-05).
#
# It installs the wrapper's dependencies without running lifecycle scripts, then
# runs `npm run lint`. It does not run `npm audit`: audits are polled in CI, not
# gate steps (RELEASE_PATTERN.md, hygiene rule 9).
#
# Usage:
#   bash tools/check_js_lint.sh
#
# Exit codes:
#   0  eslint ran and reported nothing
#   1  eslint ran and reported problems
#   2  fatal: wrappers/javascript/package.json is missing
#   3  could not run: npm is not installed, or `npm install` failed. "Could not
#      lint" is not "linted clean"; the gate fails on 3 like on 1.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JS_DIR="$REPO_ROOT/wrappers/javascript"

if [[ ! -f "$JS_DIR/package.json" ]]; then
    echo "FATAL: $JS_DIR/package.json not found" >&2
    exit 2
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "NOT RUN: npm is not installed; the JavaScript wrapper cannot be linted" >&2
    exit 3
fi

cd "$JS_DIR" || exit 2

if ! install_output=$(npm install --ignore-scripts --no-audit --no-fund 2>&1); then
    echo "NOT RUN: npm install failed in wrappers/javascript" >&2
    printf '%s\n' "$install_output" | tail -15 >&2
    exit 3
fi

if ! lint_output=$(npm run lint 2>&1); then
    printf '%s\n' "$lint_output" | tail -40
    echo "FAIL: eslint reported problems in wrappers/javascript"
    exit 1
fi

echo "OK: eslint clean (wrappers/javascript, checked under $JS_DIR)"
exit 0
