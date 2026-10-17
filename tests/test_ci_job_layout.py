"""
Tests for the layout of .github/workflows/version-and-hygiene.yml (v1.7.15, F24).

The workflow was described as "four fast checks", had eight jobs, and ran two
more checks as steps of a job named for something else, so a README-drift
failure showed up under "Country codes resolve". These tests pin one job per
check, the existing job names (branch protection may refer to them), and a
header without a count that can go stale.
"""

from __future__ import annotations

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "version-and-hygiene.yml").read_text(
    encoding="utf-8"
)

# Names that existed before v1.7.15. A rename breaks a branch-protection rule
# that refers to one of them, so this list only ever grows.
EXISTING_NAMES = [
    "Version consistency",
    "Mojibake scan",
    "Wrapper copies in sync",
    "Country codes resolve",
    "Registry freshness",
    "Snapshot freshness",
    "Countries Parquet in sync",
    "Aggregated exports in sync",
]


def _jobs() -> dict[str, str]:
    body = TEXT.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z0-9-]+):\n", body)
    return dict(zip(parts[1::2], parts[2::2]))


def _tools(job_text: str) -> list[str]:
    return re.findall(r"run:\s*python3 (tools/\w+\.py)", job_text)


def _name(job_text: str) -> str:
    return re.search(r"(?m)^    name: (.+)$", job_text).group(1).strip()


class TestOneJobPerCheck:
    def test_there_are_jobs_to_check(self):
        assert len(_jobs()) >= 10

    def test_every_job_runs_exactly_one_tool(self):
        for job_id, text in _jobs().items():
            assert len(_tools(text)) == 1, f"{job_id} runs {_tools(text)}"

    def test_each_enrichment_field_has_its_own_job(self):
        for field in ("classification", "code_lifetime", "numeric_reused", "source_url"):
            job = _jobs()["check-enrichment-" + field.replace("_", "-")]
            assert f"tools/enrich_field.py --field {field} --check" in job
            assert f"Enrichment: {field} up to date" in _name(job)

    def test_the_two_formerly_hidden_checks_have_their_own_jobs(self):
        by_tool = {_tools(text)[0]: job_id for job_id, text in _jobs().items()}
        assert by_tool["tools/check_readme_drift.py"] != by_tool["tools/check_country_codes.py"]
        assert by_tool["tools/check_verification_doc.py"] != by_tool["tools/check_country_codes.py"]
        assert "check_readme_drift" not in _jobs()["check-country-codes"]
        assert "check_verification_doc" not in _jobs()["check-country-codes"]

    def test_the_country_codes_job_keeps_its_identity(self):
        job = _jobs()["check-country-codes"]
        assert _name(job) == "Country codes resolve"
        assert _tools(job) == ["tools/check_country_codes.py"]


class TestNames:
    def test_every_job_has_a_unique_name(self):
        names = [_name(text) for text in _jobs().values()]
        assert len(names) == len(set(names))

    def test_names_that_existed_before_still_exist(self):
        names = [_name(text) for text in _jobs().values()]
        for expected in EXISTING_NAMES:
            assert expected in names, f"job name {expected!r} is gone; branch protection may refer to it"


class TestTidy:
    def test_the_header_states_no_count(self):
        header = TEXT.split("\non:\n", 1)[0]
        assert not re.search(r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+fast\s+checks\b", header)

    def test_no_whitespace_only_lines_and_no_runs_of_blank_lines(self):
        assert not re.search(r"(?m)^[ \t]+$", TEXT)
        assert "\n\n\n" not in TEXT
