#!/bin/bash
#
#   run_test_hd_2.sh (C) 2021-2025 Peter Sulyok
#   #   This script will run smoke test with CPU 1, HDD 2 configuration.
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 2 --conf-file ./test/hd_2.conf ./test/smoke_runner.py