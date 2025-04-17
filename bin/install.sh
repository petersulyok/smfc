#!/usr/bin/env bash
#
#   install.sh (C) 2021-2025, Peter Sulyok
#   Installation script for `smfc` service.
#
set -e

# Postfix extension for backup files.
POST_TAG=$(date +%4Y%m%d_%H%M%S)

# Must be executed with root privileges.
if [[ $EUID -ne 0 ]]; then
  echo "$0: Error - must be executed with root privileges!"
  exit 1
fi

# Display help text.
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
  echo "usage: $(basename $0) -h --help --keep-config"
  echo "           -h, --help      help text"
  echo "           --keep-config   keep the original configuration file"
  exit 0
fi

# Install `smfc` package from Pypi.org
pip install -q --prefix=/usr smfc

# Install configuration file.
TARGET_DIR=/etc/smfc
# Create the target folder if does not exist.
if [ ! -d "$TARGET_DIR" ]; then
  mkdir $TARGET_DIR
fi
# Backup configuration file if needed.
if [ "$1" != "--keep-config" ]; then
  cp "$TARGET_DIR/smfc.conf" "$TARGET_DIR/smfc.conf.$POST_TAG"
  curl --silent -o "$TARGET_DIR/smfc.conf" https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/config/smfc.conf
fi

# Install systemd service files.
curl --silent -o "/etc/default/smfc" https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/config/smfc
curl --silent -o "/etc/systemd/system/smfc.service" https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/config/smfc.service

# Collect all disk names for `hd_names=` parameter in case of a 'smfc.conf' file.
if [ "$1" != "--keep-config" ]; then
  hd_list=$(ls /dev/disk/by-id/|grep -v -E ".*-part.$"|grep -v -E ".*_1$")
  if [ -n "$hd_list" ];
  then
    hd_names=""
    for hl in $hd_list; do
      hd_names+="/dev/disk/by-id/$hl\n\t"
    done
    sed -i "s|hd_names=|hd_names=$hd_names|g" "$TARGET_DIR/smfc.conf"
  fi
fi

echo "Installation finished successfully."
