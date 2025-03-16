#!/usr/bin/env bash
#
#   create_python_env.sh (C) 2025, Peter Sulyok
#   This script will create a new virtual Python environment and will install all dependencies.
#

# Check the first command-line parameter.
if [ "$1" = "" ];
then
    echo "Use: $(basename $0) 3.12.1"
    exit 1
fi

if [ "$PYENV_ROOT" = "" ];
then
    echo "Error: pyenv must be installed first."
    exit 1
fi

# Install the specified python version if it hasn't been already installed.
python_version=$(pyenv version --bare|grep $1)
if [[ "$python_version" = "" || "$?" = "1" ]];
then
    pyenv install $1
    if [[ "$?" -ne "0" ]];
    then
        echo "Error: pyenv cannot install Python $1."
        exit 1
    fi
fi
python_version=$1

# Select the python version locally.
pyenv local $python_version

# Create and activate a virtual environment (activation scope is only this script).
python -m venv .venv-$python_version
source .venv-$python_version/bin/activate

# Upgrade pip and install required python modules.
pip install --upgrade pip
pip install -r requirements-dev.txt
if [ -f docs/requirements-docs.txt ]; 
then
    pip install -r docs/requirements-docs.txt
fi

# Notify user about required action.
echo ""
echo "Activate your new virtual Python environment!"
echo "-> source .venv-$python_version/bin/activate"
exit 0
