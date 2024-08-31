#!/bin/bash
#
#   run_test_scsi.sh (C) 2021-2024 Peter Sulyok
#   This script will run smoke test: SCSI disks configuration.
#

# Find directories for test execution.
source $(dirname $BASH_SOURCE)/find_dirs.sh
smfc -c ./test/scsi.conf -l 4 -o 0
