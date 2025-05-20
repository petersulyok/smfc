#!/bin/bash
#
#   run_test_hd_4.sh (C) 2021-2025 Peter Sulyok
#   This script will run smoke test with HDD 4, GPU 4 configuration.
#
pytest --capture=tee-sys --cpu-num 0 --hd-num 4 --gpu-num 4 --conf-file ./test/hd_4.conf ./test/smoke_runner.py