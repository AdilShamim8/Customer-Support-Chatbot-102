"""
Unit tests for the version single-source-of-truth (src/__version__.py).

The release workflow verifies tags against this value; scattered
hardcoded versions are exactly the bug this module exists to prevent.
"""

import pathlib
import re

import pytest


def test_version_is_semver():
    from src.__version__ import __version__

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), (
        f"version {__version__!r} must be plain semver for tag matching"
    )


def test_version_exposed_at_package_level():
    import src

    assert src.__version__
    assert src.__version__ == src.__version__


def test_build_info_contains_version():
    from src.__version__ import BUILD_INFO, __version__

    assert BUILD_INFO["version"] == __version__
    assert BUILD_INFO["build_date"]  # a stamp must exist


def test_build_date_is_current_release():
    from src.__version__ import __build_date__

    # Documents are stamped 2026-10-15 (this release cycle)
    assert __build_date__ == "2026-10-15"


def test_no_hardcoded_versions_in_api_layer():
    """Grep-level guard: version strings must not leak into modules.

    The health endpoint and app factory both consume src.__version__;
    a literal '1.0.0'/'1.1.0' in api code means someone bypassed it.
    """
    api_dir = pathlib.Path("src/api")
    offenders = []
    for py_file in api_dir.rglob("*.py"):
        text = py_file.read_text()
        for match in re.finditer(r"version\s*=\s*[\"']\d+\.\d+\.\d+[\"']", text):
            offenders.append(f"{py_file}: {match.group(0)}")
    assert not offenders, f"Hardcoded versions found: {offenders}"


def test_pyproject_version_matches_package():
    from src.__version__ import __version__

    pyproject = pathlib.Path("pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert m, "pyproject.toml must declare a version"
    assert m.group(1) == __version__


@pytest.mark.parametrize(
    "attr",
    ["__title__", "__version__", "__author__", "__license__", "__url__"],
)
def test_metadata_complete(attr):
    import importlib

    v = importlib.import_module("src.__version__")
    assert getattr(v, attr)
