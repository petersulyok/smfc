# Automatic smoke runner

This folder holds the **non-interactive** driver for the smoke-test scenarios
defined in [`test/smoke_runner.py`](https://github.com/petersulyok/smfc/blob/main/test/smoke_runner.py).

The interactive harness (`./test/run_smoke.sh <scenario>`) is designed to run
until the user presses **CTRL-C**, which makes it awkward for regression
testing. The scripts here wrap it so every scenario can be exercised
unattended, each one for a bounded time window, with the captured log scanned
for the expected end-to-end signals.

## What it does

For every entry in `SCENARIOS` (mirrored from `test/smoke_runner.py`):

1. Launches the harness in its own process group:
   `uv run pytest --capture=tee-sys --scenario <name> ./test/smoke_runner.py`.
2. Polls every 100 ms — exits early if the service self-terminates (e.g.
   `no_enforce_fan_mode`'s `SystemExit(11)` on the first BMC drift) instead
   of sleeping the full duration.
3. After `DURATION` seconds (default **6 s**), sends **SIGINT** to drive the
   documented Ctrl-C exit path.
4. Falls back to **SIGKILL** after a 5-second grace period if the process is
   still alive.
5. Scans the captured stdout for the expected signals and prints
   `PASS` / `FAIL` per scenario plus a one-line summary.

## Quick start

From the project root:

```shell
# Run every scenario (~2 minutes wall time)
./test/automatic_smoke_runner/run_all.sh

# Run a single scenario
./test/automatic_smoke_runner/run_all.sh --only platform_x9

# Run several, with a longer per-scenario window
./test/automatic_smoke_runner/run_all.sh --only hd_8 --only shared_zones_cpu_split --duration 10

# Suppress the per-failure log tail
./test/automatic_smoke_runner/run_all.sh --quiet
```

Or invoke the Python driver directly:

```shell
uv run python test/automatic_smoke_runner/check_smoke.py [--only NAME ...] [--duration N] [--quiet]
```

## Output format

Per-scenario one-liner:

```
cpu_1                  exit=2    set_level=14  distinct=5  temp_read=6   temps_seen=4   intr=Y -> PASS
no_enforce_fan_mode    exit=1    set_level=4   distinct=2  temp_read=8   temps_seen=3   intr=N -> PASS
```

| Column | Meaning |
|--------|---------|
| `exit` | pytest exit code. `2` = clean Ctrl-C, `130` = signal-exit on SIGINT, `1` = pytest-failure (used by `no_enforce_fan_mode`, which raises `SystemExit(11)`, and by `error_tolerance_exhausted`, where the escalated read error propagates). |
| `set_level` | Number of fan-level apply lines observed (`Setting fan level: zone=N level=N%` plus the higher-level `IPMI zone [N]: new level = N%` summaries). |
| `distinct` | Number of distinct `(zone, level)` pairs — anything `> 1` confirms the service is computing levels dynamically rather than emitting the same line every iteration. |
| `temp_read` | Count of `new temperature` / `calculated level=` log lines, i.e. how many times the controllers consumed temperature input. |
| `temps_seen` | Number of distinct temperature observations. Anything `> 1` proves the drift thread's writes propagate through `TestData` and reach the controllers. |
| `intr=Y/N` | Whether `KeyboardInterrupt` was logged at exit. `N` is only expected for `no_enforce_fan_mode` and `error_tolerance_exhausted` (both terminate on their own). |
| `-> PASS / FAIL: <reasons>` | Final verdict. On `FAIL`, the last 15 lines of the scenario log are printed below the line (unless `--quiet`). |

## Signals checked

**Generic (every scenario):**
- Startup banner `Smfc version` is present.
- `Ipmi module was initialized` is present.
- At least one fan-level apply was logged.
- A `KeyboardInterrupt` ended the run.
- No non-benign Python traceback. (A traceback whose last lines mention
  `KeyboardInterrupt` is treated as benign — pytest itself sometimes crashes
  while formatting the trace on Ctrl-C; that's not a service failure.)
- Exit code is one of `2`, `130`, `-2`, `-SIGINT`.

**Driven from the `Scenario(cpu, hd, gpu, nvme, conf, fault)` tuple:**
- Every controller declared by the tuple appears with its
  `<NAME> fan controller was initialized` banner.
- `const_level` requires the `CONST` banner (it's the only `CONST`-only
  scenario).
- Hwmon-backed scenarios (CPU + HD + NVMe count > 0) must show more than one
  distinct temperature observation, proving the drift thread reaches the
  service.

**Scenario-specific:**

| Scenario | Extra assertions |
|----------|------------------|
| `platform_x9` | `platform_name = generic_x9` in startup; raw `0x30 0x91 0x5a` (X9 set_fan_level) appears in the log. |
| `platform_x14_openbmc` | `platform_name = generic_x14` in startup, resolving to `X14OpenBmcPlatform` (the Part 1.1 probe answers with a data byte); the zone 3 duty write `0x30 0x70 0x66 0x01 0x03 0x32` appears (CONST controller, 50%) and never with the read selector `0x00`; the OEM manual-mode latch `0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01` and its read-back `... 0x00 0x01` appear (note the 1-based zone byte); the zone count probe `... 0x02 <z>` runs once at startup and the same failsafe read repeats on every control check; raw `0x30 0x45 0x01` (set fan mode) never appears — writing it would clear manual mode on every zone; the release `0x30 0x70 0x66 0x02 0x00` appears at exit. |
| `platform_x14_aten` | The **same** `platform_name = generic_x14`, resolving to `X14AtenPlatform` instead because the fake BMC answers the Part 1.1 probe with `0xC1` — this pair is the assertion that the stack is detected, not guessed from the board name. The global bypass `0x30 0x70 0x66 0x02 0x01` is armed and released (`... 0x02 0x00`); the duty write uses `GenericPlatform`'s opcode `0x30 0x70 0x66 0x01 0x00 …` (ATEN is the X9–X13 firmware line); the duty read-back watchdog `0x30 0x70 0x66 0x00 0x3` appears; the fixed 50% CONST write `... 0x01 0x03 0x32` appears; raw `0x30 0x45 0x01` never appears; `restoring fan control` never appears (a correct read-back must not be mistaken for control loss). |
| `platform_x14_aten_percent` | The same config file and stack as `platform_x14_aten`, but the fake BMC uses the **other** ATEN duty path, which reports the written percentage back exactly instead of truncating it (Part 4.4). All the ATEN assertions above apply, except that the CONST controller correctly *skips* the zone 3 write — it reads `current=50% expected=50%` — which is asserted instead. This pair is what would fail if `accepted()` ever went back to a single computed expectation. |
| `platform_x10qbi` | `platform_name = X10QBi` in startup; raw `0x30 0x91 0x5c` appears in the log. |
| `no_enforce_fan_mode` | Startup logs `enforce_fan_mode = False`; the log contains `enforce_fan_mode is disabled, smfc exiting` (the `SystemExit(11)` path); the log does **not** contain `restoring fan control`. The generic `no-clean-interrupt` / `exit=1` checks are suppressed for this scenario. |
| `hd_split_zones` | Both `HD:0 fan controller was initialized` and `HD:1 fan controller was initialized` appear. |
| `smoothing_window` | At least one controller logs `smoothing = N` with `N ≥ 2`. |
| `error_tolerance` | Startup logs `error_tolerance = 3`; the log contains `temperature read failed, reusing` (the last known good value was used) and `temperature read recovered`; it does **not** contain `time(s) in a row` (the budget must not run out). |
| `error_tolerance_exhausted` | Startup logs `error_tolerance = 1`; the log contains `temperature read failed N time(s) in a row` and the propagated `FileNotFoundError: ERROR: Cannot read temperature from HWMON file`. The generic `no-clean-interrupt` / `traceback-during-run` / `exit=1` checks are suppressed: dying on the re-raised exception *is* the documented behavior. |

## Fault injection

Two scenarios do not just watch the happy path, they break a device on purpose. The
`fault` field of the `Scenario` tuple selects the injector thread in
[`test/smoke_runner.py`](https://github.com/petersulyok/smfc/blob/main/test/smoke_runner.py),
which renames one disk's fake hwmon file away so the controller's `open()` fails — the
deterministic, uid-independent stand-in for the `EIO` a real `drivetemp` read returns while a
disk is spinning up from STANDBY ([issue #87](https://github.com/petersulyok/smfc/issues/87)):

| Mode | Behavior | Scenario |
|------|----------|----------|
| `hd_flaky` | Hides the file for 2 s out of every 5 s, starting 1.5 s after launch. With `[HD] polling=1` and `error_tolerance=3` the streak stays inside the budget. | `error_tolerance` — smfc must survive, reusing the last known good temperature. |
| `hd_dead` | Hides the file once, permanently. With `error_tolerance=1` the second consecutive failure escalates. | `error_tolerance_exhausted` — smfc must stop with the original exception. |

A sample of what the tolerated run produces:

```
ERROR: HD: temperature read failed, reusing 41.0C (device=/dev/sda, 1/3, total=1): ERROR: Cannot read temperature from HWMON file (disk=/dev/sda)!
ERROR: HD: temperature read failed, reusing 41.0C (device=/dev/sda, 2/3, total=2): ERROR: Cannot read temperature from HWMON file (disk=/dev/sda)!
INFO:  HD: temperature read recovered after 2 failure(s) (device=/dev/sda, total=2)
```

## Keeping things in sync

The `SCENARIOS` dict in [`check_smoke.py`](https://github.com/petersulyok/smfc/blob/main/test/automatic_smoke_runner/check_smoke.py) is a copy of the one
in [`test/smoke_runner.py`](https://github.com/petersulyok/smfc/blob/main/test/smoke_runner.py). When you add or remove a
scenario, update both. The driver also has per-scenario assertions; if you add
a scenario that exercises a specific feature (a new platform, a new config
mode, etc.) consider extending the `check()` function with the matching
assertions so a regression in that feature surfaces as a smoke failure.

## Files

| File | Purpose |
|------|---------|
| [`check_smoke.py`](https://github.com/petersulyok/smfc/blob/main/test/automatic_smoke_runner/check_smoke.py) | The Python driver. Self-contained; no external deps beyond what the project already pulls in for `uv run pytest`. |
| [`run_all.sh`](https://github.com/petersulyok/smfc/blob/main/test/automatic_smoke_runner/run_all.sh) | Convenience wrapper that `cd`s to the project root and forwards extra args to `check_smoke.py`. |
| `README.md` | This file. |

## Limitations

- macOS/Linux only — uses `os.killpg()` with `start_new_session=True`. Windows
  would need `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` instead.
- Wall time is roughly `~6 s × len(SCENARIOS)` ≈ 2 minutes for the full sweep.
  The `--only` flag and `--duration` argument let you trade thoroughness for
  speed when iterating on a single scenario.
- The driver does **not** assert specific *values* (e.g. exact fan-level
  percentages or temperature readings) because those depend on the IPMI
  emulator's randomness. It asserts *that* the right log lines appeared,
  not their content.
