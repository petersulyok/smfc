#!/usr/bin/env bash
#
#   run_test_nvme_4.sh (C) 2026 Peter Sulyok
#   This script will run smoke test with CPU 2, NVME 4 configuration.
#
pytest --capture=tee-sys --cpu-num 2 --hd-num 0 --gpu-num 0 --nvme-num 4 --conf-file ./test/nvme_4.conf ./test/smoke_runner.py