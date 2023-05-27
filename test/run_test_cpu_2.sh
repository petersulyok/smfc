#!/bin/bash
#
#   run_test_cpu_2.sh (C) 2021-2023 Peter Sulyok
#   This script will run smoke test: CPU 2 configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/cpu_2.conf -l 4 -o 0
