# Development
This project is using `uv` for Python project management, see more details about [installation of `uv`](https://docs.astral.sh/uv/getting-started/installation/).
`uv` can provide everything that multiple tools (e.g. `pip`, `pyenv`, `venv`) provide, but much faster. For example:

* install a Python run-time: `uv python install 3.13`
* use a specific Python version: `uv python pin 3.13`
* create virtual Python environment: `uv venv`
* install all dependencies: `uv sync`

`uv` has a lock file (`uv.lock`) storing all dependencies, this should be part of version control.

Building a development environment from scratch (with Python 3.12) contains the following steps:

      pipx install uv
      pipx ensurepath
      git clone https://github.com/petersulyok/smfc.git
      uv python install 3.12
      uv python pin 3.12
      uv sync
      source .venv/bin/activate

Dependencies are listed in `pyproject.toml` file and the proper version numbers are handled by `uv`:

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


## Linting
The code can be checked with `pylint` and `ruff`. `pylint` can be executed this way:

	pylint src test

`ruff` can be executed this way:

    ruff check

# Testing  
This chapter describes the test environment of `smfc` project.  
Important notes:  
  
* All test related content can be found in `test` folder
* Only `python3` and `bash` are required for the execution of the tests (was tested on Linux, macOS), all external commands `ipmitool` and `smartctl` are substituted by scripts
* Test are executed by `pytest`
* All development dependencies (defined in `pyproject.toml`) will be installed after the execution of these commands:


      uv sync
      source .venv/bin/activate


## Smoke tests  
Several smoke tests have been provided for `smfc` where the service is executed with different configuration files. Notes:  
  
* all smoke tests should be executed from the project root folder and can be stopped by pressing `CTLR+C`:

	`$ ./test/run_test_cpu_1.sh`

* the following smoke scripts and zone configurations can be executed:  
   
   | Test script               | CPU zone  | HD zone  | GPU zone  | CONST zone | Standby guard |
   |---------------------------|-----------|----------|-----------|------------|---------------|
   | `run_test_cpu_1.sh`       | 1 x CPU   | 1 x HD   | disabled  | enabled    | enabled       |
   | `run_test_cpu_2.sh`       | 2 x CPUs  | disabled | 1 GPU     | disabled   | disabled      |
   | `run_test_cpu_4.sh`       | 4 x CPUs  | 4 x HDs  | 4 GPUs    | disabled   | enabled       |
   | `run_test_hd_1.sh`        | disabled  | 1 x HD   | disabled  | enabled    | enabled       |
   | `run_test_hd_2.sh`        | 1 x CPU   | 2 x HDs  | disabled  | disabled   | disabled      |
   | `run_test_hd_4.sh`        | disabled  | 4 x HDs  | 2 GPUs    | disabled   | disabled      |
   | `run_test_hd_8.sh`        | 4 x CPUs  | 8 x HDs  | disabled  | disabled   | enabled       |
   | `run_test_const_level.sh` | disabled  | disabled | disabled  | enabled    | enabled       |
   | `run_test_gpu_8.sh`       | 1 x CPU   | disabled | 8 GPUs    | enabled    | disabled      |

## Unit tests  
The whole project (all source code) is completely unit tested. The unit tests are executed with `pytest`:


      $ pytest
      ========================================================================================== test session starts ===========================================================================================
      platform linux -- Python 3.13.7, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 382 items                                                                                                                                                                                      
        
      test/test_01_log.py .........................................................................................................                                                                      [ 27%]
      test/test_02_ipmi.py .......................................................................                                                                                                       [ 46%]
      test/test_03_fancontroller.py .................................................                                                                                                                    [ 58%]
      test/test_04_cpuzone.py .....................                                                                                                                                                      [ 64%]
      test/test_05_hdzone.py .........................................................................                                                                                                   [ 83%]
      test/test_06_gpuzone.py ..............                                                                                                                                                             [ 87%]
      test/test_07_constzone.py .................                                                                                                                                                        [ 91%]
      test/test_08_service.py ...............................                                                                                                                                            [ 99%]
      test/test_09_cmd.py .                                                                                                                                                                              [100%]
        
      ========================================================================================== 382 passed in 1.32s ===========================================================================================
	

The code coverage could be also measured and displayed during the test execution:


      $ pytest --cov=src --cov=test
      ========================================================================================== test session starts ===========================================================================================
      platform linux -- Python 3.13.7, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 382 items                                                                                                                                                                                      
        
      test/test_01_log.py .........................................................................................................                                                                      [ 27%]
      test/test_02_ipmi.py .......................................................................                                                                                                       [ 46%]
      test/test_03_fancontroller.py .................................................                                                                                                                    [ 58%]
      test/test_04_cpuzone.py .....................                                                                                                                                                      [ 64%]
      test/test_05_hdzone.py .........................................................................                                                                                                   [ 83%]
      test/test_06_gpuzone.py ..............                                                                                                                                                             [ 87%]
      test/test_07_constzone.py .................                                                                                                                                                        [ 91%]
      test/test_08_service.py ...............................                                                                                                                                            [ 99%]
      test/test_09_cmd.py .                                                                                                                                                                              [100%]
        
      ---------- coverage: platform linux, python 3.13.7-final-0 -----------
      Name                            Stmts   Miss  Cover
      ---------------------------------------------------
      src/smfc/__init__.py               10      0   100%
      src/smfc/cmd.py                     4      0   100%
      src/smfc/constzone.py              47      0   100%
      src/smfc/cpuzone.py                34      0   100%
      src/smfc/fancontroller.py         147      0   100%
      src/smfc/gpuzone.py                62      0   100%
      src/smfc/hdzone.py                148      0   100%
      src/smfc/ipmi.py                  136      0   100%
      src/smfc/log.py                    60      0   100%
      src/smfc/service.py               159      0   100%
      test/__init__.py                    0      0   100%
      test/test_00_data.py              116      0   100%
      test/test_01_log.py                52      0   100%
      test/test_02_ipmi.py              247      0   100%
      test/test_03_fancontroller.py     134      0   100%
      test/test_04_cpuzone.py           142      0   100%
      test/test_05_hdzone.py            277      0   100%
      test/test_06_gpuzone.py           111      0   100%
      test/test_07_constzone.py          67      0   100%
      test/test_08_service.py           266      0   100%
      test/test_09_cmd.py                 9      0   100%
      ---------------------------------------------------
      TOTAL                            2228      0   100%
       
      ========================================================================================== 382 passed in 1.52s ===========================================================================================

For a more detailed HTML coverage report run this command:

	$ pytest --cov=src --cov=test --cov-report=html

The detailed HTML report will be available in folder `htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage is 100%.  


# GitHub


## Github workflow
The project implemented the following GitHub workflows:

1. Unit test and lint execution (`test.yml`). A commit can trigger this action:
   * executes unit test on `ubuntu-latest` OS and on Python versions `3.9`, `3.10`, `3.11`, `3.12`, `3.13`
   * executes `pylint` and `ruff`
   * generates coverage data and upload it to [codecov.io](https://codecov.io/)

2. Publish Python distribution packages to PyPI (`publish.yml`). A published release triggers this action:
   * build distribution package on Python `3.13`
   * upload the new package to PyPI


# Release process
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

> Written with [StackEdit](https://stackedit.io/).
