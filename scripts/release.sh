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
Usage: bash scripts/release.sh <version> [--dry-run] [--force]

Arguments:
  <version>    Target version, X.Y.Z format.

Flags:
  --dry-run    Print every site and gate without mutating anything.
  --force      Allow releasing a version that is already tagged.

Exit codes:
  0  success (or successful dry-run)
  1  precondition failed
  2  usage error
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

DRY_RUN=false
FORCE=false
VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n) DRY_RUN=true; shift ;;
        --force|-f)   FORCE=true; shift ;;
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
        
    if [[ -f tools/check_cross_language.sh ]]; then
        run_gate_step "check_cross_language.sh"     bash tools/check_cross_language.sh
    fi

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

    if ! command -v gh >/dev/null 2>&1; then
        info "gh CLI not available; skipping CI poll"
        return
    fi

    local sha
    sha="$(git rev-parse HEAD)"
    info "waiting for CI on ${sha:0:8} (up to 5 minutes)"

    local i
    for i in $(seq 1 30); do
        local runs
        runs="$(gh run list --limit 30 \
            --json databaseId,headSha,status,conclusion,workflowName \
            --jq ".[] | select(.headSha == \"$sha\") | \"\(.databaseId)|\(.status)|\(.conclusion // \"pending\")|\(.workflowName)\"" \
            2>/dev/null || echo "")"

        if [ -z "$runs" ]; then
            sleep 10
            continue
        fi

        local all_complete=true
        local failed=false
        while IFS='|' read -r id status conclusion name; do
            if [ "$status" != "completed" ]; then
                all_complete=false
                break
            fi
            if [ "$conclusion" != "success" ]; then
                failed=true
                info "✗ workflow '$name' (run $id) concluded '$conclusion'"
            fi
        done <<< "$runs"

        if $failed; then
            fail "CI failed on ${sha:0:8}"
        fi

        if $all_complete; then
            info "✓ all workflows for ${sha:0:8} are completed success"
            return
        fi

        sleep 10
    done

    info "CI poll timed out; the run may still be in progress"
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
    [[ -f tools/check_cross_language.sh ]] && \
        echo "  bash tools/check_cross_language.sh"
    echo "  python3 -m pytest tests/ -q"
    echo
    echo "Post-gate:"
    echo "  git add -A && git commit -m 'Release $TAG'"
    echo "  git push origin main"
    echo "  gh run list  (poll until completed)"
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