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

echo "Installation finished successfully."
