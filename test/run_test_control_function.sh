#!/usr/bin/env bash
#
#   run_test_control_function.sh (C) 2026 Peter Sulyok
#   Smoke test driver for the new user-defined control_function= curve (CPU 2 + HD 2).
#
pytest --capture=tee-sys --cpu-num 2 --hd-num 2 --gpu-num 0 --nvme-num 0 --conf-file ./test/control_function.conf ./test/smoke_runner.py
