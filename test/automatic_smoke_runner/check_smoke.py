#!/usr/bin/env python3
#
#   check_smoke.py (C) 2026, Peter Sulyok
#
#   Automatic driver for the smfc smoke-test scenarios.
#
#   The interactive smoke harness (`test/smoke_runner.py` + `test/run_smoke.sh`) is
#   designed to run until the user presses CTRL-C, which makes it inconvenient for
#   automated regression checks. This script wraps it: for each scenario in
#   `test/smoke_runner.py::SCENARIOS`, it launches the harness in its own process
#   group, waits up to ``DURATION`` seconds (polling so it exits early when the
#   service self-terminates — e.g. ``no_enforce_fan_mode``'s ``SystemExit(11)`` on
#   the first BMC drift), then sends SIGINT to drive the documented Ctrl-C exit
#   path. The captured stdout/stderr is scanned for a set of expected signals
#   (startup banner, controller-init log lines, fan-level commands, temperature
#   drift, clean exit, plus per-scenario assertions for the platform-override and
#   numbered-section scenarios) and a pass/fail verdict per scenario is printed.
#
#   Run from the project root:
#       uv run python test/automatic_smoke_runner/check_smoke.py
#   Or run a single scenario:
#       uv run python test/automatic_smoke_runner/check_smoke.py --only platform_x9
#
import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections import namedtuple
from pathlib import Path

# Mirrors test/smoke_runner.py::SCENARIOS. Keep this in sync when scenarios are added/removed.
Scenario = namedtuple("Scenario", ["cpu", "hd", "gpu", "nvme", "conf"])
SCENARIOS = {
    "cpu_1":               Scenario(1, 1, 0, 0, "cpu_1.conf"),
    "cpu_2":               Scenario(2, 0, 1, 0, "cpu_2.conf"),
    "cpu_4":               Scenario(4, 4, 4, 0, "cpu_4.conf"),
    "hd_1":                Scenario(0, 1, 0, 0, "hd_1.conf"),
    "hd_2":                Scenario(1, 2, 0, 0, "hd_2.conf"),
    "hd_4":                Scenario(0, 4, 4, 0, "hd_4.conf"),
    "hd_8":                Scenario(4, 8, 0, 0, "hd_8.conf"),
    "nvme_4":              Scenario(2, 0, 0, 4, "nvme_4.conf"),
    "const_level":         Scenario(1, 0, 0, 0, "const_level.conf"),
    "gpu_8_nvidia":        Scenario(1, 0, 8, 0, "gpu_8_nvidia.conf"),
    "gpu_8_amd":           Scenario(1, 0, 8, 0, "gpu_8_amd.conf"),
    "shared_zones":        Scenario(1, 0, 0, 2, "shared_zones.conf"),
    "shared_zones_cpu_split": Scenario(2, 2, 0, 0, "shared_zones_cpu_split.conf"),
    "control_function":    Scenario(2, 2, 0, 0, "control_function.conf"),
    "platform_x9":         Scenario(1, 2, 0, 0, "platform_x9.conf"),
    "platform_x14":        Scenario(1, 2, 0, 0, "platform_x14.conf"),
    "platform_x10qbi":     Scenario(1, 2, 0, 0, "platform_x10qbi.conf"),
    "no_enforce_fan_mode": Scenario(1, 2, 0, 0, "no_enforce_fan_mode.conf"),
    "hd_split_zones":      Scenario(0, 4, 0, 0, "hd_split_zones.conf"),
    "smoothing_window":    Scenario(2, 2, 0, 0, "smoothing_window.conf"),
}

# Project root resolved relative to this file (test/automatic_smoke_runner/check_smoke.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DURATION = 6   # Seconds the service runs before we send SIGINT.
GRACE_PERIOD = 5       # Seconds to wait after SIGINT before SIGKILL.


def _has_real_traceback(log: str) -> bool:
    """Return True iff the log contains a non-benign Python traceback.

    A traceback whose last few non-empty lines mention ``KeyboardInterrupt`` is
    benign — pytest crashed while printing the trace on Ctrl-C, not the service.
    Only flag tracebacks that don't end that way.
    """
    if "Traceback (most recent" not in log:
        return False
    last_lines = [ln.strip() for ln in log.rstrip().splitlines() if ln.strip()][-5:]
    return not any("KeyboardInterrupt" in ln for ln in last_lines)


def run_scenario(name: str, duration: int) -> tuple:
    """Launch one scenario, run up to ``duration`` seconds, return (exit_code, log_text).

    The harness pytest invocation is started in its own process group so SIGINT
    reaches both pytest and any shell children. The wait loop polls every 100 ms
    so the function returns immediately when the service self-terminates (e.g.
    no_enforce_fan_mode's autonomous SystemExit(11)).
    """
    log_path = tempfile.NamedTemporaryFile(mode="w+", suffix=".log", delete=False).name
    with open(log_path, "wb") as f:
        proc = subprocess.Popen(
            ["uv", "run", "pytest", "--capture=tee-sys", "--scenario", name,
             "./test/smoke_runner.py"],
            cwd=PROJECT_ROOT, stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
        )

    # Run for up to `duration` seconds, but exit early if the service self-terminates.
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            pass
    # Give it up to GRACE_PERIOD seconds to clean up after SIGINT, then SIGKILL.
    for _ in range(GRACE_PERIOD * 10):
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait(timeout=2)

    with open(log_path, "r", encoding="UTF-8", errors="replace") as f:
        text = f.read()
    os.unlink(log_path)
    return proc.returncode, text


def check(name: str, scn: Scenario, duration: int) -> tuple:
    """Run a scenario and return (status_str, signal_dict, log_text)."""
    exit_code, log = run_scenario(name, duration)

    sig = {
        "exit":         exit_code,
        "version":      "Smfc version" in log,
        "ipmi_init":    "Ipmi module was initialized" in log,
        "set_level":    (len(re.findall(r"Setting fan level: zone=\d+ level=\d+%", log))
                         + len(re.findall(r"IPMI zone \[\d+\]: new level = \d+%", log))
                         + len(re.findall(r"Shared IPMI zone \[\d+\]: new level = \d+%", log))),
        "distinct":     len(set(re.findall(r"Setting fan level: zone=\d+ level=\d+%", log))
                            | set(re.findall(r"IPMI zone \[\d+\]: new level = \d+%", log))),
        "temp_read":    len(re.findall(r"new temperature|calculated level=", log)),
        "interrupt":    "KeyboardInterrupt" in log,
        "traceback":    _has_real_traceback(log),
        "cpu_init":     bool(re.search(r"\bCPU(?::\d+)? fan controller was initialized", log)),
        "hd_init":      bool(re.search(r"\bHD(?::\d+)? fan controller was initialized", log)),
        "nvme_init":    bool(re.search(r"\bNVME(?::\d+)? fan controller was initialized", log)),
        "gpu_init":     bool(re.search(r"\bGPU(?::\d+)? fan controller was initialized", log)),
        "const_init":   bool(re.search(r"\bCONST(?::\d+)? fan controller was initialized", log)),
        # Temperature drift evidence: distinct per-device temperature observations.
        "temps_seen":   len(set(re.findall(r"new temperature > [\d.]+C|per-device temps=\[[^\]]+\]", log))),
    }

    problems = []
    # ----- Generic signals every scenario must produce -----
    if not sig["version"]:                                    problems.append("no-version-banner")
    if not sig["ipmi_init"]:                                  problems.append("no-ipmi-init")
    if sig["set_level"] < 1:                                  problems.append("no-fan-level-set")
    if not sig["interrupt"]:                                  problems.append("no-clean-interrupt")
    if sig["traceback"]:                                      problems.append("traceback-during-run")
    if sig["temp_read"] < 1:                                  problems.append("no-temp-read")
    # pytest exits 2 on KeyboardInterrupt, 130 on SIGINT signal-exit. -2 / -SIGINT can show up on
    # some platforms when the process is signalled and Popen returns the negative signal number.
    if exit_code not in (2, 130, -2, -signal.SIGINT):         problems.append(f"exit={exit_code}")

    # ----- Per-scenario controller expectations driven from the SCENARIOS tuple -----
    if scn.cpu  > 0 and not sig["cpu_init"]:                  problems.append("cpu-controller-missing")
    if scn.hd   > 0 and not sig["hd_init"]:                   problems.append("hd-controller-missing")
    if scn.nvme > 0 and not sig["nvme_init"]:                 problems.append("nvme-controller-missing")
    if scn.gpu  > 0 and not sig["gpu_init"]:                  problems.append("gpu-controller-missing")
    if name == "const_level" and not sig["const_init"]:       problems.append("const-controller-missing")

    # Temperature drift evidence: hwmon-backed scenarios must show >1 distinct temp observation.
    if (scn.cpu + scn.hd + scn.nvme) > 0 and sig["temps_seen"] < 2:
        problems.append("no-temp-drift")

    # ----- Platform-override scenarios: distinctive raw byte sequences must appear -----
    # If the override didn't take effect, the log would show Generic-style 0x30 0x70 0x66
    # commands instead of the platform-specific bytes.
    if name == "platform_x9":
        if "platform_name = generic_x9" not in log:           problems.append("x9-not-active")
        if "0x30 0x91 0x5a" not in log:                       problems.append("x9-set-bytes-missing")
    elif name == "platform_x14":
        if "platform_name = generic_x14" not in log:          problems.append("x14-not-active")
        if "0x30 0x70 0x88" not in log:                       problems.append("x14-set-bytes-missing")
        # X14 start() must enable manual mode per zone via 0x2c 0x04 0xcf 0xc2 OEM cmd.
        if "0x2c 0x04 0xcf 0xc2" not in log:                  problems.append("x14-manual-mode-missing")
    elif name == "platform_x10qbi":
        if "platform_name = X10QBi" not in log:               problems.append("x10qbi-not-active")
        if "0x30 0x91 0x5c" not in log:                       problems.append("x10qbi-set-bytes-missing")

    # ----- enforce_fan_mode=0: service is DESIGNED to exit on first BMC drift -----
    # The IPMI emulator returns mode 2, 4, or "3 -> 1" with roughly equal weight, so drift is
    # expected within a few polls. Required signals:
    #   - "enforce_fan_mode = False" in startup banner
    #   - "enforce_fan_mode is disabled, smfc exiting" log line (SystemExit(11) path)
    #   - NO "restoring FULL" log line (that's the enforce=True branch)
    # The generic Ctrl-C / exit-code checks don't apply: smfc terminated on its own.
    if name == "no_enforce_fan_mode":
        if "enforce_fan_mode = False" not in log:
            problems.append("enforce-flag-still-on")
        if "restoring FULL" in log:
            problems.append("restored-FULL-despite-flag")
        if "enforce_fan_mode is disabled, smfc exiting" not in log:
            problems.append("no-autonomous-exit-on-drift")
        # Drop the generic checks that don't apply when smfc exits on its own with SystemExit(11)
        # (pytest then reports exit=1 and there is no KeyboardInterrupt in the log).
        problems = [p for p in problems if p not in ("no-clean-interrupt", "exit=1")]

    # ----- hd_split_zones: numbered [HD:0] and [HD:1] sections must both initialize -----
    if name == "hd_split_zones":
        if "HD:0 fan controller was initialized" not in log:  problems.append("hd0-not-initialized")
        if "HD:1 fan controller was initialized" not in log:  problems.append("hd1-not-initialized")

    # ----- smoothing_window: smoothing must be reported as > 1 for at least one controller -----
    if name == "smoothing_window":
        if not re.search(r"smoothing = [2-9]\d*", log):       problems.append("smoothing-not-enabled")

    status = "PASS" if not problems else "FAIL: " + " ".join(problems)
    return status, sig, log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run every smoke scenario, capture logs, assert key signals.")
    parser.add_argument("--only", metavar="SCENARIO", action="append", default=[],
                        help="Run only the named scenario(s). Repeat to add more. "
                             "Default: every entry in SCENARIOS.")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help=f"Seconds to run each scenario before sending SIGINT "
                             f"(default: {DEFAULT_DURATION}).")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress the per-scenario log tail on failure; print PASS/FAIL only.")
    args = parser.parse_args()

    if args.only:
        unknown = [s for s in args.only if s not in SCENARIOS]
        if unknown:
            sys.exit(f"Unknown scenario(s): {', '.join(unknown)}.\n"
                     f"Valid: {', '.join(SCENARIOS)}")
        scenarios = {s: SCENARIOS[s] for s in args.only}
    else:
        scenarios = SCENARIOS

    results = []
    for name, scn in scenarios.items():
        status, sig, log = check(name, scn, args.duration)
        line = (f"{name:<22} exit={sig['exit']:<4} "
                f"set_level={sig['set_level']:<3} "
                f"distinct={sig['distinct']:<2} "
                f"temp_read={sig['temp_read']:<3} "
                f"temps_seen={sig['temps_seen']:<3} "
                f"intr={'Y' if sig['interrupt'] else 'N'} "
                f"-> {status}")
        print(line, flush=True)
        if not status.startswith("PASS") and not args.quiet:
            tail = "\n".join(log.splitlines()[-15:])
            print("  --- last 15 lines of log: ---")
            for ln in tail.splitlines():
                print(f"    {ln}")
        results.append((name, status))

    print()
    print("========== SUMMARY ==========")
    passed = sum(1 for _, s in results if s.startswith("PASS"))
    print(f"Passed: {passed} / {len(results)}")
    print(f"Failed: {len(results) - passed}")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
