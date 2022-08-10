
# Testing  
Short summary about testing environment of `smfc` project.  
Notes:  
  
 - All test related content can be found in `test` folder
 - Only `python3` and `bash` are needed for the execution of the tests (was tested on Linux, MacOSX)  
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, they are not required for running tests
  
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
All classes and the main function are completely unit tested. The unit tests can be executed from multiple folders with the help of a shell script:

	./test/run_unittest.sh		# project root folder
	./run_unittest.sh			# test folder
	../test/run_unittest.sh		# src folder

The coverage can be measured for the unit tests (a Python package called `coverage` should be installed). The coverage measurement script can be executed in the same way as unit tests:

	pip3 install coverage
	./run_coverage.sh

Coverage will generate a detailed HTML report (see `./htmlcov/index.html`) with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage report is 98%.  
  
> Written with [StackEdit](https://stackedit.io/).
