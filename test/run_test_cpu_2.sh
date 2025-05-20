#!/usr/bin/env bash
#
#   run_test_cpu2.sh (C) 2021-2025 Peter Sulyok
#   This script will run smoke test with CPU 2, GPU 1 configuration.
#
pytest --capture=tee-sys --cpu-num 2 --hd-num 0 --gpu-num 1 --conf-file ./test/cpu_2.conf ./test/smoke_runner.py
