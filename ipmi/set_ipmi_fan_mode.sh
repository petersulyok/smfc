#!/usr/bin/env bash
#
#   set_ipmi_fan_mode.sh (C) 2021-2025, Peter Sulyok
#   This script will setup IPMI fan mode.
#   Read more here: https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/
#

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Check input parameter.
case $1 in
0 | standard)
    mode=0x00
    mode_str="Standard"
    ;;
1 | full)
    mode=0x01
    mode_str="Full"
    ;;
2 | optimal)
    mode=0x02
    mode_str="Optimal"
    ;;
3 | pue)
    mode=0x03
    mode_str="PUE/2"
    ;;
4 | heavyio)
    mode=0x04
    mode_str="Heavy IO"
    ;;
*)
    echo "ERROR: Bad input parameter!"
    echo "Usage: set_ipmi_fan_mode.sh mode"
    echo "where mode is:"
    echo "    0|standard - STANDARD mode"
    echo "    1|full     - FULL mode"
    echo "    2|optimal  - OPTIMAL mode"
    echo "    3|pue      - PUE/2 mode"
    echo "    4|heavyio  - HEAVY IO mode"
    exit
    ;;
esac

# Configure IPMI fan mode.
ipmitool raw 0x30 0x45 0x01 $mode
rc=$?
echo "IPMI fan mode set to: $mode_str ($mode)."
echo "ipmitool return code: $rc"
