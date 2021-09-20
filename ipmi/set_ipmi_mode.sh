#!/bin/bash

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

ipmitool raw 0x30 0x45 0x01 $c
echo "Configured."

