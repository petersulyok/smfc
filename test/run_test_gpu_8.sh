#!/bin/bash
#
#   run_test_gpu_8.sh (C) 2025 Peter Sulyok
#   This script will run smoke test with CPU 1, GPU 8 configuration.
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 0 --gpu-num 8 --conf-file ./test/gpu_8.conf ./test/smoke_runner.py