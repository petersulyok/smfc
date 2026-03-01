#!/usr/bin/env bash
#
#   run_test_const_level.sh (C) 2021-2026 Peter Sulyok
#   This script will run smoke test with CPU 1 and CONST level configuration.
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 0 --gpu-num 0 --nvme-num 0 --conf-file ./test/const_level.conf ./test/smoke_runner.py
