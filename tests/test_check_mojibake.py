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
    doc = " ".join(cm.__doc__.split())
    assert "U+201A" in doc
    first_entry = doc.split("U+201A", 1)[1][:300]
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


# -- provenance of the docstring's signature notes: computed, not asserted ----------------------

def _hits(pattern: bytes, text: str, codec: str = "latin-1") -> bool:
    import re as _re
    return _re.search(pattern, _corrupt(text, codec)) is not None


@pytest.mark.parametrize("text", ["\u221e", "\u2211"])
def test_pattern_two_is_the_latin1_corruption_of_mathematical_operators(text):
    assert _hits(cm.MOJIBAKE_PATTERNS[1], text)


@pytest.mark.parametrize("text", ["\u2705", "\u2500", "\u251c"])
def test_pattern_two_is_not_the_check_mark_or_box_drawing(text):
    assert not _hits(cm.MOJIBAKE_PATTERNS[1], text)


@pytest.mark.parametrize("text", ["\u2014", "\u2013", "\u201c", "\u2026", "\u2022"])
def test_pattern_three_is_the_latin1_corruption_of_general_punctuation(text):
    assert _hits(cm.MOJIBAKE_PATTERNS[2], text)


@pytest.mark.parametrize("text", ["\u2500", "\u2502", "\u251c", "\u2514"])
def test_pattern_three_is_not_box_drawing(text):
    assert not _hits(cm.MOJIBAKE_PATTERNS[2], text)


@pytest.mark.parametrize("codec", ["latin-1", "cp1252"])
@pytest.mark.parametrize("lead", [0x94, 0x95])
def test_the_box_drawing_prefix_matches_no_pattern(lead, codec):
    import re as _re
    prefix = bytes([0xE2, lead]).decode(codec).encode("utf-8")
    assert not any(_re.search(p, prefix) for p in cm.MOJIBAKE_PATTERNS)


@pytest.mark.parametrize("text", ["\u2500", "\u2502", "\u251c", "\u2514"])
def test_box_drawing_read_as_latin1_matches_no_pattern(text):
    assert not any(_hits(p, text, "latin-1") for p in cm.MOJIBAKE_PATTERNS)


def test_a_box_drawing_character_is_caught_only_by_the_accident_of_its_last_byte():
    assert not any(_hits(p, "\u2500", "cp1252") for p in cm.MOJIBAKE_PATTERNS)
    assert _hits(cm.MOJIBAKE_PATTERNS[0], "\u2502", "cp1252")


def test_the_docstring_states_that_provenance():
    doc = " ".join(cm.__doc__.split())
    assert "Mathematical Operators" in doc and "General Punctuation" in doc
    assert "which no pattern covers" in doc


# ---------------------------------------------------------------------------
# Files with no scanned suffix (v1.9.0, F27)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(cm.SCAN_NAMES))
def test_text_files_without_a_scanned_suffix_are_scanned_by_name(tmp_path, name):
    (tmp_path / name).write_bytes(b"clean")
    assert tmp_path / name in cm.iter_files(tmp_path)
    (tmp_path / name).write_bytes(b"before " + _corrupt("\u2014", "cp1252"))
    assert cm.scan_file(tmp_path / name)


def test_binary_outputs_stay_skipped(tmp_path):
    (tmp_path / "x.parquet").write_bytes(b"\xef\xbf\xbd")
    assert cm.iter_files(tmp_path) == []


def test_every_real_text_file_without_a_scanned_suffix_is_covered():
    found = {p.name for p in cm.iter_files(PROJECT_ROOT)}
    for name in ("LICENSE", "VERSION", ".gitignore", ".gitattributes", "MANIFEST.in", "go.mod", "go.sum"):
        assert name in found, name
