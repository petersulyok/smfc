
# Testing  
Short summary about testing environment of `smfc` project.  
Notes:  
  
 - All tests can be executed in the root of the project directory  
 - Only `python3` and `bash` are needed for the execution of the tests (was tested on Linux, MacOSX)  
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, they are not required for running tests
  
## Smoke tests  
Several smoke tests are included in the `smfc` project to test the service with different configuration parameters. Notes:  
  
- they can be executed with the help of the following scripts in the project folder and can be stopped by pressing `CTLR+C`  
- all test data, configuration, and further scripts can be found in the following folders:  
   
   |Helper script|Configuration|
   |--|--|
   |`run_test_cpu_1.sh`| 1 x CPU |
   |`run_test_cpu_2.sh`| 2 x CPU |
   |`run_test_cpu_4.sh`| 2 x CPU |
   |`run_test_hd_1.sh`| 1 x HD |
   |`run_test_hd_2.sh`| 2 x HD |
   |`run_test_hd_4.sh`| 4 x HD |
   |`run_test_hd_8.sh`| 8 x HD | 
   |`run_test_const_level.sh`| constant fan output level |  

## Unit tests  
All classes and the main function are completely unit tested. These tests can be found in `./test/` folder. They can be executed in the project folder with the help of a shell script:

	./run_unittest.sh

You can also measure the coverage of the unit tests (a python package called `coverage` should be installed for this)  

	pip3 install coverage
	./run_coverage.sh  

Coverage will generate a detailed HTML report (see `./htmlcov/index.html`) with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage report is 98%.  
  
> Written with [StackEdit](https://stackedit.io/).
