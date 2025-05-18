# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v4.0.0b7] - 2025-05-18 Pre-release 

### New/Added
- New GPU fan controller implemented for Nvidia video cards. A new section added to the configuration file.
- Python package on `pypi.org` updated to v4.0.0b7
- Docker image IS NOT updated!


## [v4.0.0b6] - 2025-05-06 Pre-release 

### New/Added
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

### New/Added
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
- `install.sh` cannot save the existing configuration file (discussion #64)

## [v4.0.0b4] - 2025-04-18 

This pre-release is available on the main branch, pypi.org, hub.docker.com (announced in discussion #64)

### New/Added
- `smfc` is a Python Package.
- `smfc` is uploaded to pypi.org, a GitHub workflow can publish that with each new release.
- `smfc` is using `udev` (`pyudev`) for device management (thanks to @abbaad): 
  - Automatic discovery of HWMON files for both Intel and AMD CPUs, including the number of CPUs, no manual configuration required. 
  - Automatic discovery of HWMON files for HDDs/SSDs based on `hd_names=` parameter, including the number of HDDS/SSDs, no manual configuration required.
  - Automatic use of `smartctl` if no HWMON file found for a hard disks (e.g. SCSI disk).
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

### New/Added

- Remote IPMI access is supported, see `[IPMI] remote_parameters=` in the configuration file (requested in issue #27)

### Changed

- `fan_measurment.sh`: dynamically retrieves fan names rather than relying on hardcoded names (@JSouthGB)
- Docker image updated to v3.8.0


## [v3.7.0] - 2025-01-17

### New/Added

- `install.sh` adds all disks to your smfc.conf at installation time
- `hddtemp_emu.sh` added if hddtemp is not available. This feature is available in docker, too.

### Changed

- `smfc.service`: `openipmi.service` added as a prerequisite. Sometime `smfc` was initialized earlier than the IPMI interface. This is not relevant for docker.


## [v3.6.0] - 2024-12-12

### Changed

- Python 3.13 support added
- Python 3.8 support removed (because of a pylint warning)
- New shell script added to create virtual Python environment with pyenv (`./bin/create_pyhon_env.sh`)

### Fixed

- Automatic HWMON path creation for NVME SSDs is fixed (reported in #43)


## [v3.5.1] - 2024-08-23

### Changed

- Documentation updated (IPMI thresholds for X13 motherboards, Swapped zones (#38), FAQ)
- Simplified log message for new fan level
- Docker image updated


## [v3.5.0] - 2024-05-21

### New/Added

- checking run-time dependencies (kernel modules and external command) added to startup
- X13 and AST2600 compatibility notes added to documentation


## [v3.4.0] - 2023-11-28

### New/Added

- Docker support added, smfc docker image can be pulled from docker hub


## [v3.3.0] - 2023-11-09

### New/Added

- Support for new Python 3.12
- New emergency exit feature extended to all exit/exception situations (if IPMI management is already configured in smfc)
- Documentation updated
- Unit test updated to the new feature/refactoring, code coverage improved to 99%


## [v3.2.0] - 2023-11-08

### New/Added

- New emergency exit implemented for exceptions and runtime errors. It will switch all fans back to speed 100% if smfc terminates (fix for issue #32)

### Changed

- Log message for new temperature/level improved to avoid such a long format
- CPU zone: new level > 65.0C > [T:65.33333333333333C/L:50%]
- The new log message will be
- CPU zone: new level > 65.0C > [T:65.3C/L:50%]


## [v3.1.1] - 2023-08-16

### Fixed

- Fix: sample `hd_names=` parameter is not generated if --keep-config is specified in `install.sh` script


## [v3.1.0] - 2023-08-16

### New/Added

- `install.sh` script can preserve the original configuration file (using `--keep-config` command-line option) during the installation


## [v3.0.2] - 2023-08-16

### Fixed

- Fix: a `chown` warning fixed in `install.sh` script.


## [v3.0.1] - 2023-08-16

### Fixed

- Fix: a flake8 warning (E231) corrected for Python 3.8


## [v3.0.0] - 2023-08-16

### New/Added

- support for SAS/SCSI disks (with the help of hddtemp)
- support for NVME SSDs
- support mixed configuration for SATA, SAS/SCSI, and NVME disks
- Recommendation added to AMD users (thanks to @staaled in #25)
- new script added to reset BMC and measure the time (ipmi/ipmi_bmc_reset.sh)
- all tests and documentation updated


## [v2.5.0] - 2023-05-26

### New/Added

- new log level defined for logging initial configuration.

### Changed

- Unit test and documentation have been updated.


## [v2.4.1] - 2023-05-25

### Fixed

- after v2.4.0 refactoring, the HD zone could not be enabled and initialized (issue #18)


## [v2.4.0] - 2023-05-19

### New/Added

- Use of the configuration file parameters in the IPMI class was refactored, unit tests have been updated
- new chapter added to the documentation about the HW compatibility

### Fixed

- Note added to cover issue #8 by @fcladera


## [v2.3.1] - 2023-02-15

### Fixed

- smfc version number updated.


## [v2.3.0] - 2023-02-15

### New/Added

- Swapped zones feature implemented (see issue #7), smoke and unit tests are updated, the feature is documented
- Documentation improved, issue #12 documented
- Test documentation updated


## [v2.2.2] - 2023-01-12

### Fixed

- new error handling for IPMI issues in `Ipmi.get_fan_mode()` (see issue #14).


## [v2.2.1] - 2023-01-03

### Fixed

- Missing `test/find_dirs.sh` file recovered for smoke tests
- a parameter fixed in `smfc-sample5.conf`  by @smtdev


## [v2.2.0] - 2022-11-04

### New/Added

- GitHub workflow upgraded to the final Python 3.11.0
- Configuration parameters of Python tools moved to `pyproject.toml` file
- Unit test coverage improved a bit


## [v2.1.0] - 2022-08-12

### New/Added

- Minimum requirement changed to Python 3.7 (see Issue #4 for more details)
- `flake8` and `pylint` warnings corrected
- Unit test execution moved to pytest
- GitHub workflow implemented
- Test status badge added to README.md


## [v2.0.1] - 2022-08-10

### Fixed

- installation script fixed.


## [v2.0.0] - 2022-08-10

### New/Added

- `hwmon_path=` parameter constructed automatically in both zones (the configuration file changed!)
- Sample configuration files provided for different scenarios

### Changed
 
- Default values of configuration parameters adjusted
- Unit tests are updated and refactored
- Smoke tests are covers more configuration cases

### Fixed

- Issue #3 is fixed (`hd_names=` must be specified in /dev/disk/by-id/... form)


## [v1.2.0] - 2022-03-27

### New/Added

- IPMI scripts are updated.
- Documentation extended, new picture added, typos fixed.


## [v1.1.0] - 2022-02-12

### New/Added

- Support multiple CPUs.
- Temperature calculation can be configured for multiple CPUs and HDDs. It can be minimum, average, and maximum value.
- Smoke tests and unit tests have been updated.


## [v1.0.0] - 2021-10-15 - Prelease

- This is a pre-release after one-year stabilization, refactoring and testing.
- The code is ready to be tested by other users.
