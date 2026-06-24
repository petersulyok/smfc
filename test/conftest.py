#!/usr/bin/env python3
#
#   conftest.py (C) 2021-2026, Peter Sulyok
#   Setup test configuration for pytest.
#
from typing import Iterator
import pytest
from .test_data import TestData


def pytest_addoption(parser):
    """Additional command-line parameters for pytest (smoke test scenario selection)."""
    parser.addoption("--scenario", action="store", help="smoke test scenario id (see smoke_runner.SCENARIOS)")


@pytest.fixture(name="td")
def fixture_td() -> Iterator[TestData]:
    """Provide a TestData instance; its temporary directory is removed on teardown."""
    data = TestData()
    yield data
    # Drop the reference so TestData.__del__ removes the temporary directory deterministically.
    del data


# End.
