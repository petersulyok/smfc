# Testing

This document describes how the `smfc` test suite is organised and how each
layer relates to the source code. It is intended for a new contributor who
needs to find their way around the tests, understand the design choices, and
know where new tests belong.

> If you only need *how to run the tests*, jump to the "Running" subsections
> under each chapter. This document covers both the *shape* of the suite and
> the commands to drive it.

## Goals

The test suite is built to satisfy four goals, in order:

1. **Catch regressions in *behaviour*, not in *implementation*.** Tests assert
   what the service does (logs produced, fan levels applied, exit codes
   returned), not how it does it. Internal refactors should not require
   rewriting tests.
2. **Run anywhere.** No real hardware, no real `ipmitool`, no real
   `smartctl`, no real `nvidia-smi` / `rocm-smi`, no real udev. Every external
   command is substituted by a generated bash script; every device tree by a
   temp directory; every system probe by a python mock. The suite runs on a
   stock laptop in roughly **20 seconds** for unit tests and **2 minutes** for
   the full smoke matrix.
3. **Two complementary layers.** A fast, deterministic **unit-test** layer
   that exercises each class in isolation, plus a slower **smoke-test** layer
   that boots the real `Service.run()` loop end-to-end against mocked devices.
   The two layers answer different questions: "is this class correct?" vs.
   "does the whole pipeline work?".
4. **Source ↔ test 1:1.** Every source module under `src/smfc/` has a matching
   `test_*.py` module under `test/`. Two well-justified exceptions: the four
   concrete platform implementations share a single matrix-driven
   `test_platforms.py`, and the abstract base class `platform.py` is exercised
   indirectly through its concrete subclasses.

## Prerequisites

The whole suite runs from a clean checkout with no system-level installs:

- Only `python3` and `bash` are required (tested on Linux and macOS). All
  external commands — `ipmitool`, `smartctl`, `nvidia-smi`, `rocm-smi` — are
  substituted by generated bash scripts.
- All development dependencies (defined in `pyproject.toml`) are installed
  with `uv`:

   ```commandline
   uv sync
   source .venv/bin/activate
   ```

  After that, the invocations in the rest of this document work as written.

## Unit tests

Unit tests verify each source class in isolation. They are fast, deterministic,
and the layer CI runs on every push.

### Design principles

- **Test full functionality with 100% code coverage.** Every branch in every
  source module is exercised by at least one unit test. Coverage is enforced
  in CI via `pytest --cov=src --cov=test` and uploaded to Codecov on every
  push (see [Running](#running) below for the local equivalent). A new
  feature is not complete until the new branches are covered.
- **Tests are data-driven, not duplicated.** Anywhere multiple cases differ
  only in input/output, they are expressed as `@pytest.mark.parametrize` rows
  with `pytest.param(..., id="...")`, not as separate test methods. Test ids
  appear in pytest's output and replace any need for `error_str` arguments
  threaded through asserts.
- **Test method names describe the behaviour under test**, not internal
  numbering schemes — e.g. `test_run_maps_temperature_to_level`,
  `test_init_sets_attributes_from_config`,
  `test_run_exits_on_bad_args_or_config`.
- **Shared infrastructure over copy-paste.** When a setup pattern recurs
  across multiple test modules — building a fake hwmon tree, constructing an
  `Ipmi` without going through the real `__init__`, asserting the
  `FanController` base contract — it lives in a dedicated helper module, not
  duplicated per file.
- **Pytest-managed temp directories.** Tests that need on-disk artefacts
  declare the `td: TestData` fixture in their signature. `TestData` is
  populated against pytest's `tmp_path` (one fresh directory per test);
  pytest creates the directory before the test, hands it over, and reclaims
  it on teardown. Failed tests keep their directory for inspection. Tests
  receive a ready-to-use `TestData` instance from the fixture.
- **Mock at the boundary, not in the middle.** External boundaries
  (`pyudev.Context`, `subprocess.run` for ipmitool/smartctl/SMI, file I/O on
  hwmon paths) are mocked. Internal interactions between smfc's own classes
  are exercised through real method calls. This keeps tests resilient to
  refactors that don't change the external contract.

### Running

The unit suite runs in roughly **20 seconds** on a stock laptop:

```commandline
pytest
```

Add coverage to see per-module statement and branch coverage:

```commandline
pytest --cov=src --cov=test
```

For a detailed HTML coverage report (which lines are / aren't covered, with
syntax highlighting) use:

```commandline
pytest --cov=src --cov=test --cov-report=html
```

The report lands in `htmlcov/index.html`. The same `--cov` invocation is what
CI uses (with `--cov-report=xml` for Codecov upload). Target is 100%.

### Layered structure

```
test/
├── conftest.py              ← pytest hooks + the `td` fixture
├── test_*.py                ← 16 unit-test modules, one per source class
├── test_config_builders.py  ← shared infra: config-object factories
├── test_fc_helpers.py       ← shared infra: FanController base-contract helpers
├── test_fixtures.py         ← shared infra: TestData (temp hwmon trees, fake commands)
└── test_mocks.py            ← shared infra: pyudev mock classes
```

The four shared-infra files form the foundation that every test module reuses:

- **`test_fixtures.py`** owns the `TestData` class — a temp-directory-backed
  builder that materializes fake `hwmon` trees and bash scripts emulating
  external commands (`ipmitool`, `smartctl`, `nvidia-smi`, `rocm-smi`). The
  `td` fixture in `conftest.py` wraps it with deterministic teardown.
- **`test_mocks.py`** holds the `pyudev` doubles — `MockDevice`,
  `MockContext`, `MockDevices`, `factory_mockdevice`, `MockedContextGood`,
  `MockedContextError`. Stateless, used by both unit tests and the smoke
  harness.
- **`test_config_builders.py`** holds six `create_*_config(...)` builders, one
  per smfc config dataclass. Each returns a fully-populated `*Config`
  instance with defaults sourced from `Config.DV_*`. Tests can write
  `create_cpu_config(steps=4)` without touching a real config file.
- **`test_fc_helpers.py`** holds builders specific to the `FanController`
  hierarchy: `FcHarness`, `assert_fc_base_contract()`, and per-controller
  `build_cpu_fc` / `build_hd_fc` / `build_nvme_fc` / `build_gpu_fc` helpers
  that absorb the `pyudev.Context.__new__` / `Ipmi.__new__` / `print` mock
  boilerplate.

### Source ↔ test mapping

Every smfc class has a matching test module. The "Primary classes" column
names the most prominent test class(es) within each module; many modules
contain several test classes grouped by feature.

| Source                           | Test module                  | Primary class(es) |
|----------------------------------|------------------------------|-------------------|
| `client.py`                      | `test_client.py`             | Arg parsing, colour detection, offline report formatter, snapshot-driven report, snapshot fetch over HTTP, controller construction, main online/offline path selection |
| `cmd.py`                         | `test_cmd.py`                | `__main__` entry point |
| `config.py`                      | `test_config.py`             | Static parsers, per-section parsing + validation (`Ipmi` / `Exporter` / `CPU` / `HD` / `NVMe` / `GPU` / `Const`), control-function precedence, duplicate-zone detection, edge cases, full multi-section integration |
| `constfc.py`                     | `test_constfc.py`            | Fixed-level controller init, `run`, deferred apply |
| `cpufc.py`                       | `test_cpufc.py`              | Hwmon discovery, ordinal `cpuN` device names |
| `exporter.py`                    | `test_exporter.py`           | Prometheus text rendering, HTTP server endpoints (`/snapshot`, `/metrics`, `/healthz`), 404/500 handling, idempotent stop |
| `fancontroller.py`               | `test_fancontroller.py`      | Base contract: construction, `get_hwmon_path`, `get_temp` modes, per-device temp caching, `set_fan_level`, deferred level application, `run()` mapping, smoothing algorithm, LUT construction (legacy vs. user-defined `control_function=`) |
| `generic.py`, `genericx9.py`, `genericx14.py`, `x10qbi.py` | `test_platforms.py` | Matrix-driven: same 11-method contract for all four platforms |
| `gpufc.py`                       | `test_gpufc.py`              | `exec_smi` (Nvidia/AMD), AMD sensor selection, temp parse errors |
| `hdfc.py`                        | `test_hdfc.py`               | `exec_smartctl` (sudo / rc / exceptions), standby-state formatting, `check_standby_state`, `go_standby_state`, standby-guard `run`, smartctl debug path |
| `ipmi.py`                        | `test_ipmi.py`               | Init (positive/negative, BMC timeout, client mode), `exec_ipmitool` (remote args, sudo, rc, exceptions), `get/set_fan_mode`, fan-mode name mapping, `get/set_fan_level`, `set_multiple_fan_levels`, exception surface |
| `log.py`                         | `test_log.py`                | Init (valid/invalid level+output combos), level/output/message-type mapping, message routing to stdout/stderr/syslog |
| `nvmefc.py`                      | `test_nvmefc.py`             | NVMe name validation, smartctl-based temps |
| `platform.py`                    | *(no dedicated module)*      | Exercised indirectly through `test_platforms.py` |
| `platform_factory.py`            | `test_platform_factory.py`   | `create_platform` dispatch per platform name + fallback |
| `service.py`                     | `test_service.py`            | Lifecycle (`exit_func`), dependency checks (CPU/HD/GPU/NVMe, AMD, invalid type), `run()` exit-code matrix, fan-mode drift enforcement, exporter start/stop wiring, **shared-zone arbitration** (`collect_desired_levels`, `apply_fan_levels` across single/shared/multi-zone, const winner/loser, caching, oscillation) |
| `snapshot.py`                    | `test_snapshot.py`           | Schema/version, fan-mode block, per-controller entries (cpu/hd/nvme/gpu/const), curve vs. legacy min/max, zones block, applied levels, per-device temperatures |

Behind that table sit two cross-cutting topics worth knowing about:

- **Fan-controller subclasses share a contract.** The four `FanController`
  subclasses (`CpuFc`, `HdFc`, `NvmeFc`, `GpuFc`) implement the same base
  contract but differ in how they discover devices. The shared base
  behaviours (construction, `set_fan_level`, deferred levels, the smoothing
  algorithm, LUT construction) are tested *once* in `test_fancontroller.py`.
  Each subclass test then asserts only its device-specific surface
  (`exec_smartctl`, `exec_smi`, standby handling), with `build_*` / `make_bare_*`
  helpers from `test_fc_helpers.py` absorbing the discovery-mock boilerplate.
- **Platforms share a matrix.** All four platforms (`Generic`, `GenericX9`,
  `GenericX14`, `X10QBi`) implement the same 11-method `Platform` interface
  but with very different raw IPMI byte sequences and level encodings. A
  single `test_platforms.py` module drives every platform through every
  method via a `PlatformSpec` per platform. Adding a new Supermicro platform
  is one `PLATFORMS` entry; the test count grows automatically.

### Where to add new unit tests

| You're adding... | It goes in... |
|------------------|---------------|
| A new method or branch in an existing class | The matching `test_<class>.py` |
| A new source class | A new `test_<class>.py` following the patterns described above |
| A new Supermicro platform | A new `PlatformSpec` row in `test_platforms.py` |
| A new `FanController` subclass | A new `test_<class>fc.py` that reuses `test_fc_helpers.py` for the base contract |
| A new shared mock or builder | Extend the appropriate infra module (`test_fixtures.py` / `test_mocks.py` / `test_config_builders.py` / `test_fc_helpers.py`); do **not** add it to a test module |

## Smoke tests

Where unit tests verify each class in isolation, smoke tests verify the
**whole service running end-to-end** against mocked devices. The smoke layer
catches integration bugs — wrong configuration wiring, missing IPMI commands
on a platform, broken fan-zone arbitration — that unit tests cannot see.

### Design principles

- **The smoke runner is the only place that boots the real service.** Unit
  tests construct individual classes and call individual methods; the smoke
  runner constructs a real `Service` and calls `Service.run()`, with only the
  device-discovery layer replaced by injected fakes. Everything else —
  configuration parsing, controller wiring, IPMI command formatting,
  fan-zone arbitration — runs unmodified.
- **One scenario per `.conf`.** Each scenario is a single configuration file
  under `test/scenarios/` plus a row in `SCENARIOS` describing its device
  counts. There is no scenario-specific Python code; everything is data.
- **Dynamic inputs, real loop.** A background thread drifts the fake hwmon
  temperatures every second so the service genuinely sees changing inputs
  and reacts to them across multiple polling cycles. The run continues until
  the operator sends Ctrl-C (the documented exit path) — or, for one
  scenario, until the service self-terminates on the configured trigger.
- **Two entry points.** The interactive `./test/run_smoke.sh <scenario>`
  dispatcher runs one scenario at a time until Ctrl-C, for hands-on
  debugging. The non-interactive
  `test/automatic_smoke_runner/check_smoke.py` driver runs every scenario in
  turn with a bounded time window and asserts the expected end-to-end
  signals appear in each log.

### Running

A single scenario runs from the project root via the wrapper script:

```commandline
./test/run_smoke.sh <scenario>
```

For example:

```commandline
./test/run_smoke.sh cpu_1
```

The smoke test runs until you press `CTRL+C`. The wrapper validates the
scenario name against the authoritative `SCENARIOS` table in
`test/smoke_runner.py`; with no argument or an unknown id it prints the full
list of valid scenarios.

Refer to the [scenario matrix](#scenario-matrix) below for what each
scenario contains.

To run **every** scenario in turn with automated pass/fail assertions per
scenario, use the non-interactive driver:

```commandline
./test/automatic_smoke_runner/run_all.sh           # all 20 scenarios (~2 min)
./test/automatic_smoke_runner/run_all.sh --only platform_x9
./test/automatic_smoke_runner/run_all.sh --quiet   # PASS/FAIL only, no log tails
```

See [`test/automatic_smoke_runner/README.md`](test/automatic_smoke_runner/README.md)
for the full flag list and what each scenario's checks look for.

### Layered structure

```
test/
├── smoke_runner.py          ← end-to-end smoke harness (one scenario per run)
├── run_smoke.sh             ← interactive smoke-test entry point (Ctrl-C to stop)
├── scenarios/               ← 20 .conf files, one per smoke scenario
└── automatic_smoke_runner/  ← non-interactive driver that exercises every scenario
```

`smoke_runner.py` and the unit-test shared infrastructure (`test_fixtures.py`,
`test_mocks.py`) work together: the smoke runner imports `TestData` from
`test_fixtures.py` and `MockedContextGood` from `test_mocks.py`, then layers
its own `_make_*fc_init` factories on top that bypass device discovery and
inject the fake hwmon paths into each `FanController` subclass.

### How the smoke runner works

A smoke run boots a real `Service` against fakes:

1. **`TestData` materializes the environment**: a temp directory containing
   a hwmon tree (`coretemp.N/hwmon/temp1_input` for CPU, `disks/N:0:0:0/...`
   for HD, `nvme/N/...` for NVMe), plus bash scripts that emulate
   `ipmitool` / `smartctl` / `nvidia-smi` / `rocm-smi` and return realistic
   output for every command the service issues.
2. **`smoke_runner.py` patches the device-discovery layer**:
   `pyudev.Context.__init__` is replaced with `MockedContextGood`, and each
   `*Fc.__init__` is replaced by a small factory that injects the fake hwmon
   paths and SMI command paths from `TestData`. Everything else — the
   `Service` constructor, the configuration parser, the IPMI command
   formatter, the fan-zone arbitration logic — runs unmodified.
3. **Config injection**: the chosen `.conf` file is loaded via `ConfigParser`,
   the generated command paths and device names are merged in, and the
   result is written to a temp file the service will read.
4. **Background drift thread**: a daemon thread updates the fake hwmon
   temperature files every second (random ±0–3 °C within the configured
   `min_temp`/`max_temp` range). GPU temperatures drift via state files
   inside the SMI emulator scripts.
5. **`Service.run()` is called** and runs until the operator sends Ctrl-C
   (the documented exit path) or — for one specific scenario,
   `no_enforce_fan_mode` — until the service self-terminates on a BMC drift
   it is configured not to correct.

The scenario itself is described by a single tuple:

```python
Scenario = namedtuple("Scenario", ["cpu", "hd", "gpu", "nvme", "conf"])
```

— device counts plus a `.conf` filename under `test/scenarios/`. The full set
lives in `test/smoke_runner.py::SCENARIOS`, which is the **single source of
truth** for both the interactive runner and the automatic driver.

### Scenario matrix

The scenario matrix is designed to exercise every meaningful combination of
controllers, platforms, and configuration modes:

- **Per-controller sanity**: `cpu_1` / `cpu_2` / `cpu_4`, `hd_1` / `hd_2` /
  `hd_4` / `hd_8`, `nvme_4`, `const_level`, `gpu_8_nvidia` / `gpu_8_amd` —
  scaling each controller type from 1 to 8 instances.
- **Cross-controller integration**: `cpu_4` (CPU + HD + GPU), `nvme_4` (CPU +
  NVMe), `hd_4` (HD + GPU). These prove the wiring between distinct
  controller types in a single service.
- **Shared-zone arbitration**: `shared_zones` (CPU + NVMe both in zone 0),
  `shared_zones_cpu_split` (numbered `[CPU:0]` + `[CPU:1]`, with `CPU:1` and
  `HD` sharing zone 1). The arbitration code path is one of the most complex
  in the service.
- **Numbered sections**: `shared_zones_cpu_split` (multi-CPU) and
  `hd_split_zones` (multi-HD pool across zones).
- **Curve modes**: `control_function` (user-defined T→L curves on both CPU
  and HD, with the legacy `min_temp`/`max_temp` keys omitted).
- **Platform overrides**: `platform_x9`, `platform_x14`, `platform_x10qbi`
  drive the non-default platform code paths end-to-end. Each platform emits
  a distinctive IPMI raw byte sequence that proves the platform layer is
  actually engaged.
- **Configuration toggles**: `no_enforce_fan_mode` (service exits on BMC
  drift instead of restoring FULL), `smoothing_window` (moving-average
  temperature filter with `smoothing>1`).

The full table — what each scenario contains:

| Scenario             | conf                       | CPU                         | HD                          | NVME      | GPU           | CONST      | Standby guard |
|----------------------|----------------------------|-----------------------------|-----------------------------|-----------|---------------|------------|---------------|
| `cpu_1`              | `cpu_1.conf`               | 1 x CPU                     | 1 x HD                      | disabled  | disabled      | enabled    | enabled       |
| `cpu_2`              | `cpu_2.conf`               | 2 x CPUs                    | disabled                    | disabled  | 1 GPU         | disabled   | disabled      |
| `cpu_4`              | `cpu_4.conf`               | 4 x CPUs                    | 4 x HDs                     | disabled  | 4 GPUs        | disabled   | enabled       |
| `hd_1`               | `hd_1.conf`                | disabled                    | 1 x HD                      | disabled  | disabled      | enabled    | enabled       |
| `hd_2`               | `hd_2.conf`                | 1 x CPU                     | 2 x HDs                     | disabled  | disabled      | disabled   | disabled      |
| `hd_4`               | `hd_4.conf`                | disabled                    | 4 x HDs                     | disabled  | 2 GPUs        | disabled   | disabled      |
| `hd_8`               | `hd_8.conf`                | 4 x CPUs                    | 8 x HDs                     | disabled  | disabled      | disabled   | enabled       |
| `const_level`        | `const_level.conf`         | 1 x CPU                     | disabled                    | disabled  | disabled      | enabled    | enabled       |
| `gpu_8_nvidia`       | `gpu_8_nvidia.conf`        | 1 x CPU                     | disabled                    | disabled  | 8 Nvidia GPUs | enabled    | disabled      |
| `gpu_8_amd`          | `gpu_8_amd.conf`           | 1 x CPU                     | disabled                    | disabled  | 8 AMD GPUs    | enabled    | disabled      |
| `nvme_4`             | `nvme_4.conf`              | 2 x CPU                     | disabled                    | 4 x NVME  | disabled      | enabled    | disabled      |
| `shared_zones`       | `shared_zones.conf`        | 1 x CPU                     | disabled                    | 2 x NVMEs | disabled      | disabled   | disabled      |
| `shared_zones_cpu_split` | `shared_zones_cpu_split.conf` | 2 x CPUs (`CPU:0`, `CPU:1`) | 2 x HDs                     | disabled  | disabled      | disabled   | disabled      |
| `control_function`   | `control_function.conf`    | 2 x CPUs                    | 2 x HDs                     | disabled  | disabled      | disabled   | disabled      |
| `platform_x9`        | `platform_x9.conf`         | 1 x CPU                     | 2 x HDs                     | disabled  | disabled      | enabled    | disabled      |
| `platform_x14`       | `platform_x14.conf`        | 1 x CPU                     | 2 x HDs                     | disabled  | disabled      | enabled    | disabled      |
| `platform_x10qbi`    | `platform_x10qbi.conf`     | 1 x CPU                     | 2 x HDs                     | disabled  | disabled      | enabled    | disabled      |
| `no_enforce_fan_mode`| `no_enforce_fan_mode.conf` | 1 x CPU                     | 2 x HDs                     | disabled  | disabled      | disabled   | disabled      |
| `hd_split_zones`     | `hd_split_zones.conf`      | disabled                    | 4 x HDs (`HD:0`, `HD:1`)    | disabled  | disabled      | disabled   | disabled      |
| `smoothing_window`   | `smoothing_window.conf`    | 2 x CPUs (`smoothing=5`)    | 2 x HDs (`smoothing=3`)     | disabled  | disabled      | disabled   | disabled      |

Notes:

- The `Standby guard` column reflects each `*.conf`; note that the smoke
  runner force-disables the standby guard at runtime (it would otherwise
  drive the fake `smartctl` command into STANDBY and stop temperature
  readings).
- `shared_zones` tests the shared IPMI zone arbitration where CPU and NVME
  fan controllers both use IPMI zone 0.
- `shared_zones_cpu_split` tests the multi-curve CPU feature combined with
  shared-zone arbitration: `CPU:0` controls zone 0, while `CPU:1` and `HD`
  share zone 1.
- `gpu_8_nvidia` and `gpu_8_amd` test the GPU fan controller with Nvidia and
  AMD GPUs respectively.
- `control_function` tests the `control_function=` parameter: the CPU
  section uses a 4-point curve (`30-35, 50-40, 60-90, 65-100`) and the HD
  section uses a 3-point curve (`32-35, 38-45, 46-100`), both with
  `min_temp`/`max_temp`/`min_level`/`max_level` omitted.
- `platform_x9`, `platform_x14`, `platform_x10qbi` force a specific platform
  via `platform_name=` (overriding the BMC auto-detect path). Each platform
  produces a distinctive raw IPMI byte sequence on `set_fan_level`: X9 uses
  `raw 0x30 0x91 0x5a 0x03 …` with the 0–255 scaled level encoding, X14 uses
  `raw 0x30 0x70 0x88 …` with direct-% encoding plus an OEM
  `raw 0x2c 0x04 0xcf 0xc2 …` manual-mode-enable sequence at startup, and
  X10QBi uses `raw 0x30 0x91 0x5c 0x03 …` preceded by an 11-line Nuvoton
  NCT7904D TMFR/FOMC init.
- `no_enforce_fan_mode` sets `enforce_fan_mode=0` in `[Ipmi]`. Unlike every
  other scenario, the service is **designed to exit immediately**
  (`SystemExit(11)`) the first time the BMC fan-mode reads as anything other
  than `FULL`, instead of restoring it. The smoke run typically terminates
  within 0–6 seconds; the log ends with `ERROR: BMC fan mode drifted from
  FULL to … ; enforce_fan_mode is disabled, smfc exiting.`
- `hd_split_zones` exercises numbered `[HD:0]` / `[HD:1]` sections — the 4
  generated `/dev/sd?` devices are split across two HD controllers each
  driving its own IPMI zone, modelling a backplane split (front pool vs.
  rear pool).
- `smoothing_window` exercises the temperature-smoothing moving-average
  window with `smoothing=5` (CPU) and `smoothing=3` (HD). Short polling
  intervals (1–2 s) let the window fill within the smoke run while the
  drift thread keeps feeding varying values, so the moving-average output
  changes across cycles.
- During smoke tests, temperature values change gradually over time to
  simulate realistic thermal behavior. A background thread updates hwmon
  temperature files (for CPU, HD, NVMe) every second, applying random
  changes of +/- 0-3 degrees within the configured min/max range. GPU
  temperatures (both Nvidia and AMD) also change gradually between
  invocations using a state file to track previous values.

### The automatic smoke driver

`test/automatic_smoke_runner/check_smoke.py` is a non-interactive driver
that runs every scenario in turn and scans the captured log for the expected
end-to-end signals: startup banner, controller init, fan-level apply,
temperature drift observable, clean Ctrl-C exit, plus per-scenario
assertions (e.g. the X9 raw byte sequence for `platform_x9`, the
autonomous-exit log line for `no_enforce_fan_mode`). It is used by
contributors to confirm a change hasn't regressed any scenario; CI does not
run it (CI runs the unit suite only). See
[`test/automatic_smoke_runner/README.md`](test/automatic_smoke_runner/README.md)
for full details on assertions and flags.

### Where to add new smoke tests

| You're adding... | It goes in... |
|------------------|---------------|
| A new end-to-end scenario | One `.conf` under `test/scenarios/` + one row in `test/smoke_runner.py::SCENARIOS` (and matching entry/checks in the automatic driver) |
| A new platform that needs end-to-end verification | A `platform_<name>.conf` scenario plus the corresponding row, alongside the unit-test `PlatformSpec` |
| New on-disk emulator behaviour (a new fake command, extra ipmitool branches) | `test_fixtures.py` (so unit tests and smoke share the same emulator) |
