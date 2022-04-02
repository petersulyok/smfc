#!/bin/bash
#
#   run_unittest.sh (C) 2021-2022 Peter Sulyok
#   This script will execute all unit tests.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

# Run all unit tests.
python3 -m unittest discover $test_dir
