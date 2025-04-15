#!/bin/bash
#
#   run_test_hd_4.sh (C) 2021-2025 Peter Sulyok
#   #   This script will run smoke test with CPU 2, HDD 4 configuration.
#
pytest --capture=tee-sys --cpu-num 2 --hd-num 4 --conf-file ./test/hd_4.conf ./test/smoke_runner.py