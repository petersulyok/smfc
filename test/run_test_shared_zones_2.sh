#!/usr/bin/env bash
#
#   run_test_shared_zones_2.sh (C) 2026 Peter Sulyok
#   This script will run smoke test with CPU:0, CPU:1 and HD configuration where
#   CPU:0 and CPU:1 share IPMI zone 0 and HD uses IPMI zone 1.
#
pytest --capture=tee-sys --cpu-num 2 --hd-num 2 --gpu-num 0 --nvme-num 0 --conf-file ./test/shared_zones_2.conf ./test/smoke_runner.py
