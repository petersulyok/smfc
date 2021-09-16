#!/bin/bash

for i in 1 2 4 A B; 
do 
    ipmitool  sensor thresh FAN${i} lower 0 100 200;
done

for i in 1 2 4 A B; 
do 
    ipmitool  sensor thresh FAN${i} upper 1600 1700 1800;
done
