# Check `smfc` program and the test directory.

# Check if `smfc` command is available
c=$(command -v smfc|echo $?)
if [ "$c" != "0" ]; then
    echo "ERROR: smfc cannot be executed."
    echo "       (pip install -e .)"
    exit -1
fi

# Check if `test` directory exists.
test_dir=./test
if [ ! -d "$test_dir" ]; then
    echo "ERROR: Test cannot be executed from an unknown folder."
    exit -1
fi
