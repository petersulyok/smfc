#!/usr/bin/env bash
#
#   get_ipmi_fan_level.sh (C) 2021-2025, Peter Sulyok
#   This script will read the current fan level in a specified IPMI zone.
#

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Check first (zone) parameter.
case $1 in
0 | cpu)
    zone=0x00
    zone_str="CPU"
    ;;
1 | hd)
    zone=0x01
    zone_str="HD"
    ;;
2 | 3 | 4 | 5 | 6 | 7)
    zone="0x$1"
    zone_str=$1
*)
    echo "Bad zone parameter"
    echo "Use: $0 zone"
    echo "Where zone is:"
    echo "   0|cpu       CPU zone"
    echo "   1|hd        HD zone"
    echo "   2|3|4|5|6|7 2..7 IPMI zone"
    exit
    ;;
esac

# Read IPMI fan level in the specified zone.
level=$((16#$(ipmitool raw 0x30 0x45 0x00 $zone)))
rc=$?
echo "Current IPMI fan level in $zone_str is: $level."
echo "ipmitool return code: $rc"
