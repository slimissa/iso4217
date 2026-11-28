"""
`npm test` runs every JavaScript suite (v1.9.7).

CI's JavaScript leg runs `npm test`. Until v1.9.7 that script ran test.js and numeric_contract.test.js only, so the
lookup-contract and collection-order suites ran in CI only through pytest. Every suite file in wrappers/javascript (test.js and
*.test.js) must be in the script, and the script must pass.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JS = PROJECT_ROOT / "wrappers" / "javascript"
SCRIPT = json.loads((JS / "package.json").read_text(encoding="utf-8"))["scripts"]["test"]
SUITES = sorted(p.name for p in JS.glob("*.js") if p.name == "test.js" or p.name.endswith(".test.js"))


def test_there_are_four_suites():
    assert SUITES == ["collection_order.test.js", "lookup_contract.test.js", "numeric_contract.test.js", "test.js"]


def test_npm_test_runs_every_suite_and_nothing_else():
    run = re.findall(r"node (\S+\.js)", SCRIPT)
    assert sorted(run) == SUITES, SCRIPT
    assert set(re.split(r"\s*&&\s*", SCRIPT)) == {f"node {s}" for s in run}, "suites are chained with && only"


def test_npm_test_passes():
    npm = shutil.which("npm")
    assert npm, "npm is required (hygiene rule 7)"
    done = subprocess.run([npm, "test", "--silent"], cwd=JS, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-1000:]
    for marker in ("LOOKUP_CONTRACT javascript", "COLLECTION_ORDER javascript"):
        assert marker in done.stdout, marker
