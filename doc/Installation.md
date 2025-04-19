# Installation
This document describes how to install `smfc`, there are several ways.  

## 1. Manual installation
This project provides an installation script ([`bin/install.sh`](https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh))
which can install `smfc` from the GitHub repository (without cloning or downloading of the repository).
The installation script requires `curl` and `pip` commands and can be executed this way:

`curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash`

or if you want to preserve your existing configuration file, this way:

`curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash /dev/stdin --keep-config`

The installation script contains the following steps:

  - installation of `smfc` package (with `pip`) to the `/usr/local` folder
  - creation of `/etc/smfc` folder (if needed)
  - if no `--keep-config` option was specified:
    - saving of the existing configuration file
    - creation of a new `/etc/smfc/smfc.conf` file
    - listing all of your hard disks in the `hd_names=` configuration parameter  
  - creation of a new `/etc/default/smfc` file
  - creation of a new `/etc/systemd/system/smfc.service` file

The default locations of the installation files: 

| Files           | Installation folder                               | Description                     |
|-----------------|---------------------------------------------------|---------------------------------|
| `smfc.service`  | `/etc/systemd/system`                             | systemd service definition file |
| `smfc`          | `/etc/default`                                    | service command line options    |
| `smfc.conf`     | `/etc/smfc`                                       | service configuration file      |
| `smfc package`  | `/usr/local/bin`<br/> `/usr/local/lib/python3.xx` | python package                  |

Final steps after a successful installation:
  - PLEASE EDIT YOUR CONFIGURATION FILE!!
  - install program dependencies (`ipmitool` and `smartctl`)
  - load proper kernel modules (`coretemp` or `k10temp` and `drivetemp`)
  - start `smfc` as a standard `systemd` service:

    ```
    systemctl daemon-reload
    systemctl enable --now smfc
    systemctl status smfc
    ● smfc.service - Super Micro Fan Control
         Loaded: loaded (/etc/systemd/system/smfc.service; enabled; preset: enabled)
         Active: active (running) since Fri 2025-04-18 16:32:36 CEST; 11h ago
       Main PID: 127141 (smfc)
          Tasks: 1 (limit: 76924)
         Memory: 10.3M
            CPU: 54.921s
         CGroup: /system.slice/smfc.service
                 └─127141 /usr/bin/python3 /usr/local/bin/smfc -c /etc/smfc/smfc.conf -l 3
    
    Apr 19 03:58:19 nas smfc.service[127141]: CPU zone: new fan level > 48%/35.0C
    Apr 19 03:58:23 nas smfc.service[127141]: CPU zone: new fan level > 35%/31.0C
    Apr 19 03:58:27 nas smfc.service[127141]: CPU zone: new fan level > 48%/36.0C
    Apr 19 03:58:31 nas smfc.service[127141]: CPU zone: new fan level > 35%/32.0C
    Apr 19 03:58:49 nas smfc.service[127141]: CPU zone: new fan level > 48%/35.0C
    ```

**Although this is a safe installation method, it is not recommended**, since manual systemd-wide installation of Python packages with `pip` is not recommended by newest Linux distributions. 
This is the reason why `pip` generates a warning during the installation. 

## 2. Docker installation
`smfc` is also available as a docker image, see more details in [Docker.md](../docker/Docker.md). In this scenario, your job is only to provide your configuration file and start the container. 

This type of installation can work if the docker image can access the temperature sources of the host (e.g. HWMON files in `/sys`).
If the IPMI interface of the host is not accessible, you can still use IPMI remote access:

    [Ipmi]
    ...
    # IPMI parameters for remote access (HOST is the BMC network address).
    #remote_parameters=-U USERNAME -P PASSWORD -H HOST

Docker installation could be useful for special situations, for example, TrueNas Scale installed in a Proxmox VM with HW passthrough.
