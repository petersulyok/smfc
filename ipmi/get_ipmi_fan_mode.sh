#!/usr/bin/env bash
#
#   get_ipmi_fan_mode.sh (C) 2021-2026, Peter Sulyok
#   This script will read the current IPMI fan mode.
#   Read more here: https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/
#

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Read current IPMI fan mode (ipmitool prints the byte in hex, e.g. " 0a").
reply=$(ipmitool raw 0x30 0x45 0x00)
rc=$?
if [ $rc -ne 0 ] || [ -z "${reply// /}" ]
then
    echo "ERROR: IPMI fan mode cannot be read (ipmitool return code: $rc)."
    exit 1
fi
fan_mode=$(( 16#${reply// /} ))

# Check input parameter.
case $fan_mode in
0)
    mode_str="Standard"
    ;;
1)
    mode_str="Full"
    ;;
2)
    mode_str="Optimal"
    ;;
3)
    mode_str="PUE/2"
    ;;
4)
    mode_str="Heavy IO"
    ;;
5)
    mode_str="PUE3"
    ;;
6)
    mode_str="Liquid Cooling"
    ;;
7)
    mode_str="Smart"
    ;;
8)
    mode_str="PUE"
    ;;
9)
    mode_str="Smart Cooling"
    ;;
10)
    mode_str="Performance"
    ;;
11)
    mode_str="Silent"
    ;;
*)
    mode_str="Unknown"
    ;;
esac

echo "Current IPMI fan mode is: $mode_str ($fan_mode)."
echo "ipmitool return code: $rc."
