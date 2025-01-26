#!/bin/bash
#
#   install.sh (C) 2021-2025, Peter Sulyok
#   Installation script for smfc service.
#

TARGET_DIR=/opt/smfc
POSTFIX=$(date +%4Y%m%d_%H%M%S)

# Must be executed with root privileges.
if [[ $EUID -ne 0 ]]; then
  echo "$0: Error - must be executed with superuser privileges!"
  exit 1
fi

# Display help text.
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
  echo "usage: $(basename $0) -h --help --keep-config"
  echo "           -h, --help      help text"
  echo "           --keep-config   keep the original configuration file"
  exit 0
fi

# Backup original files.
if [ -f "$TARGET_DIR/smfc.py" ]; then
  cp "$TARGET_DIR/smfc.py" "$TARGET_DIR/smfc.py.$POSTFIX"
  if [ "$1" != "--keep-config" ]; then
    cp "$TARGET_DIR/smfc.conf" "$TARGET_DIR/smfc.conf.$POSTFIX"
  fi
fi

# Create the target folder if does not exist.
if [ ! -d "$TARGET_DIR" ]; then
  mkdir $TARGET_DIR
fi

# Check if the source files are downloaded to the current folder.
if [ ! -f "./src/smfc.py" ]; then
  echo "Installation error: smfc files are missing (try to download/clone smfc first)."
  exit 1
fi
# Copy new files to the target folders
cp ./src/smfc.py "$TARGET_DIR/"
cp ./bin/hddtemp_emu.sh "$TARGET_DIR/"
if [ "$1" != "--keep-config" ]; then
  cp ./src/smfc.conf "$TARGET_DIR/"
  chown root:root "$TARGET_DIR/smfc.py"
fi
cp ./src/smfc /etc/default/
cp ./src/smfc.service /etc/systemd/system/
chown root:root "$TARGET_DIR/smfc.py" "$TARGET_DIR/hddtemp_emu.sh" /etc/default/smfc /etc/systemd/system/smfc.service

# Collect all disk names to hd_names= entry in the new 'smfc.conf'.
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
