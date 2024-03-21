#!/bin/bash
#
#   set_ipmi_fan_mode.sh (C) 2021-2024, Peter Sulyok
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
    c=0x00
    echo "Standard speed."
    ;;
1 | full)
    c=0x01
    echo "Full speed."
    ;;
2 | optimal)
    c=0x02
    echo "Optimal speed."
    ;;
4 | heavyio)
    c=0x04
    echo "HeavyIO speed."
    ;;
*)
    echo "ERROR: Bad input parameter!"
    exit
    ;;
esac

# Configure IPMI fan mode.
ipmitool raw 0x30 0x45 0x01 $c
echo "Done."

