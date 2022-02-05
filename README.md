
# smfc
Super Micro fan control for Linux (home) server/NAS

## TL;DR

This is a `systemd service` running on Linux and is able to control fans of CPU and HD zones with the help of IPMI functions on a Super Micro X9/X10/X11 motherboard.

### 1. Prerequisites
 - Super Micro X9/X10/X11 motherboard with BMC (AST2x00 chip)
 - python 3.6+
 - Linux (kernel 5.6+) with `systemd` (`coretemp` and `drivetemp` kernel modules for CPU and hard disk temperatures)
 - `bash`
 - `ipmitool`
 - optional: `smartmontools` for feature *standby guard* 

### 2. Installation and configuration
 1. Setup the IPMI threshold values for your fans (see script `ipmi/set_ipmi_threshold.sh`). 
 2. Optional: you may consider to enable advanced power management features for your CPU and SATA hard disks for a minimal power consumption (i.e. heat generation) and a low fan noise. 
 3. Load kernel modules (`coretemp` and `drivetemp`).
 4. Install the service with running the script `install.sh`.
 5. Edit the configuration file `/opt/smfc/smfc.conf` and command line options in `/etc/default/smfc`.
 6. Start the `systemd` service
 7. Check results in system log

## Details

### 1. How does it work?
This service was planned for PC cases with two independent cooling systems, CPU zone and HD (peripheral) zone, with their own fans and own temperatures. The fan rotation speeds in these zones can be controlled dynamically by IPMI functions. You can read more about [Super Micro IPMI utilities](https://www.supermicro.com/en/solutions/management-software/ipmi-utilities) and [`ipmitool`](https://github.com/ipmitool/ipmitool). The service will use IPMI `FULL MODE` for fans. 

In this service a fan control logic is implemented for both zones which can:

 1. read the zone's temperature from Linux kernel (minimum, average, maximum temperature values can be calculated based on the configuration)
 2. calculate the proper fan level based on a user-defined control parameters and the temperature value
 3. setup the newly calculated fan level with the help of `ipmitool`
 
The user-defined parameters creates a mapping where a temperature interval is being mapped to a fan level interval. Using this mapping any new temperate value can be mapped to a new fan level.

 <img src="https://github.com/petersulyok/smfc/raw/main/doc/control_function.jpg" align="center" width="500">

When we adjust the rotation speed of a fan, it takes time while fan reaches the new rotation speed. We always apply a delay time in this case (see configuration parameter `[IPMI] fan_level_delay`). The fan control logic try to avoid the continuous adjustments of the fan rotation speeds (when the temperature is changing continuously) in two different ways:

 1. It calculates only limited discrete steps for fan output levels (defined by configuration parameter `[CPU zone]/[HD zone] steps`)
 2. it uses a sensitivity threshold for temperature changes (see configuration parameter `[CPU zone]/[HD zone] sensitivity`) and if the temperature change will not reach  threshold then the control logic will not react

 <img src="https://github.com/petersulyok/smfc/raw/main/doc/fan_output.jpg" align="center" width="500">

The fan control logic can be enabled and disabled independently per zone.

For HD zone an additional optional feature was implemented, called *Standby guard*, with the following assumptions:
	
 - SATA hard disks are organized in a RAID array
 - this array will go to standby mode recurrently

This feature is monitoring the power state of SATA hard disks (with the help of the `smartctl`) and will put the whole array to standby mode if a few members are already stepped into that mode. With this feature we can avoid a situation where the array is partially in standby mode while other members are still active.

### 2. IPMI fan control and thresholds
This is a well-known fact for NAS and home server community that in case of Super Micro boards with IPMI `FULL MODE` the rotation speed of the fans can be controlled freely while the rotation speed does not go above or fall below predefined thresholds. If it happens, IPMI sets the fans back to full rotation speed (level 100%). You can avoid such a situation if you redefine IPMI thresholds based on your fan specification. On Linux you can display and change several IPMI parameters (like fan mode, fan level, sensor data and thresholds etc.) with the help of `ipmitool`.

 IPMI defines six sensor thresholds for fans:
 1. Lower Non-Recoverable  
 2. Lower Critical  
 3. Lower Non-Critical
 4. Upper Non-Critical  
 5. Upper Critical  
 6. Upper Non-Recoverable

You can redefine the proper thresholds in following way:
1. Check the specification of your fans and find the minimum and maximum rotation speeds. In case of [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm) these are 300 and 1500 rpm.
2. Configure the lower thresholds below the minimum fan rotation speed and upper thresholds above the maximum fan rotation speed (e.g. in case of the previous Noctua fan the thresholds are 0, 100, 200, 1600, 1700, 1800).  Edit and run `ipmi/set_ipmi_treshold.sh` to redefine IPMI thresholds. If you install a new BMC firmware on your Super Micro motherboard you have to repeat this step!
3. Check the configured IPMI thresholds:

		root@home:~# ipmitool sensor
		...
		FAN1             | 700.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000
		FAN2             | 700.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000
		FAN3             | na         |            | na    | na        | na        | na        | na        | na        | na
		FAN4             | 600.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000
		FANA             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000
		FANB             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000
		...

You can read more about:

 - IPMI fan control: [STH Forums](https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/) and [TrueNAS Forums](https://www.truenas.com/community/threads/pid-fan-controller-perl-script.50908/)
 - Change IPMI sensors thresholds: [TrueNAS Forums](https://www.truenas.com/community/resources/how-to-change-ipmi-sensor-thresholds-using-ipmitool.35/)

### 3. Power management
If  low noise, low power consumption (i.e. low heat generation) are important attributes of your Linux box then you may consider the following chapters.
#### 3.1 CPU
Most of the modern CPUs has multiple energy saving features. You can check your BIOS and enable [these features](https://metebalci.com/blog/a-minimum-complete-tutorial-of-cpu-power-management-c-states-and-p-states/) like:

 - Intel(R) Speed Shift Technology
 - Intel(R) SpeedStep
 - C-states
 - Boot performance mode

With this setup the CPU will change its base frequency and power consumption dynamically based on the load.

TODO: Recommendation for AMD users.

#### 3.2 SATA hard disks
In case of SATA hard disks you may enable:

 - advanced power management
 - spin down timer

With the help of command `hdparm` you can enable advanced power management and specify a spin down timer (read more [here](https://en.wikipedia.org/wiki/Hdparm)):

	hdparm -B 127 /dev/sda
	hdparm -S 240 /dev/sda
	
In file `/etc/hdparm.conf` you can specify all parameters in a persistent way:

	quiet

	/dev/sda {
        apm = 127
        spindown_time = 240
	}
	/dev/sdb {
        apm = 127
        spindown_time = 240
	}
	...

If you are planning to spin down your hard disks and put them to standby mode you have to setup the configuration parameter `[HD zone] polling` minimum twice as much as the spin down timer here.

### 4. Kernel modules
We need to load two important Linux kernel modules:

 - [`coretemp`](https://www.kernel.org/doc/html/latest/hwmon/coretemp.html): temperature report for Intel(R) CPUs
 - [`drivetemp`](https://www.kernel.org/doc/html/latest/hwmon/drivetemp.html): temperature report for SATA hard disks (available in kernel 5.6+ versions)

Use file `/etc/modules` for persistent loading of these modules. Both modules provides `hwmon` interface in filesystem `/sys` so we can read the the temperatures of CPU and hard disks easily with reading the content of specific files. Check your installation and identify the location of these files:

 - CPU: `/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input`
 - HD: `/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input`

There is an enumeration mechanism (i.e. numbering) in Linux kernel, so your final path may be different. Reading file content from filesystem `/sys` is the fastest way to get the temperature of the CPU and hard disks. `drivetemp` has also an additional advantage that it can read temperature of the hard disks in standby mode too. 

TODO: Recommendation for AMD users.

### 5. Installation
For the installation you need a root user. The default installation script `install.sh` will use the following folders:

|File|Installation folder|Description|
|--|--|--|
|`smsc.service`|`/etc/systemd/system`|systemd service definition file|
|`smsc`|`/etc/default`|service command line options|
|`smsc.py`|`/opt/smfc`|service (python program)|
|`smsc.conf`|`/opt/smfc`|service configuration file|

but you can use freely any other folders too. The service has the following command line options:

	root@home:~/opt/smfc# ./smfc.py --help
	usage: smfc.py [-h] [-c CONFIG_FILE] [-v] [-l {0,1,2,3}] [-o {0,1,2}]

	optional arguments:
	  -h, --help      show this help message and exit
	  -c CONFIG_FILE  configuration file
	  -v              show program's version number and exit
	  -l {0,1,2,3}    log level: 0-NONE, 1-ERROR(default), 2-INFO, 3-DEBUG
	  -o {0,1,2}      log output: 0-stdout, 1-stderr, 2-syslog(default)

You may configure logging output and logging level here and these options can be specified in `/etc/default/smfc`in a persistent way.

### 6. Configuration file
Edit `/opt/smfc/smfc.conf` and specify your configuration parameters here:

	#
	#   smfc.conf
	#   smfc service configuration parameters
	#
	
	
	[Ipmi]
	# Path for ipmitool (str, default=/usr/bin/ipmitool)
	command=/usr/bin/ipmitool 
	# Delay time after changing IPMI fan mode (int, seconds, default=10)
	fan_mode_delay=10
	# Delay time after changing IPMI fan level (int, seconds, default=2)
	fan_level_delay=2
	
	
	[CPU zone]
	# Fan controller enabled (bool, default=0)
	enabled=1
	# Number of CPUs (int, default=1)
	count=1
	# Calculation of CPU temperatures (int, [0-minimum, 1-average, 2-maximum], default=1)
	temp_calc=1
	# Discrete steps in mapping of temperatures to fan level (int, default=5)
	steps=5
	# Threshold in temperature change before the fan controller reacts (float, C, default=4.0)
	sensitivity=4.0
	# Polling time interval for reading temperature (int, sec, default=2)
	polling=2
	# Minimum CPU temperature (float, C, default=30.0)
	min_temp=30.0
	# Maximum CPU temperature (float, C, default=55.0)
	max_temp=55.0
	# Minimum CPU fan level (int, %, default=35)
	min_level=35
	# Maximum CPU fan level (int, %, default=100)
	max_level=100
	# Path for CPU hwmon/coretemp file in sysfs (str, default=/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input)
	hwmon_path=/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input
	
	
	[HD zone]
	# Fan controller enabled (bool, default=0)
	enabled=1
	# Number of HDs (int, default=8)
	count=8
	# Calculation of HD temperatures (int, [0-minimum, 1-average, 2-maximum], default=1)
	temp_calc=1
	# Discrete steps in mapping of temperatures to fan level (int, default=4)
	steps=4
	# Threshold in temperature change before the fan controller reacts (float, C, default=2.0)
	sensitivity = 2
	# Polling interval for reading temperature (int, sec, default=2400)
	polling=2400
	# Minimum HD temperature (float, C, default=32.0)
	min_temp=32.0
	# Maximum HD temperature (float, C, default=48.0)
	max_temp=48.0
	# Minimum HD fan level (int, %, default=35)
	min_level=35
	# Maximum HD fan level (int, %, default=100)
	max_level=100
	# Names of the HDs (str list, default=/dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdg /dev/sdh)
	hd_names=/dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdg /dev/sdh
	# Path for HD hwmon/drivetemp files in sysfs (str multi-line list,
	#   default=/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/1:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/2:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/3:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/4:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/5:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/6:0:0:0/device/hwmon/hwmon*/temp1_input
	#           /sys/class/scsi_device/7:0:0:0/device/hwmon/hwmon*/temp1_input
	hwmon_path=/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/1:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/2:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/3:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/4:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/5:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/6:0:0:0/device/hwmon/hwmon*/temp1_input
			   /sys/class/scsi_device/7:0:0:0/device/hwmon/hwmon*/temp1_input
	# Standby guard feature for the RAID array (bool, default=0)
	standby_guard_enabled=1
	# Number of HDs already in STANDBY state before the full RAID array will be forced to it (int, default=1)
	standby_hd_limit=1
	# Path for 'smartctl' command (str, default=/usr/sbin/smartctl)
	smartctl_path=/usr/sbin/smartctl


Important notes:

 1. `[CPU zone] / [HD zone} min_level / max_level`: Check the stability of the fans and refine these values on demand. As it was stated earlier, IPMI can switch back to full rotation speed if fans reach specific thresholds. You can collect real data about the behavior of your fans if you edit and run script `ipmi/fan_measurement.sh`. The script will set fan levels from 100% to 20% in 5% steps and results will be saved in the file `fan_result.csv`:

		root:~# cat fan_result.csv
		Level,FAN1,FAN2,FAN4,FANA,FANB
		100,1300,1300,1200,1300,1300
		95,1300,1300,1100,1200,1300
		90,1200,1200,1100,1200,1200
		85,1100,1100,1000,1100,1100
		80,1100,1100,1000,1100,1100
		75,1000,1000,900,1000,1000
		70,900,900,800,1000,900
		65,900,900,800,900,900
		60,800,800,700,900,800
		55,700,700,700,800,700
		50,700,700,600,700,700
		45,600,600,500,700,600
		40,500,500,500,600,500
		35,500,500,400,500,500
		30,400,400,300,400,400
		25,300,300,300,400,300
		20,1300,1300,1200,1300,1300

	My experience is that Noctua fans in my box are running stable in the 35-100% fan level interval.  

 3. `[CPU zone] / [HD zone} hwmon_path`: The service will automatically resolve any wildcard characters in the path specified here in order to make this configuration step more flexible and comfortable.

### 7. Running the service
This `systemd` service can be started stopped in the standard way. Do not forget to reload `systemd` configuration after a new installation or if you changed the service definition file:

	systemctl daemon-reload
	systemctl start smfc.service
	systemctl stop smfc.service
	systemctl restart smfc.service
	systemctl status smfc.service
	● smfc.service - Super Micro Fan Control
	     Loaded: loaded (/etc/systemd/system/smfc.service; enabled; vendor preset: enabled)
	     Active: active (running) since Fri 2021-09-17 23:28:10 CEST; 1 day 19h ago
	   Main PID: 1064180 (smfc.py)
	      Tasks: 1 (limit: 38371)
	     Memory: 7.4M
	        CPU: 41.917s
	     CGroup: /system.slice/smfc.service
	             └─1064180 /usr/bin/python3 /opt/smfc/smfc.py -c /opt/smfc/smfc.conf -l 2

	Sep 19 17:12:39 home smfc.service[1064180]: CPU zone: new level > 39.0C > [T:40.0C/L:61%]
	Sep 19 17:12:42 home smfc.service[1064180]: CPU zone: new level > 33.0C > [T:35.0C/L:48%]
	Sep 19 17:48:14 home smfc.service[1064180]: CPU zone: new level > 38.0C > [T:40.0C/L:61%]

If you are testing your configuration you can start `smfc.py` directly in a terminal. Logging to the standard output and debug log level are useful in this case:

	cd /opt
	smfc.py -o 0 -l 3

### 8. Checking result and monitoring logs
All messages will be logged to the specific output and the specific level.
With the help of command `journalctl` you can check logs easily. For examples:

1. listing service logs of the last two hours:

		journalctl -u smfc --since "2 hours ago"

2. listing service logs from the last boot:

		journalctl -b -u smfc

## FAQ

### Q: My fans are spinning up and they are loud. What is wrong?
You can check the current fan rotation speeds:

	ipmitool sdr

and you can also check Super Micro remote web interface (Server Health > Health Event log). If you see Assertions log messages for fans:

	Fan(FAN1)	Lower Critical - going low - Assertion
	Fan(FAN1)	Lower Non-recoverable - going low - Assertion
	Fan(FAN1)	Lower Non-recoverable - going low - Deassertion
	Fan(FAN1)	Lower Critical - going low - Deassertion
	Fan(FAN4)	Lower Critical - going low - Assertion
	Fan(FAN4)	Lower Non-recoverable - going low - Assertion

then  you have to adjust your configuration because IPMI switched back to full rotation speed.

### Q: I would like to use constant fan rotation speed in one or both zones. How can I configure that?
You should configure the temperatures and levels with the same value. 

	min_temp=40
	max_temp=40
	min_level=60
	max_level=60

With this setup there will be a constant 60% fan level in the specific zone. The temperature value is ignored, `steps` parameter is also ignored.

### Q: How does the author test/use this service?
My configuration is the following:

 - [Super Micro X11SCH-F motherboard](https://www.supermicro.com/en/products/motherboard/X11SCH-F)
 - [Intel Core i3-8300T CPU](https://ark.intel.com/content/www/us/en/ark/products/129943/intel-core-i3-8300t-processor-8m-cache-3-20-ghz.html)
- 32 GB ECC DDR4 RAM
 - [Fractal Design Node 804 case](https://www.fractal-design.com/products/cases/node/node-804/black/), with separated chambers for the motherboard and the hard disks:
 
	<img src="https://www.legitreviews.com/wp-content/uploads/2014/05/fractal-design-node-804-vendor-fans.jpg" align="center" width="500">

 - Debian Linux LTS (actually bullseye with Linux kernel 5.10)
 - 8 x [WD Red 12TB (WD120EFAX)](https://shop.westerndigital.com/en-ie/products/outlet/internal-drives/wd-red-plus-sata-3-5-hdd#WD120EFAX) hard disks in ZFS RAID
 - 3 x [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm)  fans (FAN1, FAN2, FAN4) in CPU zone 
 - 2 x [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm) fans (FANA, FANB) in HD zone

## References
Further readings:

 - [\[STH forums\] Reference Material: Supermicro X9/X10/X11 Fan Speed Control](https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/)
 - [\[TrueNAS forums\] How To: Change IPMI Sensor Thresholds using ipmitool](https://www.truenas.com/community/resources/how-to-change-ipmi-sensor-thresholds-using-ipmitool.35/)
 - [\[TrueNAS forums\] Script to control fan speed in response to hard drive temperatures](https://www.truenas.com/community/threads/script-to-control-fan-speed-in-response-to-hard-drive-temperatures.41294/)
- [\[Pcfe's blog\] Set fan thresholds on my Super Micro H11DSi-NT](https://blog.pcfe.net/hugo/posts/2018-08-14-epyc-ipmi-fans/)
- [\[Super Micro\] IPMI Utilities](https://www.supermicro.com/en/solutions/management-software/ipmi-utilities)
- Documentation of [`coretemp`](https://www.kernel.org/doc/html/latest/hwmon/coretemp.html) kernel module
- Documentation of [`drivetemp`](https://www.kernel.org/doc/html/latest/hwmon/drivetemp.html) kernel module and its [github project](https://github.com/groeck/drivetemp)

Similar projects:
 - [\[GitHub\] Kevin Horton's nas_fan_control](https://github.com/khorton/nas_fan_control)
 - [\[GitHub\] Rob Urban's fork nas_fan control](https://github.com/roburban/nas_fan_control)
 - [\[GitHub\] sretalla's fork nas_fan control](https://github.com/sretalla/nas_fan_control)
 - [\[GitHub\] Andrew Gunnerson's ipmi-fan-control](https://github.com/chenxiaolong/ipmi-fan-control)

> Written with [StackEdit](https://stackedit.io/).
