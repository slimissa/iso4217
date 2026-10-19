"""
A tool must name itself.

tools/check_registry_freshness.py printed "usage: check_snapshot_freshness.py" and listed that name in its
Usage block for as long as it existed (v1.8.3, F18). This reads every tool statically: each argparse `prog=`
and each `python3 tools/X.py` line in a docstring's Usage block must name the file it is in.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS = sorted((PROJECT_ROOT / "tools").glob("*.py"))


@pytest.mark.parametrize("path", TOOLS, ids=[p.name for p in TOOLS])
def test_a_tool_names_itself_in_prog_and_in_its_usage_block(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed = {path.name, path.stem}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "ArgumentParser":
            for kw in node.keywords:
                if kw.arg == "prog" and isinstance(kw.value, ast.Constant):
                    assert kw.value.value in allowed, f"{path.name}: prog={kw.value.value!r}"
    doc = ast.get_docstring(tree) or ""
    usage = doc.split("Usage:", 1)[1] if "Usage:" in doc else ""
    for name in re.findall(r"python3 tools/(\w+)\.py", usage):
        assert name == path.stem, f"{path.name}: its Usage block names {name}.py"
