#!/bin/bash
#
#   run_test_hd_8.sh (C) 2021-2025 Peter Sulyok
#   #   This script will run smoke test with CPU 4, HDD 8 configuration.
#
pytest --capture=tee-sys --cpu-num 4 --hd-num 8 --gpu-num 0 --conf-file ./test/hd_2.conf ./test/smoke_runner.py