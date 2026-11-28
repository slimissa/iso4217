"""
tools/six_facts.py (v1.9.7): List One XML -> the facts fixture read by tests/test_six_list_one_parity.py.

SIX's XML is not committed, so these tests build small List One and List Three files of the same shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "tools" / "six_facts.py"

ENTRY = "<CcyNtry><CtryNm>{c}</CtryNm><CcyNm>x</CcyNm><Ccy>{a}</Ccy><CcyNbr>{n}</CcyNbr><CcyMnrUnts>{m}</CcyMnrUnts></CcyNtry>"


def list_one(tmp_path: Path, entries: list[tuple], published: str = "2026-09-17", name: str = "one.xml") -> Path:
    body = "".join(ENTRY.format(c=c, a=a, n=n, m=m) for c, a, n, m in entries)
    body += "<CcyNtry><CtryNm>ANTARCTICA</CtryNm><CcyNm>No universal currency</CcyNm></CcyNtry>"
    p = tmp_path / name
    p.write_text(f'<?xml version="1.0" encoding="UTF-8"?><ISO_4217 Pblshd="{published}"><CcyTbl>{body}</CcyTbl></ISO_4217>',
                 encoding="utf-8")
    return p


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(TOOL), *map(str, args)], capture_output=True, text=True, timeout=60)


SAMPLE = [("FRANCE", "EUR", "978", "2"), ("SPAIN", "EUR", "978", "2"), ("IMF", "XDR", "960", "N.A."), ("JAPAN", "JPY", "392", "0")]


def test_it_writes_one_row_per_code_sorted_with_the_publication_date(tmp_path):
    out = tmp_path / "facts.json"
    r = run(list_one(tmp_path, SAMPLE), "--out", out)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["published"] == "2026-09-17" and data["code_count"] == 3
    assert data["codes"] == [{"code": "EUR", "numeric": "978", "minor_units": 2},
                             {"code": "JPY", "numeric": "392", "minor_units": 0},
                             {"code": "XDR", "numeric": "960", "minor_units": None}]


def test_check_passes_on_what_it_wrote_and_fails_on_any_difference(tmp_path):
    out = tmp_path / "facts.json"
    xml = list_one(tmp_path, SAMPLE)
    assert run(xml, "--out", out).returncode == 0
    assert run(xml, "--check", "--out", out).returncode == 0
    changed = list_one(tmp_path, SAMPLE[:-1] + [("JAPAN", "JPY", "392", "2")], name="changed.xml")
    r = run(changed, "--check", "--out", out)
    assert r.returncode == 1 and "is not what" in r.stdout
    assert run(xml, "--check", "--out", tmp_path / "absent.json").returncode == 1


def test_a_code_the_list_gives_two_ways_is_refused(tmp_path):
    r = run(list_one(tmp_path, [("A", "EUR", "978", "2"), ("B", "EUR", "978", "3")]), "--out", tmp_path / "f.json")
    assert r.returncode == 1 and "two ways" in r.stderr


@pytest.mark.parametrize("text", [
    '<ISO_4217 Pblshd="2026-01-01"><HstrcCcyTbl></HstrcCcyTbl></ISO_4217>',   # List Three
    '<ISO_4217><CcyTbl></CcyTbl></ISO_4217>',                                # no publication date
    "not xml",
])
def test_anything_but_list_one_is_a_usage_error(tmp_path, text):
    p = tmp_path / "x.xml"
    p.write_text(text, encoding="utf-8")
    r = run(p, "--out", tmp_path / "f.json")
    assert r.returncode == 2 and "FATAL" in r.stderr
    assert not (tmp_path / "f.json").exists()


def test_the_committed_fixture_has_the_shape_the_tool_writes():
    data = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "six_list_one_facts.json").read_text(encoding="utf-8"))
    assert list(data) == ["description", "source", "published", "code_count", "codes"]
