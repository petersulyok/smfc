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
#   drift, clean exit, plus per-scenario assertions for the platform-override,
#   numbered-section and error_tolerance scenarios) and a pass/fail verdict per scenario is printed.
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
# The optional `fault` field selects a fault injector (see FAULT_INJECTORS); None = no fault.
# `bmc_stack` and `aten_duty_path` pick which 14th generation BMC firmware the fake ipmitool emulates;
# the defaults give the stack-agnostic behaviour every other scenario relies on. `npu` is the NPU card
# count. All four are appended after `fault`, so the existing positional entries stay unchanged.
Scenario = namedtuple("Scenario",
                      ["cpu", "hd", "gpu", "nvme", "conf", "fault", "bmc_stack", "aten_duty_path", "npu"],
                      defaults=(None, "", "pwm", 0))
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
    "npu_2":               Scenario(1, 0, 0, 0, "npu_2.conf", npu=2),
    "shared_zones":        Scenario(1, 0, 0, 2, "shared_zones.conf"),
    "shared_zones_cpu_split": Scenario(2, 2, 0, 0, "shared_zones_cpu_split.conf"),
    "control_function":    Scenario(2, 2, 0, 0, "control_function.conf"),
    "platform_x9":         Scenario(1, 2, 0, 0, "platform_x9.conf"),
    "platform_x14_openbmc": Scenario(1, 2, 0, 0, "platform_x14_openbmc.conf", None, "openbmc"),
    "platform_x14_aten":   Scenario(1, 2, 0, 0, "platform_x14_aten.conf", None, "aten"),
    "platform_x14_aten_percent": Scenario(1, 2, 0, 0, "platform_x14_aten.conf", None, "aten", "percent"),
    "platform_x10qbi":     Scenario(1, 2, 0, 0, "platform_x10qbi.conf"),
    "no_enforce_fan_mode": Scenario(1, 2, 0, 0, "no_enforce_fan_mode.conf"),
    "hd_split_zones":      Scenario(0, 4, 0, 0, "hd_split_zones.conf"),
    "smoothing_window":    Scenario(2, 2, 0, 0, "smoothing_window.conf"),
    "error_tolerance":     Scenario(0, 4, 0, 0, "error_tolerance.conf", "hd_flaky"),
    "error_tolerance_exhausted": Scenario(0, 4, 0, 0, "error_tolerance_exhausted.conf", "hd_dead"),
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


def _expected_exit_level(scn) -> int:
    """Return the `[Ipmi] exit_level=` value of the scenario's configuration file.

    The scenario files are the single source of truth: a scenario that does not set the parameter falls back to
    the smfc default (100%), so adding `exit_level=` to a scenario automatically changes what is asserted.
    """
    conf = (PROJECT_ROOT / "test" / "scenarios" / scn.conf).read_text(encoding="utf-8")
    m = re.search(r"^\s*exit_level\s*=\s*(-?\d+)", conf, re.MULTILINE)
    return int(m.group(1)) if m else 100


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
    # pylint: disable=too-many-branches,too-many-statements
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
        "npu_init":     bool(re.search(r"\bNPU(?::\d+)? fan controller was initialized", log)),
        "const_init":   bool(re.search(r"\bCONST(?::\d+)? fan controller was initialized", log)),
        # Temperature drift evidence: distinct per-device temperature observations.
        "temps_seen":   len(set(re.findall(r"new temperature > [\d.]+C|per-device temps=\[[^\]]+\]", log))),
        # [Ipmi] exit_level= applied by Service.exit_func() at interpreter exit. The level is the one
        # configured in the scenario file, so the expected value is looked up per scenario below.
        "exit_level":   (int(m.group(1))
                         if (m := re.search(r"smfc terminated: fans set to (\d+)% in zone\(s\)", log)) else None),
    }

    problems = []
    # ----- Generic signals every scenario must produce -----
    if not sig["version"]:                                    problems.append("no-version-banner")
    if not sig["ipmi_init"]:                                  problems.append("no-ipmi-init")
    if sig["set_level"] < 1:                                  problems.append("no-fan-level-set")
    if not sig["interrupt"]:                                  problems.append("no-clean-interrupt")
    if sig["traceback"]:                                      problems.append("traceback-during-run")
    if sig["temp_read"] < 1:                                  problems.append("no-temp-read")
    # Service.exit_func() must apply the configured [Ipmi] exit_level= to every controlled zone. This runs at
    # interpreter exit, after pytest tore down its capture, but the output still reaches the captured stdout of
    # the harness process. It is the only end-to-end coverage of the platform-specific end() implementations.
    if sig["exit_level"] != _expected_exit_level(scn):         problems.append(f"exit-level={sig['exit_level']}")
    # pytest exits 2 on KeyboardInterrupt, 130 on SIGINT signal-exit. -2 / -SIGINT can show up on
    # some platforms when the process is signalled and Popen returns the negative signal number.
    if exit_code not in (2, 130, -2, -signal.SIGINT):         problems.append(f"exit={exit_code}")

    # ----- Per-scenario controller expectations driven from the SCENARIOS tuple -----
    if scn.cpu  > 0 and not sig["cpu_init"]:                  problems.append("cpu-controller-missing")
    if scn.hd   > 0 and not sig["hd_init"]:                   problems.append("hd-controller-missing")
    if scn.nvme > 0 and not sig["nvme_init"]:                 problems.append("nvme-controller-missing")
    if scn.gpu  > 0 and not sig["gpu_init"]:                  problems.append("gpu-controller-missing")
    if scn.npu  > 0 and not sig["npu_init"]:                  problems.append("npu-controller-missing")
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
    elif name == "platform_x14_openbmc":
        if "platform_name = generic_x14" not in log:          problems.append("x14-not-active")
        # The probe of Part 1.1 must run before anything else, and must select the OpenBMC class.
        if "X14OpenBmcPlatform" not in log:                   problems.append("x14-openbmc-not-detected")
        # The CONST controller drives zone 3 at a fixed 50%, so the duty write is exact and 0-based.
        # Selector 0x01 writes the duty; 0x00 is the read, and a duty write sent with it changes nothing.
        if "0x30 0x70 0x66 0x01 0x03 0x32" not in log:        problems.append("x14-set-bytes-missing")
        if "0x30 0x70 0x66 0x00 0x03 0x32" in log:            problems.append("x14-set-uses-read-selector")
        # OpenBMC start() must latch manual mode per zone via the 0x2e 0x04 0xcf 0xc2 OEM cmd, with the
        # 1-based zone byte (zone 0 -> 0x01), and confirm it with the op 0x00 read-back.
        if "0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01" not in log:
            problems.append("x14-manual-mode-missing")
        if "0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01" not in log:   problems.append("x14-manual-readback-missing")
        # The base fan mode must never be written on X14: it would clear manual mode on every zone.
        if "0x30 0x45 0x01" in log:                           problems.append("x14-fan-mode-written")
        # The latch must be released at exit, whatever the exit level: a latch that is never released
        # leaves every zone frozen at its last duty with nothing regulating it.
        if "0x30 0x70 0x66 0x02 0x00" not in log:             problems.append("x14-latch-not-released")
    elif name.startswith("platform_x14_aten"):
        if "platform_name = generic_x14" not in log:          problems.append("aten-not-active")
        # The same configuration value must reach the *other* class here, chosen by the 0xC1 probe reply.
        if "X14AtenPlatform" not in log:                      problems.append("aten-not-detected")
        if "X14OpenBmcPlatform" in log:                       problems.append("aten-wrong-stack-selected")
        # The lever is the global bypass flag, not FULL fan mode: without it the BMC's automatic control
        # loop overwrites every duty within a second.
        if "0x30 0x70 0x66 0x02 0x01" not in log:             problems.append("aten-bypass-not-armed")
        # The duty write is GenericPlatform's, byte for byte (ATEN is the X9-X13 firmware line). Zone 0 is
        # driven by the CPU controller, whose level follows the drifting temperature, so it always writes.
        if "0x30 0x70 0x66 0x01 0x00 0x" not in log:          problems.append("aten-set-bytes-missing")
        # The fixed 50% CONST write on zone 3 is expected on the PWM read-back path only. On the percent
        # path the BMC reports the duty back exactly, so the controller sees "current=50% expected=50%" and
        # correctly skips the write - which is precisely the behavioural difference between the two duty
        # paths of Part 4.4, and the reason accepted() compares against a set rather than one value.
        if name == "platform_x14_aten" and "0x30 0x70 0x66 0x01 0x03 0x32" not in log:
            problems.append("aten-const-zone-write-missing")
        if name == "platform_x14_aten_percent" and "CONST: zone 3 current=50% expected=50%" not in log:
            problems.append("aten-percent-readback-not-exact")
        # The bypass cannot be read back, so the watchdog reads each zone's duty instead.
        if "0x30 0x70 0x66 0x00 0x3" not in log:              problems.append("aten-duty-readback-missing")
        # The base fan mode must never be written: it persists across a BMC restart while the bypass does
        # not, so a board left in Full Speed would come back at 100% with nothing to stop it.
        if "0x30 0x45 0x01" in log:                           problems.append("aten-fan-mode-written")
        # The bypass must be released at exit, or every zone on the board stays frozen at its last duty.
        if "0x30 0x70 0x66 0x02 0x00" not in log:             problems.append("aten-bypass-not-released")
        # The read-back path must not be mistaken for control loss on either kind of board.
        if "restoring fan control" in log:                    problems.append("aten-false-control-loss")
    elif name == "platform_x10qbi":
        if "platform_name = X10QBi" not in log:               problems.append("x10qbi-not-active")
        if "0x30 0x91 0x5c" not in log:                       problems.append("x10qbi-set-bytes-missing")

    # ----- enforce_fan_mode=0: service is DESIGNED to exit on first BMC drift -----
    # The IPMI emulator returns mode 2, 4, or "3 -> 1" with roughly equal weight, so drift is
    # expected within a few polls. Required signals:
    #   - "enforce_fan_mode = False" in startup banner
    #   - "enforce_fan_mode is disabled, smfc exiting" log line (SystemExit(11) path)
    #   - NO "restoring fan control" log line (that's the enforce=True branch)
    # The generic Ctrl-C / exit-code checks don't apply: smfc terminated on its own.
    if name == "no_enforce_fan_mode":
        if "enforce_fan_mode = False" not in log:
            problems.append("enforce-flag-still-on")
        if "restoring fan control" in log:
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

    # ----- error_tolerance: a transient read failure must NOT stop the service -----
    # The injector hides one disk's hwmon file for 2 s out of every 5 s while [HD] runs with
    # polling=1 and error_tolerance=3, so the streak stays inside the budget. Required signals:
    #   - the reuse log line (last known good temperature used instead of a fresh read)
    #   - the recovery log line once the file is back
    #   - NO budget-exhausted line, and the normal Ctrl-C exit (covered by the generic checks)
    if name == "error_tolerance":
        if "error_tolerance = 3" not in log:
            problems.append("error-tolerance-not-configured")
        if "temperature read failed, reusing" not in log:
            problems.append("no-tolerated-read-failure")
        if "temperature read recovered" not in log:
            problems.append("no-read-recovery")
        if "time(s) in a row" in log:
            problems.append("budget-exhausted-unexpectedly")

    # ----- error_tolerance_exhausted: smfc is DESIGNED to stop when the budget runs out -----
    # The injector hides one disk's hwmon file permanently and [HD] runs with error_tolerance=1,
    # so the second consecutive failure escalates. Required signals:
    #   - the budget-exhausted log line naming the device and the budget
    #   - the ORIGINAL exception object reaching the top unchanged (type + message), which is what
    #     the exit handler then reacts to
    # The service dies on that re-raised exception, so the generic Ctrl-C / exit-code / traceback
    # checks do not apply here — that traceback IS the documented behavior. The exit handler's own
    # exit_level step still runs at interpreter exit and is asserted by the generic exit-level check
    # above: this scenario is the error-exit coverage of Service.exit_func().
    if name == "error_tolerance_exhausted":
        if "error_tolerance = 1" not in log:
            problems.append("error-tolerance-not-configured")
        if not re.search(r"temperature read failed \d+ time\(s\) in a row", log):
            problems.append("no-budget-exhausted-line")
        if "FileNotFoundError: ERROR: Cannot read temperature from HWMON file" not in log:
            problems.append("original-exception-not-propagated")
        problems = [p for p in problems
                    if p not in ("no-clean-interrupt", "traceback-during-run", "exit=1")]

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
