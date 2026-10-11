"""
Tests that the registry's date logic runs on UTC, not on the machine's clock.

CI runs in UTC; a maintainer does not. Dates written by one side and compared
by the other disagreed for a few hours every day (the v1.7.5 incident was
patched with a one-day tolerance, not by removing the cause). v1.7.14 makes
every date that is written into data, or compared against such a date, UTC.

The behavioural tests run each tool under two time zones, UTC+14 and UTC-12.
At any moment of the day at least one of them is on a different calendar day
from UTC, so a tool that still reads the local clock fails in at least one
parametrization at any hour the suite runs. The source guards (AST) catch a
call that behaviour cannot reach.

Left on the local clock on purpose: dates and timestamps used only in file
names, and the report timestamp in update_from_iso.py.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS = PROJECT_ROOT / "tools"
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"
ZONES = ["Pacific/Kiritimati", "Etc/GMT+12"]          # UTC+14 and UTC-12


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _stable(run):
    """Run `run()` and retry once if UTC midnight passed during the call."""
    before = _utc_today()
    result = run()
    return (result, before) if _utc_today() == before else (run(), _utc_today())


# ---------------------------------------------------------------------------
# Behaviour under a non-UTC clock
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="TZ semantics")
class TestBehaviourUnderLocalTimeZones:
    @pytest.mark.parametrize("zone", ZONES)
    def test_registry_freshness_measures_age_from_the_utc_date(self, tmp_path, zone):
        def run():
            (tmp_path / "iso4217.json").write_text(json.dumps({"meta": {"updated": _utc_today()}}))
            result = subprocess.run(
                [sys.executable, str(TOOLS / "check_registry_freshness.py"), "--root", str(tmp_path), "--json"],
                capture_output=True, text=True, env=dict(os.environ, TZ=zone), timeout=60,
            )
            return json.loads(result.stdout)
        report, _ = _stable(run)
        assert report["age_days"] == 0 and report["future"] is False

    @pytest.mark.parametrize("zone", ZONES)
    def test_snapshot_freshness_reports_the_utc_date(self, zone):
        def run():
            result = subprocess.run(
                [sys.executable, str(TOOLS / "check_snapshot_freshness.py"), "--json"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, env=dict(os.environ, TZ=zone), timeout=60,
            )
            return json.loads(result.stdout)["today"]
        today, utc = _stable(run)
        assert today == utc

    @pytest.mark.parametrize("zone", ZONES)
    def test_release_sh_dates_the_release_in_utc(self, zone):
        line = re.search(r'^TODAY="\$\(date[^"]*\)"', RELEASE_SH.read_text(encoding="utf-8"), re.M)
        assert line, "TODAY assignment not found in scripts/release.sh"
        def run():
            result = subprocess.run(
                [shutil.which("bash"), "-c", line.group(0) + '; printf %s "$TODAY"'],
                capture_output=True, text=True, env=dict(os.environ, TZ=zone), timeout=30,
            )
            return result.stdout
        today, utc = _stable(run)
        assert today == utc


# ---------------------------------------------------------------------------
# Source guards
# ---------------------------------------------------------------------------

def _calls(path: Path):
    """(line, 'date.today'|'datetime.now', enclosing function) for naive clock reads."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            f = node.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                    and f.value.id in ("date", "datetime") and f.attr in ("today", "now")):
                tz_given = f.attr == "now" and (node.args or node.keywords)
                if not tz_given:
                    hits.append((node.lineno, f"{f.value.id}.{f.attr}", self.stack[-1] if self.stack else "<module>"))
            self.generic_visit(node)

    Visitor().visit(tree)
    return hits


class TestSourceGuards:
    @pytest.mark.parametrize("name", ["check_registry_freshness.py", "check_snapshot_freshness.py", "validate.py"])
    def test_compare_sites_never_read_the_local_clock(self, name):
        assert _calls(TOOLS / name) == []

    def test_update_from_iso_reads_the_local_clock_only_for_file_names_and_report_timestamps(self):
        allowed = {
            ("date.today", "save_source_data"),      # file name
            ("datetime.now", "backup_registry"),     # file name
            ("datetime.now", "generate_diff"),       # report timestamp
            ("datetime.now", "save_report"),         # file name
        }
        found = {(kind, func) for _, kind, func in _calls(TOOLS / "update_from_iso.py")}
        assert found == allowed

    def test_every_utc_write_in_update_from_iso_says_why(self):
        lines = (TOOLS / "update_from_iso.py").read_text(encoding="utf-8").splitlines()
        writes = [l for l in lines if "datetime.now(timezone.utc)" in l]
        assert len(writes) == 5            # meta.updated x2, last_verified, withdrawn_date, source_date
        for line in writes:
            assert "# UTC, matching the freshness checks and release.sh" in line

    def test_release_sh_has_no_local_date_call(self):
        text = RELEASE_SH.read_text(encoding="utf-8")
        assert not re.search(r"\bdate\s+\+%", text)        # `date +%...` without -u
        assert re.search(r'^TODAY="\$\(date -u \+%Y-%m-%d\)"', text, re.M)
