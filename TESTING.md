
# Testing  
Short summary about test environment of `smfc` project.  
Notes:  
  
 - All test related content can be found in `test` folder
 - Only `python3` and `bash` are required for the execution of the tests (was tested on Linux, MacOSX)  
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, so they are not required for test execution
- installation of required Python test tools can be done with `pip`:  

	`$ pip install -r requirements-dev.txt`

 
## Smoke tests  
Several smoke tests are provided for `smfc` where the service is executed with different configuration parameters. Notes:  
  
- all smoke tests should be executed from the project root folder and can be stopped by pressing `CTLR+C`:

	`$ ./test/run_test_cpu_1.sh`

- the following smoke scripts and configurations are available:  
   
   | Helper script             | CPU configuration                | HD configuration                    | Standby guard |
   |---------------------------|----------------------------------|-------------------------------------|--|
   | `run_test_cpu_1.sh`       | 1 x CPU                          | 1 x HD                              | enabled |
   | `run_test_cpu_2.sh`       | 2 x CPUs                         | disabled                            | disabled |
   | `run_test_cpu_4.sh`       | 4 x CPUs                         | 4 x HDs                             | enabled |
   | `run_test_hd_1.sh`        | disabled                         | 1 x HD                              | enabled |
   | `run_test_hd_2.sh`        | 1 x CPU                          | 2 x HDs                             | disabled |
   | `run_test_hd_4.sh`        | 2 x CPUs                         | 4 x HDs                             | disabled |
   | `run_test_hd_8.sh`        | 4 x CPUs                         | 8 x HDs                             | enabled |
   | `run_test_const_level.sh` | 1 x CPU (60% constant fan level) | 4 x HDs (55% constant fan level)    | enabled |
   | `run_test_scsi.sh`        | 4 x CPU                          | 8 x HDs (SCSI and SATA disks mixed) | enabled |

## Unit tests  
All classes and the main function are completely unit tested. The unit tests can be executed with `pytest`:

	$ pytest
	============================= test session starts ==============================
	platform linux -- Python 3.11.1, pytest-7.2.0, pluggy-1.0.0
	rootdir: /home/petersulyok/git/github/smfc, configfile: pyproject.toml
	plugins: cov-4.0.0
	collected 23 items                                                             

	test/test_01_log.py ....                                                 [ 17%]
	test/test_02_ipmi.py .....                                               [ 39%]
	test/test_03_fancontroller.py .....                                      [ 60%]
	test/test_04_cpuzone.py ..                                               [ 69%]
	test/test_05_hdzone.py ......                                            [ 95%]
	test/test_06_main.py .                                                   [100%]
	
	============================== 23 passed in 0.46s ==============================

The code coverage could be also measured and displayed during the test execution:

	$ pytest --cov=src --cov=test
	============================= test session starts ==============================
	platform linux -- Python 3.11.1, pytest-7.2.0, pluggy-1.0.0
	rootdir: /home/petersulyok/git/github/smfc, configfile: pyproject.toml
	plugins: cov-4.0.0
	collected 23 items                                                             
	
	test/test_01_log.py ....                                                 [ 17%]
	test/test_02_ipmi.py .....                                               [ 39%]
	test/test_03_fancontroller.py .....                                      [ 60%]
	test/test_04_cpuzone.py ..                                               [ 69%]
	test/test_05_hdzone.py ......                                            [ 95%]
	test/test_06_main.py .                                                   [100%]
	
	---------- coverage: platform linux, python 3.11.1-final-0 -----------
	Name                            Stmts   Miss  Cover
	---------------------------------------------------
	src/smfc.py                       497     11    98%
	test/test_00_data.py              137      1    99%
	test/test_01_log.py               124      0   100%
	test/test_02_ipmi.py              211      0   100%
	test/test_03_fancontroller.py     278      0   100%
	test/test_04_cpuzone.py           154      0   100%
	test/test_05_hdzone.py            386      0   100%
	test/test_06_main.py               81      0   100%
	---------------------------------------------------
	TOTAL                            1868     12    99%
	
	
	============================== 23 passed in 0.69s ==============================

For a more detailed HTML coverage report run this command:

	$ pytest --cov=src --cov=test --cov-report=html

The detailed HTML report will be available in folder `./htmlcov/index.html` with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage result is 99%.  

## Linting
The code was checked with `pylint` and `flake8`. They can be executed this way:

	pylint src/*.py test/*.py
	flake8

## Github workflow
A github workflow has been implemented for this project that is executed in case of push and pull request operations. The workflow contains the following steps:

 - lint with `flake8` and `pylint`
 - unit test with `pytest` (coverage measurement is also included)

The workflow is executed on the following test matrix:

 - OS: `ubuntu-latest`
 - Python version: `3.7`, `3.8`, `3.9`, `3.10`, `3.11`, `3.12` 
 
> Written with [StackEdit](https://stackedit.io/).
