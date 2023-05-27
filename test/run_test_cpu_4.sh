#!/bin/bash
#
#   run_test_cpu_4.sh (C) 2021-2023 Peter Sulyok
#   This script will run smoke test: CPU 4 configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/cpu_4.conf -l 4 -o 0
