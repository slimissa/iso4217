"""pytest options for the suite. --fail-on-skip was added in v1.7.14 (RELEASE_PATTERN.md, hygiene rule 7)."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--fail-on-skip",
        action="store_true",
        default=False,
        help=(
            "exit non-zero if any test was skipped; a skipped test verifies "
            "nothing (CI and the release gate pass this; the allowed number is 0)"
        ),
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--fail-on-skip"):
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter is not None else []
    if not skipped:
        return

    reporter.write_sep("=", "fail-on-skip")
    reporter.write_line(
        f"FAIL-ON-SKIP: {len(skipped)} test(s) were skipped; a skipped test "
        "verified nothing. Install the missing dependency or remove the skip."
    )
    for report in skipped[:50]:
        longrepr = report.longrepr
        reason = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
        reporter.write_line(f"  {report.nodeid}: {reason}")
    if len(skipped) > 50:
        reporter.write_line(f"  ... and {len(skipped) - 50} more")

    # Keep any other non-zero status (failures, usage errors); only a clean
    # run is turned into a failure.
    if int(session.exitstatus) == 0:
        session.exitstatus = 1
