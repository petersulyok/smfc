#!/usr/bin/env bash
#
#   install.sh (C) 2021-2025, Peter Sulyok
#   Installation script for `smfc` service.
#
set -e

function print_help() {
  echo "usage: $(basename $0) [-h|--help] [-k|--keep-config] [-v|--verbose]"
  echo "           -h, --help         help text"
  echo "           -k, --keep-config  keep original configuration file"
  echo "           -v, --verbose      verbose output"
  exit 0
}

function verbose_echo() {
  if [ -n "${VERBOSE}" ]; then
    echo "$1"
  fi
}

# Postfix extension for backup files.
POST_TAG=$(date +%4Y%m%d_%H%M%S)
# GitHUb URL
GITHUB_URL="https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main"

# Parsing of command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      print_help
      ;;
    -k|--keep-config)
      KEEP_CONFIG="yes"
      shift # past value
      ;;
    -v|--verbose)
      VERBOSE="yes"
      shift # past value
      ;;
    *)
      # Unknown option
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Must be executed with root privileges.
if [[ $EUID -ne 0 ]]; then
  echo "$(basename $0): Error - must be executed with root privileges!"
  exit 1
fi
verbose_echo "Root privilege granted."

# Red the lastest smfc version from GitHub.
LATEST_VERSION=$(curl --silent "$GITHUB_URL/pyproject.toml"|grep "version = "|cut -d "\"" -f2)
verbose_echo "Latest smfc version from GitHub: $LATEST_VERSION"

# Install latest `smfc` package from Pypi.org
pip install -q --prefix=/usr smfc==$LATEST_VERSION > /dev/null 2>&1
verbose_echo "pip installed smfc==$LATEST_VERSION."

# Install configuration file.
TARGET_DIR=/etc/smfc
# Create the target folder if does not exist.
if [ ! -d "$TARGET_DIR" ]; then
  mkdir -p $TARGET_DIR
  verbose_echo "$TARGET_DIR folder created."
fi
# Backup the old configuration file and install the new one.
if [ -z "${KEEP_CONFIG}" ]; then
  if [ -f "$TARGET_DIR/smfc.conf" ]; then
    cp "$TARGET_DIR/smfc.conf" "$TARGET_DIR/smfc.conf.$POST_TAG"
    verbose_echo "Originial configuration file saved ($TARGET_DIR/smfc.conf.$POST_TAG)."
  fi
  curl --silent -o "$TARGET_DIR/smfc.conf" "$GITHUB_URL/config/smfc.conf"
  verbose_echo "New configuration file installed ($TARGET_DIR/smfc.conf)."
fi

# Install systemd service files.
curl --silent -o "/etc/default/smfc" "$GITHUB_URL/config/smfc"
curl --silent -o "/etc/systemd/system/smfc.service" "$GITHUB_URL/config/smfc.service"
verbose_echo "Systemd files for smfc installed."

# Collect all disk names for `hd_names=` parameter in case of a 'smfc.conf' file.
if [ -z "${KEEP_CONFIG}" ]; then
  hd_list=$(ls /dev/disk/by-id/|grep -v -E ".*-part.$"|grep -v -E ".*_1$")
  if [ -n "$hd_list" ]; then
    hd_names=""
    for hl in $hd_list; do
      hd_names+="/dev/disk/by-id/$hl\n\t"
    done
    sed -i "s|hd_names=|hd_names=$hd_names|g" "$TARGET_DIR/smfc.conf"
    verbose_echo "HDD names are listed in the new configuration file."
  fi
fi

verbose_echo "smfc installation finished."
