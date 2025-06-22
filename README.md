
# smfc
[![Tests](https://github.com/petersulyok/smfc/actions/workflows/test.yml/badge.svg)
](https://github.com/petersulyok/smfc/actions/workflows/tests.yml) [![Codecov](https://codecov.io/gh/petersulyok/smfc/branch/main/graph/badge.svg)
](https://app.codecov.io/gh/petersulyok/smfc) [![Issues](https://img.shields.io/github/issues/petersulyok/smfc)
](https://github.com/petersulyok/smfc/issues) [![Supported Python Versions](https://img.shields.io/pypi/pyversions/smfc)](https://pypi.org/project/smfc)
[![PyPI version](https://badge.fury.io/py/smfc.svg)](https://badge.fury.io/py/smfc)


Super Micro fan control for Linux (home) servers.

> [!NOTE]
> BETA-14 released: Fix for parsing temperate of newer SCSI disks (issue #76).

See [discussion#77](https://github.com/petersulyok/smfc/discussions/77) for more details.

## TL;DR

This is a `systemd service` running on Linux and can control fans with help of IPMI on Super Micro X10-X13 (and some X9) motherboards.

You can also run `smfc` in docker, see more details in [Docker.md](docker/Docker.md).

### 1. Prerequisites
 - a Super Micro motherboard with ASPEED AST2400/2500/2600 chip
 - Python 3.9-3.13
 - a Linux distribution with:
   - `systemd` and `bash`
   - `coretemp` kernel module for Intel CPUs or `k10temp` kernel module for AMD CPUs
   - `drivetemp` kernel module (kernel version 5.6+ required) modules for SATA HDDs/SSDs
 - `ipmitool`
 - optional: `smartmontools` for SAS/SCSI disks and *standby guard* feature
 - optional: `nvidia-smi` for GPU fan controller 


### 2. Installation and configuration
 1. Set up the IPMI threshold values for your fans (see [this chapter](https://github.com/petersulyok/smfc?tab=readme-ov-file#7-ipmi-fan-control-and-sensor-thresholds) for details). 
 2. Optional: enable advanced power management features for your CPU and SATA hard disks for lower power consumption, heat generation and fan noise. 
 3. Load kernel modules (`coretemp/k10temp` and `drivetemp`).
 4. Install `smfc` service (check [Installation.md](doc/Installation.md) for more details)`.
 5. Edit the configuration file `/etc/smfc/smfc.conf` and command line options in `/etc/default/smfc`.
 6. Start the `systemd` service
 7. Check results in system log
 8. Leave a feedback in [discussion #55](https://github.com/petersulyok/smfc/discussions/55)

Feel free to visit [Discussions](https://github.com/petersulyok/smfc/discussions) and raise your questions or share your experience on this project.

## Details
### 1. How does it work?
This service was designed for Super Micro motherboards with IPMI functionality, implementing different fan controllers connected to one or more IPMI zones.
In `smfc`, the following fan controllers are implemented:

| Fan controller | Temperature source      | Configuration                                                           | Default IPMI zone   |
|----------------|-------------------------|-------------------------------------------------------------------------|---------------------|
| CPU zone       | Intel/AMD CPU(s)        | CPUs are identified automatically                                       | 0 (CPU zone)        |
| HD zone        | SATA and SCSI HDDs/SSDs | Hard disks' names must be specified `[HD zone] hd_names=` parameter     | 1 (Peripheral zone) | 
| GPU zone       | Nvidia GPUs             | GPU indices must be specified in `[GPU zone] gpu_device_ids=` parameter | 1 (Peripheral zone) |
| Constant zone  | None                    | Constant fan level can be specified in `[CONST zone] level=` parameter  | 1 (Peripheral zone) |

These fan controllers can be enabled and disabled independently. They can be used in a free combination with on or more IPMI zones, but different fan controllers should control different IPMI zones (i.e. no overlapping is allowed)!

The _IPMI zone_ is a logical term, representing a cooling zone, where there are predefined fans having the same rotation speed. Please note that the fan assignment to an IPMI zone is predefined on the motherboard, it cannot be changed! 
On a typical Super Micro motherboard, there are two IPMI zones:

- CPU or System zone (IPMI zone 0) with fan names: FAN1, FAN2, etc.
- Peripheral or HD zone (IPMI zone 1) with fan names: FANA, FANB, etc.

On Super Micro server motherboards, there could be more IPMI zones with different fan names (see [issue #31](https://github.com/petersulyok/smfc/issues/31)). 

Note: `smfc v3.8.0` and previous versions implemented _Swapped Zones_ feature to swap IPMI zone 0 and 1. From `smfc v4.0.0` the IPMI zones can be assigned freely to fan controllers providing more freedom and convince for the user (see `ipmi_zone=` parameter for more detail).  

In `smfc`, temperature-driven fan controllers have the following control logic:

 1. it reads the zone's temperature
 2. it calculates a new fan level based on the user-defined control function and the temperature value of the zone 
 3. it configures the new fan level for the zone(s) with IPMI commands (i.e. `ipmitool`)

<img src="https://github.com/petersulyok/smfc/raw/main/doc/smfc_overview.png" align="center" width="600">

If there are multiple heat sources in the zone, the user can configure different temperature calculation methods (i.e. minimum, average, maximum temperatures).
The _Constant zone_ is an exception here, it does not have/require a temperature source, it can provide a constant fan level for one or more IPMI zones.

Please note that `smfc` will set all fans back to 100% speed at service termination to avoid overheating! 

#### 2. User-defined control function
Fan controllers are using user-defined control functions where a temperature interval is being mapped to a fan rotation level interval.

 <img src="https://github.com/petersulyok/smfc/raw/main/doc/userdefined_control_function.png" align="center" width="500">

The following five parameters will define such a function:

     min_temp=
     max_temp=
     min_level=
     max_level=
     steps=

In this way, a fan controller can map any new temperature value to a fan level (from Celsius degrees to % value).   
Changing the fan rotational speed is a very slow process (it could take several seconds depending on the fan type and the requested amount of change), so we try to minimize these kinds of actions. Instead of setting fan rotational speed continuously, we define discrete fan levels based on `steps=` parameter.

 <img src="https://github.com/petersulyok/smfc/raw/main/doc/fan_output_levels.png" align="center" width="500">

The fan controllers implement the following strategies to avoid/minimize the unnecessary change of fan rotation speed:

 1. When the fan rotational speed is changed, it always applies a delay time (defined in `[IPMI] fan_level_delay=` configuration parameter) to let the fan implement the physical change.
 2. There is a sensitivity threshold parameter (`sensitivity=`) in the fan controller configuration. While the temperature change is below this value, the fan controller does not react. 
 3. The configuration parameter `polling=` defines the frequency of the temperature reading. The bigger polling time, the lower frequency of the fan speed change.

#### 3. Standby guard
For HD zone fan controller, an additional optional feature was implemented, called *Standby guard*, with the following assumptions:
	
 - SATA hard disks are organized into a RAID array
 - the RAID array will go to standby mode recurrently

This feature is monitoring the power state of SATA hard disks (with the help of the `smartctl`) and will put the whole array to standby mode if a few members are already stepped into that. With this feature, the situation can be avoided where the array is partially in standby mode while other members are still active.
SCSI disks are not compatible with this feature.

#### 5. Hard disk compatibility
The `smfc` service was originally designed for `SATA` hard drives, but `smfc v3.0.0` is also compatible with `NVME` and `SAS/SCSI` disks. The following table summarizes how the temperature is read for different disk types: 

| Disk type  | Temperature source   | Kernel module | Command    |
|------------|----------------------|---------------|------------|
| `SATA`     | Linux kernel (HWMON) | `drivetemp`   | -          |
| `NVME`     | Linux kernel (HWMON) | -             | -          |
| `SAS/SCSI` | `smartctl`           | -             | `smartctl` |

Some additional notes:

- For `NVME` SSDs no kernel driver needs to be loaded the kernel can handle this disk type automatically
- For `SATA` disks the `drivetemp` kernel module should be loaded. **This is the fastest way to read disk temperature**, and the kernel module can report the temperature while hard disks are in sleep mode!
- For `SAS/SCSI` disks the `smartctl` command will be used to read disk temperature
- If `drivetemp` module is not loaded or an HDD is not compatible with `drivetemp` module then `smfc` will use `smartctl` automatically.   
- Different disks types can be mixed in `hd_names=` configuration parameter but the *Standby guard* feature will not be supported in this case.
- It is NOT RECOMMENDED to mix NVME SSD and SATA/SCSI disks in `hd_names=` parameter, because they are operating in quite different temperature intervals (e.g. 30-40C vs 40-80C).


### 5. Super Micro compatibility
Originally this software was designed to work with Super Micro X10 and X11 motherboards with a BMC chip (i.e. ASPEED AST2400/2500) and IPMI functionality. 

In case of X9 motherboards the compatibility is not guaranteed, it depends on the hardware components of the motherboard (i.e. not all X9 motherboards employ BMC chip). 

The earlier X8 motherboards are NOT compatible with this software. They do not implement `IPMI_FULL` mode, and they cannot control fan levels how it is implemented in `smfc`.

X13 motherboards (with AST2600 BMC chips) seem to be compatible with smfc (see mode details in [issue #33](https://github.com/petersulyok/smfc/issues/33) about an X13SAE-F motherboard).
Fan control and `IPMI_FULL` mode are working properly. The only difference is in using thresholds, AST2600 implements only `Lower Critical` threshold, so setting up thresholds is different in this case.  

Feel free to create a short feedback in [discussion #55](https://github.com/petersulyok/smfc/discussions/55) on your compatibility experience.


### 6. IPMI fan control and sensor thresholds
On Super Micro X10-X11 motherboards IPMI uses six sensor thresholds to specify the safe and unsafe fan rotational speed intervals (these are RPM values rounded to nearest hundreds, defined for each fan separately):

```
Lower Non-Recoverable  
Lower Critical  
Lower Non-Critical
Upper Non-Critical  
Upper Critical  
Upper Non-Recoverable
```

but newer Super Micro X13 motherboards (with AST2600 BMC chip) have only one sensor threshold:

```
Lower Critical  
```

Originally, this chapter was created Super Micro X10-X11 motherboards, but can be easily adopted to X13 motherboards as well (see more details in #33).

Like many other utilities (created by NAS and home server community), `smfc` also uses **IPMI FULL mode** for fan control, where all fans in the zone:

   1. initially configured to full speed (100%)
   2. then their speed can be safely configured in `[Lower Critical, Upper Critical]` interval
   3. if any fan speed oversteps either `Lower Critical` or `Upper Critical` threshold then IPMI will generate an _assertion event_ and will set the all fan speeds back to 100% in the zone

Please also consider the fact that **fans are mechanical devices, their rotational speed is not stable** (it could be fluctuating). In order to avoid IPMI's assertion mechanism described here please follow the next steps: 

  1. Per fan: check the minimum and maximum rotational speeds of your fan on its vendor website
  2. Per fan: configure proper IMPI sensor thresholds adjusted to the fan speed interval
  3. Per zone: define safe `min_level`/`max_level` values for `smfc` respecting the variance of the all fans in the IPMI zone (it could take several iterations and adjustments) 

<img src="https://github.com/petersulyok/smfc/raw/main/doc/ipmi_sensor_threshold.png" align="center" width="600">

Here is a real-life example for a [Noctua NF-F12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm) fan:

```
Upper Non-Recoverable = 1800 rpm
Upper Critical = 1700 rpm
Upper Non-Critical = 1600 rpm
Lower Non-Critical = 200 rpm
Lower Critical = 100 rpm
Lower Non-Recoverable = 0 rpm
Max RPM = 1500 rpm
Min PRM = 300 rpm
max_level = 100 (i.e. 1500 rpm)
min_level = 35 (i.e. 500 rpm)
```

Notes:
  - Use the following `ipmitool` command to display the current IMPI sensor thresholds for fans:
    ```
    root@home:~# ipmitool sensor|grep FAN
    FAN1             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000  
    FAN2             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000  
    FAN3             | na         |            | na    | na        | na        | na        | na        | na        | na        
    FAN4             | 400.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000  
    FANA             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000  
    FANB             | 500.000    | RPM        | ok    | 0.000     | 100.000   | 200.000   | 1600.000  | 1700.000  | 1800.000  
    ```
  - Use the following `ipmitool` command to list assertion events:
    ```
    root@home:~# ipmitool sel list
       1 | 10/19/2023 | 05:15:35 PM CEST | Fan #0x46 | Lower Critical going low  | Asserted
       2 | 10/19/2023 | 05:15:35 PM CEST | Fan #0x46 | Lower Non-recoverable going low  | Asserted
       3 | 10/19/2023 | 05:15:38 PM CEST | Fan #0x46 | Lower Non-recoverable going low  | Deasserted
       4 | 10/19/2023 | 05:15:38 PM CEST | Fan #0x46 | Lower Critical going low  | Deasserted
       5 | 10/19/2023 | 05:20:59 PM CEST | Fan #0x46 | Lower Critical going low  | Asserted
    ```
  - Use the following `ipmitool` commands to specify all six sensor thresholds for FAN1:
    ```
    root@home:~# ipmitool sensor thresh FAN1 lower 0 100 200
    root@home:~# ipmitool sensor thresh FAN1 upper 1600 1700 1800
    ```
  - You can also edit and run `ipmi/set_ipmi_treshold.sh` to configure all IPMI sensor thresholds
  - If you install a new BMC firmware on your Super Micro motherboard you have to configure IPMI thresholds again
  - If you do not see fans when executing `ipmitool sensors`, you may want to reset the BMC to factory default using the Web UI or using `ipmitool mc reset cold`
  - Noctua specifies the variance of minimum and maximum fan rotational speeds (e.g. see the [specification of Noctua NF-F12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm/specification)). For example:

    - `Rotational speed (+/- 10%) 1500 RPM`: 1350-1650 RPM interval
    - `Min. rotational speed @ 20% PWM (+/-20%) 300 RPM`: 240-360 RPM interval
    
    Please note that [LNA](https://noctua.at/en/na-src10)/ULNA cables or [Y-cables](https://noctua.at/en/na-syc1) can modify the rotational speed calculations here and the required IPMI sensor thresholds too. 

You can read more about:

 - IPMI fan control: [STH Forums](https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/) and [TrueNAS Forums](https://www.truenas.com/community/threads/pid-fan-controller-perl-script.50908/)
 - Change IPMI sensors thresholds: [TrueNAS Forums](https://www.truenas.com/community/resources/how-to-change-ipmi-sensor-thresholds-using-ipmitool.35/)

### 7. Power management
If low noise and low heat generation are important attributes of your Linux box, then you may consider the following chapters.

#### 7.1 CPU
Most of the modern CPUs has multiple energy saving features. You can check your BIOS and enable them in order to minimize the heat generation.

Intel(R) CPUs:
 - Intel(R) Speed Shift Technology
 - Intel(R) SpeedStep
 - C-states
 - Boot performance mode

AMD(R) CPUs:
 - PowerNow!
 - Cool\`n\`quiet
 - Turbo Core

With this setup the CPU will change its base frequency and power consumption dynamically based on the load.

#### 7.2 SATA hard disks
In case of SATA hard disks, you may enable:

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

Important notes: 
 1. If you plan to spin down your hard disks or RAID array (i.e. put them to standby mode) you have to set up the configuration parameter `[HD zone] polling=` minimum twice bigger as the `spindown_time` specified here.
 2. In file `/etc/hdparm.conf` you must define HD names in `/dev/disk/by-id/...` form to avoid inconsistency.

### 8. Kernel modules
We need to load the following important Linux kernel modules:

 - [`coretemp`](https://www.kernel.org/doc/html/latest/hwmon/coretemp.html): temperature report for Intel(R) CPUs
 - [`k10temp`](https://docs.kernel.org/hwmon/k10temp.html): temperature report for AMD(R) CPUs
 - [`drivetemp`](https://www.kernel.org/doc/html/latest/hwmon/drivetemp.html): temperature report for SATA hard disks (available from kernel 5.6+ version)

Use `/etc/modules` file for persistent loading of these modules. 
Here are some sample HWMON file locations for these kernel modules:

 - `coretemp`: `/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input`
 - `k10temp`: `/sys/bus/pci/drivers/k10temp/0000*/hwmon/hwmon*/temp1_input`
 - `drivetemp`: `/sys/class/scsi_disk/0:0:0:0/device/hwmon/hwmon*/temp1_input`

Notes:
- `smfc` is able to find the proper HWMON file automatically for Intel(R) CPUs, AMD(R) CPUs, SATA drives, or NVMe drives, but users may also specify the files manually (see `hwmon_path=` parameter in the config file)
- Reading `drivetemp` module is the fastest way to get the temperature of the hard disks, and it can read temperature of the SATA hard disks even in standby mode, too. 

### 10. Installation
For the installation you need a root user. Download and extract a release file or clone the git repository first.
Then use the installation script `install.sh`, or copy the following files manually:

| File             | Installation folder   | Description                            |
|------------------|-----------------------|----------------------------------------|
| `smsc.service`   | `/etc/systemd/system` | systemd service definition file        |
| `smsc`           | `/etc/default`        | service command line options           |
| `smsc.py`        | `/opt/smfc`           | service (python program)               |
| `smsc.conf`      | `/opt/smfc`           | service configuration file             |
| `hddtemp_emu.sh` | `/opt/smfc`           | `hddtemp` emulation script (optional)  |

Notes:
  - any target folder can be used instead of `/opt`
  - `install.sh` will add all of your disks to your new `smfc.conf`, please remove the unnecessary itesm 

The service has the following command line options:

	root@home:~/opt/smfc# ./smfc.py --help
	usage: smfc.py [-h] [-c CONFIG_FILE] [-v] [-l {0,1,2,3,4}] [-o {0,1,2}]
	
	optional arguments:
  		-h, --help      show this help message and exit
  		-c CONFIG_FILE  configuration file
  		-v              show program's version number and exit
  		-l {0,1,2,3,4}  log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG
  		-o {0,1,2}      log output: 0-stdout, 1-stderr, 2-syslog(default)

You may configure logging output and logging level here, and these options can be specified in `/etc/default/smfc`in a persistent way.

### 10. Configuration file
Edit `/etc/smfc/smfc.conf` and specify your configuration parameters here:

```
#
#   smfc.conf (C) 2020-2025, Peter Sulyok
#   smfc 4.x service configuration parameters
#
#   Please read the documentation here: https://github.com/petersulyok/smfc
#

# Ipmi specific parameters.
[Ipmi]
# Path for ipmitool (str, default=/usr/bin/ipmitool)
command=/usr/bin/ipmitool 
# Delay time after changing IPMI fan mode (int, seconds, default=10)
fan_mode_delay=10
# Delay time after changing IPMI fan level (int, seconds, default=2)
fan_level_delay=2
# IPMI parameters for remote access (string, default='')
#remote_parameters=-U USERNAME -P PASSWORD -H HOST


# CPU zone: this fan controller works based on CPU(s) temperature.
[CPU zone]
# Fan controller enabled (bool, default=0)
enabled=1
# IPMI zone(s) (comma- or space-separated list of int, default=0))
ipmi_zone=0
# Calculation method for CPU temperatures (int, [0-minimum, 1-average, 2-maximum], default=1)
temp_calc=1
# Discrete steps in mapping of temperatures to fan level (int, default=6)
steps=6
# Threshold in temperature change before the fan controller reacts (float, C, default=3.0)
sensitivity=3.0
# Polling time interval for reading temperature (int, sec, default=2)
polling=2
# Minimum CPU temperature (float, C, default=30.0)
min_temp=30.0
# Maximum CPU temperature (float, C, default=60.0)
max_temp=60.0
# Minimum CPU fan level (int, %, default=35)
min_level=35
# Maximum CPU fan level (int, %, default=100)
max_level=100


# HD zone: this fan controller works based on HD(s) temperature.
[HD zone]
# Fan controller enabled (bool, default=0)
enabled=1
# IPMI zone(s) (comma- or space-separated list of int, default=1))
ipmi_zone=1
# Calculation of HD temperatures (int, [0-minimum, 1-average, 2-maximum], default=1)
temp_calc=1
# Discrete steps in mapping of temperatures to fan level (int, default=4)
steps=4
# Threshold in temperature change before the fan controller reacts (float, C, default=2.0)
sensitivity=2.0
# Polling interval for reading temperature (int, sec, default=10)
polling=10
# Minimum HD temperature (float, C, default=32.0)
min_temp=32.0
# Maximum HD temperature (float, C, default=46.0)
max_temp=46.0
# Minimum HD fan level (int, %, default=35)
min_level=35
# Maximum HD fan level (int, %, default=100)
max_level=100
# Names of the HDs (str multi-line list, default=)
# These names MUST BE specified in '/dev/disk/by-id/...' form!
hd_names=
# Path for 'smartctl' command (str, default=/usr/sbin/smartctl).
smartctl_path=/usr/sbin/smartctl
# Standby guard feature for RAID arrays (bool, default=0)
standby_guard_enabled=0
# Number of HDs already in STANDBY state before the full RAID array will be forced to it (int, default=1)
standby_hd_limit=1


# GPU zone: this fan controller works based on GPU(s) temperature.
[GPU zone]
# Fan controller enabled (bool, default=0)
enabled=0
# IPMI zone(s) (comma- or space-separated list of int, default=1))
ipmi_zone=1
# Calculation of GPU temperatures (int, [0-minimum, 1-average, 2-maximum], default=1)
temp_calc=1
# Discrete steps in mapping of temperatures to fan level (int, default=5)
steps=5
# Threshold in temperature change before the fan controller reacts (float, C, default=2.0)
sensitivity=2.0
# Polling interval for reading temperature (int, sec, default=10)
polling=2
# Minimum GPU temperature (float, C, default=40.0)
min_temp=40.0
# Maximum GPU temperature (float, C, default=70.0)
max_temp=70.0
# Minimum GPU zone fan level (int, %, default=35)
min_level=35
# Maximum GPU zone fan level (int, %, default=100)
max_level=100
# GPU device IDs (comma- or space-separated list of int, default=0)
# These are indices in nvidia-smi temperature report.
gpu_device_ids=0
# Path for 'nvidia-smi' command (str, default=/usr/bin/nvidia-smi).
nvidia_smi_path=/usr/bin/nvidia-smi


# Const zone: this fan controller does not read any temperature and sets constant fan level for IPMI zones(s).
[CONST zone]
# Fan controller enabled (bool, default=0)
enabled=0
# IPMI zone(s) (comma- or space-separated list of int, default=1))
ipmi_zone=1
# Polling interval for checking level and restting if needed (int, sec, default=30)
polling=30
# Constant fan level (int, %, default=50)
level=50
```

Important notes:
 1. `[HD zone} hd_names=`: This is a compulsory parameter, its value must be specified in `/dev/disk/by-id/...` form (the `/dev/sda` form is not persistent could be changed after a reboot).
 2. `[CPU zone] / [HD zone] min_level= / max_level=`: Check the stability of your fans and adjust the fan levels based on your measurement. As it was stated earlier, IPMI can switch back to full rotational speed if fans reach specific thresholds. You can collect real data about the behavior of your fans if you edit and run script `ipmi/fan_measurement.sh`. The script will set fan levels from 100% to 20% in 5% steps and results will be saved in the file `fan_result.csv`:

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

	My experience is that Noctua fans in my box are running stable in the 35-100% fan level interval. An additional user experience is (see [issue #12](https://github.com/petersulyok/smfc/issues/12)) when Noctua fans are paired with Ultra Low Noise Adapter the minimum stable fan level could go up to 45% (i.e. 35% is not stable).  

 3. `[CPU zone] / [HD zone] hwmon_path=`: This parameter is optional for Intel(R) CPUs, AMD(R) CPUs, SATA drives, and NVME drives (i.e., `smfc` can automatically identify the proper file locations), but may also be specified manually for special use cases. In case of SAS/SCSI hard disks (where `drivetemp` cannot be loaded) you can specify `hddtemp` value. You can use wild characters (`?,*`) in this parameter and `smfc` will do the path resolution automatically.
 4. `[Ipmi] remote_parameters=`: if you run `smfc` in a Virtual Machine (e.g. you run TrueNAS Scale in a Proxmox VM with direct access on controller or HDDs) you would like to access IPMI remotely on your host. With this parameter your can specify IPMI remote parameters added to each IPMI calls (see [issue #27](https://github.com/petersulyok/smfc/issues/27)). Please note that the host address here is the BMC network address (not the VM host address). 
 5. Several sample configuration files are provided for different scenarios in folder `./src/samples`. Please take a look on them, it could be a good starting point in the creation of your own configuration.

### 11. Automatic execution of the service
This `systemd` service can be started and stopped in the standard way. Do not forget to reload `systemd` configuration after a new installation or if you changed the service definition file:

```
systemctl daemon-reload
systemctl start smfc.service
systemctl stop smfc.service
systemctl restart smfc.service
systemctl status smfc.service
● smfc.service - Super Micro Fan Control
     Loaded: loaded (/etc/systemd/system/smfc.service; enabled; preset: enabled)
     Active: active (running) since Mon 2025-01-27 00:55:26 CET; 8h ago
   Main PID: 33361 (smfc.py)
      Tasks: 1 (limit: 76963)
     Memory: 8.1M
        CPU: 21.388s
     CGroup: /system.slice/smfc.service
             └─33361 /usr/bin/python3 /opt/smfc/smfc.py -c /opt/smfc/smfc.conf -l 3

Jan 27 09:10:44 nas smfc.service[33361]: CPU zone: new fan level > 48%/37.0C
Jan 27 09:10:48 nas smfc.service[33361]: CPU zone: new fan level > 35%/29.0C
Jan 27 09:10:54 nas smfc.service[33361]: CPU zone: new fan level > 48%/35.0C
```

If you are testing your configuration, you can start `smfc.py` directly in a terminal. Logging to the standard output and debug log level are useful in this case:

	cd /opt
	sudo smfc.py -o 0 -l 3

### 12. Checking the results and monitoring the logs
All messages will be logged to the specific output and the specific level.
With the help of command `journalctl` you can check logs easily. For example:

1. listing service logs of the last two hours:

		journalctl -u smfc --since "2 hours ago"

2. listing service logs from the last boot:

		journalctl -b -u smfc

## 13. FAQ

### Q: My fans are spinning up and loud. What's wrong?
Most probably, the rotational speed of a fan went above or below of a IPMI threshold and IPMI switched back that zone to full rotational speed.
You can check the current fan rotational speeds:

	ipmitool sdr

and you can also check IPMI event log and list assertion events:

```
root@home:~# ipmitool sel list
   1 | 10/19/2023 | 05:15:35 PM CEST | Fan #0x46 | Lower Critical going low  | Asserted
   2 | 10/19/2023 | 05:15:35 PM CEST | Fan #0x46 | Lower Non-recoverable going low  | Asserted
   3 | 10/19/2023 | 05:15:38 PM CEST | Fan #0x46 | Lower Non-recoverable going low  | Deasserted
   4 | 10/19/2023 | 05:15:38 PM CEST | Fan #0x46 | Lower Critical going low  | Deasserted
   5 | 10/19/2023 | 05:20:59 PM CEST | Fan #0x46 | Lower Critical going low  | Asserted
```

If the problematic fan (causing the alert) is identified then you must adjust its threshold. This process could take several adjustment cycle. Be patent :)
You may read [this chapter](https://github.com/petersulyok/smfc#7-ipmi-fan-control-and-sensor-thresholds) for more details. 

### Q: I would like to use constant fan rotational speed in one or both zones. How can I configure that?
You should configure the temperatures and levels with the same value. 

	min_temp=40
	max_temp=40
	min_level=60
	max_level=60

With this setup there will be a constant 60% fan level in the specific zone. The temperature value is ignored, `steps` parameter is also ignored.

### Q: I receive an error message "Cannot read hwmon*/temp1_input file". What is the problem?
The problem is that the specific file cannot be found in HWMON system. The potential reasons behind this issue could be:
 - `drivetemp` driver cannot support your disks (it support only SATA hard disks). In case of SAS/SCSI hard disks you can use `hddtemp` instead of `drivetemp`. See more details in [issue #21](https://github.com/petersulyok/smfc/issues/21).
 - Maybe you specified the `hwmon_path=` parameter manually and it contains an invalid path. You can correct it.

### Q: How does the author test/use this service?
The configuration is the following:

 - [Super Micro X11SCH-F motherboard](https://www.supermicro.com/en/products/motherboard/X11SCH-F)
 - [Intel Core i3-9300T CPU](https://ark.intel.com/content/www/us/en/ark/products/134875/intel-core-i39300t-processor-8m-cache-up-to-3-80-ghz.html)
 - 64 GB ECC DDR4 RAM
 - [Fractal Design Node 804 case](https://www.fractal-design.com/products/cases/node/node-804/black/), with separate chambers for the motherboard and the hard disks:
 
	<img src="https://www.legitreviews.com/wp-content/uploads/2014/05/fractal-design-node-804-vendor-fans.jpg" align="center" width="500">

 - Debian Linux LTS (actually bookworm with backported Linux kernel 6.5)
 - 8 x [WD Red 12TB (WD120EFAX)](https://shop.westerndigital.com/en-ie/products/outlet/internal-drives/wd-red-plus-sata-3-5-hdd#WD120EFAX) hard disks in ZFS RAID
 - 3 x [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm)  fans (FAN1, FAN2, FAN4) in CPU zone 
 - 2 x [Noctua NF-12 PWM](https://noctua.at/en/products/fan/nf-f12-pwm) fans (FANA, FANB) in HD zone

## 15. References
Further readings:

### Super Micro
 - [BMC IPMI User's Guide 1.1b (X10/X11/H11)](https://www.supermicro.com/manuals/other/IPMI_Users_Guide.pdf)
 - [BMC resources](https://www.supermicro.com/en/solutions/management-software/bmc-resources)
 - [IPMI Utilities](https://www.supermicro.com/en/solutions/management-software/ipmi-utilities)
 - [IPMICFG download](https://www.supermicro.com/wdl/utility/IPMICFG/)
 - [IPMICFG User's Guide 1.15 ](https://www.supermicro.com/wdl/utility/IPMICFG/IPMICFG_UserGuide.pdf)

### Forums/blogs
 - [\[STH forums\] Reference Material: Supermicro X9/X10/X11 Fan Speed Control](https://forums.servethehome.com/index.php?resources/supermicro-x9-x10-x11-fan-speed-control.20/)
   - [\[STH forums\] Addition to X9 motherboards](https://forums.servethehome.com/index.php?threads/supermicro-x9-x10-x11-fan-speed-control.10059/post-339801) 
 - [\[TrueNAS forums\] How To: Change IPMI Sensor Thresholds using ipmitool](https://www.truenas.com/community/resources/how-to-change-ipmi-sensor-thresholds-using-ipmitool.35/)
 - [\[TrueNAS forums\] Script to control fan speed in response to hard drive temperatures](https://www.truenas.com/community/threads/script-to-control-fan-speed-in-response-to-hard-drive-temperatures.41294/)
 - [\[Pcfe's blog\] Set fan thresholds on my Super Micro H11DSi-NT](https://blog.pcfe.net/hugo/posts/2018-08-14-epyc-ipmi-fans/)

### Linux kernel
 - [coretemp] [documentation](https://www.kernel.org/doc/html/latest/hwmon/coretemp.html)
 - [drivetemp] [documentation](https://www.kernel.org/doc/html/latest/hwmon/drivetemp.html) and its [GitHub respository](https://github.com/groeck/drivetemp)
 - How to install [hddtemp](https://www.cyberciti.biz/tips/howto-monitor-hard-drive-temperature.html) from a source package

### Similar projects
 - [\[GitHub\] Kevin Horton's nas_fan_control](https://github.com/khorton/nas_fan_control)
 - [\[GitHub\] Rob Urban's fork nas_fan control](https://github.com/roburban/nas_fan_control)
 - [\[GitHub\] sretalla's fork nas_fan control](https://github.com/sretalla/nas_fan_control)
 - [\[GitHub\] Andrew Gunnerson's ipmi-fan-control](https://github.com/chenxiaolong/ipmi-fan-control)

> Written with [StackEdit](https://stackedit.io/).
