#!/usr/bin/env bash
#
#   get_ipmi_fan_mode.sh (C) 2021-2025, Peter Sulyok
#   This script will read the current IPMI fan mode.
#   Read more here: https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/
#

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Configure IPMI fan mode.
fan_mode=$(( $(ipmitool raw 0x30 0x45 0x00) ))
rc=$?

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
*)
    mode_str="Unknown"
    ;;
esac

echo "Current IPMI fan mode is: $mode_str ($fan_mode)."
echo "ipmitool return code: $rc."
