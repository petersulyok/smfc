#!/bin/bash
#
#   run_test_nvme.sh (C) 2021-2024 Peter Sulyok
#   This script will run smoke test: NVME disk configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/nvme.conf -l 4 -o 0
