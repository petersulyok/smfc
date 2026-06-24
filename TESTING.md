# Testing Overview

This document gives a structured inventory of the `smfc` test suite: what each test
module covers, the shared test infrastructure, and a set of concrete ideas for
making the suite more consistent and easier to extend.

> Companion docs: high-level test setup lives in [`DEVELOPMENT.md`](DEVELOPMENT.md)
> (how to run unit + smoke tests); architecture lives in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## At a glance

| Metric | Value |
|--------|-------|
| Unit test modules | 16 (`test/test_*.py`) |
| Shared infrastructure | `conftest.py`, `test_data.py`, `smoke_runner.py` |
| Smoke configs / drivers | 15 `*.conf` + 15 `run_test_*.sh` |

Every source module under `src/smfc/` has a matching `test_*.py` module, with two
exceptions: `test_platform_factory.py` covers the platform factory, and the four concrete
platform implementations share a single matrix-driven `test_platforms.py`
(see improvement idea 1, now implemented).

## Source ↔ test mapping

| Source module | Test module | LoC (test) | Primary test class(es) |
|---------------|-------------|-----------:|------------------------|
| `client.py` | `test_client.py` | 1311 | `TestParseArgs`, `TestUseColor`, `TestFormatReport`, `TestMain`, `TestSafeHelpers`, `TestFormatReportErrorPaths`, `TestConstructControllers`, `TestFormatReportFromSnapshot`, `TestTryFetchSnapshot`, `TestMainOnlinePath` |
| `cmd.py` | `test_cmd.py` | 30 | `TestMain` |
| `config.py` | `test_config.py` | 1412 | `TestConfigStaticMethods`, `TestControlFunctionSectionWiring`, `TestConfigFileLoading`, `TestIpmiConfigParsing`, `TestExporterConfigParsing`, `TestCpuConfigParsing`, `TestHdConfigParsing`, `TestNvmeConfigParsing`, `TestGpuConfigParsing`, `TestConstConfigParsing`, `TestFanControllerValidation`, `TestConfigConstants`, `TestEdgeCases`, `TestConfigFullIntegration`, `TestDuplicateZoneValidation` |
| `constfc.py` | `test_constfc.py` | 173 | `TestConstFc` |
| `cpufc.py` | `test_cpufc.py` | 261 | `TestCpuFc` |
| `exporter.py` | `test_exporter.py` | 365 | `TestPrometheusRenderer`, `TestExporterHTTP` |
| `fancontroller.py` | `test_fancontroller.py` | 866 | `TestFanController` |
| `generic.py`, `genericx9.py`, `genericx14.py`, `x10qbi.py` | `test_platforms.py` | 321 | `TestPlatforms` (matrix-driven) |
| `gpufc.py` | `test_gpufc.py` | 284 | `TestGpuFc` |
| `hdfc.py` | `test_hdfc.py` | 700 | `TestHdFc` |
| `ipmi.py` | `test_ipmi.py` | 700 | `TestIpmi` |
| `log.py` | `test_log.py` | 277 | `TestLog` |
| `nvmefc.py` | `test_nvmefc.py` | 262 | `TestNvmeFc` |
| `platform_factory.py` | `test_platform_factory.py` | 115 | `TestCreatePlatform` |
| `service.py` | `test_service.py` | 1861 | `TestService` |
| `snapshot.py` | `test_snapshot.py` | 419 | `TestBuildSnapshot` |
| `platform.py` (base ABC, `FanMode`, `validate_input_range`) | — | — | Covered indirectly through the four concrete platform test modules |

## Shared test infrastructure

### `conftest.py`
Registers extra pytest command-line options consumed only by the smoke runner:
`--cpu-num`, `--hd-num`, `--gpu-num`, `--nvme-num`, `--conf-file`.

### `test_data.py` (625 LoC)
The central helper module. It currently mixes three responsibilities:

1. **`TestData`** — a class that builds temporary hwmon trees and fake external
   commands on disk: `create_cpu_data`, `create_hd_data`, `create_nvme_data`,
   `create_config_file`, `create_command_file`, `create_ipmi_command`,
   `create_smart_command`, `create_nvidia_smi_command`, `create_rocm_smi_command`,
   `update_hwmon_temperatures`. Lifecycle is managed by `__init__`/`__del__`
   (temp dir created/removed).
2. **pyudev mocks** — `MockDevice`, `MockContext`, `MockDevices`,
   `factory_mockdevice`, `MockedContextError`, `MockedContextGood`.
3. **Config factories** — module-level builders returning ready-made config
   objects: `create_ipmi_config`, `create_cpu_config`, `create_hd_config`,
   `create_nvme_config`, `create_gpu_config`, `create_const_config`.

### `smoke_runner.py` + `run_test_*.sh`
End-to-end smoke harness: `TestSmoke.test_smoke` boots the real `Service.run()`
loop against mocked devices using a config file and device counts supplied on the
command line. The 15 `run_test_*.sh` wrappers each invoke pytest with a different
`(cpu, hd, gpu, nvme, conf)` matrix (see the table in `DEVELOPMENT.md`).

## Covered test cases by module

### Fan controllers (`FanController` and subclasses)

`test_fancontroller.py` (`TestFanController`) covers the **base contract**:
- Construction (`test_init_p1`, `test_init_n1`) and duplicate-zone collapsing.
- `get_hwmon_path`, `get_temp` (per-`temp_calc` modes), per-device temp caching,
  default device names.
- `set_fan_level` / deferred level application, single- and multi-zone.
- The main `run()` loop, polling skip, and the temperature-smoothing algorithm
  (spike, warmup, sustained heat, disabled, rapid oscillation, sensitivity,
  boundaries).
- LUT construction: legacy linear LUT vs. user-defined `control_function=` curve
  (`create_legacy_lut*`, `create_control_function*`, `build_lut` dispatch,
  plateau logging, run-via-LUT).

Each concrete subclass test repeats a common skeleton — `init_p1` (attribute
wiring), `init_p2`/`init_n*` (validation), `get_nth_temp_p/n` — and adds
device-specific cases:
- **`test_cpufc.py`** — hwmon discovery, ordinal `cpuN` device names.
- **`test_hdfc.py`** — `exec_smartctl` (sudo / rc / exceptions), standby-state
  string formatting, `check_standby_state`, `go_standby_state`, standby-guard
  `run`, smartctl debug path.
- **`test_nvmefc.py`** — NVMe name validation, smartctl-based temps.
- **`test_gpufc.py`** — `exec_smi` (Nvidia/AMD), AMD sensor selection, temp parse
  errors.
- **`test_constfc.py`** — fixed-level controller init, `run`, deferred apply.

### Platforms

`test_platforms.py` (`TestPlatforms`) covers the **same 11-method contract** for
all four platform classes from one matrix: `get_fan_mode`, `get_fan_level` (valid
+ invalid zone), `start`, `end`, `set_fan_mode` (valid + invalid), `set_fan_level`
(valid + invalid), `set_multiple_fan_levels` (valid + invalid). Each platform
contributes a `PlatformSpec` describing its raw ipmitool byte sequences, zone
range, level normalisation (X9/X10-QBi 0–100 → 0–255) and `start`/`end`
behaviour; `_cases()` expands the per-platform vectors into individual
parametrized cases (ids like `x10qbi-3`). Adding a new platform is a single
`PLATFORMS` entry. This replaced four ~270-line near-duplicate modules with no
loss of coverage (142 cases, 100% on all four platform sources).

`test_platform_factory.py` (`TestCreatePlatform`) covers `create_platform` dispatch for
each platform name plus fallback behaviour.

### IPMI (`test_ipmi.py`)
Init (positive/negative, BMC timeout, client mode), `exec_ipmitool` (remote args,
sudo, rc, exceptions), `get/set_fan_mode`, fan-mode name mapping,
`get/set_fan_level`, `set_multiple_fan_levels`, exception surface.

### Configuration (`test_config.py`)
The largest behavioural surface: static parsers (`parse_ipmi_zones`,
`parse_device_names`, `parse_gpu_ids`, `parse_control_function`), per-section
parsing + validation for IPMI / Exporter / CPU / HD / NVMe / GPU / Const,
control-function vs. legacy min/max precedence, duplicate-zone detection,
constants, a large `TestEdgeCases` boundary battery, and full multi-section
integration.

### Service (`test_service.py`)
Lifecycle (`exit_func`), dependency checks (CPU/HD/GPU/NVMe, AMD, invalid type),
the `run()` exit-code matrix (`run_026n`, `run_5n`, `run_7n`, `run_810n`,
`run_9n`, `run_100p`, old section names), fan-mode drift enforcement, exporter
start/stop wiring, and an extensive **shared-zone arbitration** battery
(`collect_desired_levels`, `apply_fan_levels` across single/shared/multi-zone,
const winner/loser, caching, oscillation, 3–5 controller overlaps).

### Client / snapshot / exporter (observability)
- **`test_client.py`** — arg parsing, colour detection, the offline report
  formatter, the snapshot-driven (online) report formatter, snapshot fetch over
  HTTP, controller construction, and `main` online/offline path selection.
- **`test_snapshot.py`** (`TestBuildSnapshot`) — snapshot schema/version, fan-mode
  block, per-controller entries (cpu/hd/nvme/gpu/const), curve vs. legacy
  min/max, zones block, applied levels, per-device temperatures.
- **`test_exporter.py`** — Prometheus text rendering (`TestPrometheusRenderer`)
  and the HTTP server endpoints `/snapshot`, `/metrics`, `/healthz`, 404/500
  handling, idempotent stop (`TestExporterHTTP`).

### Logging (`test_log.py`)
Init (valid/invalid level+output combos), level/output/message-type string
mapping, and message routing to stdout/stderr/syslog.

---

# Improvement ideas

The suite is genuinely thorough — coverage is broad and the parametrized
positive/negative style is consistent *within* most files. The friction is
**cross-file duplication** and a few **naming/lifecycle conventions** that make
the suite feel chaotic and raise the cost of adding the next controller or
platform. Ordered by payoff:

### 1. Collapse the four platform test modules into one matrix ✅ *(done)*
**Implemented** in `test/test_platforms.py`. `test_generic.py`,
`test_genericx9.py`, `test_genericx14.py`, and `test_x10qbi.py` (~1090 lines
testing the *same 11 methods*) were replaced by a single 321-line module driven
by a `PlatformSpec` per platform and `@pytest.mark.parametrize`. Per-platform
test vectors live in the spec and are expanded into individual cases by
`_cases()`; case ids carry the platform label (e.g. `x10qbi-3`) instead of the
old hand-maintained `error_str` strings. Adding the next Supermicro platform is
now a single `PLATFORMS` entry. Coverage is unchanged: 142 cases, 100% on all
four platform source modules.

### 2. Extract a shared `FanController` contract test  ✅ *(done)*
The five FC test modules repeat the same `init_p1 / init_p2 / init_n* /
get_nth_temp_p/n` skeleton plus the same pyudev/`get_hwmon_path`/`print` mock
boilerplate. Factor the common contract into a reusable base test class (or a
parametrized fixture providing the FC class + its config factory), so each
subclass module keeps **only** its device-specific surface (`exec_smartctl`,
`exec_smi`, standby handling). This also centralises the mock setup that is
currently copy-pasted into every `test_init_*`.

**Status:** shared layer landed in `test/test_fc_helpers.py` (`FcHarness`,
`assert_fc_base_contract`, per-controller `build_*`/`make_bare_*` helpers) plus a
`td` fixture in `conftest.py` (folds in idea 5). **All four controllers migrated:
NVMe, CPU, HD, GPU** — each at identical case count and 100% source coverage.
Each migration also applied ideas 3 (`id=` over `error_str`) and 4 (descriptive
names) and the detailed step/ASSERT docstring style. (`ConstFc` is out of scope —
it is not a `FanController` subclass.) Only the smoke-runner final step remains.

**Final step — refactor `smoke_runner.py` to match. ✅ Done.** `smoke_runner.py`
now carries an inline `SCENARIOS` table (single source of truth), module-level
`_make_*fc_init` factories (the old nested `mocked_*fc_init` are gone, along with
their `# duplicate-code` disable), and a single `--scenario <id>` option. The 14
`run_test_*.sh` wrappers were replaced by one `run_smoke.sh <scenario>`
dispatcher, and the `hd_8` scenario now correctly uses `hd_8.conf` (it had pointed
at `hd_2.conf`). `TestData`'s generators stay imported from `test_data.py` (the
idea-6 invariant holds). Verified end-to-end: CPU/HD/CONST, GPU, NVMe and
shared-zone scenarios all boot `Service.run()` and drive fan levels.

### 3. Drop the hand-maintained `error_str` parameters; use `pytest.param(id=...)`  🔶 *(partial)*
Almost every parametrized case carries a positional message string like
`"CpuFc.__init__() p1"` threaded through to every `assert ..., error_str`. This:
- duplicates information pytest already shows,
- drifts from the code (renamed methods leave stale strings),
- is inconsistently named (`error_str` vs `error`).

Replace with `pytest.param(..., id="cpu-zone0-calc-min")`. The test id then names
the case in the report, and the asserts lose the trailing `, error_str`.

**Status:** done in `test_platforms.py` and all controller modules (`test_nvmefc`,
`test_cpufc`, `test_hdfc`, `test_gpufc`, `test_constfc`). **Remaining (5 legacy
modules still carry `error_str`):** `test_config.py`, `test_fancontroller.py`,
`test_ipmi.py`, `test_log.py`, `test_service.py`.

### 4. Rename the opaque test cases  🔶 *(partial)*
`test_run_026n`, `test_run_5n`, `test_run_7n`, `test_run_810n`, `test_run_9n`,
`test_run_100p` (in `test_service.py`) encode an internal numbering scheme nobody
can read. Rename to intent (`test_run_exits_on_missing_config`,
`test_run_happy_path`, …). Same for the `p1/p2/n1/n2` suffixes elsewhere.

**Status:** the controller + platform + const modules are renamed to descriptive
behaviour names. **Remaining:** the `test_run_*n` cases in `test_service.py`, and
the `init_p1/n1` / `exec_*_p/n` suffixes in `test_ipmi.py`, `test_log.py`,
`test_fancontroller.py`.

### 5. Turn `TestData` lifecycle into fixtures  🔶 *(partial)*
`TestData` relies on `__del__` for temp-dir cleanup and is used as
`my_td = TestData(); ...; del my_td` throughout. `__del__`-based cleanup is
non-deterministic and easy to leak. Expose it as a pytest fixture with explicit
teardown, so cleanup is guaranteed and the boilerplate disappears from each test.
The repeated `Ipmi.__new__(Ipmi)` / `pyudev.Context.__new__(...)` constructions
are good fixture candidates too.

**Status:** the `td` fixture exists in `conftest.py` and is used by the migrated
controller modules (`test_cpufc`, `test_nvmefc`, `test_hdfc`); the `build_*`
helpers also absorb the `Ipmi.__new__`/`Context.__new__` boilerplate for those.
**Remaining:** adopt `td` in `test_fancontroller.py`, `test_ipmi.py`,
`test_service.py`, `test_config.py`, `test_log.py` (still `my_td = TestData()`).

### 6. Split `test_data.py` by responsibility  ⬜ *(not started)*
It currently bundles filesystem fixtures, pyudev mocks, and config factories in
one 625-line file. Split into `fixtures.py` (or move into `conftest.py`),
`mocks.py`, and `factories.py`. Promote the broadly-used config factories and the
`create_config` / `create_config_file` fixtures (today private to
`test_config.py`) into `conftest.py` so they are auto-injected and not
re-imported per file.

### 7. Split the three oversized modules  ⬜ *(not started)*
`test_service.py` (1861), `test_config.py` (1412), and `test_client.py` (1311)
each mix several concerns under one class. Splitting along existing seams would
improve navigability, e.g. `test_service.py` →
`test_service_lifecycle.py` / `test_service_arbitration.py` /
`test_service_exporter.py` (the shared-zone arbitration block alone is ~900
lines).

### 8. Generate the smoke matrix instead of 15 bash wrappers  ✅ *(done)*
The 14 `run_test_*.sh` scripts (which differed only in the
`(cpu, hd, gpu, nvme, conf)` tuple) were replaced by the inline `SCENARIOS` table
in `smoke_runner.py` plus one `run_smoke.sh <scenario>` dispatcher (see idea 2).
Adding a scenario is now one table row + one `.conf`; `DEVELOPMENT.md` links to
the table instead of restating it.

### 9. Close the small consistency gaps  🔶 *(partial)*
- ✅ `test_platform.py` was renamed to `test_platform_factory.py` (matches its
  source module `platform_factory.py`; disambiguates from `test_platforms.py`).
- ⬜ `platform.py` (the base ABC, `FanMode`, `validate_input_range`) still has no
  dedicated test module — it is only exercised indirectly through the four
  concrete platforms. A small `test_platform_base.py` would make that intentional.
- 🔶 Naming/suffix standardisation lands module-by-module with ideas 3 and 4.

---

## Progress summary & remaining phases

**Done ✅**
- Idea 1 — platform tests collapsed into `test_platforms.py` (matrix).
- Idea 2 — `test_fc_helpers.py` shared layer; NVMe/CPU/HD/GPU migrated; `ConstFc`
  modernised standalone; **smoke runner refactored** (inline `SCENARIOS`,
  `--scenario`, one `run_smoke.sh`). All at identical case counts and 100% source
  coverage; full suite green.
- Idea 8 — smoke matrix collapsed into the `SCENARIOS` table + single dispatcher.
- Idea 9 — `test_platform_factory.py` rename.
- The `td` fixture (part of idea 5) exists in `conftest.py`.

**Remaining phases (suggested order)**
1. **Finish ideas 3 + 4 + 5 on the 5 legacy modules** — `test_config.py`,
   `test_fancontroller.py`, `test_ipmi.py`, `test_log.py`, `test_service.py`:
   drop `error_str` for `pytest.param(id=...)`, rename opaque cases
   (`test_run_026n` → intent), and adopt the `td` fixture.
2. **Idea 6** — split `test_data.py` (filesystem fixtures / mocks / config
   factories); must preserve the smoke-runner import invariant.
3. **Idea 7** — split the oversized `test_service.py` / `test_config.py` /
   `test_client.py` along their existing seams.
4. **Idea 9 (remainder)** — add `test_platform_base.py` for `platform.py`.
