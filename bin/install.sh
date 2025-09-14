#!/usr/bin/env bash
#
#   install.sh (C) 2021-2025, Peter Sulyok
#   Installation script for `smfc` service.
#
set -e


function print_help() {
  echo "usage: $(basename $0) [-h|--help] [-k|--keep-config] [-l|--local] [-v|--verbose]"
  echo "           -h, --help         help text"
  echo "           -k, --keep-config  keep original configuration file"
  echo "           -l, --local        installation from a local git repository"
  echo "           -v, --verbose      verbose output"

  exit 0
}


function verbose_echo() {
  if [ -n "${VERBOSE}" ]; then
    echo "$1"
  fi
}


function new_configuration() {
  # Install a new configuration file (if the old one should not be preserved)
  if [ -z "${KEEP_CONFIG}" ]; then
    # Backup the old existing configuration file.
    if [ -f /etc/smfc/smfc.conf ]; then
      cp /etc/smfc/smfc.conf /etc/smfc/smfc.conf.$POST_TAG
      verbose_echo "Original configuration file saved (/etc/smfc/smfc.conf.$POST_TAG)."
    fi
    # Execute installation command (parameter)
    $1
    verbose_echo "New configuration file installed (/etc/smfc/smfc.conf)."
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
    -l|--local)
      LOCAL_INSTALL="yes"
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

# Create the configuration target folder if it does not exist.
if [ ! -d /etc/smfc ]; then
  mkdir -p /etc/smfc
  verbose_echo "/etc/smfc folder created."
fi
# Create the target folder for manual page.
if [ ! -d /usr/share/man/man1 ]; then
  mkdir -p /usr/share/man/man1
  verbose_echo "/usr/share/man/man1 folder created."
fi
# PIP parameters.
PIP_PARAM="-q --root-user-action=ignore --break-system-packages"

# CASE 1: Local installation from the current folder.
if [ "$LOCAL_INSTALL" = "yes" ]; then

  # Display the installation type.
  verbose_echo "Local installation from current folder."

  # Read smfc version from the current folder.
  SMFC_VERSION=$(grep "version = " ./pyproject.toml|cut -d "\"" -f2)
  verbose_echo "smfc version: $SMFC_VERSION."

  # Install smfc package from `./dist` folder
  pip install "./dist/smfc-$SMFC_VERSION.tar.gz"
  verbose_echo "pip installed smfc==$SMFC_VERSION."

  # Install configuration file.
  new_configuration "cp ./config/smfc.conf /etc/smfc/smfc.conf"

  # Install smfc files.
  cp -f ./config/smfc /etc/default/smfc
  cp -f ./config/smfc.service /etc/systemd/system/smfc.service
  cp -f ./doc/smfc.1 /usr/share/man/man1/smfc.1

# CASE 2: Remote installation from GitHub and pypi.
else

  # Display the installation type.
  verbose_echo "Remote installation from GitHub."

  # GitHUb URL
  GITHUB_URL="https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main"

  # Read the smfc version from GitHub.
  SMFC_VERSION=$(curl --silent "$GITHUB_URL/pyproject.toml"|grep "version = "|cut -d "\"" -f2)
  verbose_echo "smfc version from GitHub: $SMFC_VERSION"

  # Install smfc package from Pypi.org
  pip install $PIP_PARAM smfc==$SMFC_VERSION
  verbose_echo "pip installed smfc==$SMFC_VERSION."

  # Install configuration file.
  new_configuration "curl --silent -o /etc/smfc/smfc.conf $GITHUB_URL/config/smfc.conf"

  # Install smfc files.
  curl --silent -o "/etc/default/smfc" "$GITHUB_URL/config/smfc"
  curl --silent -o "/etc/systemd/system/smfc.service" "$GITHUB_URL/config/smfc.service"
  curl --silent -o "/usr/share/man/man1/smfc.1" "$GITHUB_URL/doc/smfc.1"

fi

# Compress manual page.
gzip -f /usr/share/man/man1/smfc.1
mandb > /dev/null 2>&1
chown root:root \
  /etc/smfc/smfc.conf \
  /etc/default/smfc \
  /etc/systemd/system/smfc.service \
  /usr/share/man/man1/smfc.1.gz
verbose_echo "smfc files have been installed."

# Collect all disk names for `hd_names=` parameter in 'smfc.conf' file.
if [ -z "${KEEP_CONFIG}" ]; then
  hd_list=$(ls /dev/disk/by-id/|grep -v -E ".*-part|wwn-|-eui|-nvme|dm-|lvm-|_1+$")
  if [ -n "$hd_list" ]; then
    hd_names=""
    for hl in $hd_list; do
      hd_names+="/dev/disk/by-id/$hl\n\t"
    done
    sed -i "s|^hd_names=|hd_names=$hd_names|g" /etc/smfc/smfc.conf
    verbose_echo "HDD names are listed in the new configuration file (please edit!)."
  fi
fi

verbose_echo "smfc installation finished successfully."
