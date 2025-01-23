#!/usr/bin/env bash
#
#   hddtemp.sh (C) 2025, Peter Sulyok
#   This script will emulate hddtemp command (with the help of `smartctl`) if it is not available.
#   The expected way of use (how smfc.py os calling hddtemp):
#       $ hddtemp -q -n /dev/sda
#       27
#

# Check first two parameters.
if [ $1 != "-q" ];
then
    exit 1
fi
if [ $2 != "-n" ];
then
    exit 1
fi

# Read disk temperature with `smartctl` command.
hdd_temp=$(smartctl -a $3|grep Temp|tr -s " "|cut -d" " -f 10)
rv=$?

# Print the temperature out.
echo "$hdd_temp"
exit $rv
