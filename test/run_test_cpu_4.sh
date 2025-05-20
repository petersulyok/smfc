#!/usr/bin/env bash
#
#   run_test_cpu_4.sh (C) 2021-2025 Peter Sulyok
#   This script will run smoke test with CPU 4, HDD 4, GPU 4 configuration.
#
pytest --capture=tee-sys --cpu-num 4 --hd-num 4 --gpu-num 4 --conf-file ./test/cpu_4.conf ./test/smoke_runner.py
