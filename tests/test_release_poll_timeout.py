"""
The default CI poll timeout of scripts/release.sh (v1.9.7).

validate.yml took 8m16s on the v1.9.6 release commit (run 46086580455, as reported by the maintainer; not re-measured here),
longer than the 300 s default of the time: a green release would have timed out and stopped before tagging. The default is
1200 s; this test keeps it at 900 s or more, and keeps every place that states the default in step with the script.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE = PROJECT_ROOT / "scripts" / "release.sh"
TEXT = RELEASE.read_text(encoding="utf-8")


def _default() -> int:
    values = re.findall(r"^POLL_TIMEOUT=(\d+)$", TEXT, re.M)
    assert len(values) == 1, values
    return int(values[0])


def test_the_default_is_at_least_900_seconds():
    assert _default() >= 900, "validate.yml has taken over 8 minutes on a release commit (run 46086580455)"


def test_the_usage_text_states_the_default():
    done = subprocess.run(["bash", str(RELEASE), "--help"], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0
    assert f"default {_default()})" in " ".join(done.stdout.split())


def test_the_readme_states_the_default():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"(default {_default()})" in readme
    assert "(default 300)" not in readme
