#!/usr/bin/env bash
#
# scripts/release.sh — deterministic release pipeline for ISO 4217.
#
# Usage:
#   bash scripts/release.sh <version>              # full release
#   bash scripts/release.sh <version> --dry-run    # preview, no mutation
#   bash scripts/release.sh <version> --force      # re-run on existing tag
#
# Exit codes (each one is a different recovery; ADR 0014, D6):
#   0  success (or successful dry-run)
#   1  a precondition found a problem (nothing was mutated)
#   2  usage error
#   3  could not run: gh missing or unauthenticated, origin unreadable (nothing was mutated)
#   4  a generator, a version bump or the gate failed (tree mutated, nothing committed)
#   5  commit or push failed
#   6  CI not green, no run for the pushed commit, or the poll timed out (commit is on origin, nothing tagged)
#   7  tag creation, verification or push failed
#   8  the verification doc failed (released and tagged; only the doc is missing)
#
# Preconditions (all must hold, checked before anything is mutated):
#   - working tree is clean
#   - current branch is main
#   - tag v<version> exists neither on origin nor locally (--force recreates a tag that exists only locally;
#     a tag on origin is never moved)
#   - CHANGELOG.md contains a '## [<version>]' section
#   - tools/check_version_consistency.py currently passes
#
# Dependencies:
#   pyarrow is a build-time dependency of this script. The Parquet
#   generators (export_parquet.py, export_countries_parquet.py,
#   export_aggregated.py) and their --check modes import it, so
#   regenerate_artifacts() and run_gate() fail without it.
#
# Regeneration order follows the data layers (docs/LAYERS.md):
#   RAW -> CURATED (SQL, CSV, Parquet, countries Parquet, wrapper copies)
#       -> AGGREGATED. export_aggregated.py reads iso4217.parquet and
#   iso4217.countries.parquet, so it must run after both.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERSION_FILE="VERSION"
CHANGELOG="CHANGELOG.md"
ISO_JSON="iso4217.json"
README="README.md"
PY_SETUP="wrappers/python/setup.py"
JS_PKG="wrappers/javascript/package.json"
RUST_CARGO="wrappers/rust/Cargo.toml"

EXIT_OK=0
EXIT_PRECOND=1
EXIT_USAGE=2
EXIT_COULD_NOT=3
EXIT_GATE=4
EXIT_PUSH=5
EXIT_CI=6
EXIT_TAG=7
EXIT_DOC=8

# Temporary state, removed by cleanup() on every exit, normal or not.
DRY_COPY=""
GATE_LOG_FILE=""
GATE_STEPS=0
GATE_PASSED=0
CI_RUN_LINES=""
RECREATE_TAG=false

cleanup() {
    if [ -n "$DRY_COPY" ]; then
        rm -rf "$DRY_COPY"
    fi
    if [ -n "$GATE_LOG_FILE" ]; then
        rm -f "$GATE_LOG_FILE"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

info()  { printf '  %s\n' "$*"; }
step()  { printf '\n== %s ==\n' "$*"; }
fail_code() { local code="$1"; shift; printf 'FAIL: %s\n' "$*" >&2; exit "$code"; }
fail()  { fail_code "$EXIT_PRECOND" "$@"; }

# What the operator should do after a failure that happened once the tree was being changed.
mutated_hint() {
    if $DRY_RUN; then
        echo "this is a dry run: your working tree was not touched"
    else
        echo "the working tree may be modified and nothing was committed; restore it with: git checkout -- ."
    fi
}

usage() {
    cat <<'EOF'
Usage: bash scripts/release.sh <version> [--dry-run] [--force] [--poll-timeout N]

Arguments:
  <version>    Target version, X.Y.Z format.

Flags:
  --dry-run    Run the preconditions, then bump, regenerate and run the gate
               on a throwaway copy of the tree. Nothing is committed, pushed
               or tagged, and your working tree is not touched.
  --force      Recreate a tag that exists only locally (a release whose tag
               push failed). A tag on origin is never moved; --force does not
               change that.
  --poll-timeout N
               Seconds to wait for CI after the push (positive integer,
               default 300). A timeout fails the release; it never tags.

Prerequisite: the gh CLI, installed and able to list this repository's
workflow runs. The release refuses to start without it.

Exit codes:
  0  success (or successful dry-run)
  1  precondition failed (nothing mutated)
  2  usage error
  3  could not run: gh missing or unauthenticated, origin unreadable
  4  generator, version bump or gate failed (tree modified, nothing committed)
  5  commit or push failed
  6  CI not green, no run, or poll timed out (commit is on origin; nothing tagged)
  7  tag creation, verification or push failed
  8  verification doc failed (released and tagged; only the doc is missing)
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

# A positive integer, at most six digits, no leading zero (bash would read
# 08 as octal). Checked when the flag is parsed, so a bad value is a usage
# error before anything else runs.
check_poll_timeout() {
    if ! [[ "$1" =~ ^[1-9][0-9]{0,5}$ ]]; then
        printf 'ERROR: --poll-timeout needs a positive integer (seconds), got: %s\n' "$1" >&2
        exit "$EXIT_USAGE"
    fi
}

DRY_RUN=false
FORCE=false
VERSION=""
POLL_TIMEOUT=300

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n) DRY_RUN=true; shift ;;
        --force|-f)   FORCE=true; shift ;;
        --poll-timeout)
            if [[ $# -lt 2 ]]; then
                printf 'ERROR: --poll-timeout needs a value\n' >&2
                exit "$EXIT_USAGE"
            fi
            check_poll_timeout "$2"; POLL_TIMEOUT="$2"; shift 2 ;;
        --poll-timeout=*)
            check_poll_timeout "${1#--poll-timeout=}"; POLL_TIMEOUT="${1#--poll-timeout=}"; shift ;;
        --help|-h)    usage; exit 0 ;;
        -*)           printf 'ERROR: unknown flag: %s\n' "$1" >&2; usage >&2; exit "$EXIT_USAGE" ;;
        *)
            if [[ -n "$VERSION" ]]; then
                printf 'ERROR: multiple version arguments\n' >&2
                exit "$EXIT_USAGE"
            fi
            VERSION="$1"; shift ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    printf 'ERROR: missing version argument\n' >&2
    usage >&2
    exit "$EXIT_USAGE"
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf 'ERROR: version must be X.Y.Z, got: %s\n' "$VERSION" >&2
    exit "$EXIT_USAGE"
fi

TAG="v$VERSION"
TODAY="$(date -u +%Y-%m-%d)"   # UTC: CI and the freshness checks run in UTC
CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")"

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

check_head_at_origin() {
    if ! git fetch origin main --quiet 2>/dev/null; then
        fail_code "$EXIT_COULD_NOT" "cannot fetch origin/main; check network and remote access"
    fi
    local local_head remote_head
    local_head="$(git rev-parse HEAD)"
    remote_head="$(git rev-parse origin/main 2>/dev/null || echo "")"
    if [ -z "$remote_head" ]; then
        fail_code "$EXIT_COULD_NOT" "cannot resolve origin/main after fetch"
    fi
    if [ "$local_head" != "$remote_head" ]; then
        fail "HEAD is not at origin/main (local: ${local_head:0:8}, origin/main: ${remote_head:0:8})"
    fi
}

check_workflows_covered() {
    local declared=("$@")
    local actual
    actual="$(find .github/workflows -maxdepth 1 \( -name '*.yml' -o -name '*.yaml' \) \
        -exec basename {} \; 2>/dev/null \
        | grep -v -E '^(monitor|fetch|refresh|update|schedule)' || true)"
    if [ -z "$actual" ]; then
        return
    fi
    while read -r wf; do
        [ -z "$wf" ] && continue
        local found=0
        for d in "${declared[@]}"; do
            if [ "$wf" = "$d" ]; then
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            fail "workflow $wf is not in the poll list (add it to POLLED_WORKFLOWS)"
        fi
    done <<< "$actual"
}

POLLED_WORKFLOWS=(
    "validate.yml"
    "version-and-hygiene.yml"
)

# poll_ci timing. POLL_GRACE is how long a polled workflow may have no run
# for the release SHA before the push is treated as having failed to trigger
# it. Constants, not flags: a missing run is a misconfiguration, not a slow
# CI. POLL_TIMEOUT (the --poll-timeout flag) bounds the whole wait.
POLL_GRACE=60
POLL_INTERVAL=10

# Ported from ISO 3166 v1.6.3, commit db74f96.
# Shell-side only. The version bumps live in scripts/bump_version.py (ADR 0014,
# D8), which is Python and fails loudly on its own.
check_no_orphan_variables() {
    local orphans
    orphans="$(grep -nE '\$\{[A-Z_]+\}|\$[A-Z_]{3,}' scripts/release.sh \
        | grep -vE '^[0-9]+:\s*#' \
        | grep -oE '\$\{?[A-Z_]+' \
        | sort -u \
        | while read -r v; do
            v="${v#\$}"
            v="${v#\{}"
            case "$v" in
                BASH_SOURCE|BASH_VERSION|BASH|BASHPID|LINENO|FUNCNAME|PIPESTATUS|EUID|UID|IFS|HOME|PATH|PWD|USER|OLDPWD|OPTARG|OPTIND|REPLY|RANDOM|SECONDS|SHELL|SHLVL|HOSTNAME|HOSTTYPE|MACHTYPE|OSTYPE|PPID|GROUPS|DIRSTACK|BASH_REMATCH) continue ;;
            esac
            if ! grep -qE "(^|\s)${v}=" scripts/release.sh; then
                echo "$v"
            fi
        done || true)"

    if [ -n "$orphans" ]; then
        echo "orphan variables (defined nowhere, expanded somewhere):" >&2
        echo "$orphans" | sed 's/^/  /' >&2
        fail "release script references undefined variables"
    fi
}

check_manifest_has_version() {
    local manifest="tools/release_claims.json"
    if [ ! -f "$manifest" ]; then
        fail "$manifest not found"
    fi
    if ! python3 -c "
import json, sys
manifest = json.load(open('$manifest'))
sys.exit(0 if '$VERSION' in manifest else 1)
" 2>/dev/null; then
        fail "$manifest has no entry for version $VERSION"
    fi
}

check_clean_tree() {
    if [[ -n "$(git status --porcelain)" ]]; then
        git status --short >&2
        fail "working tree is not clean"
    fi
}

check_on_main() {
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [[ "$branch" != "main" ]]; then
        fail "not on main (currently on: $branch)"
    fi
}

# gh is a prerequisite, not an option: invariant 7 (tag only on green) cannot
# be honoured without it. The probe is the same call poll_ci makes, so it
# proves installation, authentication, repository access, and Actions access
# together, and it runs before anything is changed (also under --dry-run).
check_gh_ready() {
    if ! command -v gh >/dev/null 2>&1; then
        fail_code "$EXIT_COULD_NOT" "gh CLI not found; release.sh needs it to verify CI before tagging (https://cli.github.com)"
    fi
    if ! gh run list --limit 1 --json databaseId >/dev/null 2>&1; then
        fail_code "$EXIT_COULD_NOT" "gh cannot list workflow runs; run 'gh auth login' and check access to this repository"
    fi
}

# Tag state is read from both places, origin first (ADR 0014, D3). A tag on origin is
# published and is never moved. A tag that exists only locally was never published
# (a release whose tag push failed); --force recreates it.
check_tag_free() {
    local remote_tags
    if ! remote_tags="$(git ls-remote --tags origin "refs/tags/$TAG" 2>&1)"; then
        fail_code "$EXIT_COULD_NOT" "cannot read tags on origin (git ls-remote failed): ${remote_tags:0:200}"
    fi
    if [ -n "$remote_tags" ]; then
        fail "tag $TAG already exists on origin; a published tag is never moved, and --force does not change that"
    fi
    if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
        if $FORCE; then
            RECREATE_TAG=true
            info "tag $TAG exists locally only (--force given): it will be recreated from the CHANGELOG"
        else
            fail "tag $TAG already exists locally (not on origin); use --force to recreate it"
        fi
    elif $FORCE; then
        info "--force given, but tag $TAG does not exist anywhere: nothing to do"
    fi
}

check_changelog_section() {
    if ! grep -q "^## \[$VERSION\]" "$CHANGELOG"; then
        fail "CHANGELOG.md has no '## [$VERSION]' section"
    fi
}

check_version_consistency() {
    if ! python3 tools/check_version_consistency.py >/dev/null 2>&1; then
        python3 tools/check_version_consistency.py >&2 || true
        fail "check_version_consistency.py is not currently passing"
    fi
}

# ---------------------------------------------------------------------------
# Version bump: one call to scripts/bump_version.py per site (ADR 0014, D8)
# ---------------------------------------------------------------------------

BUMP_SCRIPT="scripts/bump_version.py"

# bump_site <site> <from> <to>. The script is idempotent and fails loudly, so a
# site that cannot be bumped stops the release here instead of staying old.
bump_site() {
    local site="$1" from="$2" to="$3"
    if ! python3 "$BUMP_SCRIPT" --from "$from" --to "$to" "$site"; then
        fail_code "$EXIT_GATE" "bump of site '$site' failed (see above); $(mutated_hint)"
    fi
}

# The clock is read once, at the top of this script (TODAY, UTC), and passed in.
bump_all_sites() {
    step "Bumping version sites to $VERSION"
    local heading_old="## [$VERSION] — Unreleased"
    local heading_new="## [$VERSION] — $TODAY"
    local dated
    if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
        # A re-run after the release commit exists: the heading already carries its date.
        dated="$(grep -E "^## \[$VERSION\] — [0-9]{4}-[0-9]{2}-[0-9]{2}$" "$CHANGELOG" | head -1 || true)"
        if [ -n "$dated" ]; then
            heading_old="$dated"
            heading_new="$dated"
        fi
    fi
    bump_site version          "$CURRENT_VERSION" "$VERSION"
    bump_site changelog        "$heading_old" "$heading_new"
    bump_site iso_json_version "$CURRENT_VERSION" "$VERSION"
    bump_site iso_json_updated DATE "$TODAY"
    bump_site readme_badge     "$CURRENT_VERSION" "$VERSION"
    bump_site setup_py         "$CURRENT_VERSION" "$VERSION"
    bump_site package_json     "$CURRENT_VERSION" "$VERSION"
    bump_site cargo_toml       "$CURRENT_VERSION" "$VERSION"
}

# ---------------------------------------------------------------------------
# Artifact regeneration — sixteen files from six generators
# ---------------------------------------------------------------------------

regenerate_artifacts() {
    step "Regenerating artifacts"
    python3 tools/export_sql.py       >/dev/null || fail_code "$EXIT_GATE" "export_sql.py exited non-zero; $(mutated_hint)"
    info "✓ SQL exports (4 files)"
    python3 tools/export_csv.py       >/dev/null || fail_code "$EXIT_GATE" "export_csv.py exited non-zero; $(mutated_hint)"
    info "✓ CSV/TSV exports (4 files)"
    python3 tools/export_parquet.py   >/dev/null || fail_code "$EXIT_GATE" "export_parquet.py exited non-zero; $(mutated_hint)"
    info "✓ Parquet export (1 file)"
    python3 tools/export_countries_parquet.py >/dev/null || fail_code "$EXIT_GATE" "export_countries_parquet.py exited non-zero; $(mutated_hint)"
    info "✓ Countries Parquet (1 file)"
    python3 tools/export_aggregated.py        >/dev/null || fail_code "$EXIT_GATE" "export_aggregated.py exited non-zero; $(mutated_hint)"
    info "✓ Aggregated exports (3 files)"
    python3 tools/sync_wrappers.py    >/dev/null || fail_code "$EXIT_GATE" "sync_wrappers.py exited non-zero; $(mutated_hint)"
    info "✓ Wrapper copies (3 files)"
}

# ---------------------------------------------------------------------------
# Gate — every check runs and every failure is reported; the script stops after the last one
# ---------------------------------------------------------------------------

GATE_FAILED=0

run_gate_step() {
    local name="$1"
    shift
    local output rc=0 mark
    output=$("$@" 2>&1) || rc=$?
    GATE_STEPS=$((GATE_STEPS + 1))
    if [ "$rc" -eq 0 ]; then
        GATE_PASSED=$((GATE_PASSED + 1))
        mark="✓"
        info "✓ $name"
    else
        mark="✗"
        info "✗ $name"
        printf '%s\n' "$output" | tail -25
        GATE_FAILED=1
    fi
    # The record the verification doc is built from (D4): what each step printed, last 20 lines.
    if [ -n "$GATE_LOG_FILE" ]; then
        {
            printf '### %s %s\n\n```\n' "$mark" "$name"
            printf '%s\n' "$output" | tail -20
            printf '```\n\n'
        } >> "$GATE_LOG_FILE"
    fi
}

run_gate() {
    step "Running gate"
    GATE_FAILED=0
    GATE_STEPS=0
    GATE_PASSED=0

    run_gate_step "validate.py"                     python3 tools/validate.py
    run_gate_step "check_version_consistency.py"    python3 tools/check_version_consistency.py
    run_gate_step "export_sql.py --check"           python3 tools/export_sql.py --check
    run_gate_step "export_csv.py --check"           python3 tools/export_csv.py --check
    run_gate_step "export_parquet.py --check"       python3 tools/export_parquet.py --check
    run_gate_step "export_countries_parquet.py --check"  python3 tools/export_countries_parquet.py --check
    run_gate_step "export_aggregated.py --check"         python3 tools/export_aggregated.py --check
    run_gate_step "sync_wrappers.py --check"        python3 tools/sync_wrappers.py --check
    run_gate_step "check_release_claims.py"         python3 tools/check_release_claims.py "$VERSION"
    run_gate_step "check_mojibake.py"               python3 tools/check_mojibake.py
    run_gate_step "check_line_endings.py"           python3 tools/check_line_endings.py
    run_gate_step "check_snapshot_freshness.py"     python3 tools/check_snapshot_freshness.py
    run_gate_step "check_registry_freshness.py"     python3 tools/check_registry_freshness.py
    run_gate_step "check_country_codes.py"          python3 tools/check_country_codes.py
    run_gate_step "check_country_codes.py --membership"  python3 tools/check_country_codes.py --membership
    run_gate_step "vendor_iso3166.py --check"       python3 tools/vendor_iso3166.py --check
    run_gate_step "check_readme_drift.py"           python3 tools/check_readme_drift.py
    run_gate_step "check_provenance.py"             python3 tools/check_provenance.py
    run_gate_step "check_verification_doc.py"       python3 tools/check_verification_doc.py
    run_gate_step "check_audit_table.py"            python3 tools/check_audit_table.py
    run_gate_step "enrich_field.py --field classification --check"  python3 tools/enrich_field.py --field classification --check
    run_gate_step "enrich_field.py --field code_lifetime --check"  python3 tools/enrich_field.py --field code_lifetime --check
    run_gate_step "enrich_field.py --field numeric_reused --check"  python3 tools/enrich_field.py --field numeric_reused --check
    run_gate_step "enrich_field.py --field source_url --check"  python3 tools/enrich_field.py --field source_url --check
        
    run_gate_step "check_cross_language.sh"         bash tools/check_cross_language.sh
    run_gate_step "check_js_lint.sh"                bash tools/check_js_lint.sh

    run_gate_step "pytest tests/"                   python3 -m pytest tests/ -q --fail-on-skip
    run_gate_step "pytest wrappers/python/tests/"   python3 -m pytest wrappers/python/tests/ -q --fail-on-skip

    if [[ "$GATE_FAILED" -ne 0 ]]; then
        fail_code "$EXIT_GATE" "gate failed; see output above; $(mutated_hint)"
    fi
}

# ---------------------------------------------------------------------------
# Commit, push, poll CI
# ---------------------------------------------------------------------------

commit_and_push() {
    step "Committing and pushing"

    # A release only modifies tracked files: version bumps and regenerated
    # artifacts. Anything else is something the gate or a generator left
    # behind, or a deletion nobody asked for. Stop before it can enter the
    # release commit, and leave the tree as it was found.
    local untracked staged_other
    untracked="$(git ls-files --others --exclude-standard)"
    if [ -n "$untracked" ]; then
        fail_code "$EXIT_GATE" "untracked file(s) would be added to the release commit:
$untracked
nothing was committed; $(mutated_hint), and remove the file(s) listed above"
    fi

    git add -A || fail_code "$EXIT_PUSH" "git add failed"

    staged_other="$(git diff --cached --name-status | awk '$1 != "M"')"
    if [ -n "$staged_other" ]; then
        git reset -q
        fail_code "$EXIT_GATE" "the release commit would add, delete, or rename files (only modifications are expected); unstaged:
$staged_other
nothing was committed; $(mutated_hint)"
    fi

    # --no-pager: an interactive shell would open a pager and block here until 'q'.
    git --no-pager diff --cached --stat

    if git diff --cached --quiet; then
        info "no changes to commit"
    else
        git commit -m "Release $TAG" || fail_code "$EXIT_PUSH" "git commit failed; nothing was pushed"
        info "committed: Release $TAG"
    fi

    git push origin main || fail_code "$EXIT_PUSH" "git push origin main failed; the release commit exists locally only and nothing was tagged"
    info "pushed to origin/main"
}

poll_ci() {
    step "Polling CI"

    # Fail closed. This function returns only when every workflow in
    # POLLED_WORKFLOWS has a run for the release SHA and every run is
    # completed/success. Every other outcome calls fail:
    #   - gh errors              -> immediately, with gh's own message
    #   - a run is not green     -> immediately, naming workflow and run
    #   - a workflow has no run  -> after POLL_GRACE seconds
    #   - still running          -> after POLL_TIMEOUT seconds
    # $SECONDS has whole-second granularity, so a wait can end up to one
    # second early; that is irrelevant at a 300 s default.
    local sha start elapsed wf out errf err id status conclusion
    local missing pending
    sha="$(git rev-parse HEAD)"
    start=$SECONDS
    errf="$(mktemp "${TMPDIR:-/tmp}/poll_ci.XXXXXX")"
    info "waiting for ${#POLLED_WORKFLOWS[@]} workflow(s) on ${sha:0:8} (timeout ${POLL_TIMEOUT}s, ${POLL_GRACE}s for each to appear)"

    while true; do
        missing=""
        pending=""
        CI_RUN_LINES=""
        for wf in "${POLLED_WORKFLOWS[@]}"; do
            if ! out="$(gh run list --workflow "$wf" --event push --limit 20 \
                --json databaseId,headSha,status,conclusion \
                --jq ".[] | select(.headSha == \"$sha\") | \"\(.databaseId)|\(.status)|\(.conclusion // \"pending\")\"" \
                2>"$errf")"; then
                err="$(head -c 300 "$errf")"
                rm -f "$errf"
                fail_code "$EXIT_CI" "gh run list failed for $wf: ${err:-no error text}"
            fi
            if [ -z "$out" ]; then
                missing="$missing $wf"
                continue
            fi
            while IFS='|' read -r id status conclusion; do
                if [ "$status" != "completed" ]; then
                    pending="$pending $wf"
                    continue
                fi
                if [ "$conclusion" != "success" ]; then
                    rm -f "$errf"
                    fail_code "$EXIT_CI" "workflow $wf (run $id) concluded '$conclusion' on ${sha:0:8}"
                fi
                CI_RUN_LINES="${CI_RUN_LINES}${wf}|${id}|${conclusion}"$'\n'
            done <<< "$out"
        done

        if [ -z "$missing" ] && [ -z "$pending" ]; then
            rm -f "$errf"
            info "✓ all ${#POLLED_WORKFLOWS[@]} workflow(s) for ${sha:0:8} are completed success"
            return 0
        fi

        elapsed=$((SECONDS - start))
        if [ -n "$missing" ] && [ "$elapsed" -ge "$POLL_GRACE" ]; then
            rm -f "$errf"
            fail_code "$EXIT_CI" "no run for${missing} on ${sha:0:8} after ${POLL_GRACE}s: the push did not trigger it"
        fi
        if [ "$elapsed" -ge "$POLL_TIMEOUT" ]; then
            rm -f "$errf"
            fail_code "$EXIT_CI" "CI poll timed out after ${POLL_TIMEOUT}s on ${sha:0:8}; still waiting on:${missing}${pending}"
        fi
        sleep "$POLL_INTERVAL"
    done
}

# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------

tag_release() {
    step "Tagging release"

    local message msgfile recorded
    message="$(awk -v v="$VERSION" '
        $0 ~ "^## \\[" v "\\]" { capturing=1; next }
        capturing && /^## \[/ { exit }
        capturing && NF { print }
    ' "$CHANGELOG" | head -15 | sed 's/[[:space:]]*$//')"

    if [[ -z "$message" ]]; then
        message="Release $TAG"
    fi

    # Written to a file and passed with -F, so what git records can be compared
    # with what was meant. --cleanup=verbatim is deliberate: git's default
    # removes every line that begins with '#', which drops the Markdown section
    # headings (### Fixed) from this message, and the whitespace mode still
    # rewrites the text (trailing whitespace, runs of blank lines). Verbatim
    # records the file exactly as written.
    msgfile="$(mktemp "${TMPDIR:-/tmp}/tagmsg.XXXXXX")"
    printf '%s\n' "$message" > "$msgfile"
    if ! [ -s "$msgfile" ]; then
        rm -f "$msgfile"
        fail_code "$EXIT_TAG" "tag message file is empty; no tag created, nothing pushed"
    fi
    # A tag that exists only locally was never published; --force recreates it (D3).
    if $RECREATE_TAG && git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
        git tag -d "$TAG" >/dev/null || fail_code "$EXIT_TAG" "could not delete the local-only tag $TAG; delete it by hand and re-run with --force"
        info "deleted the local-only tag $TAG (never published); recreating it"
    fi
    git tag -a "$TAG" --cleanup=verbatim -F "$msgfile" || fail_code "$EXIT_TAG" "git tag $TAG failed; nothing was pushed"

    # A12: tag-message verification. Comparison is content-equivalent after
    # trailing-newline normalization — $(...) strips trailing newlines on both
    # sides, so byte-for-byte identity is unachievable and not what we verify.
    # Never use diff for this; exit 2 reads as "differ" and hides "could not run."
    # Verification must precede push so delete-on-mismatch is safe.
    verified=0
    if recorded="$(git for-each-ref "refs/tags/$TAG" --format='%(contents)')" \
        && [[ "$recorded" == "$message" ]]; then
        verified=1
    fi
    rm -f "$msgfile"
    if [[ "$verified" -ne 1 ]]; then
        if ! git tag -d "$TAG" >/dev/null; then
            fail_code "$EXIT_TAG" "git recorded a different tag message than the CHANGELOG text (or it could not be read back), and 'git tag -d $TAG' failed: local tag $TAG STILL EXISTS and nothing was pushed; run 'git tag -d $TAG' by hand before re-running"
        fi
        fail_code "$EXIT_TAG" "git recorded a different tag message than the CHANGELOG text (or it could not be read back); local tag $TAG deleted, nothing pushed"
    fi

    git push origin "$TAG" || fail_code "$EXIT_TAG" "git push origin $TAG failed; the tag exists locally only (fix the cause, then re-run with --force)"
    info "tagged and pushed: $TAG"
}

# ---------------------------------------------------------------------------
# Verification doc
# ---------------------------------------------------------------------------

# The doc is written after the tag because it names the tag commit and the CI runs, neither of
# which can exist before the commit does (ADR 0014, D4). It is complete: every number in it comes
# from the run just made. If it would fail tools/check_verification_doc.py it is not committed.
write_verification_doc() {
    step "Writing verification doc"

    local doc="docs/$TAG-verification.md"

    if [[ -f "$doc" ]]; then
        info "$doc already exists; leaving it alone"
        return
    fi

    local tag_commit wf id conclusion
    tag_commit="$(git rev-parse "$TAG^{commit}")"

    {
        printf '# %s Post-Release Verification\n\n' "$TAG"
        printf '**Date:** %s\n' "$TODAY"
        printf '**Tag:** %s\n' "$TAG"
        printf '**Tag commit:** %s\n' "$tag_commit"
        printf '**Written by:** scripts/release.sh, from the run it just made. It records what was run and what each step printed.\n\n'
        printf '## Summary\n\n'
        printf '| Check | Result |\n|-------|--------|\n'
        printf '| Gate | %s of %s steps passed |\n' "$GATE_PASSED" "$GATE_STEPS"
        while IFS='|' read -r wf id conclusion; do
            [ -z "$wf" ] && continue
            printf '| CI: %s | run %s, %s |\n' "$wf" "$id" "$conclusion"
        done <<< "$CI_RUN_LINES"
        printf '\n## CI\n\n'
        printf 'These runs were read from GitHub for the tag commit before the tag was created.\n\n'
        printf '| Workflow | Run id | Conclusion |\n|----------|--------|------------|\n'
        while IFS='|' read -r wf id conclusion; do
            [ -z "$wf" ] && continue
            printf '| %s | %s | %s |\n' "$wf" "$id" "$conclusion"
        done <<< "$CI_RUN_LINES"
        printf '\n## Gate\n\n'
        printf 'Every step of the release gate ran on the release tree. The last lines each step printed:\n\n'
        if [ -n "$GATE_LOG_FILE" ]; then
            cat "$GATE_LOG_FILE"
        fi
        printf '## Known limits\n\n'
        printf 'This record was generated by the release script. CI on the commit that adds this document runs after the push and is not part of it.\n'
    } > "$doc"

    if ! python3 tools/check_verification_doc.py >&2; then
        rm -f "$doc"
        fail_code "$EXIT_DOC" "the generated $doc failed tools/check_verification_doc.py and was not committed; $TAG is tagged and pushed, only the doc is missing"
    fi

    git add "$doc" || fail_code "$EXIT_DOC" "git add of $doc failed; $TAG is tagged and pushed"
    git commit -q -m "Add $TAG verification doc" || fail_code "$EXIT_DOC" "git commit of $doc failed; $TAG is tagged and pushed"
    git push origin main || fail_code "$EXIT_DOC" "git push of the verification doc failed; $TAG is tagged and pushed; the doc commit exists locally only"
    info "wrote and pushed $doc"
}

# ---------------------------------------------------------------------------
# Dry run — print the plan without mutating anything
# ---------------------------------------------------------------------------

print_plan() {
    echo "============================================================"
    echo " Release plan: $TAG"
    echo "============================================================"
    echo
    echo "Current version: $CURRENT_VERSION"
    echo "Target version:  $VERSION"
    echo "Today:           $TODAY"
    echo
    echo "Sites to bump:"
    if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
        echo "  (already at target; only the CHANGELOG date will change)"
    else
        echo "  VERSION                                 -> $VERSION"
        echo "  CHANGELOG.md                            -> $VERSION dated $TODAY"
        echo "  iso4217.json meta.version               -> $VERSION"
        echo "  iso4217.json meta.updated               -> $TODAY"
        echo "  README.md registry badge                -> $VERSION"
        echo "  wrappers/python/setup.py                -> $VERSION"
        echo "  wrappers/javascript/package.json        -> $VERSION"
        echo "  wrappers/rust/Cargo.toml                -> $VERSION"
    fi
    echo
    echo "Artifacts to regenerate:"
    echo "  iso4217.sql, iso4217.postgresql.sql, iso4217.mysql.sql, iso4217.sqlite.sql"
    echo "  iso4217.csv, iso4217.excel.csv, iso4217.european.csv, iso4217.tsv"
    echo "  iso4217.parquet"
    echo "  iso4217.countries.parquet"
    echo "  currencies_by_region.parquet, pegs_summary.parquet, coverage_timeline.parquet"
    echo "  wrappers/python/iso4217.json"
    echo "  wrappers/go/iso4217.json"
    echo "  wrappers/rust/iso4217.json"
    echo "  wrappers/javascript/iso4217.json"
    echo
    echo "Preconditions:"
    echo "  clean tree"
    echo "  HEAD at origin/main"
    echo "  on main branch"
    echo "  all per-push workflows in poll list"
    echo "  gh installed and able to list workflow runs"
    echo "  tag free"
    echo "  CHANGELOG section present"
    echo "  check_version_consistency.py passes"
    echo "  no orphaned variables in release.sh"
    echo
    echo "Gate:"
    echo "  python3 tools/validate.py"
    echo "  python3 tools/check_version_consistency.py"
    echo "  python3 tools/export_sql.py --check"
    echo "  python3 tools/export_csv.py --check"
    echo "  python3 tools/export_parquet.py --check"
    echo "  python3 tools/export_countries_parquet.py --check"
    echo "  python3 tools/export_aggregated.py --check"
    echo "  python3 tools/sync_wrappers.py --check"
    echo "  python3 tools/check_release_claims.py \$VERSION"
    echo "  python3 tools/check_mojibake.py"
    echo "  python3 tools/check_line_endings.py"
    echo "  python3 tools/check_snapshot_freshness.py"
    echo "  python3 tools/check_registry_freshness.py"
    echo "  python3 tools/check_country_codes.py"
    echo "  python3 tools/check_country_codes.py --membership"
    echo "  python3 tools/vendor_iso3166.py --check"
    echo "  python3 tools/check_readme_drift.py"
    echo "  python3 tools/check_provenance.py"
    echo "  python3 tools/check_verification_doc.py"
    echo "  python3 tools/check_audit_table.py"
    echo "  python3 tools/enrich_field.py --field classification --check"
    echo "  python3 tools/enrich_field.py --field code_lifetime --check"
    echo "  python3 tools/enrich_field.py --field numeric_reused --check"
    echo "  python3 tools/enrich_field.py --field source_url --check"
    echo "  bash tools/check_cross_language.sh"
    echo "  bash tools/check_js_lint.sh"
    echo "  python3 -m pytest tests/ -q --fail-on-skip"
    echo "  python3 -m pytest wrappers/python/tests/ -q --fail-on-skip"
    echo
    echo "Post-gate:"
    echo "  git add -A && git commit -m 'Release $TAG'"
    echo "  git push origin main"
    echo "  poll CI: gh run list per workflow in POLLED_WORKFLOWS;"
    echo "    each must appear within ${POLL_GRACE}s and be completed/success;"
    echo "    timeout ${POLL_TIMEOUT}s (--poll-timeout); any other outcome fails, nothing is tagged"
    echo "  git tag -a $TAG -m '<first 15 lines of CHANGELOG section>'"
    echo "  git push origin $TAG"
    echo "  write docs/$TAG-verification.md (complete: tag commit, CI run ids, gate output; checked before it is committed)"
    echo
}

# --dry-run: the plan, then bump, regenerate and the gate on a throwaway copy, so "would the gate
# pass?" has an answer and the operator's tree is never touched (ADR 0014, D5). cleanup() removes
# the copy on every exit.
dry_run() {
    local rc=0
    print_plan
    DRY_COPY="$(mktemp -d "${TMPDIR:-/tmp}/release-dryrun.XXXXXX")"
    step "Dry run on a throwaway copy"
    info "copying the tree to a temporary directory (removed on exit)"
    cp -a "$REPO_ROOT/." "$DRY_COPY/" || fail_code "$EXIT_COULD_NOT" "could not copy the tree for the dry run"
    (
        cd "$DRY_COPY"
        bump_all_sites
        regenerate_artifacts
        run_gate
    ) || rc=$?
    if [ "$rc" -ne 0 ]; then
        exit "$rc"
    fi
    echo
    echo "============================================================"
    echo " DRY RUN: the gate passed on a throwaway copy; nothing was changed"
    echo "============================================================"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo "============================================================"
echo " ISO 4217 Release Pipeline"
echo " Target:  $TAG"
echo " Dry run: $DRY_RUN"
echo "============================================================"

step "Preconditions"

check_clean_tree
info "✓ clean tree"

check_head_at_origin
info "✓ HEAD is at origin/main"

check_on_main
info "✓ on main"

check_workflows_covered "${POLLED_WORKFLOWS[@]}"
info "✓ all per-push workflows are in the poll list"

check_gh_ready
info "✓ gh can list workflow runs"

check_tag_free
info "✓ tag $TAG is free"

check_changelog_section
info "✓ CHANGELOG.md has section ## [$VERSION]"

check_manifest_has_version
info "✓ release_claims.json has entry for $VERSION"

check_version_consistency
info "✓ check_version_consistency.py passes"

check_no_orphan_variables
info "✓ no orphaned variables in release.sh"

if $DRY_RUN; then
    dry_run
    exit "$EXIT_OK"
fi

GATE_LOG_FILE="$(mktemp "${TMPDIR:-/tmp}/gatelog.XXXXXX")"

bump_all_sites
regenerate_artifacts
run_gate
commit_and_push
poll_ci
tag_release
write_verification_doc

echo
echo "============================================================"
echo " Released $TAG"
echo "============================================================"