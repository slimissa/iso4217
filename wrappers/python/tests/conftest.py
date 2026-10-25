"""
Gives wrappers/python/tests the --fail-on-skip option defined in the repository's tests/conftest.py.

pytest looks for conftest.py files only above the paths it is given, and for
`pytest wrappers/python/tests/...` the rootdir is wrappers/python (it holds setup.py), so
tests/conftest.py is never loaded and `--fail-on-skip` is an unrecognised argument. This shim
loads that file by path and re-exports its hooks, so there is one implementation of the flag
(v1.9.1, P5-05; RELEASE_PATTERN.md, hygiene rule 7).

If both conftest files are loaded in one session, the second registration of the option is
ignored instead of raising.
"""

import importlib.util
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[3] / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("_iso4217_repo_conftest", _SOURCE)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

pytest_sessionfinish = _module.pytest_sessionfinish


def pytest_addoption(parser):
    try:
        _module.pytest_addoption(parser)
    except ValueError:
        pass
