#!/usr/bin/env python3
#
#   conftest.py (C) 2021-2025, Peter Sulyok
#   Setup test configuration for pytest.
#

def pytest_addoption(parser):
    """Additional command-line parameters for pytest."""
    parser.addoption("--cpu-num", action="store")
    parser.addoption("--hd-num", action="store")
    parser.addoption("--gpu-num", action="store")
    parser.addoption("--conf-file", action="store")

# End.
