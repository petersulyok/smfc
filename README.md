# smfc
Super Micro Fan Control for a Linux (home) server

## TL;DR

This is a `systemd service` running on Linux which is able to control fans of CPU and HD zones through IPMI functions on a Super Micro X9/X10/X11 motherboard.

### 1. Prerequisites
You need the following things: 
 - Super Micro X9/X10/X11 motherboard with BMC (AST2x00 chip)
 - python 3.6+
 - linux with systemd and kernel 5.6+ (`coretemp` and `drivetemp` kernel modules for CPU and HD temperatures)
 - `bash`
 - `ipmitool`
 - optional: `smartmontools` for feature *standby guard* 

### 2. Installation and configuration
 1. Setup the IPMI threshold values for your fans (see script `ipmi/set_ipmi_threshold.sh`). 
 2. For the efficient power consumption and low heat generation you may consider to enable:

	 - Intel(R) Speed Shift Technology and/or Intel(R) SpeedStep features in BIOS for the CPU
	 - advanced power management and sleep timer for SATA hard disks (`hdparm`)

 3. Install kernel modules (`coretemp` and `drivetemp`)
 4. Installation can be executed by running script `install.sh`. Default target directory is `/opt/smfc`. Some other files will be installed to folders `/etc/default` and `/etc/systemd/system` too.
 5. Edit configuration file `/opt/smfc/smfc.conf` based on your installation (fans and HDs).
 6. Edit command line options in `/etc/default/smfc`.
 7. Start the systemd service

	    systemctl daemon-reload
	    systemctl start smfc.service

 8. Check result in system log

