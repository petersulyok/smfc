#!/usr/bin/env bash
#
#   run_test_hd_1.sh (C) 2021-2025 Peter Sulyok
#   #   This script will run smoke test with CPU 0, HDD 1 configuration.
#
pytest --capture=tee-sys --cpu-num 0 --hd-num 1 --conf-file ./test/hd_1.conf ./test/smoke_runner.py