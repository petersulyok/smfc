#!/bin/bash
#
#   fan_measurement.sh (C) 2021-2022 Peter Sulyok
#   This script will measure the rotation speed belongs to different IPMI fan level.
#   Results will be stored in 'fan_result.cvs'.
#

# This script must be executed by root.
if [ "$EUID" -ne 0 ]
then
    echo "ERROR: Please run as root"
    exit -1
fi

# Start measurement in 100-20 IPMI fan level interval.
echo "Level,FAN1,FAN2,FAN3,FAN4,FANA,FANB" > fan_result.csv
echo "IPMI fan level measurement:"
for i in 100 95 90 85 80 75 70 65 60 55 50 45 40 35 30 25 20;
do
    ./set_ipmi_fan_level.sh cpu $i >/dev/nul
    ./set_ipmi_fan_level.sh hd $i >/dev/nul
    sleep 6
    ipmitool sdr > sensor_data.txt
    fan1=$(cat sensor_data.txt | grep FAN1 | awk '{ print $3}')
    fan2=$(cat sensor_data.txt | grep FAN2 | awk '{ print $3}')
    fan3=$(cat sensor_data.txt | grep FAN3 | awk '{ print $3}')
    fan4=$(cat sensor_data.txt | grep FAN4 | awk '{ print $3}')
    fanA=$(cat sensor_data.txt | grep FANA | awk '{ print $3}')
    fanB=$(cat sensor_data.txt | grep FANB | awk '{ print $3}')
    echo "$i,$fan1,$fan2,$fan3,$fan4,$fanA,$fanB" >> fan_result.csv
    echo "Fan level: $i% done"
done
rm sensor_data.txt
