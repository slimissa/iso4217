"""
The release harness (v1.9.4, audit finding P5-07, ADR 0014, docs/decisions/release-harness.md).

The older test_release_*.py files cut one function out of scripts/release.sh and run it alone. None of them runs the
script from main(), so none can see an ordering bug between stages or a failure one stage swallows. This file runs the
real script, from main(), in a throwaway git repository whose `origin` is a bare repository created for that test alone.

What is real and what is a stand-in (ADR 0014, D2):

  real      git (every push, tag, fetch and ls-remote goes to a real bare repo), bash, scripts/release.sh,
            tools/check_version_consistency.py, tools/check_verification_doc.py, scripts/bump_version.py when it exists
  stand-in  `gh` (a shell script on PATH driven by RH_GH_MODE; it reports a run only for a commit that origin holds), every other tools/ script (a stub that exits 0 unless
            the environment variable RH_FAIL names it), the pytest suites (one trivial test each)

A push is made to fail with a pre-receive hook in the bare repo, not by stubbing `git push`, so a push that does not
arrive is observable. Every test gets its own fixture; nothing is shared between tests. The one text change made to the script under test is
the poll timing (POLL_GRACE 60 to 3, POLL_INTERVAL 10 to 1), asserted to match exactly once.

Exit codes under test (ADR 0014, D6):
  0 ok | 1 precondition | 2 usage | 3 could not run | 4 generator or gate failed | 5 commit or push failed
  6 CI not green | 7 tag failed | 8 verification doc failed
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# The mutation sweep (test_release_harness_mutations.py) points these at a mutated copy; nothing else sets them.
RELEASE_SH = Path(os.environ.get("RH_RELEASE_SH") or PROJECT_ROOT / "scripts" / "release.sh")
BUMP_PY = Path(os.environ.get("RH_BUMP_PY") or PROJECT_ROOT / "scripts" / "bump_version.py")
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not BASH, reason="bash and POSIX git paths")

OLD, NEW = "1.0.0", "1.0.1"
E_OK, E_PRE, E_USAGE, E_COULD_NOT, E_GATE, E_PUSH, E_CI, E_TAG, E_DOC = 0, 1, 2, 3, 4, 5, 6, 7, 8

EXPORTERS = ["export_sql", "export_csv", "export_parquet", "export_countries_parquet", "export_aggregated", "sync_wrappers"]
STUB_PY = [
    "validate", "export_sql", "export_csv", "export_parquet", "export_countries_parquet", "export_aggregated",
    "sync_wrappers", "check_release_claims", "check_mojibake", "check_line_endings", "check_snapshot_freshness",
    "check_registry_freshness", "check_country_codes", "vendor_iso3166", "check_readme_drift", "check_provenance",
    "check_audit_table", "enrich_field",
]
STUB_SH = ["check_cross_language", "check_js_lint"]
SITE_FILES = ["VERSION", "CHANGELOG.md", "iso4217.json", "README.md", "wrappers/python/setup.py",
              "wrappers/javascript/package.json", "wrappers/rust/Cargo.toml"]

STUB_PY_SRC = '''\
import os, sys
me = os.path.basename(__file__)
if me in os.environ.get("RH_FAIL", "").split(","):
    print("forced failure of " + me)
    sys.exit(1)
if os.environ.get("RH_TODO_OUTPUT") == me:
    print("TODO: forced placeholder in the output of " + me)
if me == "export_sql.py" and os.environ.get("RH_LEAVE_UNTRACKED"):
    open("stray.txt", "w").write("left behind by a generator\\n")
print("ok " + me + " " + " ".join(sys.argv[1:]))
'''
STUB_SH_SRC = '''\
#!/usr/bin/env bash
me="$(basename "$0")"
case ",${RH_FAIL:-}," in *",$me,"*) echo "forced failure of $me"; exit 1 ;; esac
echo "ok $me $*"
'''
GH_SRC = '''\
#!/usr/bin/env bash
echo "gh $*" >> "$RH_GH_LOG"
mode="${RH_GH_MODE:-ok}"
if [ "$mode" = "error" ]; then echo "HTTP 401: Bad credentials" >&2; exit 1; fi
if [ "$1 $2" = "run list" ]; then
  case " $* " in
    *" --workflow "*)
      sha="$(printf '%s' "$*" | grep -o '[0-9a-f]\\{40\\}' | head -1)"
      if [ -n "$sha" ] && [ -n "$RH_ORIGIN" ]; then
        git --git-dir "$RH_ORIGIN" merge-base --is-ancestor "$sha" refs/heads/main 2>/dev/null || exit 0
      fi
      case "$mode" in
        norun)      exit 0 ;;
        ok)         echo "4242|completed|success" ;;
        red)        echo "4242|completed|failure" ;;
        poll_error) echo "HTTP 500: server error" >&2; exit 1 ;;
      esac ;;
  esac
fi
exit 0
'''
CONFTEST = (
    "def pytest_addoption(parser):\n"
    "    parser.addoption('--fail-on-skip', action='store_true', default=False)\n"
)
HOOK_REJECT_TAGS = ('while read old new ref; do case "$ref" in refs/tags/*) '
                    'echo "tag rejected by the test hook" >&2; exit 1;; esac; done\n')
HOOK_REJECT_MAIN = ('while read old new ref; do case "$ref" in refs/heads/main) '
                    'echo "push rejected by the test hook" >&2; exit 1;; esac; done\n')


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def no_gh_path(tmp_path_factory) -> str:
    """A PATH that holds every system executable except `gh`, so 'gh is not installed' is hermetic."""
    farm = tmp_path_factory.mktemp("nogh")
    for d in ("/usr/bin", "/bin"):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            link = farm / name
            if name != "gh" and not link.exists():
                try:
                    link.symlink_to(Path(d) / name)
                except OSError:
                    pass
    return str(farm)


class Fx:
    def __init__(self, base: Path, no_gh_path: str):
        self.base = base
        self.work = base / "work"
        self.origin = base / "origin.git"
        self.bin = base / "bin"
        self.tmp = base / "tmp"
        self.ghlog = base / "gh.log"
        self.no_gh_path = no_gh_path

    # -- git ---------------------------------------------------------------
    def _env(self, extra: dict | None = None, no_gh: bool = False) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith("RH_")}  # also drops RH_RELEASE_SH, RH_BUMP_PY
        env.update(
            GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_TERMINAL_PROMPT="0",
            PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(self.tmp), RH_GH_LOG=str(self.ghlog), RH_ORIGIN=str(self.origin),
            PATH=self.no_gh_path if no_gh else f"{self.bin}{os.pathsep}{os.environ['PATH']}",
        )
        env.update(extra or {})
        return env

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.work, capture_output=True, text=True, env=self._env())
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
        return r.stdout.strip()

    def ogit(self, *args: str) -> str:
        r = subprocess.run(["git", "--git-dir", str(self.origin), *args], capture_output=True, text=True, env=self._env())
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel: str) -> str:
        return (self.work / rel).read_text(encoding="utf-8")

    def edit(self, rel: str, old: str, new: str) -> None:
        text = self.read(rel)
        assert old in text, f"{rel} does not contain {old!r}"
        self.write(rel, text.replace(old, new, 1))

    def commit_all(self, msg: str = "fixture change") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        self.git("push", "-q", "origin", "main")

    def hook(self, body: str) -> None:
        h = self.origin / "hooks" / "pre-receive"
        h.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        h.chmod(0o755)

    def clear_hook(self) -> None:
        (self.origin / "hooks" / "pre-receive").unlink(missing_ok=True)

    # -- state -------------------------------------------------------------
    def origin_main(self) -> str:
        return self.ogit("rev-parse", "refs/heads/main")

    def origin_tags(self) -> list[str]:
        return self.ogit("tag", "-l").split()

    def local_tags(self) -> list[str]:
        return self.git("tag", "-l").split()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def snapshot(self) -> dict:
        return {
            "head": self.head(), "origin": self.origin_main(), "status": self.git("status", "--porcelain"),
            "version": self.read("VERSION"), "otags": self.origin_tags(), "ltags": self.local_tags(),
        }

    def gh_calls(self) -> list[str]:
        return self.ghlog.read_text().splitlines() if self.ghlog.exists() else []

    def tmp_entries(self) -> list[str]:
        return sorted(os.listdir(self.tmp))

    # -- run ---------------------------------------------------------------
    def run(self, *args: str, env: dict | None = None, no_gh: bool = False, timeout: int = 240):
        r = subprocess.run([BASH, "scripts/release.sh", *args], cwd=self.work, capture_output=True, text=True,
                           env=self._env(env, no_gh), timeout=timeout)
        r.out = r.stdout + r.stderr
        return r


def _verification_doc(version: str) -> str:
    return f"# v{version} Post-Release Verification\n\n" + "".join(
        f"Evidence line {i} for v{version}: recorded and checked.\n" for i in range(1, 91))


def _changelog(top_version: str = NEW, heading_tail: str = "Unreleased") -> str:
    return (
        "# Changelog\n\n"
        f"## [{top_version}] \u2014 {heading_tail}\n\n### Fixed\n\n- A fix shipped in {top_version}.\n\n"
        f"## [{OLD}] \u2014 2026-01-01\n\n- Initial release.\n"
    )


def build_fixture(base: Path, no_gh_path: str, manifest: tuple = (OLD, NEW)) -> Fx:
    fx = Fx(base, no_gh_path)
    fx.work.mkdir(parents=True)
    fx.bin.mkdir()
    fx.tmp.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(fx.origin)], check=True)
    fx.git("init", "-q", "-b", "main")
    fx.git("config", "user.email", "harness@example.com")
    fx.git("config", "user.name", "harness")
    fx.git("remote", "add", "origin", str(fx.origin))

    gh = fx.bin / "gh"
    gh.write_text(GH_SRC)
    gh.chmod(0o755)

    script = RELEASE_SH.read_text(encoding="utf-8")
    for old, new in (("POLL_GRACE=60", "POLL_GRACE=3"), ("POLL_INTERVAL=10", "POLL_INTERVAL=1")):
        assert script.count(old) == 1, f"the harness expects exactly one {old} in the script under test"
        script = script.replace(old, new)
    _mk(fx.work / "scripts" / "release.sh").write_text(script, encoding="utf-8")
    if BUMP_PY.exists():
        shutil.copy(BUMP_PY, fx.work / "scripts" / "bump_version.py")
    for real in ("check_version_consistency.py", "check_verification_doc.py"):
        shutil.copy(PROJECT_ROOT / "tools" / real, _mk(fx.work / "tools" / real))
    for name in STUB_PY:
        fx.write(f"tools/{name}.py", STUB_PY_SRC)
    for name in STUB_SH:
        fx.write(f"tools/{name}.sh", STUB_SH_SRC)

    fx.write(".gitignore", "__pycache__/\n.pytest_cache/\n")
    fx.write("VERSION", OLD + "\n")
    fx.write("CHANGELOG.md", _changelog())
    fx.write("iso4217.json", json.dumps(
        {"meta": {"version": OLD, "updated": "2026-01-01", "schema_version": "1.3.0"}, "currencies": [{"code": "USD"}]},
        indent=2) + "\n")
    fx.write("schema.json", json.dumps({"$id": "https://example.com/iso4217/schema/v1.3.0/iso4217.schema.json"}) + "\n")
    fx.write("README.md", f"# Registry\n\n![v](https://img.shields.io/badge/registry-{OLD}-orange.svg)\n"
                          "![s](https://img.shields.io/badge/schema-1.3.0-blue.svg)\n")
    fx.write("wrappers/python/setup.py", f'VERSION = "{OLD}"\n')
    fx.write("wrappers/javascript/package.json", json.dumps({"name": "iso4217", "version": OLD}, indent=2) + "\n")
    fx.write("wrappers/rust/Cargo.toml",
             f'[package]\nname = "iso4217"\nversion = "{OLD}"\n\n[dependencies.serde]\nversion = "7.0.0"\n\n'
             f'[dependencies]\nserde = {{ version = "1" }}\n')
    fx.write("tools/release_claims.json", json.dumps({v: {} for v in manifest}) + "\n")
    for wf in ("validate.yml", "version-and-hygiene.yml"):
        fx.write(f".github/workflows/{wf}", "name: x\non: push\n")
    fx.write("docs/v1.0.0-verification.md", _verification_doc(OLD))
    for d, fail_name in (("tests", "pytest"), ("wrappers/python/tests", "pytest-wrappers")):
        fx.write(f"{d}/conftest.py", CONFTEST)
        fx.write(f"{d}/test_ok.py",
                 f'import os\n\n\ndef test_ok():\n    assert "{fail_name}" not in os.environ.get("RH_FAIL", "").split(",")\n')
    fx.git("add", "-A")
    fx.git("commit", "-q", "-m", "fixture base")
    fx.git("push", "-q", "-u", "origin", "main")
    return fx


def _mk(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def fx(tmp_path, no_gh_path) -> Fx:
    return build_fixture(tmp_path, no_gh_path)


def _fx_with(tmp_path, no_gh_path, **kw) -> Fx:
    return build_fixture(tmp_path, no_gh_path, **kw)


def _release_ok(fx: Fx):
    r = fx.run(NEW)
    assert r.returncode == 0, r.out
    return r


def _assert_untouched_by_a_failed_precondition(fx: Fx, before: dict) -> None:
    assert fx.snapshot() == before, "a failed precondition must leave the repository and origin exactly as found"
    assert not any("--workflow" in c for c in fx.gh_calls()), "CI must not be polled after a failed precondition"


# ---------------------------------------------------------------------------
# Usage (exit 2)
# ---------------------------------------------------------------------------

class TestUsage:
    @pytest.mark.parametrize("args", [(), ("1.0",), ("1.0.1", "--bogus"), ("1.0.1", "1.0.2"), ("1.0.1", "--poll-timeout", "0")])
    def test_a_usage_error_exits_2_and_changes_nothing(self, fx, args):
        before = fx.snapshot()
        r = fx.run(*args)
        assert r.returncode == E_USAGE, r.out
        assert fx.snapshot() == before

    def test_release_sh_reads_the_clock_exactly_once(self):
        # ADR 0014, D8: TODAY is computed once, in UTC, and passed to every date site.
        assert RELEASE_SH.read_text(encoding="utf-8").count("date -u") == 1

    def test_bump_version_never_reads_the_clock(self):
        assert BUMP_PY.exists(), "scripts/bump_version.py does not exist yet"
        imports = re.findall(r"^\s*(?:import|from)\s+(\w+)", BUMP_PY.read_text(encoding="utf-8"), re.M)
        assert not {"datetime", "time", "calendar"} & set(imports)
        assert not re.search(r"\.(today|now|utcnow)\(", BUMP_PY.read_text(encoding="utf-8"))

    def test_usage_documents_every_exit_code(self, fx):
        r = fx.run("--help")
        assert r.returncode == 0
        for code in range(0, 9):
            assert re.search(rf"^\s*{code}\s+\S", r.out, re.M), f"--help does not document exit code {code}"


# ---------------------------------------------------------------------------
# Preconditions: ten, each forced from main() (ADR 0014, D7)
# ---------------------------------------------------------------------------

class TestPreconditions:
    def test_check_clean_tree(self, fx):
        fx.write("stray.txt", "x")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "working tree is not clean" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_head_at_origin_when_origin_has_moved(self, fx, tmp_path):
        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", str(fx.origin), str(other)], check=True, env=fx._env())
        (other / "x.txt").write_text("x")
        for a in (["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "moved"],
                  ["push", "-q", "origin", "main"]):
            subprocess.run(["git", *a], cwd=other, check=True, env=fx._env())
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "HEAD is not at origin/main" in r.out
        assert fx.snapshot()["head"] == before["head"]
        assert fx.snapshot()["version"] == before["version"]

    def test_check_head_at_origin_when_origin_is_unreachable_could_not_run(self, fx):
        fx.git("remote", "set-url", "origin", str(fx.base / "does-not-exist.git"))
        r = fx.run(NEW)
        assert r.returncode == E_COULD_NOT, r.out
        assert "cannot fetch origin/main" in r.out

    def test_check_on_main(self, fx):
        fx.git("checkout", "-q", "-b", "side")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "not on main" in r.out and "side" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_workflows_covered_refuses_an_unpolled_push_workflow(self, fx):
        fx.write(".github/workflows/extra.yml", "name: e\non: push\n")
        fx.commit_all("add a workflow")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "extra.yml is not in the poll list" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    @pytest.mark.parametrize("name", ["monitor-amendments", "fetch-x", "refresh-y", "update-docs", "schedule-z"])
    def test_check_workflows_covered_exempts_the_five_prefixes_unchanged(self, fx, name):
        # ADR 0014, consequence 7: the exemption list is unchanged here and is a v1.9.5 finding.
        fx.write(f".github/workflows/{name}.yml", "name: e\non: push\n")
        fx.commit_all("add an exempt workflow")
        r = fx.run(NEW, "--dry-run")
        assert r.returncode == E_OK, r.out
        assert "all per-push workflows are in the poll list" in r.out

    def test_check_gh_ready_gh_missing_is_could_not_run(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, no_gh=True)
        assert r.returncode == E_COULD_NOT, r.out
        assert "gh CLI not found" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_gh_ready_gh_unauthenticated_is_could_not_run(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, env={"RH_GH_MODE": "error"})
        assert r.returncode == E_COULD_NOT, r.out
        assert "gh cannot list workflow runs" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_tag_free_refuses_a_local_tag(self, fx):
        fx.git("tag", f"v{NEW}")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert f"tag v{NEW} already exists" in r.out and "--force" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_tag_free_sees_a_tag_that_exists_only_on_origin(self, fx):
        # ADR 0014, consequence 5: the v1.9.3 check asked only the local repository.
        fx.git("tag", f"v{NEW}")
        fx.git("push", "-q", "origin", f"v{NEW}")
        fx.git("tag", "-d", f"v{NEW}")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE, r.out
        assert "already exists" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_changelog_section(self, fx):
        fx2 = fx
        fx2.write("tools/release_claims.json", json.dumps({OLD: {}, NEW: {}, "1.0.2": {}}) + "\n")
        fx2.commit_all("claims for 1.0.2")
        before = fx2.snapshot()
        r = fx2.run("1.0.2")
        assert r.returncode == E_PRE
        assert "has no '## [1.0.2]' section" in r.out
        _assert_untouched_by_a_failed_precondition(fx2, before)

    def test_check_manifest_has_version(self, tmp_path, no_gh_path):
        fx = _fx_with(tmp_path, no_gh_path, manifest=(OLD,))
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "has no entry for version" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_version_consistency(self, fx):
        fx.write("wrappers/python/setup.py", 'VERSION = "0.9.0"\n')
        fx.commit_all("drift")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "check_version_consistency.py is not currently passing" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)

    def test_check_no_orphan_variables(self, fx):
        with open(fx.work / "scripts" / "release.sh", "a", encoding="utf-8") as f:
            f.write('\n# appended by the harness\ntrue "$HARNESS_ORPHAN_VAR"\n')
        fx.commit_all("orphan")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE
        assert "undefined variables" in r.out and "HARNESS_ORPHAN_VAR" in r.out
        _assert_untouched_by_a_failed_precondition(fx, before)


# ---------------------------------------------------------------------------
# Bump sites: each site holds NEW after a release, and each silent miss now fails (ADR 0014, D8, consequences 2 and 6)
# ---------------------------------------------------------------------------

def _assert_all_sites(read, version: str, changelog_date: str | None = None) -> None:
    assert read("VERSION").strip() == version
    j = json.loads(read("iso4217.json"))
    assert j["meta"]["version"] == version
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", j["meta"]["updated"])
    assert f"badge/registry-{version}-orange" in read("README.md")
    assert "badge/schema-1.3.0-blue" in read("README.md"), "the schema badge is a different axis and must not move"
    assert f'VERSION = "{version}"' in read("wrappers/python/setup.py")
    assert json.loads(read("wrappers/javascript/package.json"))["version"] == version
    cargo = read("wrappers/rust/Cargo.toml")
    assert f'version = "{version}"' in cargo and 'serde = { version = "1" }' in cargo
    assert '[dependencies.serde]\nversion = "7.0.0"' in cargo, "only [package].version may be rewritten"
    m = re.search(rf"^## \[{re.escape(version)}\] \u2014 (\S+)$", read("CHANGELOG.md"), re.M)
    assert m and re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group(1)), "the CHANGELOG heading must be dated"
    assert m.group(1) == j["meta"]["updated"], "the CHANGELOG date and meta.updated come from the same day"


class TestBumpsThroughTheRelease:
    def test_every_site_holds_the_new_version_in_the_release_commit(self, fx):
        _release_ok(fx)
        files = fx.ogit("show", "--name-only", "--format=", f"v{NEW}^{{commit}}").split()
        assert sorted(files) == sorted(SITE_FILES)
        _assert_all_sites(lambda rel: fx.ogit("show", f"v{NEW}^{{commit}}:{rel}"), NEW)

    @pytest.mark.parametrize("site,rel,old,new", [
        ("changelog", "CHANGELOG.md", "\u2014 Unreleased", "- Unreleased"),            # hyphen: skipped by the checker, missed by the bump
        ("iso_json_version", "iso4217.json", '"version"', '"ver"'),
        ("iso_json_updated", "iso4217.json", '"updated"', '"upd"'),
        ("readme_badge", "README.md", "badge/registry-", "badge/reg-"),
        ("setup_py", "wrappers/python/setup.py", "VERSION =", "PKG_VERSION ="),
        ("package_json", "wrappers/javascript/package.json", '"version": "1.0.0"', '"v": "1.0.0"'),
        ("cargo_toml", "wrappers/rust/Cargo.toml", 'name = "iso4217"\nversion = "1.0.0"', 'name = "iso4217"'),
    ])
    def test_a_site_whose_pattern_is_gone_fails_loudly_instead_of_staying_old(self, fx, site, rel, old, new):
        fx.edit(rel, old, new)
        fx.commit_all(f"break {site}")
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_GATE, f"{site}: a bump that matched nothing must exit 4, got {r.returncode}\n{r.out}"
        assert site in r.out, "the failure must name the site"
        after = fx.snapshot()
        assert after["head"] == before["head"] and after["origin"] == before["origin"]
        assert after["otags"] == before["otags"] == [] and after["ltags"] == []

    def test_iso_json_never_rewrites_a_version_outside_meta(self, fx):
        # With meta.version gone, the v1.9.3 regex rewrites the first "version" it finds anywhere in the file.
        data = {"meta": {"updated": "2026-01-01"}, "currencies": [{"code": "USD", "version": OLD}]}
        fx.write("iso4217.json", json.dumps(data, indent=2) + "\n")
        fx.commit_all("meta.version removed")
        r = fx.run(NEW)
        assert r.returncode == E_GATE, r.out
        assert json.loads(fx.read("iso4217.json"))["currencies"][0]["version"] == OLD

    def test_the_schema_badge_is_not_a_registry_site(self, fx):
        _release_ok(fx)
        assert "badge/schema-1.3.0-blue" in fx.read("README.md")


# ---------------------------------------------------------------------------
# scripts/bump_version.py, one site per call (ADR 0014, D8)
# ---------------------------------------------------------------------------

def _pkg(version: str) -> str:
    return json.dumps({"name": "x", "version": version}, indent=2) + "\n"


def _json(version: str = OLD, updated: str = "2026-01-01") -> str:
    return json.dumps({"meta": {"version": version, "updated": updated}}, indent=2) + "\n"


SITE_UNIT_CASES = {
    # site: (file, args (OLD, NEW), old content, expected new content, foreign content, no-pattern content)
    "version": ("VERSION", (OLD, NEW), f"{OLD}\n", f"{NEW}\n", "0.9.0\n", "garbage\n"),
    "changelog": ("CHANGELOG.md", (f"## [{NEW}] \u2014 Unreleased", f"## [{NEW}] \u2014 2026-10-28"),
                  f"# C\n\n## [{NEW}] \u2014 Unreleased\n\n- x\n", f"# C\n\n## [{NEW}] \u2014 2026-10-28\n\n- x\n",
                  f"# C\n\n## [{NEW}] \u2014 2026-09-09\n\n- x\n", "# C\n\n- x\n"),
    "iso_json_version": ("iso4217.json", (OLD, NEW), _json(OLD), _json(NEW), _json("0.9.0"),
                        json.dumps({"meta": {"updated": "2026-01-01"}}, indent=2) + "\n"),
    "iso_json_updated": ("iso4217.json", ("DATE", "2026-10-28"), _json(updated="2026-01-01"), _json(updated="2026-10-28"),
                         _json(updated="soon"), json.dumps({"meta": {"version": OLD}}, indent=2) + "\n"),
    "readme_badge": ("README.md", (OLD, NEW), f"![v](https://img.shields.io/badge/registry-{OLD}-orange.svg)\n",
                     f"![v](https://img.shields.io/badge/registry-{NEW}-orange.svg)\n",
                     "![v](https://img.shields.io/badge/registry-0.9.0-orange.svg)\n", "no badge here\n"),
    "setup_py": ("wrappers/python/setup.py", (OLD, NEW), f'VERSION = "{OLD}"\n', f'VERSION = "{NEW}"\n',
                 'VERSION = "0.9.0"\n', f'PKG_VERSION = "{OLD}"\n'),
    "package_json": ("wrappers/javascript/package.json", (OLD, NEW), _pkg(OLD), _pkg(NEW), _pkg("0.9.0"),
                     json.dumps({"name": "x"}, indent=2) + "\n"),
    "cargo_toml": ("wrappers/rust/Cargo.toml", (OLD, NEW),
                   f'[package]\nname = "x"\nversion = "{OLD}"\n\n[dependencies]\nserde = {{ version = "1" }}\n',
                   f'[package]\nname = "x"\nversion = "{NEW}"\n\n[dependencies]\nserde = {{ version = "1" }}\n',
                   '[package]\nname = "x"\nversion = "0.9.0"\n',
                   '[package]\nname = "x"\n\n[dependencies]\nserde = { version = "1" }\n'),
}


def _bump(root: Path, site: str, old: str, new: str):
    assert BUMP_PY.exists(), "scripts/bump_version.py does not exist yet (a missing script would exit 2 and fake a pass)"
    return subprocess.run([sys.executable, str(BUMP_PY), "--root", str(root), "--from", old, "--to", new, site],
                          capture_output=True, text=True)


@pytest.fixture(params=sorted(SITE_UNIT_CASES))
def site_case(request, tmp_path):
    site = request.param
    rel, args, old_c, new_c, foreign, nopat = SITE_UNIT_CASES[site]
    return site, tmp_path, rel, args, old_c, new_c, foreign, nopat


class TestBumpVersionScript:
    def test_the_script_exists(self):
        assert BUMP_PY.exists(), "scripts/bump_version.py is the ADR 0014 D8 extraction of the four heredocs and two seds"

    def test_it_writes_the_new_value_and_changes_nothing_else(self, site_case):
        site, root, rel, (old, new), old_c, new_c, *_ = site_case
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(old_c, encoding="utf-8")
        r = _bump(root, site, old, new)
        assert r.returncode == 0, r.stdout + r.stderr
        assert (root / rel).read_text(encoding="utf-8") == new_c

    def test_running_it_twice_is_a_no_op(self, site_case):
        site, root, rel, (old, new), old_c, new_c, *_ = site_case
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(old_c, encoding="utf-8")
        assert _bump(root, site, old, new).returncode == 0
        first = (root / rel).read_bytes()
        r = _bump(root, site, old, new)
        assert r.returncode == 0 and (root / rel).read_bytes() == first
        assert "already" in (r.stdout + r.stderr).lower()

    def test_a_site_holding_neither_old_nor_new_exits_1_and_is_left_alone(self, site_case):
        site, root, rel, (old, new), _o, _n, foreign, _p = site_case
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(foreign, encoding="utf-8")
        r = _bump(root, site, old, new)
        assert r.returncode == 1, r.stdout + r.stderr
        assert site in (r.stdout + r.stderr) and rel in (r.stdout + r.stderr)
        assert (root / rel).read_text(encoding="utf-8") == foreign

    def test_a_site_without_its_pattern_exits_1_and_is_left_alone(self, site_case):
        site, root, rel, (old, new), _o, _n, _f, nopat = site_case
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(nopat, encoding="utf-8")
        r = _bump(root, site, old, new)
        assert r.returncode == 1, r.stdout + r.stderr
        assert (root / rel).read_text(encoding="utf-8") == nopat

    def test_a_missing_site_file_exits_2(self, site_case):
        site, root, _rel, (old, new), *_ = site_case
        assert _bump(root, site, old, new).returncode == 2

    def test_an_unknown_site_exits_2(self, tmp_path):
        assert _bump(tmp_path, "nonsense", OLD, NEW).returncode == 2


# ---------------------------------------------------------------------------
# --force and the tag state (ADR 0014, D3, consequence 4)
# ---------------------------------------------------------------------------

def _release_that_leaves_a_local_only_tag(fx: Fx):
    """The real v1.9.2 state: the release commit is on origin, the tag was created locally, its push was rejected."""
    fx.hook(HOOK_REJECT_TAGS)
    r = fx.run(NEW)
    fx.clear_hook()
    return r


class TestForce:
    def test_a_tag_push_that_fails_is_exit_7_and_leaves_the_commit_public_and_the_tag_local(self, fx):
        r = _release_that_leaves_a_local_only_tag(fx)
        assert r.returncode == E_TAG, r.out
        assert f"v{NEW}" in fx.local_tags() and fx.origin_tags() == []
        assert fx.origin_main() == fx.head(), "the release commit is public"

    def test_without_force_a_local_only_tag_is_refused_and_force_is_named(self, fx):
        _release_that_leaves_a_local_only_tag(fx)
        before = fx.snapshot()
        r = fx.run(NEW)
        assert r.returncode == E_PRE, r.out
        assert "--force" in r.out
        assert fx.snapshot() == before

    def test_force_with_a_local_only_tag_recreates_and_publishes_it_at_the_release_commit(self, fx):
        _release_that_leaves_a_local_only_tag(fx)
        release_commit = fx.head()
        r = fx.run(NEW, "--force")
        assert r.returncode == E_OK, r.out
        assert fx.origin_tags() == [f"v{NEW}"]
        assert fx.ogit("rev-parse", f"v{NEW}^{{commit}}") == release_commit
        assert fx.ogit("cat-file", "-t", f"v{NEW}") == "tag", "the tag is annotated"
        assert "A fix shipped in 1.0.1." in fx.ogit("for-each-ref", f"refs/tags/v{NEW}", "--format=%(contents)")

    def test_force_never_moves_a_tag_that_is_on_origin(self, fx):
        _release_ok(fx)
        tag_obj = fx.ogit("rev-parse", f"refs/tags/v{NEW}")
        main_before = fx.origin_main()
        r = fx.run(NEW, "--force")
        assert r.returncode == E_PRE, r.out
        # The right reason, at the right stage. Against the v1.9.3 script this exits 1 for a different reason (the
        # stub verification doc trips the gate on the re-run), so the exit code alone would be a false pass.
        assert "already exists" in r.out and "origin" in r.out.lower(), "the refusal must name the published tag"
        assert "Running gate" not in r.out and "Bumping version sites" not in r.out, "refused before anything is mutated"
        assert fx.ogit("rev-parse", f"refs/tags/v{NEW}") == tag_obj
        assert fx.origin_main() == main_before, "a refused --force must not push anything either"

    def test_force_with_no_tag_anywhere_proceeds_and_says_it_had_nothing_to_do(self, fx):
        r = fx.run(NEW, "--force")
        assert r.returncode == E_OK, r.out
        assert fx.origin_tags() == [f"v{NEW}"]
        assert "nothing to do" in r.out.lower()


# ---------------------------------------------------------------------------
# Generators, the gate, and what a failure leaves behind (D9, D10, exit 4)
# ---------------------------------------------------------------------------

class TestGateAndGenerators:
    def test_a_failing_gate_step_aborts_before_any_commit_tag_or_poll(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, env={"RH_FAIL": "check_mojibake.py"})
        assert r.returncode == E_GATE, r.out
        after = fx.snapshot()
        assert after["head"] == before["head"], "no commit"
        assert after["origin"] == before["origin"], "nothing pushed"
        assert after["otags"] == [] and after["ltags"] == [], "no tag"
        assert not any("--workflow" in c for c in fx.gh_calls()), "CI not polled"
        assert not (fx.work / f"docs/v{NEW}-verification.md").exists(), "no verification doc"

    def test_a_failed_gate_leaves_the_mutated_tree_and_names_the_exact_recovery(self, fx):
        r = fx.run(NEW, env={"RH_FAIL": "check_mojibake.py"})
        assert r.returncode == E_GATE
        assert fx.read("VERSION").strip() == NEW, "ADR 0014, D10: no automatic rollback"
        assert "git checkout -- ." in r.out

    def test_the_gate_runs_every_step_and_reports_every_failure(self, fx):
        r = fx.run(NEW, env={"RH_FAIL": "check_mojibake.py,check_line_endings.py,pytest"})
        assert r.returncode == E_GATE
        for name in ("check_mojibake.py", "check_line_endings.py", "pytest tests/"):
            assert f"\u2717 {name}" in r.out, f"{name} must be reported as failed"
        assert "\u2713 validate.py" in r.out, "steps after a failure still run"

    def test_the_script_does_not_claim_the_gate_stops_at_the_first_failure(self):
        assert "stops at the first failure" not in RELEASE_SH.read_text(encoding="utf-8")

    @pytest.mark.parametrize("gen", EXPORTERS)
    def test_a_failing_generator_is_exit_4_names_itself_and_skips_the_gate(self, fx, gen):
        r = fx.run(NEW, env={"RH_FAIL": f"{gen}.py"})
        assert r.returncode == E_GATE, r.out
        assert f"{gen}.py exited non-zero" in r.out
        assert "Running gate" not in r.out
        assert fx.origin_tags() == []

    def test_a_file_left_behind_by_a_generator_aborts_before_the_commit(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, env={"RH_LEAVE_UNTRACKED": "1"})
        assert r.returncode == E_GATE, r.out
        assert "untracked file(s) would be added to the release commit" in r.out and "stray.txt" in r.out
        assert fx.git("diff", "--cached", "--name-only") == "", "the untracked-file guard fires before anything is staged"
        assert fx.snapshot()["head"] == before["head"] and fx.origin_main() == before["origin"]


# ---------------------------------------------------------------------------
# Push, CI, tag (exits 5, 6, 7)
# ---------------------------------------------------------------------------

class TestPushCiTag:
    def test_a_rejected_push_is_exit_5_and_nothing_is_tagged(self, fx):
        fx.hook(HOOK_REJECT_MAIN)
        before = fx.origin_main()
        r = fx.run(NEW)
        assert r.returncode == E_PUSH, r.out
        assert fx.origin_main() == before and fx.origin_tags() == [] and fx.local_tags() == []
        assert not any("--workflow" in c for c in fx.gh_calls())

    def test_a_red_run_is_exit_6_the_commit_is_public_and_nothing_is_tagged(self, fx):
        r = fx.run(NEW, env={"RH_GH_MODE": "red"})
        assert r.returncode == E_CI, r.out
        assert "concluded 'failure'" in r.out
        assert fx.origin_main() == fx.head() and fx.origin_tags() == [] and fx.local_tags() == []

    def test_no_run_for_the_pushed_commit_is_exit_6_and_nothing_is_tagged(self, fx):
        r = fx.run(NEW, env={"RH_GH_MODE": "norun"})
        assert r.returncode == E_CI, r.out
        assert "no run for" in r.out
        assert fx.origin_tags() == [] and fx.local_tags() == []

    def test_a_gh_error_while_polling_is_exit_6_and_nothing_is_tagged(self, fx):
        r = fx.run(NEW, env={"RH_GH_MODE": "poll_error"})
        assert r.returncode == E_CI, r.out
        assert fx.origin_tags() == [] and fx.local_tags() == []

    def test_both_polled_workflows_are_asked_about(self, fx):
        _release_ok(fx)
        polls = " ".join(c for c in fx.gh_calls() if "--workflow" in c)
        assert "validate.yml" in polls and "version-and-hygiene.yml" in polls

    def test_a_rerun_after_a_red_ci_does_not_bump_again_and_reaches_the_tag(self, fx):
        fx.run(NEW, env={"RH_GH_MODE": "red"})
        release_commit = fx.head()
        r = fx.run(NEW)
        assert r.returncode == E_OK, r.out
        assert fx.ogit("rev-parse", f"v{NEW}^{{commit}}") == release_commit


# ---------------------------------------------------------------------------
# The verification doc (ADR 0014, D4, exit 8)
# ---------------------------------------------------------------------------

class TestVerificationDoc:
    def test_the_second_commit_is_one_complete_doc_that_the_repos_own_checker_accepts(self, fx):
        _release_ok(fx)
        log = fx.ogit("log", "--format=%H", "-3").split()
        doc_commit, release_commit = log[0], log[1]
        assert fx.ogit("rev-parse", f"v{NEW}^{{commit}}") == release_commit, "the tag names the release commit, not the doc"
        assert fx.ogit("show", "--name-only", "--format=", doc_commit).split() == [f"docs/v{NEW}-verification.md"]
        doc = fx.ogit("show", f"{doc_commit}:docs/v{NEW}-verification.md")
        assert not re.search(r"\bTODO\b|<paste|PLACEHOLDER", doc), "no stub, no placeholder"
        checker = subprocess.run([sys.executable, "tools/check_verification_doc.py"], cwd=fx.work, capture_output=True,
                                 text=True, env=fx._env())
        assert checker.returncode == 0, checker.stdout + checker.stderr

    def test_the_doc_carries_the_tag_commit_the_ci_runs_and_the_gate_steps(self, fx):
        _release_ok(fx)
        doc = fx.read(f"docs/v{NEW}-verification.md")
        assert fx.ogit("rev-parse", f"v{NEW}^{{commit}}") in doc, "the tag commit hash"
        assert "4242" in doc, "the CI run id the poll already holds"
        assert "validate.yml" in doc and "version-and-hygiene.yml" in doc
        assert "check_mojibake.py" in doc and "pytest tests/" in doc, "the gate steps"

    def test_a_todo_in_the_gate_evidence_does_not_fail_the_doc(self, fx):
        # v1.9.4 fix: a TODO inside a fenced code block (the gate evidence) is data,
        # not a placeholder. The doc is committed; the release exits 0. The prose-TODO
        # case is tested in tests/test_release_hygiene.py (function extraction).
        r = fx.run(NEW, env={"RH_TODO_OUTPUT": "check_mojibake.py"})
        assert r.returncode == E_OK, r.out
        assert fx.origin_tags() == [f"v{NEW}"], "the release is tagged"
        doc = fx.read(f"docs/v{NEW}-verification.md")
        assert "TODO: forced placeholder in the output of check_mojibake.py" in doc, "the gate evidence is present"
        checker = subprocess.run(
            [sys.executable, "tools/check_verification_doc.py"],
            cwd=fx.work, capture_output=True, text=True, env=fx._env(),
        )
        assert checker.returncode == 0, f"the doc with a fenced TODO must pass the checker:\n{checker.stdout}\n{checker.stderr}"

    def test_a_doc_push_that_fails_is_exit_8(self, fx):
        # The tag push is allowed; the push of main after the tag is rejected. The hook rejects main only once the tag exists.
        fx.hook('while read old new ref; do case "$ref" in refs/heads/main) '
                'if git rev-parse -q --verify "refs/tags/v1.0.1" >/dev/null; then echo "doc push rejected" >&2; exit 1; fi;; '
                'esac; done\n')
        r = fx.run(NEW)
        assert r.returncode == E_DOC, r.out
        assert fx.origin_tags() == [f"v{NEW}"]

    def test_a_doc_that_already_exists_is_left_alone(self, fx):
        fx.write(f"docs/v{NEW}-verification.md", _verification_doc(NEW) + "Hand-written.\n")
        fx.commit_all("pre-authored doc")
        text = fx.read(f"docs/v{NEW}-verification.md")
        r = fx.run(NEW)
        assert r.returncode == E_OK, r.out
        assert fx.read(f"docs/v{NEW}-verification.md") == text
        assert "already exists" in r.out


# ---------------------------------------------------------------------------
# Dry run (ADR 0014, D5)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_it_runs_the_gate_for_real_and_leaves_the_operators_tree_and_origin_untouched(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, "--dry-run")
        assert r.returncode == E_OK, r.out
        assert "Running gate" in r.out and "\u2713 pytest tests/" in r.out and "\u2713 check_verification_doc.py" in r.out, \
            "a dry-run that does not run the gate is a plan"
        assert fx.snapshot() == before, "the operator's tree, commits, tags and origin are exactly as they were"
        assert not any("--workflow" in c for c in fx.gh_calls()), "no CI poll"

    def test_a_dry_run_leaves_the_tree_clean_enough_for_the_real_release_to_follow(self, fx):
        assert fx.run(NEW, "--dry-run").returncode == E_OK
        assert fx.run(NEW).returncode == E_OK

    def test_a_failing_gate_in_a_dry_run_is_exit_4_and_still_touches_nothing(self, fx):
        before = fx.snapshot()
        r = fx.run(NEW, "--dry-run", env={"RH_FAIL": "check_mojibake.py"})
        assert r.returncode == E_GATE, r.out
        assert fx.snapshot() == before

    def test_the_temporary_copy_is_removed_after_a_passing_dry_run(self, fx):
        assert fx.run(NEW, "--dry-run").returncode == E_OK
        assert fx.tmp_entries() == []

    def test_the_temporary_copy_is_removed_after_a_dry_run_whose_gate_fails(self, fx):
        assert fx.run(NEW, "--dry-run", env={"RH_FAIL": "check_mojibake.py"}).returncode == E_GATE
        assert fx.tmp_entries() == []

    def test_the_temporary_copy_is_removed_after_a_dry_run_whose_bump_fails(self, fx):
        fx.edit("README.md", "badge/registry-", "badge/reg-")
        fx.commit_all("break the badge")
        before = fx.snapshot()
        r = fx.run(NEW, "--dry-run")
        assert r.returncode == E_GATE, r.out
        assert fx.tmp_entries() == []
        assert fx.snapshot() == before

    def test_a_dry_run_still_enforces_the_preconditions(self, fx):
        fx.write("stray.txt", "x")
        assert fx.run(NEW, "--dry-run").returncode == E_PRE


# ---------------------------------------------------------------------------
# The whole pipeline against the fake remote
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_release_pushes_the_commit_and_the_annotated_tag_and_polls_before_tagging(self, fx):
        r = _release_ok(fx)
        subjects = fx.ogit("log", "--format=%s", "-3").split("\n")
        assert subjects[1] == f"Release v{NEW}", subjects
        assert fx.origin_tags() == [f"v{NEW}"]
        assert fx.ogit("cat-file", "-t", f"v{NEW}") == "tag"
        msg = fx.ogit("for-each-ref", f"refs/tags/v{NEW}", "--format=%(contents)")
        assert msg.startswith("### Fixed") and "A fix shipped in 1.0.1." in msg
        assert r.out.index("Polling CI") < r.out.index("Tagging release") < r.out.index("Writing verification doc")
        assert fx.snapshot()["status"] == "", "the operator's tree is clean afterwards"
        assert fx.tmp_entries() == [], "no temporary file survives a release"
