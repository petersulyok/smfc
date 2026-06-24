#!/usr/bin/env bash
#
#   run_smoke.sh (C) 2021-2026 Peter Sulyok
#   Run a single smfc smoke-test scenario. Stop it with CTRL-C.
#
#   Usage: ./test/run_smoke.sh <scenario>
#   Scenario ids are defined in test/smoke_runner.py (SCENARIOS); an unknown or
#   missing id makes pytest print the list of valid scenarios.
#
exec pytest --capture=tee-sys --scenario "${1:-}" ./test/smoke_runner.py
