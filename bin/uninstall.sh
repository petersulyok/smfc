#!/usr/bin/env bash
#
#   uninstall.sh (C) 2021-2025, Peter Sulyok
#   Uninstallation script for `smfc` service.
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


function remove_file() {
  # Remove existing files only.
  if [ -f $1 ]; then
    rm $1
  fi
}


# Postfix extension for backup files.
POST_TAG=$(date +%4Y%m%d_%H%M%S)

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

# Remove smfc files.
remove_file /etc/default/smfc
remove_file /etc/systemd/system/smfc.service
remove_file /usr/share/man/man1/smfc.1.gz
remove_file /usr/local/share/man/man1/smfc.1.gz
verbose_echo "smfc files removed."

# Remove config file.
if [ -z "${KEEP_CONFIG}" ]; then
  remove_file /etc/smfc/smfc.conf
  verbose_echo "smfc config file removed."
fi

# Remove smfc package with pip.
PIP_PARAM="-y -q --root-user-action=ignore --break-system-packages"
pip uninstall $PIP_PARAM smfc
verbose_echo "pip removed smfc package."

verbose_echo "smfc uninstalled successfully."
