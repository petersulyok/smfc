
# smfc
Super Micro Fan Control for a Linux (home) server

## TL;DR

This is a `systemd service` running on Linux which is able to control fans of CPU and HD zones through IPMI functions on a Super Micro X9/X10/X11 motherboard.

### 1. Prerequisites
 - Super Micro X9/X10/X11 motherboard with BMC (AST2x00 chip)
 - python 3.6+
 - Linux (kernel 5.6+) with `systemd` (`coretemp` and `drivetemp` kernel modules for CPU and SATA HD temperatures)
 - `bash`
 - `ipmitool`
 - optional: `smartmontools` for feature *standby guard* 

### 2. Installation and configuration
 1. Setup the IPMI threshold values for your fans (see script `ipmi/set_ipmi_threshold.sh`). 
 2. Optional: you may consider to enable advanced power management features for your CPU and SATA hard disks for a minimal power consumption (i.e. heat generation) and a low fan noise. 
 3. Load kernel modules (`coretemp` and `drivetemp`).
 4. Install the service with running the script `install.sh`.
 5. Edit the configuration file `/opt/smfc/smfc.conf` and command line options in `/etc/default/smfc`.
 6. Start the service:

	    systemctl daemon-reload
	    systemctl start smfc.service

 7. Check results in system log

## Details

### 1. How does it work?



### 2. IPMI fan control
The NAS and home server community discovered the fact that in IPMI's `FULL MODE`the rotation speed of the fans can be controlled freely while the rotation speed does not go above or fall below predefined thresholds. If it happens, IPMI sets the fans back to full rotation speed (level 100%). We can avoid such a situation with adjusting the IPMI thresholds based on fan specification. IPMI defines six thresholds for fans:
 1. Lower Non-Recoverable  
 2. Lower Critical  
 3. Lower Non-Critical
 4. Upper Non-Critical  
 5. Upper Critical  
 6. Upper Non-Recoverable

On Linux you can display and change the IPMI's fan mode, fan level, and thresholds with the help of command `ipmitool`.

You can follow these steps to setup IPMI thresholds properly:
1. Check the specification of your fans and find the minimum and maximum rotation speeds. In case of [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm) these are 300 and 1500 rpm.
2. Configure the lower thresholds below the minimum fan rotation speed and upper thresholds above the maximum fan rotation speed (e.g. for the previous Noctua fan the thresholds are 0, 100, 200, 1600, 1700, 1800).  Edit and run `ipmi/set_ipmi_treshold.sh` to redefine IPMI thresholds. If you install a new BMC firmware on your Super Micro motherboard you have to repeat this step!
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
If  low noise, low power consumption (i.e. low heat generation) are important attributes of your Linux server then you may consider the following chapters.
#### 3.1 CPU
Most of the modern CPUs has multiple energy saving features. You can check your BIOS and enable [these features](https://metebalci.com/blog/a-minimum-complete-tutorial-of-cpu-power-management-c-states-and-p-states/) like:

 - Intel(R) Speed Shift Technology
 - Intel(R) SpeedStep
 - C-states
 - Boot performance mode

With this setup the CPU will change its base frequency and power consumption dynamically based on the load.
TODO: Recommendation for AMD users.

#### 3.2 SATA Hard disks
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

If you are planning to spin down your hard disks and put them to sleep mode you have to setup the configuration parameter `[HD zone] polling` minimum twice as much as the spin down timer here.

### 4. Kernel modules
We need to load two important Linux kernel modules:

 - `coretemp`: temperature report for Intel(R) CPUs
 - `drivetemp`: temperature report for SATA hard disks (available in kernel 5.6+ version)

Use file `/etc/modules` for persistent loading of these modules. Both modules provides `hwmon` interface in filesystem `/sys` so we can read the the temperatures of CPU and hard disks easily with reading the content of specific files. Check your installation and identify the location of these files:

 - CPU: `/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input`
 - HD: `/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input`

There is an enumeration mechanism (i.e. numbering) in Linux kernel, so your final path may be different.
TODO: Recommendation for AMD users.

### 5. Installation
For installation you need a root user. The default installation with with script `install.sh` will use the following folders:

|File|Installation folder|Role|
|--|--|--|
|`smsc.service`|`/etc/systemd/system`|systemd service definition file|
|`smsc`|`/etc/default`|service command line options|
|`smsc.py`|`/opt/smfc`|service (python program)|
|`smsc.conf`|`/opt/smfc`|service configuration file|

but you can use any other folders too. The service has the following command line options:

	root@home:~/opt/smfc# ./smfc.py --help
	usage: smfc.py [-h] [-c CONFIG_FILE] [-v] [-l {0,1,2,3}] [-o {0,1,2}]

	optional arguments:
	  -h, --help      show this help message and exit
	  -c CONFIG_FILE  configuration file
	  -v              show program's version number and exit
	  -l {0,1,2,3}    log level: 0-NONE, 1-ERROR(default), 2-INFO, 3-DEBUG
	  -o {0,1,2}      log output: 0-stdout, 1-stderr, 2-syslog(default)

You may configure logging output and logging level here and these options can be specified in  `/etc/default/smfc`in persistent way.
