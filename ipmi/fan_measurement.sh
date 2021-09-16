#!/bin/bash

echo "Level,FAN1,FAN2,FAN4,FANA,FANB" > fan_result.csv
echo "IPMI fan level measurement:"

for i in 100 95 90 85 80 75 70 65 60 55 50 45 40 35 30 25 20;
do
    ./set_ipmi_fan_level.sh cpu $i >/dev/nul
    sleep 6
    ./set_ipmi_fan_level.sh hd $i >/dev/nul
    sleep 6
    ipmitool sdr > sensor_data.txt
    fan1=$(cat sensor_data.txt | grep FAN1 | awk '{ print $3}')
    fan2=$(cat sensor_data.txt | grep FAN2 | awk '{ print $3}')
    fan4=$(cat sensor_data.txt | grep FAN4 | awk '{ print $3}')
    fanA=$(cat sensor_data.txt | grep FANA | awk '{ print $3}')
    fanB=$(cat sensor_data.txt | grep FANB | awk '{ print $3}')
    echo "$i,$fan1,$fan2,$fan4,$fanA,$fanB" >> fan_result.csv
    echo "Fan level: $i% done"
done

rm sensor_data.txt
