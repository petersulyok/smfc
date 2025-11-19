#!/usr/bin/env bash
#
#   set_ipmi_fan_level.sh (C) 2021-2025, Peter Sulyok
#   This script will setup fan level in a specified IPMI zone.
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
    zone="0x0$1"
    zone_str=$1
    ;;
*)
    echo "Bad zone parameter"
    echo "Use: $0 zone level"
    echo "     zone         fan zone: \"cpu\" or \"hd\""
    echo "     level        fan level: 0-100"
    exit
    ;;
esac

# Check second (level) parameter.
if (( 0<=$2 && $2<=100 ))
then 
    level=$(printf "0x%02x" $2)
    echo "Fan level set to $2% ($level) in zone $zone_str ($zone)."
else
    echo "ERROR: Bad level parameter!"
    echo "Use: $0 zone level"
    echo "     zone         IPMI zone: 0|cpu, 1|hd, 2, 3, 4, 5, 6, or 7"
    echo "     level        fan level: 0-100"
    exit
fi

# Configure IPMI fan level in the specified zone.
ipmitool raw 0x30 0x70 0x66 0x01 $zone $level
echo "ipmitool return code: $?"
