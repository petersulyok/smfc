
# Testing  
Short summary about test environment of `smfc` project.  
Notes:  
  
 - All test related content can be found in `test` folder
 - Only `python3` and `bash` are required for the execution of the tests (was tested on Linux, MacOSX)  
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, so they are not required for test execution
  
## Smoke tests  
Several smoke tests are provided for `smfc` where the service is executed with different configuration parameters. Notes:  
  
- all smoke tests should be executed from the project root folder and can be stopped by pressing `CTLR+C`:

	`#./test/run_test_cpu_1.sh`

- the following smoke scripts and configurations are available:  
   
   | Helper script | CPU configuration | HD configuration | Standby guard |
   |--|--|--|--|
   |`run_test_cpu_1.sh`| 1 x CPU | 1 x HD | enabled |
   |`run_test_cpu_2.sh`| 2 x CPUs | disabled | disabled |
   |`run_test_cpu_4.sh`| 4 x CPUs | 4 x HDs | enabled |
   |`run_test_hd_1.sh`| disabled | 1 x HD | enabled |
   |`run_test_hd_2.sh`| 1 x CPU | 2 x HDs | disabled |
   |`run_test_hd_4.sh`| 2 x CPUs | 4 x HDs | disabled |
   |`run_test_hd_8.sh`| 4 x CPUs | 8 x HDs | enabled |
   |`run_test_const_level.sh`| 1 x CPU (60% constant fan level) | 4 x HDs (55% constant fan level) | enabled |

## Unit tests  
All classes and the main function are completely unit tested. The unit tests can be executed with `pytest`. It can be installed with `pip`:

	pip install pytest pytest-cov
	pytest

The code coverage could be also measured and displayed during the test execution:

	pytest --cov=src --cov=test

For a more detailed HTML coverage report run this command:

	pytest --cov=src --cov=test --cov-report=html

The detailed HTML report will be available in folder `./htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage result is 98%.  

## Github workflow
A github workflow implemented for this project that will be executed for all pushes and pull requests. The workflow contains the following steps:

 - lint with `flake8` and `pylint`
 - unit test with `pytest` (coverage measurement is included)

The workflow is executed on the following test matrix:

 - OS: `ubuntu-latest`
 - Python version: `3.7`, `3.8`, `3.9`, `3.10`, `3.11-rc.1`
 
> Written with [StackEdit](https://stackedit.io/).
