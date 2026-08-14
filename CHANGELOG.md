# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [6.2.0] - 2026.08.14

### Added
- New `exit_level=` parameter in the `[Ipmi]` section (int, `[-1..100]`%, default=`100`). It is the fan level applied to all configured IPMI zones when the service terminates. The special value `-1` means "do not change the fan levels", so the zones stay at the last applied level. On X14 motherboards the level is applied and then manual fan control is released, so automatic BMC fan control is restored - see [README chapter 1.5](https://github.com/petersulyok/smfc/blob/main/README.md#15-service-termination) and [chapter 6](https://github.com/petersulyok/smfc/blob/main/README.md#6-ipmi-fan-control-and-sensor-thresholds) for the details of this platform difference. This parameter was added while fixing [issue #118](https://github.com/petersulyok/smfc/issues/118).

### Changed
- The section headings of this changelog use the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) categories consistently now (`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`). The earlier `New`, `New/Added`, `Fix` and `Change` headings were renamed accordingly in all releases, the entries themselves are unchanged.
- The fan mode is not changed at exit any more. `smfc` is already running in FULL mode at that point, so the redundant `set_fan_mode()` call only cost a `fan_mode_delay` long sleep on every service stop.

### Deprecated
- The `-ne` command-line option. It is still accepted and still means "no fan level change at exit" (it is equivalent to `exit_level=-1`), but it logs a deprecation warning and it will be removed in a future release.

### Fixed
- The documented safe shutdown did not happen on a normal service stop. Fan levels were restored through an `atexit` handler only, and CPython does not run `atexit` callbacks when the process is terminated by SIGTERM, which is the default kill signal of systemd. As a result nothing happened on `systemctl stop` or `systemctl restart`: the BMC was left in FULL mode at the last applied duty cycle with no component regulating it, which is exactly the state FULL mode is not safe in. `smfc` installs a SIGTERM handler now, so a normal service stop performs an ordinary interpreter shutdown and the configured `exit_level=` is applied. If you prefer the previous behavior, set `exit_level=-1`. See [issue #118](https://github.com/petersulyok/smfc/issues/118).
- `smfc-client` reported the wrong fan level for controllers that lose a [shared IPMI zone arbitration](https://github.com/petersulyok/smfc/blob/main/README.md#13-shared-ipmi-zone-arbitration). Both the `Fan controllers` table and the `--verbose` block showed the level applied to the zone instead of the level the controller itself requested, so a losing controller contradicted its own `Window:`/`Curve:` lines (e.g. an NVME controller at 39.9C displaying `Level: 74 %` while its curve maps that temperature to 35%). Each controller now reports its own request, and when the zone ended up at a different level that value is appended explicitly as `(zone N applied: Z %)`. Controllers on non-shared zones and the winner of a shared zone are unchanged.
- Documentation of `smfc-client --verbose`: `shared=yes` was described as meaning that *another* controller is currently driving the row's IPMI zone. It marks participation in zone arbitration and is reported for every controller on a shared zone, the current winner included.

## [6.1.0] - 2026.07.31

### Added
- New `error_tolerance=` parameter for the `[CPU]`, `[HD]`, `[NVME]` and `[GPU]` sections (int, default=3): the number of consecutive failed temperature reads tolerated per device. Behavior change: a transient temperature read error does not stop `smfc` any more. While a device is inside its budget its last known good temperature is reused and the failure is logged at ERROR level; only an exhausted budget stops the service with the original error, as before. Use `error_tolerance=0` for the old, intolerant behavior. This fixes the crash reported for disks waking up from STANDBY, where the kernel's `drivetemp` driver returns `EIO` for a second or two - see [issue #87](https://github.com/petersulyok/smfc/issues/87).
- `smfc-client --verbose` shows the per-device read error counts in a new, conditional `Errors` column: it appears only when at least one device of that controller has failed a temperature read since `smfc` was started, so the output of a healthy system is unchanged.
- The per-device read errors are also published: new `read_errors` (current consecutive streak) and `read_errors_total` (failures since startup) fields in the `/snapshot` device entries, and the matching `smfc_device_temp_read_errors` gauge and `smfc_device_temp_read_errors_total` counter in `/metrics`, so these events are visible in Grafana and not only in the log. Both counters appear in the log messages as well: `HD: temperature read failed, reusing 33.0C (device=/dev/disk/by-id/..., 2/3, total=9): ...`.

### Changed
- Two new smoke-test scenarios with fault injection: `error_tolerance` (one disk becomes unreadable for a short window, `smfc` must survive it by reusing the last known good temperature) and `error_tolerance_exhausted` (the disk stays unreadable, the budget runs out and `smfc` must stop). The smoke runner hides the disk's fake hwmon file to reproduce the failing read of issue #87.
- `smfc` man page lists the supported motherboards (X9, X10-X13/H10-H13, X10QBi, X14/H14) like the README and the DEB package description.
- The APT repository can be added with a single `deb822` file (`smfc.sources`, with embedded signing key) now, the one-line format is also documented - see [README chapter 9.1](https://github.com/petersulyok/smfc/blob/main/README.md#91-deb-package-installation).

### Fixed
- `uninstall.sh` removed `/etc/default/smfc` even with `--keep-config`; both configuration files are preserved now, like in `install.sh`.

## [6.0.1] - 2026.07.26

### Added
- Arch Linux users can install `smfc` from the [AUR package](https://aur.archlinux.org/packages/smfc) (community-maintained by `urirocky`, based on v6.0.0) — see new [README chapter 9.3](https://github.com/petersulyok/smfc/blob/main/README.md#93-arch-linux-aur-package-installation).
- New [`Docker.md` chapter](https://github.com/petersulyok/smfc/blob/main/docker/Docker.md#smfc-client-in-docker) about `smfc-client` in the docker images: how to run it in the running container (`docker exec`), live snapshot vs standalone mode, and how to start it in a separate container.

### Changed
- `smfc-client --help` and its documentation (README, man page) rewritten in plain, user-facing language.
- `auto` platform detection now also matches BMC product names starting with `H14` (not just `X14`), selecting `generic_x14`.
- Docker images are now built on pinned base images (`alpine:3.24.1`, `debian:13.6-slim`, `ubuntu:noble-20260610`) instead of floating tags, so a rebuild always produces the same base. The base image and component versions of all three images are listed in [`Docker.md`](https://github.com/petersulyok/smfc/blob/main/docker/Docker.md).
- The `--break-system-packages` pip parameter was removed from the AMD dockerfile, it was not needed (`--prefix` is enough), so all three dockerfiles use the same pip command now.
- The obsolete `version: "2"` attribute was removed from all docker compose files and from the compose samples in [`Docker.md`](https://github.com/petersulyok/smfc/blob/main/docker/Docker.md); it has been ignored by Docker Compose V2 and only produced a warning on every start.

### Fixed
- X9 fan duty readback scaling (`generic_x9` platform): `get_fan_level()` returned the raw 0-255 BMC byte as if it were a percentage, so `smfc-client` displayed values like 242% for a real 95% duty cycle and CONST controllers kept re-applying an already-correct level. The readback is now converted back to the 0-100 percent platform contract - based on [PR #117](https://github.com/petersulyok/smfc/pull/117) by @krecik, validated on a Supermicro X9DR3-LN4F+ (BMC 3.48).
- The same fan duty readback scaling issue was found and fixed on the `X10QBi` platform: `set_fan_level()` writes the duty cycle on the NCT7904D 0-255 scale, but `get_fan_level()` returned the raw byte as a percentage (100% duty was reported as 255%). This fix is based on the datasheet and on the symmetry with the write path, it is **not validated on real hardware yet** - X10QBi owners, please share your experience in [discussion #110](https://github.com/petersulyok/smfc/discussions/110).
- Docker image sizes: `pip` was installed and removed in different layers, so it stayed in the images, and the AMD image used the `rocm/dev-ubuntu` base image with the complete ROCm SDK. The AMD image is built on the standard Ubuntu base image now, with only the `rocm-smi-lib` package installed. New sizes: standard 70.5 MB → 58.6 MB, `-nvidia` 583 MB → 230 MB, `-amd` 3.99 GB → 210 MB.
- AMD Docker image: `rocm-smi` was not available at `/usr/bin/rocm-smi`, the default value of the `[GPU] rocm_smi_path=` parameter, so the GPU fan controller did not start with the default configuration. It is linked to `/usr/bin` now.
- NVIDIA Docker image (`-nvidia`) failed to start under the NVIDIA Container Toolkit with `mkdirat run/nvidia-ctk-hook: read-only file system`, because the wide `/run:/run:ro` bind mount shadowed the container's writable `/run` and blocked the toolkit's `createContainer` hook. All Docker examples (compose files, `docker run` scripts, `Docker.md`) now bind-mount only `/run/udev:/run/udev:ro` — all `smfc` needs there is the udev database for `pyudev` — which leaves `/run` writable. See [issue #107](https://github.com/petersulyok/smfc/issues/107).


## [6.0.0] - 2026.07.09

### Added
- Signed [APT repository](https://petersulyok.github.io/smfc-deb/) for DEB packages, hosted at [`petersulyok/smfc-deb`](https://github.com/petersulyok/smfc-deb). Users on Debian/Ubuntu/Proxmox/Mint/Raspberry Pi OS can now install `smfc` directly with `apt install smfc` after adding the repository — see [README chapter 9.1](https://github.com/petersulyok/smfc/blob/main/README.md#91-deb-package-installation).
- Signed [DNF repository](https://petersulyok.github.io/smfc-rpm/) for RPM packages, hosted at [`petersulyok/smfc-rpm`](https://github.com/petersulyok/smfc-rpm). Users on Fedora/RHEL/Rocky/AlmaLinux/CentOS Stream/openSUSE can now install `smfc` directly with `dnf install smfc` after adding the repository — see [README chapter 9.2](https://github.com/petersulyok/smfc/blob/main/README.md#92-rpm-package-installation).
- New companion `smfc-client` tool showing a live read-only snapshot of controllers, fan levels, IPMI zones, and standby state — works either against a running `smfc` service or fully standalone. See [README chapter 14](https://github.com/petersulyok/smfc/blob/main/README.md#14-smfc-client).
- New platform support for Supermicro X14 motherboards (`generic_x14`), auto-detected from the BMC product name — **experimental**, your feedback is welcome at [discussion #106](https://github.com/petersulyok/smfc/discussions/106).
- New Grafana integration: sample dashboard and step-by-step guide for visualizing live and historical fan/temperature data — see [`grafana/GRAFANA.md`](https://github.com/petersulyok/smfc/blob/main/grafana/GRAFANA.md).
- New documentation: [`ARCHITECTURE.md`](https://github.com/petersulyok/smfc/blob/main/ARCHITECTURE.md) (internal design for contributors), [`TESTING.md`](https://github.com/petersulyok/smfc/blob/main/TESTING.md) (test suite guide), [`grafana/GRAFANA.md`](https://github.com/petersulyok/smfc/blob/main/grafana/GRAFANA.md) (Grafana integration guide).
- Advanced multi-segment user-defined control function: `control_function=` now accepts a sequence of `temp-level` points defining an arbitrary piecewise-linear curve, instead of a single linear segment between `min_temp/max_temp` and `min_level/max_level` — see [README chapter 2.2](https://github.com/petersulyok/smfc/blob/main/README.md#22-advanced-multi-segment-user-defined-function).
- New fan mode enforcement: `smfc` now detects and restores when the BMC drifts out of FULL mode, see new `[Ipmi] enforce_fan_mode=` parameter. More details in [README chapter 6](https://github.com/petersulyok/smfc/blob/main/README.md#6-ipmi-fan-control-and-sensor-thresholds).
- Multiple fan curves per controller type: numbered sections (e.g. `[CPU]` + `[CPU:1]`) let a single controller family drive independent fan curves across different IPMI zones.
- Install script now auto-prefills `nvme_names=` with detected NVMe devices (matching the existing `hd_names=` prefill), skipping duplicate `nvme-nvme.*` (NGUID) links.
- Startup log now shows the active control function as a plateau list, making it easy to confirm the configured temperature-to-fan-level curve at a glance.

### Changed
- `platform_name=` values reworked: `genericx9` renamed to `generic_x9` (old value still accepted for compatibility), unrecognized values now rejected at config-parse time, and `auto` detection now matches the BMC product name by prefix (`X14` → `generic_x14`, `X10QBi` → `X10QBi`, `X9` → `generic_x9`, otherwise `generic`).
- Default polling interval for the NVMe fan controller lowered from 10s to 2s, matching CPU/GPU defaults.
- Unit and smoke test suites reorganized and expanded for maintainability; source code now holds 100% test coverage — see [`TESTING.md`](https://github.com/petersulyok/smfc/blob/main/TESTING.md).
- Installation docs reorganized: DEB/RPM repository installs are now the preferred path, ahead of Docker and the manual install script — see [README chapter 9](https://github.com/petersulyok/smfc/blob/main/README.md#9-installation-and-uninstallation).
- DEB/RPM packages now enable (but do not start) the `smfc` systemd unit on install, so you can review your configuration before the service first runs — see [README chapter 9.1](https://github.com/petersulyok/smfc/blob/main/README.md#91-deb-package-installation)/[9.2](https://github.com/petersulyok/smfc/blob/main/README.md#92-rpm-package-installation).

### Fixed
- Cold-boot race: after a full power cycle, fans could be pinned at 100% on low-polling zones (e.g. HD) for as long as their polling interval, while the BMC's fan subsystem was still settling. smfc now waits for live sensor data before applying any fan level at startup.


## [5.4.0] - 2026.04.30

### Added
- AMD GPU support: `gpu_type=amd` enables temperature monitoring via `rocm-smi` - based on [PR #112](https://github.com/petersulyok/smfc/pull/112) by @GCoffland
  - New `amd_temp_sensor=` parameter selects the temperature sensor (0-junction, 1-edge, 2-memory, default=0)
  - New `rocm_smi_path=` parameter specifies the path to the `rocm-smi` command
  - GPU type validation added to dependency checker in service startup
  - New AMD GPU docker image (`petersulyok/smfc:5.4.0-amd` / `latest-amd`) added
  - Unit test and smoke tests updated
- Man page and documentation (README.md) updated
- Dynamic temperature generation in Smoke tests for all fan controllers 
- Extended DEBUG level logging across the codebase for better internal state monitoring:
  - Fan controller: temperature smoothing details (raw vs smoothed, window fill), sensitivity check results, calculated fan level, level-unchanged confirmation, polling skipped with remaining time
  - Per-device temperatures logged in multi-device setups (min/avg/max aggregation)
  - IPMI: raw `ipmitool` command execution and response tracing, fan mode and fan level changes
  - Shared IPMI zone arbitration: desired levels logged on change, zone ownership map at startup
  - HD fan controller: smartctl fallback path, standby guard state
  - CONST fan controller: current vs expected fan level per zone
- Command line help text added to `/etc/default/smfc` configuration file
- Feature list added to README.md "How does it work?" section

### Changed
- Docker: many files refactored from `-gpu` to `-nvidia` and `-amd` naming
- Docker: [`docker-build.sh`](https://github.com/petersulyok/smfc/blob/main/docker/docker-build.sh) and [`docker-push.sh`](https://github.com/petersulyok/smfc/blob/main/docker/docker-push.sh) updated to build and push all three image variants in a single call
- Installation script ([`install.sh`](https://github.com/petersulyok/smfc/blob/main/bin/install.sh)) now preserves `/etc/default/smfc` when `--keep-config` is set and the file already exists
- Shared IPMI zone arbitration log ("Arbitration desired levels") now only fires when desired levels change, reducing log noise in steady state
- Improved docstrings with better test descriptions
- Pylint warnings corrected

## [5.3.0] - 2026.04.02

### Added
- Temperature smoothing feature added to all temperature-based fan controllers (CPU, HD, NVME, GPU). The new `smoothing=` configuration parameter enables a moving average window for temperature readings, reducing fan speed oscillation caused by brief temperature spikes.

### Changed
- Removed pointless catch-and-re-raise exception handling across source files, with inline comments documenting potential exceptions.
- Renamed "Super Micro" to "Supermicro" across the entire project.
- Updated references section in README.md: added tools/standards/kernel links, removed archived/inactive similar projects, added new active ones.
- Fixed broken links and cross-references in README.md (wrong relative path, broken anchor, missing section number, unlinked issue references).

### Fixed
- Shared IPMI zone arbitration: fixed logging for CONST fan controller in single-contributor zones (was producing a dangling `=` with no temperature value).
- Shared IPMI zone arbitration: non-shared zones were processed by `_apply_fan_levels()`, causing double IPMI calls and double logging.

## [5.2.0] - 2026.03.30

### Added
- Beta support added for some Supermicro X9 motherboards, where fan level can be set with the next IPMI raw command:
  ```
  ipmitool raw 0x30 0x91 0x5A 0x03 0x10 0x80
  ```
  Use `[Ipmi] platform_name=genericx9` configuration parameter to use this feature. Please test and give feedback.

### Changed
- Platform module refactored: monolithic `platform.py` split into separate modules (`platform.py`, `generic.py`,
`genericx9.py`, `x10qbi.py`) with corresponding test files.

### Fixed
- X10QBi zone calculation: zones now use logical values (0-3) with internal register offset, instead of raw register addresses.


## [5.1.2] - 2026.03.28

### Added
- New [`./bin/update_version_number.sh`](https://github.com/petersulyok/smfc/blob/main/bin/update_version_number.sh) script created to update all release specific files.

### Fixed
- DEB and RPM artifact names configured correctly
- Release process updated in DEVELOPMENT.md


## [5.1.1] - 2026.03.28

### Fixed
- DEB and RPM package creation: version numbers updated, RPM GitHub workflow fixed
- Release process updated in DEVELOPMENT.md

## [5.1.0] - 2026.03.28

### Added
- BMC information (device ID, firmware revision, manufacturer, product info) is retrieved and logged during IPMI initialization.
  ```
  BMC information:
       manufacturer name and id = Super Micro Computer Inc. (10876)
       product name and id = X11SCH-LN4F (6929)
       IPMI version = 2.0
       firmware revision = 1.74
  ```
- Platform abstraction implemented to support multiple Supermicro motherboards with different IPMI raw commands ([PR #97](https://github.com/petersulyok/smfc/pull/97) by @samuel-emrys merged). New `[Ipmi] platform_name=` configuration parameter added (values: `auto`, `generic`, `X10QBi`). Support for incompatible Supermicro X10QBi motherboard also added.
- DEB and RPM package creation added. See [PACKAGES.md](https://github.com/petersulyok/smfc/blob/main/PACKAGES.md) for more details. GitHub workflow will create DEB and RPM packages for new releases. 

### Changed
- Docstrings consistency check and update across source and test files.
- Docker files updated to Debian 13 (slim).
- @fz6 added to contributors (for shared IPMI zones work in [PR #89](https://github.com/petersulyok/smfc/pull/89)).
- Documentation updated for DEB/RPM packaging, hard disk and Supermicro compatibility.

### Fixed
- Inconsistent log level references in comments (`DEBUG` vs `CONFIG`) corrected in `constfc.py` and `fancontroller.py`.
- `openipmi.service` target removed from `smfc.service`.
- Smoketest execution fixed.


## [5.0.0] - 2026.03.04

### Added
- Shared IPMI zones implemented, multiple fan controllers can share an IPMI zone (inspired by PR [#89](https://github.com/petersulyok/smfc/pull/89) by @fz6)
- New NVME fan controller added.
- Python 3.14 support added.
- `./bin/create_python_env.sh` added again (using `uv`) to setup the Python development environment.

### Changed
- Logging changed to IPMI zone oriented way (this is a consequence of shared IPMI zones).
- Python maintenance window moved, current supported versions are: `3.10` - `3.14`.
Please note that other Python versions may also work but not tested.
- Many typos and grammar errors are corrected in the MD files.
- During the remote installation, `./bin/install.sh` will read additional `smfc` content from a targeted GitHub
version tag, not from git HEAD. It can secure the installation when the GitHub main/HEAD is changed. 
- Naming of fan controllers and IPMI zones is differentiated in a better way (see more details about the background [here](https://github.com/petersulyok/smfc/discussions/105)).
It means:
  - Fan controller section names have been changed, `zone` tags have been removed from there in the configuration files.
While this is an incompatible change and the old section names are deprecated, they will be supported for a while. You are
highly encouraged to update your configuration file.
  - Source code and files names have been refactored, `Zone` tags have been removed.
  - MD files and pictures are also updated.

### Removed
- HD fan controller doesn't accept NVME disks

 
## [v4.2.1] - 2025-10-26 

### Fixed
- [Issue #95](https://github.com/petersulyok/smfc/issues/95): SMFC fails to start as system service after reboot. If BMC is not fully initialized when `smfc` is starting
then `smfc` can stop with an error. It can happen if the BMC and the PC are booting at the same time. With this fix
`smfc` waits maximum 120 seconds for BMC initialization and will check BMC again every 5 seconds.


## [v4.1.1] - 2025-09-30 

### Changed
- Improved error messages for [HD zone] if temperature value cannot be read, the problematic disk name is also displayed.  


## [v4.1.0] - 2025-08-28 

### Added
- Linux man page added to `smfc`, part of the installation.
- Documentation updates.
- Delays added between starting fan controllers at startup (to provide more time for fan speed changes)
- `install.sh`: new dependencies added (`gzip`, `mandb` commands).

### Changed
- `uv` dependencies changed in `pyproject.toml`.
- `install.sh`: pip errors visible again.

### Removed
- `openipmi.service` target removed from `smfc.service`, Debian 13 Trixie complained about it.


## [v4.0.0] - 2025-07-08 Final Release 
The final release is identical with the beta-14 version and some documentation updates. Here is a high level summary of new features and changes:

### Added
- `smfc` is using `udev` (`pyudev` package) for device management (thanks to @abbaad): 
  - Automatic discovery of HWMON files for both Intel and AMD CPUs, including the number of CPUs, no manual configuration required. 
  - Automatic discovery of HWMON files for HDDs/SSDs based on `hd_names=` parameter, including the number of HDDS/SSDs, no manual configuration required.
  - Automatic use of `smartctl` if no HWMON file found for a hard disk (e.g. SCSI disk).
- `smfc` is a Python package, uploaded to pypi.org
- `smfc` has new command-line options (-s, -nd, -ne)
- `smfc` is using `uv` for Python project management
- `smfc` implements new fan controllers:
  - `[GPU zone]`: supporting nvidia GPUs (using `nvidia-smi` command)
  - `[CONST zone]` constant fan level in the zone(s)
- `smfc` implements free IPMI zone assignment, where a fan controller can control fans on one or more IPMI zones (see `ipmi_zone=` parameter)
- `CHANGELOG.md` added

### Changed
- `smfc` installer moved to `bin` folder, and can install remotely:

    `curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash /dev/stdin --keep-config --verbose`

- Default location of `smfc.conf ` moved to `/etc/smfc` folder.
- `hddtemp` is deprecated, `smfc` uses `smartctl` command for SAS/SCSI disks.
- `smfc` configuration file changes: 
  - `smfc` can read the old configuration files (version 3.x), but some parameters are not used anymore.
  - `count=` parameter is not used anymore, count is calculated automatically.
  - `hwmon_path=` parameter is not used anymore, identified automatically.
  - `hddtemp_path`= is not used anymore.
  - `swapped_zones=` is not used anymore, use `ipmi_zone=` parameter instead to specify the proper IPMI zone
- `TESTING.md` was renamed to `DEVELOPMENT.md`
- Docker changes:
  - There are two docker images available: smaller standard image (Alpine Linux based), bigger gpu-enabled image (Debian 12 based)
  - Tag naming is also changed (e.g. 4.0, latest, 4.0-gpu, latest-gpu)

### Removed
- Unused test data files from `test` folder 
- Unused scripts from `bin` folder 
- `hddtemp` removed

### Fixed
- Support of AMD CPUs (without manual configuration) - [issue #25](https://github.com/petersulyok/smfc/issues/25)


## [v4.0.0b14] - 2025-06-22 Pre-release 

### Fixed
- Fix: [issue #76](https://github.com/petersulyok/smfc/issues/76) corrected, where a parsing error blocked HdZone's initialization for newer SCSI disks.


## [v4.0.0b13] - 2025-06-06 Pre-release 

### Fixed
- Fix: test_08_service.py stopped running if `nvidia-smi` was not installed.
- Fix: pylint warning


## [v4.0.0b12] - 2025-06-06 Pre-release 

### Added
- GPU zone fan controller is enabled in docker (please read [Docker.md](https://github.com/petersulyok/smfc/blob/main/docker/Docker.md))
- There are two docker images available: standard, gpu-enabled
- Dependency check: check of `nvidia-smi` added


## [v4.0.0b11] - 2025-06-02 Pre-release 

### Added
- Docker building script updated to BuildKit
- New docker image uploaded to docker hub (but GPU zone is still not working in docker)
- New package uploaded to pypi.org


## [v4.0.0b10] - 2025-05-23 Pre-release 

### Added
- A new fan controller, called CONST zone, was implemented to provide constant fan level in one or more IPMI zones. It does not have any temperature source
and does not read any temperature. The zone configuration is the following:

```
# Const zone: this fan controller does not read any temperature and sets constant fan level for IPMI zones(s).
[CONST zone]
# Fan controller enabled (bool, default=0)
enabled=0
# IPMI zone(s) (comma- or space-separated list of int, default=1))
ipmi_zone=1
# Polling interval for checking level and resetting if needed (int, sec, default=30)
polling=30
# Constant fan level (int, %, default=50)
level=50
```

- Unit tests and smoketest updated
- Python package on `pypi.org` updated to v4.0.0b10
- Docker image IS NOT updated!


## [v4.0.0b9] - 2025-05-22 Pre-release 

### Fixed
- HdZone init fixed.
- Python package on `pypi.org` updated to v4.0.0b9
- Docker image IS NOT updated!


## [v4.0.0b8] - 2025-05-19 Pre-release 

### Fixed
- GPU fan controller feature fixed (missing commit added).
- Python package on `pypi.org` updated to v4.0.0b8
- Docker image IS NOT updated!


## [v4.0.0b7] - 2025-05-18 Pre-release 

### Added
- New GPU fan controller implemented for Nvidia video cards. A new section added to the configuration file.
- Python package on `pypi.org` updated to v4.0.0b7
- Docker image IS NOT updated!


## [v4.0.0b6] - 2025-05-06 Pre-release 

### Added
- Further enhancement of **_Free zone assignment_** feature: multiple IPMI zones can be assigned to a fan controller.
It means that `ipmi_zone=` parameter could be a (comma- or space-separated) list of integers. This configuration could
be useful for server chassis or motherboard where the fans are cooling everything and the proper heat source needs
to be selected for all fans. For example:

    ```
    [CPU zone]
    ...
    ipmi_zone = 0, 1
    ```
    in this configuration, the CPU temperature will control the fans in the IPMI zones 0 and 1, while here:

    ```
    [HD zone]
    ...
    ipmi_zone = 2, 3
    ```
    the HDD temperature will control the fans in the IPMI zones 2 and 3.

- IPMI zone information added to the new fan level log message, for example:

    `smfc.service[1645]: CPU zone: new fan level > 35%/28.0C @ IPMI [0, 1] zone(s).`

- Python package on `pypi.org` updated to v4.0.0b6
- Docker image updated to v4.0.0.b6


## [v4.0.0b5] - 2025-04-21 Pre-release 

### Added
- Free IPMI zone assignment feature implemented:
  - Any IPMI zone can be assigned to _CPU zone_ or _Hd Zone_, to support server motherboards having multiple IPMI zones,
and to implement the former _Swapped zones_ feature in a more generic way.
  - `ipmi_zone=` parameter added to zone configuration
  - Users of _Swapped zones_ feature, please adjust your configuration!
- New command line options added to `install.sh` (`-k`, `-v`)
- CHANGELOG.md document added

### Changed
- DEVELOPMENT.md document added (TESTING.md renamed/extended)

### Removed
- `swapped_zones=` parameter is not used anymore, this feature can be used with free IPMI zone assignment. 

### Fixed
- `install.sh` cannot save the existing configuration file ([discussion #64](https://github.com/petersulyok/smfc/discussions/64))

## [v4.0.0b4] - 2025-04-18 

This pre-release is available on the main branch, pypi.org, hub.docker.com (announced in discussion #64)

### Added
- `smfc` is a Python Package.
- `smfc` is uploaded to pypi.org, a GitHub workflow can publish that with each new release.
- `smfc` is using `udev` (`pyudev`) for device management (thanks to @abbaad): 
  - Automatic discovery of HWMON files for both Intel and AMD CPUs, including the number of CPUs, no manual configuration required. 
  - Automatic discovery of HWMON files for HDDs/SSDs based on `hd_names=` parameter, including the number of HDDS/SSDs, no manual configuration required.
  - Automatic use of `smartctl` if no HWMON file found for a hard disk (e.g. SCSI disk).
- New command line parameters for `smfc`:
  - `-s`: use of `sudo` with `ipmitool` and `smartctl` commands.
  - `-nd`: do not check dependencies.
  - `-ne`: do not set fan speed to 100% at emergency exit
- A new docker image created, `4.0.0b4` version
- `uv` is used for Python project management (`uv.lock` is part of version control)

### Changed
- Changes in the manual installation script ([`./bin/install.sh`](https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh)):
  - moved to the `bin` folder.
  - script has several new command-line options (`-v`, `-k`).
  - can install `smfc` from remote sources (i.e. from pypi.org and GitHub): 

      `curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash /dev/stdin --keep-config --verbose`

- Default location of `smfc.conf ` moved to `/etc/smfc` folder.
- `smfc` configuration file changes: 
  - `smfc` can read the old configuration files (version 3.x), but some parameters are not used anymore.
  - `count=` parameter is not used anymore, count is calculated automatically.
  - `hwmon_path=` parameter is not used anymore, identified automatically.
  - `hddtemp_path`= is not used anymore, `hddtemp` command is replaced by `smartctl`.
- Docker changes:
  - all files moved to `docker` folder
  - `hddtemp` compilation is removed from the `Dockerfile`
  - `py3-pyudev` is added as a dependency
  - version management is refactored 
  - `smfc` is installed with `pip` at build creation time
- Testing changes:
  - unit tests are refactored to use `pytest`, `mock`, and `pytest-mock`
  - smoke tests are also executed with `pytest`

### Removed
- Unused test data files from `test` folder 
- Unused scripts from `bin` folder 
- Use of `hddtemp` removed


## [v3.8.0] - 2025-03-15

### Added

- Remote IPMI access is supported, see `[IPMI] remote_parameters=` in the configuration file (requested in [issue #27](https://github.com/petersulyok/smfc/issues/27))

### Changed

- `fan_measurment.sh`: dynamically retrieves fan names rather than relying on hardcoded names (@JSouthGB)
- Docker image updated to v3.8.0


## [v3.7.0] - 2025-01-17

### Added

- `install.sh` adds all disks to your smfc.conf at installation time
- `hddtemp_emu.sh` added if hddtemp is not available. This feature is available in docker, too.

### Changed

- `smfc.service`: `openipmi.service` added as a prerequisite. Sometimes `smfc` was initialized earlier than the IPMI interface. This is not relevant for docker.


## [v3.6.0] - 2024-12-12

### Changed

- Python 3.13 support added
- Python 3.8 support removed (because of a pylint warning)
- New shell script added to create virtual Python environment with pyenv (`./bin/create_pyhon_env.sh`)

### Fixed

- Automatic HWMON path creation for NVME SSDs is fixed (reported in [#43](https://github.com/petersulyok/smfc/issues/43))


## [v3.5.1] - 2024-08-23

### Changed

- Documentation updated (IPMI thresholds for X13 motherboards, Swapped zones ([#38](https://github.com/petersulyok/smfc/issues/38)), FAQ)
- Simplified log message for new fan level
- Docker image updated


## [v3.5.0] - 2024-05-21

### Added

- checking run-time dependencies (kernel modules and external command) added to startup
- X13 and AST2600 compatibility notes added to documentation


## [v3.4.0] - 2023-11-28

### Added

- Docker support added, smfc docker image can be pulled from docker hub


## [v3.3.0] - 2023-11-09

### Added

- Support for new Python 3.12
- New emergency exit feature extended to all exit/exception situations (if IPMI management is already configured in smfc)
- Documentation updated
- Unit test updated to the new feature/refactoring, code coverage improved to 99%


## [v3.2.0] - 2023-11-08

### Added

- New emergency exit implemented for exceptions and runtime errors. It will switch all fans back to speed 100% if smfc terminates (fix for [issue #32](https://github.com/petersulyok/smfc/issues/32))

### Changed

- Log message for new temperature/level improved to avoid such a long format
- CPU zone: new level > 65.0C > [T:65.33333333333333C/L:50%]
- The new log message will be
- CPU zone: new level > 65.0C > [T:65.3C/L:50%]


## [v3.1.1] - 2023-08-16

### Fixed

- Fix: sample `hd_names=` parameter is not generated if --keep-config is specified in `install.sh` script


## [v3.1.0] - 2023-08-16

### Added

- `install.sh` script can preserve the original configuration file (using `--keep-config` command-line option) during the installation


## [v3.0.2] - 2023-08-16

### Fixed

- Fix: a `chown` warning fixed in `install.sh` script.


## [v3.0.1] - 2023-08-16

### Fixed

- Fix: a flake8 warning (E231) corrected for Python 3.8


## [v3.0.0] - 2023-08-16

### Added

- support for SAS/SCSI disks (with the help of hddtemp)
- support for NVME SSDs
- support mixed configuration for SATA, SAS/SCSI, and NVME disks
- Recommendation added to AMD users (thanks to @staaled in [#25](https://github.com/petersulyok/smfc/issues/25))
- new script added to reset BMC and measure the time (ipmi/ipmi_bmc_reset.sh)
- all tests and documentation updated


## [v2.5.0] - 2023-05-26

### Added

- new log level defined for logging initial configuration.

### Changed

- Unit test and documentation have been updated.


## [v2.4.1] - 2023-05-25

### Fixed

- after v2.4.0 refactoring, the HD zone could not be enabled and initialized ([issue #18](https://github.com/petersulyok/smfc/issues/18))


## [v2.4.0] - 2023-05-19

### Added

- Use of the configuration file parameters in the IPMI class was refactored, unit tests have been updated
- new chapter added to the documentation about the HW compatibility

### Fixed

- Note added to cover [issue #8](https://github.com/petersulyok/smfc/issues/8) by @fcladera


## [v2.3.1] - 2023-02-15

### Fixed

- smfc version number updated.


## [v2.3.0] - 2023-02-15

### Added

- Swapped zones feature implemented (see [issue #7](https://github.com/petersulyok/smfc/issues/7)), smoke and unit tests are updated, the feature is documented
- Documentation improved, [issue #12](https://github.com/petersulyok/smfc/issues/12) documented
- Test documentation updated


## [v2.2.2] - 2023-01-12

### Fixed

- new error handling for IPMI issues in `Ipmi.get_fan_mode()` (see [issue #14](https://github.com/petersulyok/smfc/issues/14)).


## [v2.2.1] - 2023-01-03

### Fixed

- Missing `test/find_dirs.sh` file recovered for smoke tests
- a parameter fixed in `smfc-sample5.conf`  by @smtdev


## [v2.2.0] - 2022-11-04

### Added

- GitHub workflow upgraded to the final Python 3.11.0
- Configuration parameters of Python tools moved to `pyproject.toml` file
- Unit test coverage improved a bit


## [v2.1.0] - 2022-08-12

### Added

- Minimum requirement changed to Python 3.7 (see [Issue #4](https://github.com/petersulyok/smfc/issues/4) for more details)
- `flake8` and `pylint` warnings corrected
- Unit test execution moved to pytest
- GitHub workflow implemented
- Test status badge added to README.md


## [v2.0.1] - 2022-08-10

### Fixed

- installation script fixed.


## [v2.0.0] - 2022-08-10

### Added

- `hwmon_path=` parameter constructed automatically in both zones (the configuration file changed!)
- Sample configuration files provided for different scenarios

### Changed
 
- Default values of configuration parameters adjusted
- Unit tests are updated and refactored
- Smoke tests cover more configuration cases

### Fixed

- [Issue #3](https://github.com/petersulyok/smfc/issues/3) is fixed (`hd_names=` must be specified in /dev/disk/by-id/... form)


## [v1.2.0] - 2022-03-27

### Added

- IPMI scripts are updated.
- Documentation extended, new picture added, typos fixed.


## [v1.1.0] - 2022-02-12

### Added

- Support multiple CPUs.
- Temperature calculation can be configured for multiple CPUs and HDDs. It can be minimum, average, and maximum value.
- Smoke tests and unit tests have been updated.


## [v1.0.0] - 2021-10-15 - Prelease

- This is a pre-release after one-year stabilization, refactoring and testing.
- The code is ready to be tested by other users.
