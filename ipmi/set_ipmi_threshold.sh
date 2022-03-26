#!/bin/bash
#
#   set_ipmi_threshold.sh (C) 2021-2022 Peter Sulyok
#   This script will setup IPMI threshold values for fans.
#   Read more here: https://www.truenas.com/community/resources/how-to-change-ipmi-sensor-thresholds-using-ipmitool.35/

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Setup of the lower threshold limits of the fans.
# Edit the list of fans here (FAN1, FAN2, FAN4, FANA, FANB)!
for i in 1 2 4 A B; 
do
    # Edit the lower threshold values here (0, 100, 200)!
    ipmitool sensor thresh FAN${i} lower 0 100 200;
done

# Setup of the upper threshold limits of the fans.
# Edit the list of fans here (FAN1, FAN2, FAN4, FANA, FANB)!
for i in 1 2 4 A B; 
do
    # Edit the upper threshold values here (1600, 1700, 1800)!
    ipmitool sensor thresh FAN${i} upper 1600 1700 1800;
done
