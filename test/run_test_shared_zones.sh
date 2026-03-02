#!/usr/bin/env bash
#
#   run_test_shared_zones.sh (C) 2026 Peter Sulyok
#   This script will run smoke test with CPU 1, NVME 2 configuration sharing IPMI zone 0.
#
pytest --capture=tee-sys --cpu-num 1 --hd-num 0 --gpu-num 0 --nvme-num 2 --conf-file ./test/shared_zones.conf ./test/smoke_runner.py
