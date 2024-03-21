#!/bin/bash
#
#   run_test_scsi.sh (C) 2021-2024 Peter Sulyok
#   This script will run smoke test: SCSI disks configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh

$src_dir/smfc.py -c $test_dir/scsi.conf -l 4 -o 0
