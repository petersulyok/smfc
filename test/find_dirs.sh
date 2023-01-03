# Find source and test directories and prepare smoke test and unit test execution.

# Case 1: we are in root project directory.
src_dir=./src
if [ -d "$src_dir" ]; then
    export PYTHONPATH=$PYTHONPATH:$src_dir
    test_dir=./test
else
    # Case 2: we are in src directory.
    if [ -f "./smfc.py" ]; then
        src_dir=.
        test_dir=../test
    else
        # Case 3: we are in test directory.
        if [ -d "bin" ]; then
            src_dir=../src
            export PYTHONPATH=$PYTHONPATH:$src_dir
            test_dir=.
        else
            echo "ERROR: Test cannot be executed from an unknown folder."
            exit -1
        fi
    fi
fi
