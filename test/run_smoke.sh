#!/usr/bin/env bash
#
#   run_smoke.sh (C) 2021-2026 Peter Sulyok
#   Run a single smfc smoke-test scenario. Stop it with CTRL-C.
#
#   Usage: ./test/run_smoke.sh <scenario>
#   Scenario ids are defined in test/smoke_runner.py (SCENARIOS); pass --list (or
#   no argument) to see the full set.
#
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$HERE/smoke_runner.py"

# Extract the scenario ids from smoke_runner.py's SCENARIOS dict (single source of truth).
# The grep pattern matches lines like:    "cpu_1":             Scenario(1, 1, 0, 0, "cpu_1.conf"),
SCENARIOS=$(grep -oE '^\s*"[a-z_0-9]+":\s*Scenario\(' "$RUNNER" | sed -E 's/.*"([a-z_0-9]+)".*/\1/')

usage() {
    echo "Usage: ./test/run_smoke.sh <scenario>"
    echo
    echo "Available scenarios:"
    echo "$SCENARIOS" | sed 's/^/  /'
    echo
    echo "Stop the running smoke test with CTRL-C."
}

SCENARIO="${1:-}"

if [[ -z "$SCENARIO" || "$SCENARIO" == "--list" || "$SCENARIO" == "-h" || "$SCENARIO" == "--help" ]]; then
    if [[ -z "$SCENARIO" ]]; then
        echo "Error: no scenario specified." >&2
        echo >&2
    fi
    usage >&2
    [[ -z "$SCENARIO" ]] && exit 2 || exit 0
fi

if ! echo "$SCENARIOS" | grep -qx "$SCENARIO"; then
    echo "Error: unknown scenario '$SCENARIO'." >&2
    echo >&2
    usage >&2
    exit 2
fi

exec uv run pytest --capture=tee-sys --scenario "$SCENARIO" "$RUNNER"
