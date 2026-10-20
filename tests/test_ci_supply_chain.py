"""
Tests for the CI supply-chain pins (v1.7.15, finding F7).

A workflow action referenced by a movable tag, or a pip install that resolves
to whatever is newest today, changes what CI does without a commit. These
tests read the workflow files as text and fail if a tag, an unpinned install,
or a missing Dependabot ecosystem comes back.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _lines():
    for path in WORKFLOWS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield path.name, number, line


class TestActionsArePinned:
    def test_every_remote_action_is_a_full_sha_with_a_version_comment(self):
        bad, seen = [], 0
        for name, number, line in _lines():
            match = re.search(r"\buses:\s*(\S+)(.*)$", line)
            if not match or "@" not in match.group(1):
                continue
            seen += 1
            ref, rest = match.groups()
            if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref) or not re.fullmatch(r"\s+# \S.*", rest):
                bad.append(f"{name}:{number}: {line.strip()}")
        assert seen >= 30, f"only {seen} `uses:` lines found; the test is not reading the workflows"
        assert not bad, "unpinned or uncommented actions:\n" + "\n".join(bad)

    def test_no_third_party_action_is_referenced_by_a_branch(self):
        for name, number, line in _lines():
            assert not re.search(r"uses:\s*\S+@(stable|main|master|latest)\b", line), f"{name}:{number}"


class TestInstallsArePinned:
    def test_pip_never_upgrades_itself(self):
        for name, number, line in _lines():
            assert "--upgrade pip" not in line, f"{name}:{number}"

    def test_every_pip_install_reads_the_requirements_file_or_the_local_wrapper(self):
        allowed = re.compile(r'pip install\s+(?:-r requirements-ci\.txt|-e "wrappers/python\[dev\]")')
        bad = [
            f"{name}:{number}: {line.strip()}"
            for name, number, line in _lines()
            if "pip install" in line and not allowed.search(line)
        ]
        assert not bad, "unpinned pip installs:\n" + "\n".join(bad)

    def test_npm_is_not_installing_anything(self):
        # v1.8.4 (H9a): `npm audit` needs a lockfile and package-lock.json is gitignored, so the audit job writes one with
        # `npm install --package-lock-only --ignore-scripts`, which installs nothing. Any other `npm install` still fails.
        for name, number, line in _lines():
            stripped = line.replace("npm install --package-lock-only --ignore-scripts", "")
            assert "npm install" not in stripped, f"{name}:{number}"


class TestAuditsRun:
    """v1.8.4 (H9a): every wrapper ecosystem is audited in the validate-wrappers job."""

    def test_the_four_audits_are_in_validate_yml(self):
        text = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        for needle in ("cargo audit", "npm audit --audit-level=high", "pip-audit -r requirements-ci.txt", "govulncheck ./..."):
            assert needle in text, needle


class TestRequirementsFile:
    def _requirements(self):
        text = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]

    def test_the_expected_packages_are_listed(self):
        names = sorted(re.split(r"[=<>~!]", req, maxsplit=1)[0] for req in self._requirements())
        assert names == ["duckdb", "jsonschema", "pandas", "pyarrow", "pytest"]

    def test_duckdb_is_pinned_exactly(self):
        assert any(re.fullmatch(r"duckdb==\d+(\.\d+)+", req) for req in self._requirements())

    def test_every_other_package_has_a_lower_and_an_upper_bound(self):
        for req in self._requirements():
            if req.startswith(("duckdb", "pyarrow")):
                continue
            assert ">=" in req and "<" in req, req

    def test_pyarrow_is_pinned_exactly(self):
        # pyarrow writes the five byte-comparable Parquet exports. A range
        # would let a different pyarrow produce different bytes for the same
        # logical content, and the --check modes would fail on the next
        # machine that made the other choice. ISO 3166 Item 5 is the case.
        reqs = list(self._requirements())
        pinned = [r for r in reqs if r.startswith("pyarrow==")]
        assert pinned, "pyarrow must be pinned exactly, not with a range"
        assert pinned[0] == "pyarrow==26.0.0", pinned[0]


class TestDependabot:
    def _config(self) -> str:
        return (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    def test_the_four_ecosystems_are_configured(self):
        ecosystems = re.findall(r"(?m)^\s*-\s*package-ecosystem:\s*(\S+)", self._config())
        assert sorted(ecosystems) == ["cargo", "github-actions", "gomod", "pip"]

    def test_each_ecosystem_points_at_a_directory_and_runs_weekly(self):
        config = self._config()
        assert config.count("interval: weekly") == 4
        for directory in ("directory: /\n", "directory: /wrappers/go\n", "directory: /wrappers/rust\n"):
            assert directory in config
