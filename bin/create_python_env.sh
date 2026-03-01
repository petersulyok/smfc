#!/bin/sh
#
#   create_python_env.sh (C) 2024-2026, Peter Sulyok
#   This script will create a new virtual Python environment and will install all dependencies.
#

# Show help and exit if -h is given or more than one argument is provided.
if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ "$#" -gt 1 ]; then
    echo "Usage: $(basename "$0") [PYTHON_VERSION]"
    echo ""
    echo "  Creates a virtual Python environment and installs all dependencies."
    echo ""
    echo "Arguments:"
    echo "  PYTHON_VERSION  Python version to install and pin (default: 3.14)"
    echo ""
    echo "Options:"
    echo "  -h, --help      Show this help message and exit"
    echo ""
    echo "Examples:"
    echo "  $(basename "$0")         # uses Python 3.14"
    echo "  $(basename "$0") 3.12    # uses Python 3.12"
    exit 0
fi

# Step 1: Check if uv can be executed; install it from astral.sh if not.
if ! command -v uv > /dev/null 2>&1; then
    echo "uv is not installed, installing it from astral.sh..."

    # Step 1.2: Verify curl is available before attempting download.
    if ! command -v curl > /dev/null 2>&1; then
        echo "Error: curl is not installed, cannot download the uv installer."
        exit 1
    fi

    # Step 1.1: Run the official uv install script.
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "Error: uv installation script failed."
        exit 1
    fi

    # Make uv available in the current shell session.
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *)
            export PATH="$HOME/.local/bin:$PATH"

            if ! grep -q '\.local/bin' "$HOME/.profile" 2>/dev/null; then
                cat >> "$HOME/.profile" <<'PROFILE'

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
PROFILE
            fi
            ;;
    esac

    if ! command -v uv > /dev/null 2>&1; then
        echo "Error: uv was installed but cannot be executed; check your PATH."
        exit 1
    fi
fi

# Step 2: Use the Python version from $1 or fall back to the default.
python_version=${1:-3.14}

# Install the requested Python version.
if ! uv python install "$python_version"; then
    echo "Error: uv cannot install Python $python_version."
    exit 1
fi

# Step 2.2: Pin the Python version for this project.
if ! uv python pin "$python_version"; then
    echo "Error: uv cannot pin Python $python_version."
    exit 1
fi

# Step 3: Sync dependencies and create the local build.
if ! uv sync; then
    echo "Error: uv sync failed."
    exit 1
fi

if ! uv build; then
    echo "Error: uv build failed."
    exit 1
fi

# Step 4: Hint for the user on how to activate the virtual environment.
echo ""
echo "Activate your new virtual Python environment:"
echo "  bash:  source .venv/bin/activate"
echo "  zsh:   source .venv/bin/activate"
echo "  sh:    . .venv/bin/activate"
exit 0
