
# Testing  
Short summary about testing environment of `smfc` project.  
Notes:  
  
 - All test related content can be found in `test` folder
 - Only `python3` and `bash` are needed for the execution of the tests (was tested on Linux, MacOSX)  
 - commands `ipmitool` and `smartctl`are substituted by shell scripts, they are not required for running tests
  
## Smoke tests  
Several smoke tests are provided for `smfc` where the service is executed with different configuration parameters. Notes:  
  
- all smoke tests should be executed from the project folder and can be stopped by pressing `CTLR+C`:

	`#./test/run_test_cpu_1.sh`

- the following smoke scripts and configurations are available:  
   
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
All classes and the main function are completely unit tested. They can be executed from both the project and the test folders with the help of a shell script:

	./run_unittest.sh
	./test/run_unittest.sh

The coverage can be also measured for the unit tests (a python package called `coverage` should be installed)  

	pip3 install coverage
	./run_coverage.sh  

Coverage will generate a detailed HTML report (see `./htmlcov/index.html`) with coverage statistics and showing the covered and non-covered lines in the source code. The actual coverage report is 98%.  
  
> Written with [StackEdit](https://stackedit.io/).
