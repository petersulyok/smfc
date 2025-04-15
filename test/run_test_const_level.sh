#!/usr/bin/env bash
#
#   run_test_const_level.sh (C) 2021-2025 Peter Sulyok
#   This script will run smoke test with constant level configuration (CPU 1/60%, HD 4/55%).
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 4 --conf-file ./test/const_level.conf ./test/smoke_test.py
