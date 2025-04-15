
# Testing  
Short summary about test environment of `smfc` project.  
Notes:  
  
 - All test related content can be found in `test` folder
 - Only `python3` and `bash` are required for the execution of the tests (was tested on Linux, macOS), commands `ipmitool` and `smartctl` are substituted by shell scripts, so they are not required for test execution
 - Python testing tools should be installed with `pip`:  

	`$ pip install -r requirements-dev.txt`

 
## Smoke tests  
Several smoke tests have been provided for `smfc` where the service is executed with different configuration parameters. Notes:  
  
- all smoke tests should be executed from the project root folder and can be stopped by pressing `CTLR+C`:

	`$ ./test/run_test_cpu_1.sh`

- the following smoke scripts and configurations can be executed:  
   
   | Test script              | CPU configuration                | HD configuration                    | Standby guard |
   |---------------------------|----------------------------------|-------------------------------------|---------------|
   | `run_test_cpu_1.sh`       | 1 x CPU                          | 1 x HD                              | enabled       |
   | `run_test_cpu_2.sh`       | 2 x CPUs                         | disabled                            | disabled      |
   | `run_test_cpu_4.sh`       | 4 x CPUs                         | 4 x HDs                             | enabled       |
   | `run_test_hd_1.sh`        | disabled                         | 1 x HD                              | enabled       |
   | `run_test_hd_2.sh`        | 1 x CPU                          | 2 x HDs                             | disabled      |
   | `run_test_hd_4.sh`        | 2 x CPUs                         | 4 x HDs                             | disabled      |
   | `run_test_hd_8.sh`        | 4 x CPUs                         | 8 x HDs                             | enabled       |
   | `run_test_const_level.sh` | 1 x CPU (60% constant fan level) | 4 x HDs (55% constant fan level)    | enabled       |

## Unit tests  
The whole project (all source code) is completely unit tested. The unit tests are executed with `pytest`:


      $ pytest
      ================================================= test session starts ==================================================
      platform linux -- Python 3.9.21, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 344 items                                                                                                    
      
      test/test_01_log.py ............................................................................................ [ 26%]
      .............                                                                                                    [ 30%]
      test/test_02_ipmi.py ..........................................................................                  [ 52%]
      test/test_03_fancontroller.py .......................................                                            [ 63%]
      test/test_04_cpuzone.py .....................                                                                    [ 69%]
      test/test_05_hdzone.py .........................................................................                 [ 90%]
      test/test_06_service.py ...............................                                                          [ 99%]
      test/test_07_cmd.py .                                                                                            [100%]
      
      ================================================= 344 passed in 2.24s =================================================


The code coverage could be also measured and displayed during the test execution:


      $ pytest --cov=src --cov=test
      ================================================= test session starts ==================================================
      platform linux -- Python 3.9.21, pytest-8.3.5, pluggy-1.5.0
      rootdir: /home/petersulyok/git/github/smfc
      configfile: pyproject.toml
      plugins: cov-6.0.0, mock-3.14.0
      collected 344 items                                                                                                    
      
      test/test_01_log.py ............................................................................................ [ 26%]
      .............                                                                                                    [ 30%]
      test/test_02_ipmi.py ..........................................................................                  [ 52%]
      test/test_03_fancontroller.py .......................................                                            [ 63%]
      test/test_04_cpuzone.py .....................                                                                    [ 69%]
      test/test_05_hdzone.py .........................................................................                 [ 90%]
      test/test_06_service.py ...............................                                                          [ 99%]
      test/test_07_cmd.py .                                                                                            [100%]
      
      ---------- coverage: platform linux, python 3.9.21-final-0 -----------
      Name                            Stmts   Miss  Cover
      ---------------------------------------------------
      src/smfc/__init__.py                8      0   100%
      src/smfc/cmd.py                     4      0   100%
      src/smfc/cpuzone.py                33      0   100%
      src/smfc/fancontroller.py         144      0   100%
      src/smfc/hdzone.py                147      0   100%
      src/smfc/ipmi.py                  120      0   100%
      src/smfc/log.py                    60      0   100%
      src/smfc/service.py               125      0   100%
      test/__init__.py                    0      0   100%
      test/test_00_data.py              107      0   100%
      test/test_01_log.py                52      0   100%
      test/test_02_ipmi.py              209      0   100%
      test/test_03_fancontroller.py     129      0   100%
      test/test_04_cpuzone.py           142      0   100%
      test/test_05_hdzone.py            273      0   100%
      test/test_06_service.py           229      0   100%
      test/test_07_cmd.py                 9      0   100%
      ---------------------------------------------------
      TOTAL                            1791      0   100%
      
      
      ================================================= 344 passed in 2.62s ==================================================


For a more detailed HTML coverage report run this command:

	$ pytest --cov=src --cov=test --cov-report=html

The detailed HTML report will be available in folder `htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage is 100%.  

## Linting
The code was checked with `pylint`. This linter can be executed this way:

	pylint src test

## Github workflow
A github workflow has been implemented for this project that is executed in case of push and pull request operations. The workflow contains the following steps:

 - lint with `pylint`
 - unit test with `pytest` (coverage measurement is also included)

The workflow is executed on the following test matrix:

 - OS: `ubuntu-latest`
 - Python version: `3.9`, `3.10`, `3.11`, `3.12`, `3.13`  
 
> Written with [StackEdit](https://stackedit.io/).
