#!/bin/bash
#
#   run_test_const_level.sh (C) 2021-2023 Peter Sulyok
#   This script will run smoke test: constant level configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/const_level.conf -l 4 -o 0
