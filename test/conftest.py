#!/usr/bin/env python3
#
#   conftest.py (C) 2021-2026, Peter Sulyok
#   Setup test configuration for pytest.
#
import pytest
from .test_fixtures import TestData


def pytest_addoption(parser):
    """Additional command-line parameters for pytest (smoke test scenario selection)."""
    parser.addoption("--scenario", action="store", help="smoke test scenario id (see automatic_smoke_runner.SCENARIOS)")


@pytest.fixture(name="td")
def fixture_td(tmp_path) -> TestData:
    """Provide a TestData instance backed by pytest's per-test `tmp_path`.
    Pytest creates the directory before the test, keeps it on failure for inspection,
    and removes it during its own teardown (kept across the last 3 sessions for debugging)."""
    return TestData(tmp_path)


# End.
