#!/bin/bash

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

if (( 0<=$2 && $2<=100 ))
then 
    s=$(printf "0x%02x" $2)
    echo "Fan level set to $2 ($s)"
else
    echo "ERROR: Bad input parameter!"
    exit
fi

ipmitool raw 0x30 0x70 0x66 0x01 $z $s
echo "Done."
