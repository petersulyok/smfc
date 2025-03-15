#!/bin/bash
#
#   run_test_hd_2.sh (C) 2021-2025 Peter Sulyok
#   This script will run smoke test: HD 2 configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/hd_2.conf -l 4 -o 0
