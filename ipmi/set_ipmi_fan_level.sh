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
    z=0x00
    echo "CPU zone."
    ;;
1 | hd)
    z=0x01
    echo "HD zone."
    ;;
*)
    echo "Use: $0 zone leve"
    echo "     zone         fan zone: \"cpu\" or \"hd\""
    echo "     level        fan level: 0-100"
    exit
    ;;
esac

# Check second (level) parameter.
if (( 0<=$2 && $2<=100 ))
then 
    s=$(printf "0x%02x" $2)
    echo "Fan level set to $2 ($s)"
else
    echo "ERROR: Bad input parameter!"
    exit
fi

# Configure IPMI fan level in the specified zone.
ipmitool raw 0x30 0x70 0x66 0x01 $z $s
echo "Done."
