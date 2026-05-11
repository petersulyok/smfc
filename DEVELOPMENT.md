# Development

> For an overview of the internal structure (classes, execution order, shared IPMI zones, etc.) see [ARCHITECTURE.md](ARCHITECTURE.md).

This project is using `uv` for Python project management, see more details about [installation of `uv`](https://docs.astral.sh/uv/getting-started/installation/).
`uv` can provide everything that multiple tools (e.g. `pip`, `pyenv`, `venv`) provide, but much faster. For example:

* install a Python run-time: `uv python install 3.14`
* use a specific Python version: `uv python pin 3.14`
* create virtual Python environment: `uv venv`
* install all dependencies: `uv sync`

`uv` has a lock file (`uv.lock`) for storing dependencies, this should be part of version control.

Building a development environment from scratch (with Python 3.14) contains the following steps:

```commandline
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/petersulyok/smfc.git
uv python install 3.14
uv python pin 3.14
uv sync
source .venv/bin/activate
```

Dependencies are listed in `pyproject.toml` file and the proper version numbers are handled by `uv`:

```ini
dependencies = [
    "pyudev"
]

[dependency-groups]
dev = [
    "build",
    "coverage",
    "mock",
    "pytest",
    "pytest-cov",
    "pytest-mock",
    "twine"
]

lint = [
    "ruff",
    "pylint"
]
```

All the steps above (installing `uv`, Python, and dependencies) can be automated with the `./bin/create_python_env.sh` script:

```commandline
./bin/create_python_env.sh 3.14
```

## Linting

The code can be checked with `pylint` and `ruff`:

```commandline
pylint src test
ruff check
```

# Testing

This chapter describes the test environment of `smfc` project.  
Important notes:  
  
* All test related content can be found in `test` folder
* Only `python3` and `bash` commands are required for the execution of the tests (was tested on Linux, macOS), all external commands `ipmitool` and `smartctl` are substituted by scripts
* Test are executed by `pytest`
* All development dependencies (defined in `pyproject.toml`) will be installed after the execution of these commands:

```commandline
uv sync
source .venv/bin/activate
```

## Smoke tests  

Several smoke tests have been provided for `smfc` where the service is executed with different configuration files. Notes:  
  
* all smoke tests should be executed from the project root folder and can be stopped by pressing `CTRL+C`:

```commandline
$ ./test/run_test_cpu_1.sh
```

* the following smoke scripts and fan controller configurations can be executed:

   | Test script                  | CPU                         | HD        | NVME      | GPU           | CONST      | Standby guard |
   |------------------------------|-----------------------------|-----------|-----------|---------------|------------|---------------|
   | `run_test_cpu_1.sh`          | 1 x CPU                     | 1 x HD    | disabled  | disabled      | enabled    | enabled       |
   | `run_test_cpu_2.sh`          | 2 x CPUs                    | disabled  | disabled  | 1 GPU         | disabled   | disabled      |
   | `run_test_cpu_4.sh`          | 4 x CPUs                    | 4 x HDs   | disabled  | 4 GPUs        | disabled   | enabled       |
   | `run_test_hd_1.sh`           | disabled                    | 1 x HD    | disabled  | disabled      | enabled    | enabled       |
   | `run_test_hd_2.sh`           | 1 x CPU                     | 2 x HDs   | disabled  | disabled      | disabled   | disabled      |
   | `run_test_hd_4.sh`           | disabled                    | 4 x HDs   | disabled  | 2 GPUs        | disabled   | disabled      |
   | `run_test_hd_8.sh`           | 4 x CPUs                    | 8 x HDs   | disabled  | disabled      | disabled   | enabled       |
   | `run_test_const_level.sh`    | 1 x CPU                     | disabled  | disabled  | disabled      | enabled    | enabled       |
   | `run_test_gpu_8_nvidia.sh`   | 1 x CPU                     | disabled  | disabled  | 8 Nvidia GPUs | enabled    | disabled      |
   | `run_test_gpu_8_amd.sh`      | 1 x CPU                     | disabled  | disabled  | 8 AMD GPUs    | enabled    | disabled      |
   | `run_test_nvme_4.sh`         | 2 x CPU                     | disabled  | 4 x NVME  | disabled      | enabled    | disabled      |
   | `run_test_shared_zones.sh`   | 1 x CPU                     | disabled  | 2 x NVMEs | disabled      | disabled   | disabled      |
   | `run_test_shared_zones_2.sh` | 2 x CPUs (`CPU:0`, `CPU:1`) | 2 x HDs   | disabled  | disabled      | disabled   | disabled      |

   Notes:
   - `run_test_shared_zones.sh` tests the shared IPMI zone arbitration where CPU and NVME fan controllers both use IPMI zone 0.
   - `run_test_shared_zones_2.sh` tests the multi-curve CPU feature combined with shared-zone arbitration: `CPU:0` controls zone 0, while `CPU:1` and `HD` share zone 1.
   - `run_test_gpu_8_nvidia.sh` and `run_test_gpu_8_amd.sh` test GPU fan controller with Nvidia and AMD GPUs respectively.
   - During smoke tests, temperature values change gradually over time to simulate realistic thermal behavior. A background thread updates hwmon temperature files (for CPU, HD, NVMe) every second, applying random changes of +/- 0-3 degrees within the configured min/max range. GPU temperatures (both Nvidia and AMD) also change gradually between script invocations using a state file to track previous values.

## Unit tests

The whole project (all source code) is completely unit tested. The unit tests are executed with `pytest`:

```commandline
$ pytest
============================= test session starts ==============================
platform linux -- Python 3.14.3, pytest-8.3.5, pluggy-1.5.0
rootdir: /home/petersulyok/git/github/smfc
configfile: pyproject.toml
plugins: cov-6.0.0, mock-3.14.0
collected 708 items                                                            

test/test_cmd.py .                                                       [  0%]
test/test_config.py .................................................... [  7%]
........................................................................ [ 17%]
..................................................                       [ 24%]
test/test_constfc.py ................                                    [ 26%]
test/test_cpufc.py .....................                                 [ 29%]
test/test_fancontroller.py ............................................. [ 36%]
.....                                                                    [ 37%]
test/test_generic.py ................................                    [ 41%]
test/test_genericx9.py .................................                 [ 46%]
test/test_gpufc.py ...................                                   [ 48%]
test/test_hdfc.py ...................................................... [ 56%]
......................                                                   [ 59%]
test/test_ipmi.py ...................................................... [ 67%]
.................                                                        [ 69%]
test/test_log.py ....................................................... [ 77%]
..................................................                       [ 84%]
test/test_nvmefc.py ..............                                       [ 86%]
test/test_platform.py .....                                              [ 87%]
test/test_service.py ................................................... [ 94%]
........                                                                 [ 95%]
test/test_x10qbi.py ................................                     [100%]

============================= 708 passed in 1.59s ==============================
```

The code coverage could be also measured and displayed during the test execution:

```commandline
$ pytest --cov=test --cov=src  
======================================= test session starts ========================================
platform linux -- Python 3.14.3, pytest-8.3.5, pluggy-1.5.0
rootdir: /home/petersulyok/git/github/smfc
configfile: pyproject.toml
plugins: cov-6.0.0, mock-3.14.0
collected 708 items                                                                                

test/test_cmd.py .                                                                           [  0%]
test/test_config.py ........................................................................ [ 10%]
............................................................................................ [ 23%]
..........                                                                                   [ 24%]
test/test_constfc.py ................                                                        [ 26%]
test/test_cpufc.py .....................                                                     [ 29%]
test/test_fancontroller.py ..................................................                [ 37%]
test/test_generic.py ................................                                        [ 41%]
test/test_genericx9.py .................................                                     [ 46%]
test/test_gpufc.py ...................                                                       [ 48%]
test/test_hdfc.py .......................................................................... [ 59%]
..                                                                                           [ 59%]
test/test_ipmi.py .......................................................................    [ 69%]
test/test_log.py ........................................................................... [ 80%]
..............................                                                               [ 84%]
test/test_nvmefc.py ..............                                                           [ 86%]
test/test_platform.py .....                                                                  [ 87%]
test/test_service.py ...........................................................             [ 95%]
test/test_x10qbi.py ................................                                         [100%]

---------- coverage: platform linux, python 3.14.3-final-0 -----------
Name                           Stmts   Miss  Cover
--------------------------------------------------
src/smfc/__init__.py              13      0   100%
src/smfc/cmd.py                    4      0   100%
src/smfc/config.py               269      0   100%
src/smfc/constfc.py               33      0   100%
src/smfc/cpufc.py                 16      0   100%
src/smfc/fancontroller.py        105      0   100%
src/smfc/generic.py               27      0   100%
src/smfc/genericx9.py             34      0   100%
src/smfc/gpufc.py                 55      0   100%
src/smfc/hdfc.py                 120      0   100%
src/smfc/ipmi.py                 122      0   100%
src/smfc/log.py                   57      0   100%
src/smfc/nvmefc.py                23      0   100%
src/smfc/platform.py              37      0   100%
src/smfc/platform_factory.py      14      0   100%
src/smfc/service.py              209      0   100%
src/smfc/x10qbi.py                42      0   100%
test/__init__.py                   0      0   100%
test/test_cmd.py                   9      0   100%
test/test_config.py              522      0   100%
test/test_constfc.py              80      0   100%
test/test_cpufc.py               139      0   100%
test/test_data.py                173      0   100%
test/test_fancontroller.py       318      0   100%
test/test_generic.py              80      0   100%
test/test_genericx9.py            82      0   100%
test/test_gpufc.py               131      0   100%
test/test_hdfc.py                305      0   100%
test/test_ipmi.py                245      0   100%
test/test_log.py                  52      0   100%
test/test_nvmefc.py              142      0   100%
test/test_platform.py             32      0   100%
test/test_service.py             981      0   100%
test/test_x10qbi.py               85      0   100%
--------------------------------------------------
TOTAL                           4556      0   100%


======================================= 708 passed in 2.34s ========================================
```

For a more detailed HTML coverage report run this command:

```commandline
$ pytest --cov=src --cov=test --cov-report=html
```

The detailed HTML report will be available in folder `htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage is 100%.  


# GitHub

## GitHub workflow
The project implemented the following GitHub workflows:

1. Unit test and lint execution (`test.yml`). A commit can trigger this action:
   * executes unit test on `ubuntu-latest` OS and on Python versions `3.10`, `3.11`, `3.12`, `3.13`, `3.14`
   * executes `pylint` and `ruff`
   * generates coverage data and upload it to [codecov.io](https://codecov.io/)

2. Publish Python distribution packages to PyPI (`publish.yml`). A published release triggers this action:
   * build distribution package on Python `3.14`
   * upload the new package to PyPI

3. Build DEB and RPM packages (`packages.yml`). A published release triggers this action:
   * build DEB package on `debian:trixie`
   * build RPM package on `fedora:latest`
   * upload both packages as release artifacts


# Release process

## Creation of a new GitHub release
Follow these steps to create a new release:

* Run `./bin/update_version_number.sh X.Y.Z` to update the version number in all release-specific files
  (`pyproject.toml`, `doc/smfc.1`, `smfc.spec`, `debian/changelog`, `uv.lock`)
* Update the changelog entries in `smfc.spec` and `debian/changelog` with the actual release notes
* Commit all changes
* Run unit tests with `pytest`, and correct all errors
* Run linters `pylint` and `ruff`, and correct all warnings
* Update CHANGELOG.md with the new release information
* Commit all changes and test again
* Create a new release on GitHub with the same version number, and the new package will be published on PyPI automatically. DEB and RPM packages will be built automatically by the `packages.yml` workflow.
* Build new images for docker and upload them

## Building and uploading of Docker images
After publishing an `smfc` release, the docker image could be built and uploaded. 
The docker images can be built locally in the project root folder:

```commandline
./docker/docker-build.sh 4.1.0 latest
```
Notes:
- Please note that the dockerfile will install `smfc` from `pypi.org`, so the version must refer an official `smfc` release.
- The build script will generate the following tags: `4.1.0`, `latest`, `4.1.0-nvidia`, `latest-nvidia`, `4.1.0-amd`, `latest-amd`.

The generated docker images can be uploaded to [hub.docker.com](https://hub.docker.com/r/petersulyok/smfc)
in the following way:

```commandline
./docker/docker-push.sh 4.1.0 latest
```

This pushes all three image variants (`4.1.0`, `4.1.0-nvidia`, `4.1.0-amd`) and their secondary tags (`latest`, `latest-nvidia`, `latest-amd`) in a single call.

> Written with [StackEdit](https://stackedit.io/).
