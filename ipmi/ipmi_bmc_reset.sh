#!/bin/bash
#
#   ipmi_bmc_reset.sh (C) 2023, Peter Sulyok
#   This script will send cold reset to BMC chip and will measure required time for the operation.
#

# This script must be executed by root.
if [[ "$EUID" -ne 0 ]];
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Read a number of the measurements (default is 1).
echo "This script will measure the time length of the BMC cold reset."
read -p "Enter the number of iterations (default is 1): " loop
if [[ "$loop" == "" ]];
then
    loop=1
elif ! [[ "$loop" =~ ^[0-9]+$ ]];
then
    echo "Error: Not a number ($loop)" >&2
    exit 1
fi

echo "BMC will be cold reset $loop times."
for (( i=1; i<=$loop; i++))
do
    echo $i
    start_time=$(date +%s)
    ipmitool mc reset cold
    sleep 4
    fan1_rpm=""
    while :
    do
        fan1_rpm=$(ipmitool sdr |& grep FAN1 | cut -d"|" -f2 | grep RPM)
        if [[ "$fan1_rpm" != "" ]];
        then
            break
        fi
    done
    end_time=$(date +%s)
    echo "Length of the BMC cold reset cycle was `expr $end_time - $start_time` seconds."
done
