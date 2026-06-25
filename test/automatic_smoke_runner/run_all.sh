#!/usr/bin/env bash
#
#   run_all.sh (C) 2026, Peter Sulyok
#
#   Convenience wrapper: invoke check_smoke.py from the project root.
#   Any extra args are forwarded (e.g. --only platform_x9, --duration 10, --quiet).
#
set -e
cd "$(dirname "$0")/../.."
exec uv run python test/automatic_smoke_runner/check_smoke.py "$@"
