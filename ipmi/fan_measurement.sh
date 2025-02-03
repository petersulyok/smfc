#!/usr/bin/env bash

#   fan_measurement.sh (C) 2021-2024, Peter Sulyok
#   This script will measure the rotation speed belongs to different IPMI fan level.
#   Results will be stored in 'fan_result.cvs'.

# This script must be executed by root.
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root"
    exit 1
fi

output_file="fan_result.csv"

# get list of fans
fan_data=$(ipmitool sdr list | grep FAN)

# double check list isn't empty
if [ -z "$fan_data" ]; then
    echo "No fan data found."
    exit 1
fi

# get actual fan names since they can differ
fan_names=($(echo "$fan_data" | awk '{print $1}'))

# write CSV header
{
    echo -n "Level"
    for fan_name in "${fan_names[@]}"; do
        echo -n ",$fan_name"
    done
    echo
} > "$output_file"

echo "IPMI fan level measurement:"

# Start measurement in 100-20 IPMI fan level interval.
for i in 100 95 90 85 80 75 70 65 60 55 50 45 40 35 30 25 20; do
    ./set_ipmi_fan_level.sh cpu $i >/dev/null
    ./set_ipmi_fan_level.sh hd $i >/dev/null
    sleep 6

    ipmitool sdr > sensor_data.txt

    fan_speeds=()
    for fan_name in "${fan_names[@]}"; do
        speed=$(grep "$fan_name" sensor_data.txt | awk '{print $3}')
        fan_speeds+=("$speed")
    done

    # write results to CSV file
    {
        echo -n "$i"
        for speed in "${fan_speeds[@]}"; do
            echo -n ",$speed"
        done
        echo
    } >> "$output_file"

    echo "Fan level: $i% done"
done

rm sensor_data.txt

echo "Fan speeds have been written to $output_file"