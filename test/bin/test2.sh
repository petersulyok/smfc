#!/usr/bin/env bash
# smartctl emulation script

# smartctl -i -n standby /dev/sd?
if [[ $1 = "-i" && $2 = "-n" && $3 = "standby" ]] ; then
  r=$((RANDOM % 2))
  if [[ "$r" -eq "0" ]] ; then
    cat << EOF
smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

=== START OF INFORMATION SECTION ===
Model Family:     Samsung based SSDs
Device Model:     Samsung SSD 870 QVO 8TB
Serial Number:    S5SSNG0NB01828M
LU WWN Device Id: 5 002538 f70b0ee2f
Firmware Version: SVQ01B6Q
User Capacity:    8,001,563,222,016 bytes [8.00 TB]
Sector Size:      512 bytes logical/physical
Rotation Rate:    Solid State Device
Form Factor:      2.5 inches
TRIM Command:     Available, deterministic, zeroed
Device is:        In smartctl database [for details use: -P show]
ATA Version is:   ACS-4 T13/BSR INCITS 529 revision 5
SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)
Local Time is:    Sat May 15 14:26:26 2021 CEST
SMART support is: Available - device has SMART capability.
SMART support is: Enabled
Power mode is:    ACTIVE or IDLE
EOF
    r=0
  fi
  if [[ "$r" -eq "1" ]] ; then
    cat << EOF
smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

Device is in STANDBY mode, exit(2)
EOF
    r=2
  fi
  exit $r
fi

# smartctl -s standby,now /dev/sd?
if [[ $1 = "-s" && $2 = "standby,now" ]] ; then
  cat << EOF
smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

Device placed in STANDBY mode
EOF
  exit 0
fi
