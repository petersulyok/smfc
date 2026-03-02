# Development

This project is using `uv` for Python project management, see more details about [installation of `uv`](https://docs.astral.sh/uv/getting-started/installation/).
`uv` can provide everything that multiple tools (e.g. `pip`, `pyenv`, `venv`) provide, but much faster. For example:

* install a Python run-time: `uv python install 3.13`
* use a specific Python version: `uv python pin 3.13`
* create virtual Python environment: `uv venv`
* install all dependencies: `uv sync`

`uv` has a lock file (`uv.lock`) storing all dependencies, this should be part of version control.

Building a development environment from scratch (with Python 3.12) contains the following steps:
```
      pipx install uv
      pipx ensurepath
      git clone https://github.com/petersulyok/smfc.git
      uv python install 3.12
      uv python pin 3.12
      uv sync
      source .venv/bin/activate
```
Dependencies are listed in `pyproject.toml` file and the proper version numbers are handled by `uv`:
```
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

## Linting

The code can be checked with `pylint` and `ruff`:
```
	pylint src test
    ruff check
```

# Testing

This chapter describes the test environment of `smfc` project.  
Important notes:  
  
* All test related content can be found in `test` folder
* Only `python3` and `bash` are required for the execution of the tests (was tested on Linux, macOS), all external commands `ipmitool` and `smartctl` are substituted by scripts
* Test are executed by `pytest`
* All development dependencies (defined in `pyproject.toml`) will be installed after the execution of these commands:

```
      uv sync
      source .venv/bin/activate
```

## Smoke tests  

Several smoke tests have been provided for `smfc` where the service is executed with different configuration files. Notes:  
  
* all smoke tests should be executed from the project root folder and can be stopped by pressing `CTRL+C`:

	`$ ./test/run_test_cpu_1.sh`

* the following smoke scripts and fan controller configurations can be executed:

   | Test script               | CPU      | HD       | NVME      | GPU      | CONST      | Standby guard |
   |---------------------------|----------|----------|-----------|----------|------------|---------------|
   | `run_test_cpu_1.sh`       | 1 x CPU  | 1 x HD   | disabled  | disabled | enabled    | enabled       |
   | `run_test_cpu_2.sh`       | 2 x CPUs | disabled | disabled  | 1 GPU    | disabled   | disabled      |
   | `run_test_cpu_4.sh`       | 4 x CPUs | 4 x HDs  | disabled  | 4 GPUs   | disabled   | enabled       |
   | `run_test_hd_1.sh`        | disabled | 1 x HD   | disabled  | disabled | enabled    | enabled       |
   | `run_test_hd_2.sh`        | 1 x CPU  | 2 x HDs  | disabled  | disabled | disabled   | disabled      |
   | `run_test_hd_4.sh`        | disabled | 4 x HDs  | disabled  | 2 GPUs   | disabled   | disabled      |
   | `run_test_hd_8.sh`        | 4 x CPUs | 8 x HDs  | disabled  | disabled | disabled   | enabled       |
   | `run_test_const_level.sh` | 1 x CPU  | disabled | disabled  | disabled | enabled    | enabled       |
   | `run_test_gpu_8.sh`       | 1 x CPU  | disabled | disabled  | 8 GPUs   | enabled    | disabled      |
   | `run_test_nvme_4.sh`      | 2 x CPU  | disabled | 4 x NVME  | disabled | enabled    | disabled      |
   | `run_test_shared_zones.sh`| 1 x CPU  | disabled | 2 x NVMEs | disabled | disabled   | disabled      |

   Note: `run_test_shared_zones.sh` tests the shared IPMI zone arbitration where CPU and NVME fan controllers both use IPMI zone 0.

## Unit tests

The whole project (all source code) is completely unit tested. The unit tests are executed with `pytest`:


      $ pytest
      =========================================== test session starts ===========================================
      platform linux -- Python 3.14.3, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 400 items                                                                                       
      
      test/test_01_log.py ............................................................................... [ 19%]
      ..........................                                                                          [ 26%]
      test/test_02_ipmi.py .......................................................................        [ 44%]
      test/test_03_fancontroller.py .................................................                     [ 56%]
      test/test_04_cpufc.py .....................                                                         [ 61%]
      test/test_05_hdfc.py ...........................................................................    [ 80%]
      test/test_06_gpufc.py ..............                                                                [ 83%]
      test/test_07_constfc.py .................                                                           [ 88%]
      test/test_08_service.py .................................                                           [ 96%]
      test/test_09_cmd.py .                                                                               [ 96%]
      test/test_10_nvmefc.py ..............                                                               [100%]
      
      =========================================== 400 passed in 1.49s ===========================================


The code coverage could be also measured and displayed during the test execution:


      $ pytest --cov=test --cov=src
      =========================================== test session starts ===========================================
      platform linux -- Python 3.14.3, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 400 items                                                                                       
      
      test/test_01_log.py ............................................................................... [ 19%]
      ..........................                                                                          [ 26%]
      test/test_02_ipmi.py .......................................................................        [ 44%]
      test/test_03_fancontroller.py .................................................                     [ 56%]
      test/test_04_cpufc.py .....................                                                         [ 61%]
      test/test_05_hdfc.py ...........................................................................    [ 80%]
      test/test_06_gpufc.py ..............                                                                [ 83%]
      test/test_07_constfc.py .................                                                           [ 88%]
      test/test_08_service.py .................................                                           [ 96%]
      test/test_09_cmd.py .                                                                               [ 96%]
      test/test_10_nvmefc.py ..............                                                               [100%]
      
      ---------- coverage: platform linux, python 3.14.3-final-0 -----------
      Name                            Stmts   Miss  Cover
      ---------------------------------------------------
      src/smfc/__init__.py               11      0   100%
      src/smfc/cmd.py                     4      0   100%
      src/smfc/constfc.py                46      0   100%
      src/smfc/cpufc.py                  34      0   100%
      src/smfc/fancontroller.py         127      0   100%
      src/smfc/gpufc.py                  58      0   100%
      src/smfc/hdfc.py                  143      0   100%
      src/smfc/ipmi.py                  130      0   100%
      src/smfc/log.py                    57      0   100%
      src/smfc/nvmefc.py                 47      0   100%
      src/smfc/service.py               160      0   100%
      test/__init__.py                    0      0   100%
      test/test_00_data.py              134      0   100%
      test/test_01_log.py                52      0   100%
      test/test_02_ipmi.py              247      0   100%
      test/test_03_fancontroller.py     134      0   100%
      test/test_04_cpufc.py             142      0   100%
      test/test_05_hdfc.py              293      0   100%
      test/test_06_gpufc.py             111      0   100%
      test/test_07_constfc.py            67      0   100%
      test/test_08_service.py           303      0   100%
      test/test_09_cmd.py                 9      0   100%
      test/test_10_nvmefc.py            144      0   100%
      ---------------------------------------------------
      TOTAL                            2453      0   100%
      
      
      =========================================== 400 passed in 2.37s ===========================================


For a more detailed HTML coverage report run this command:

	$ pytest --cov=src --cov=test --cov-report=html

The detailed HTML report will be available in folder `htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage is 100%.  


# GitHub

## Github workflow
The project implemented the following GitHub workflows:

1. Unit test and lint execution (`test.yml`). A commit can trigger this action:
   * executes unit test on `ubuntu-latest` OS and on Python versions `3.10`, `3.11`, `3.12`, `3.13`, `3.14`
   * executes `pylint` and `ruff`
   * generates coverage data and upload it to [codecov.io](https://codecov.io/)

2. Publish Python distribution packages to PyPI (`publish.yml`). A published release triggers this action:
   * build distribution package on Python `3.13`
   * upload the new package to PyPI


# Release process

## Creation of a new GitHub release
Follow these steps to create a new release:

* Change the version number in `pyproject.toml` and `./doc/smfc.1` files
* Run `uv sync` for updating version number in `uv.lock` file
* Commit all changes
* Run unit tests with `pytest`, and correct all errors
* Run linters `pylint` and `ruff`, and correct all warnings
* Update CHANGELOG.md with the new release information
* Commit all changes and test again
* Create a new release on GitHub with the same version number, and the new package will be published on PyPI automatically
* Build new images for docker and upload them

## Building and uploading of Docker images
After publishing an `smfc` release, the docker image could be built and uploaded. 
The docker images can be built locally in the project root folder:

```commandline
./docker/docker-build.sh 4.1.0 latest
```
Notes:
- Please note that the dockerfile will install `smfc` from `pypi.org`, so the version must refer an official `smfc` release.
- The build script will generate the following tags: `4.1.0`, `latest`, `4.1.0-gpu`, `latest-gpu`.

The generated docker images can be uploaded to [hub.docker.com](https://hub.docker.com/r/petersulyok/smfc)
in the following way:

```commandline
./docker/docker-push.sh 4.1.0 latest
./docker/docker-push.sh 4.1.0-gpu latest-gpu
```

> Written with [StackEdit](https://stackedit.io/).
