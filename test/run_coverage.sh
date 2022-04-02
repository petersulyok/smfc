#!/bin/bash
#
#   run_coverage.sh (C) 2021-2022 Peter Sulyok
#   This script will execute all unit tests and will generate coverage information.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

# Run all unit test with coverage.
coverage run -m unittest discover $test_dir

# Generate HTML report
coverage html
