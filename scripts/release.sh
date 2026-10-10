#!/usr/bin/env bash
#
# scripts/release.sh — deterministic release pipeline for ISO 4217.
#
# Usage:
#   bash scripts/release.sh <version>              # full release
#   bash scripts/release.sh <version> --dry-run    # preview, no mutation
#   bash scripts/release.sh <version> --force      # re-run on existing tag
#
# Exit codes:
#   0  success (or successful dry-run)
#   1  precondition failed (dirty tree, wrong branch, tag exists, gate failed)
#   2  usage error
#
# Preconditions (all must hold, checked before anything is mutated):
#   - working tree is clean
#   - current branch is main
#   - tag v<version> does not already exist (unless --force)
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

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

info()  { printf '  %s\n' "$*"; }
step()  { printf '\n== %s ==\n' "$*"; }
fail()  { printf 'FAIL: %s\n' "$*" >&2; exit "$EXIT_PRECOND"; }

usage() {
    cat <<'EOF'
Usage: bash scripts/release.sh <version> [--dry-run] [--force] [--poll-timeout N]

Arguments:
  <version>    Target version, X.Y.Z format.

Flags:
  --dry-run    Print every site and gate without mutating anything.
  --force      Allow releasing a version that is already tagged.
  --poll-timeout N
               Seconds to wait for CI after the push (positive integer,
               default 300). A timeout fails the release; it never tags.

Prerequisite: the gh CLI, installed and able to list this repository's
workflow runs. The release refuses to start without it.

Exit codes:
  0  success (or successful dry-run)
  1  precondition failed
  2  usage error
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
TODAY="$(date +%Y-%m-%d)"
CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")"

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

check_head_at_origin() {
    if ! git fetch origin main --quiet 2>/dev/null; then
        fail "cannot fetch origin/main; check network and remote access"
    fi
    local local_head remote_head
    local_head="$(git rev-parse HEAD)"
    remote_head="$(git rev-parse origin/main 2>/dev/null || echo "")"
    if [ -z "$remote_head" ]; then
        fail "cannot resolve origin/main after fetch"
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
# Shell-side only. Inline Python in bump_* functions is checked at
# runtime by NameError; extending this check to cover it is deferred
# until 4217 hits the failure mode.
check_no_orphan_variables() {
    local orphans
    orphans="$(grep -nE '\$\{[A-Z_]+\}|\$[A-Z_]{3,}' scripts/release.sh \
        | grep -vE '^\s*#' \
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
        die "release script references undefined variables"
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
        fail "gh CLI not found; release.sh needs it to verify CI before tagging (https://cli.github.com)"
    fi
    if ! gh run list --limit 1 --json databaseId >/dev/null 2>&1; then
        fail "gh cannot list workflow runs; run 'gh auth login' and check access to this repository"
    fi
}

check_tag_free() {
    if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
        if $FORCE; then
            info "tag $TAG already exists (--force given, continuing)"
        else
            fail "tag $TAG already exists; use --force to override"
        fi
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
# Version bump — each site edited in place, format preserved
# ---------------------------------------------------------------------------

bump_version_file() {
    printf '%s\n' "$VERSION" > "$VERSION_FILE"
}

bump_changelog() {
    python3 - "$VERSION" "$TODAY" <<'PYEOF'
import re, sys
from pathlib import Path
version, today = sys.argv[1], sys.argv[2]
p = Path("CHANGELOG.md")
text = p.read_text(encoding="utf-8")
pattern = re.compile(
    r"^(## \[" + re.escape(version) + r"\]) — Unreleased$",
    re.MULTILINE,
)
new_text, n = pattern.subn(r"\1 — " + today, text)
if n > 0:
    p.write_text(new_text, encoding="utf-8")
PYEOF
}

bump_iso_json() {
    python3 - "$VERSION" "$TODAY" <<'PYEOF'
import re, sys
from pathlib import Path
version, today = sys.argv[1], sys.argv[2]
p = Path("iso4217.json")
text = p.read_text(encoding="utf-8")
# meta.version — first occurrence
text = re.sub(
    r'("version":\s*)"[0-9]+\.[0-9]+\.[0-9]+"',
    r'\1"' + version + '"',
    text,
    count=1,
)
# meta.updated — first occurrence
text = re.sub(
    r'("updated":\s*)"[0-9]{4}-[0-9]{2}-[0-9]{2}"',
    r'\1"' + today + '"',
    text,
    count=1,
)
p.write_text(text, encoding="utf-8")
PYEOF
}

bump_readme_badges() {
    # Only the registry badge moves on a registry release; the schema
    # badge tracks the schema axis, which is independent.
    sed -i "s|badge/registry-[0-9]\+\.[0-9]\+\.[0-9]\+-orange|badge/registry-$VERSION-orange|" "$README"
}

bump_python_setup() {
    sed -i "s/^VERSION = \"[0-9]\+\.[0-9]\+\.[0-9]\+\"/VERSION = \"$VERSION\"/" "$PY_SETUP"
}

bump_js_package() {
    python3 - "$VERSION" <<'PYEOF'
import json, sys
from pathlib import Path
version = sys.argv[1]
p = Path("wrappers/javascript/package.json")
data = json.loads(p.read_text(encoding="utf-8"))
data["version"] = version
p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PYEOF
}

bump_rust_cargo() {
    python3 - "$VERSION" <<'PYEOF'
import sys
from pathlib import Path
version = sys.argv[1]
p = Path("wrappers/rust/Cargo.toml")
lines = p.read_text(encoding="utf-8").splitlines()
out = []
in_pkg = False
for line in lines:
    s = line.strip()
    if s.startswith("[") and s.endswith("]"):
        in_pkg = (s == "[package]")
    if in_pkg and s.startswith("version"):
        line = 'version = "' + version + '"'
    out.append(line)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
PYEOF
}

bump_all_sites() {
    step "Bumping version sites to $VERSION"
    info "VERSION"
    bump_version_file
    info "CHANGELOG.md"
    bump_changelog
    info "iso4217.json (meta.version, meta.updated)"
    bump_iso_json
    info "README.md (registry badge)"
    bump_readme_badges
    info "wrappers/python/setup.py"
    bump_python_setup
    info "wrappers/javascript/package.json"
    bump_js_package
    info "wrappers/rust/Cargo.toml"
    bump_rust_cargo
}

# ---------------------------------------------------------------------------
# Artifact regeneration — sixteen files from six generators
# ---------------------------------------------------------------------------

regenerate_artifacts() {
    step "Regenerating artifacts"
    python3 tools/export_sql.py       >/dev/null && info "✓ SQL exports (4 files)"
    python3 tools/export_csv.py       >/dev/null && info "✓ CSV/TSV exports (4 files)"
    python3 tools/export_parquet.py   >/dev/null && info "✓ Parquet export (1 file)"
    python3 tools/export_countries_parquet.py >/dev/null && info "✓ Countries Parquet (1 file)"
    python3 tools/export_aggregated.py        >/dev/null && info "✓ Aggregated exports (3 files)"
    python3 tools/sync_wrappers.py    >/dev/null && info "✓ Wrapper copies (3 files)"
}

# ---------------------------------------------------------------------------
# Gate — every check must pass; the script stops at the first failure
# ---------------------------------------------------------------------------

GATE_FAILED=0

run_gate_step() {
    local name="$1"
    shift
    local output
    if output=$("$@" 2>&1); then
        info "✓ $name"
    else
        info "✗ $name"
        printf '%s\n' "$output" | tail -25
        GATE_FAILED=1
    fi
}

run_gate() {
    step "Running gate"
    GATE_FAILED=0

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
    run_gate_step "check_snapshot_freshness.py"     python3 tools/check_snapshot_freshness.py
    run_gate_step "check_registry_freshness.py"     python3 tools/check_registry_freshness.py
    run_gate_step "check_country_codes.py"          python3 tools/check_country_codes.py
    run_gate_step "check_readme_drift.py"           python3 tools/check_readme_drift.py
    run_gate_step "check_verification_doc.py"       python3 tools/check_verification_doc.py
        
    run_gate_step "check_cross_language.sh"         bash tools/check_cross_language.sh

    run_gate_step "pytest tests/"                   python3 -m pytest tests/ -q

    if [[ "$GATE_FAILED" -ne 0 ]]; then
        fail "gate failed; see output above"
    fi
}

# ---------------------------------------------------------------------------
# Commit, push, poll CI
# ---------------------------------------------------------------------------

commit_and_push() {
    step "Committing and pushing"

    git add -A
    if git diff --cached --quiet; then
        info "no changes to commit"
    else
        git commit -m "Release $TAG"
        info "committed: Release $TAG"
    fi

    git push origin main
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
        for wf in "${POLLED_WORKFLOWS[@]}"; do
            if ! out="$(gh run list --workflow "$wf" --event push --limit 20 \
                --json databaseId,headSha,status,conclusion \
                --jq ".[] | select(.headSha == \"$sha\") | \"\(.databaseId)|\(.status)|\(.conclusion // \"pending\")\"" \
                2>"$errf")"; then
                err="$(head -c 300 "$errf")"
                rm -f "$errf"
                fail "gh run list failed for $wf: ${err:-no error text}"
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
                    fail "workflow $wf (run $id) concluded '$conclusion' on ${sha:0:8}"
                fi
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
            fail "no run for${missing} on ${sha:0:8} after ${POLL_GRACE}s: the push did not trigger it"
        fi
        if [ "$elapsed" -ge "$POLL_TIMEOUT" ]; then
            rm -f "$errf"
            fail "CI poll timed out after ${POLL_TIMEOUT}s on ${sha:0:8}; still waiting on:${missing}${pending}"
        fi
        sleep "$POLL_INTERVAL"
    done
}

# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------

tag_release() {
    step "Tagging release"

    local message
    message="$(awk -v v="$VERSION" '
        $0 ~ "^## \\[" v "\\]" { capturing=1; next }
        capturing && /^## \[/ { exit }
        capturing && NF { print }
    ' "$CHANGELOG" | head -15)"

    if [[ -z "$message" ]]; then
        message="Release $TAG"
    fi

    git tag -a "$TAG" -m "$message"
    git push origin "$TAG"
    info "tagged and pushed: $TAG"
}

# ---------------------------------------------------------------------------
# Verification doc
# ---------------------------------------------------------------------------

write_verification_doc() {
    step "Writing verification doc"

    local doc="docs/$TAG-verification.md"

    if [[ -f "$doc" ]]; then
        info "$doc already exists; leaving it alone"
        return
    fi

    cat > "$doc" <<EOF
# $TAG Post-Release Verification

**Date:** $TODAY
**Tag:** $TAG
**Tag commit:** $(git rev-parse HEAD)

## Summary

| # | Check | Result |
|---|-------|--------|
| 8.1 | CI | TODO |
| 8.2 | Version consistency | TODO |
| 8.3 | Export drift | TODO |
| 8.4 | Validation | TODO |
| 8.5 | Mojibake | TODO |

## 8.1 — CI

TODO: paste the CI run URL and result.

## 8.2 — Version consistency

TODO: paste the output of \`python3 tools/check_version_consistency.py\`.

## 8.3 — Export drift

TODO: paste the output of the three \`--check\` commands and \`sync_wrappers.py --check\`.

## 8.4 — Validation

TODO: paste the output of \`python3 tools/validate.py\`.

## 8.5 — Mojibake

TODO: paste the output of \`python3 tools/check_mojibake.py\`.

## Known gaps

TODO
EOF

    git add "$doc"
    git commit -m "Add $TAG verification doc"
    git push origin main
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
    echo "  python3 tools/check_release_claims.py \$VERSION"
    echo "  python3 tools/export_sql.py --check"
    echo "  python3 tools/export_csv.py --check"
    echo "  python3 tools/export_parquet.py --check"
    echo "  python3 tools/export_countries_parquet.py --check"
    echo "  python3 tools/export_aggregated.py --check"
    echo "  python3 tools/sync_wrappers.py --check"
    echo "  python3 tools/check_mojibake.py"
    echo "  python3 tools/check_snapshot_freshness.py"
    echo "  python3 tools/check_registry_freshness.py"
    echo "  python3 tools/check_country_codes.py"
    echo "  bash tools/check_cross_language.sh"
    echo "  python3 -m pytest tests/ -q"
    echo
    echo "Post-gate:"
    echo "  git add -A && git commit -m 'Release $TAG'"
    echo "  git push origin main"
    echo "  poll CI: gh run list per workflow in POLLED_WORKFLOWS;"
    echo "    each must appear within ${POLL_GRACE}s and be completed/success;"
    echo "    timeout ${POLL_TIMEOUT}s (--poll-timeout); any other outcome fails, nothing is tagged"
    echo "  git tag -a $TAG -m '<first 15 lines of CHANGELOG section>'"
    echo "  git push origin $TAG"
    echo "  write docs/$TAG-verification.md"
    echo
    echo "============================================================"
    echo " DRY RUN — no changes will be made"
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
    print_plan
    exit "$EXIT_OK"
fi

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