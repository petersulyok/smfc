# Testing
Short summary about testing environment of `smfc` project.
Notes:

 - All tests can be executed in the root of the project directory
 - Only `python3` and `bash` are needed for the execution of the tests (was tested on Linux, MacOSX)
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, they are not required for running tests

## Smoke tests
Several smoke tests are included in `smfc` project to check the service with different configurations. Notes:

- they can be started with different helper scripts in the project folder and can be interrupted by pressing `CTLR+C`
- all test data, configuration, and further scripts can be found in the following folders:
 
	|Helper script|Configuration|Test folder|
	|--|--|--|
	|`run_test_hd_2.sh`| 2 x HD |`./test/hd_2/`|
	|`run_test_hd_4.sh`| 4 x HD |`./test/hd_4/`|
	|`run_test_hd_4_constant.sh`| 4 x HD with constant fan output level |`./test/hd_4_constant/`|
	|`run_test_hd_8.sh`| 8 x HD |`./test/hd_8/`|

## Unit tests
All classes and the main function are completely unit tested. These tests can be found in `./test/` folder. They can be executed in the project folder with the help of a shell script:
	
	./run_unittest.sh

You can also measure the coverage of the unit tests (a python package called `coverage` should be installed for this)

	pip3 install coverage
	./run_coverage.sh

Coverage will generate a detailed HTML report (see `./htmlcov/index.html`) with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage report is 98%.

> Written with [StackEdit](https://stackedit.io/).
