"""
Tests for tools/check_mojibake.py.

The checker had none. Corrupted text is built at run time from real characters, so this file holds no
corrupted sequence and does not trip the check it tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_mojibake as cm  # noqa: E402


def _corrupt(text: str, codec: str) -> bytes:
    """UTF-8 bytes read as a single-byte codec and saved again as UTF-8."""
    return text.encode("utf-8").decode(codec).encode("utf-8")


CORRUPTED = [
    ("em dash read as Windows-1252", _corrupt("\u2014", "cp1252")),
    ("euro sign read as Windows-1252", _corrupt("\u20ac", "cp1252")),
    ("em dash read as Latin-1", _corrupt("\u2014", "latin-1")),
    ("infinity sign read as Latin-1", _corrupt("\u221e", "latin-1")),
    ("accented letter read as Latin-1", _corrupt("\u00f4", "latin-1")),
    ("replacement character", "\ufffd".encode("utf-8")),
]

CLEAN = [
    "an em dash \u2014 and an en dash \u2013",
    "euro \u20ac and rupee \u20b9",
    "check mark \u2705 and box drawing \u251c\u2500\u2502",
    "accents \u00f4 \u00e7 \u00f1",
    "plain ascii",
]


def _scan(tmp_path: Path, data: bytes):
    p = tmp_path / "sample.txt"
    p.write_bytes(data)
    return cm.scan_file(p)


@pytest.mark.parametrize("label,data", CORRUPTED, ids=[c[0] for c in CORRUPTED])
def test_every_corruption_class_is_detected(tmp_path, label, data):
    assert _scan(tmp_path, b"before " + data + b" after"), label


@pytest.mark.parametrize("text", CLEAN)
def test_genuine_characters_are_not_flagged(tmp_path, text):
    assert _scan(tmp_path, text.encode("utf-8")) == []


def test_the_skip_marker_is_honoured(tmp_path):
    data = b"# mojibake-scan: skip\n" + _corrupt("\u2014", "cp1252")
    assert _scan(tmp_path, data) == []


def test_the_checker_does_not_trip_over_its_own_source():
    assert cm.scan_file(PROJECT_ROOT / "tools" / "check_mojibake.py") == []


def test_the_docstring_names_u201a_and_does_not_call_it_an_em_dash():
    doc = cm.__doc__
    assert "U+201A" in doc
    first_entry = doc.split("U+201A", 1)[1].split("\n\n", 1)[0]
    assert "It is not an em dash." in first_entry


@pytest.mark.parametrize("data,expected", [(_corrupt("\u2014", "cp1252"), 1), (b"clean\n", 0)])
def test_the_cli_exit_code_follows_the_scan(tmp_path, data, expected):
    p = tmp_path / "sample.txt"
    p.write_bytes(data)
    r = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "check_mojibake.py"), "--path", str(p)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == expected
