#!/bin/bash
#
#   run_test_gpu_8_nvidia.sh (C) 2026 Peter Sulyok
#   This script will run smoke test with CPU 1, nvidia GPU 8 configuration.
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 0 --gpu-num 8 --nvme-num 0 --conf-file ./test/gpu_8_nvidia.conf ./test/smoke_runner.py