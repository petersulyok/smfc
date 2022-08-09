#!/bin/bash

TARGET_DIR=/opt/smfc
POSTFIX=$(date +%4Y%m%d_%H%M%S)

# Must be executed with root privileges.
if [[ $EUID -ne 0 ]]; then
  echo "$0: Error - must be executed with superuser privileges!"
  exit 1
fi

# Backup original files
if [ -f "$TARGET_DIR/smfc.py" ]; then
  cp "$TARGET_DIR/smfc.py" "$TARGET_DIR/smfc.py.$POSTFIX"
  cp "$TARGET_DIR/smfc.conf" "$TARGET_DIR/smfc.conf.$POSTFIX"
fi

# Create the target folder if does not exist
if [ ! -d "$TARGET_DIR" ]; then
  mkdir $TARGET_DIR
fi

# Copy new files to the target folders
cp ./src/smfc.py "$TARGET_DIR/"
cp ./src/smfc.conf "$TARGET_DIR/"
cp ./src/smfc /etc/default/
cp ./src/smfc.service /etc/systemd/system/
chown root.root "$TARGET_DIR/smfc.py" "$TARGET_DIR/smfc.conf" /etc/default/smfc /etc/systemd/system/smfc.service

# Generate a real hd_names= entry in the new 'smfc.conf'.
hd_name = $(ls -l /dev/disk/by-id/|grep .*ata-.*sda$|cut -d ' ' -f 10)
if [ -n $hd_name ];
then
  sed -i 's|hd_names=|hd_names=$hd_name|g' "$TARGET_DIR/smfc.conf"
fi

echo "Installation finished successfully."
