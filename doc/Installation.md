# Installation
This document describes how to install `smfc`, there are several ways.  

## 1. Manual installation
This project provides an installation script ([`bin/install.sh`](https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh))
which can install `smfc` from the GitHub repository (without cloning or downloading of the repository).
The installation script requires `curl` and `pip` commands and can be executed this way:

`curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash`

or if you want to preserve the existing configuration file, this way:

`curl --silent https://raw.githubusercontent.com/petersulyok/smfc/refs/heads/main/bin/install.sh|bash /dev/stdin --keep-config`

The installation script contains the following steps:

  - installs `smfc` package (with `pip`) to the `/usr/local` folder
  - creates `/etc/smfc` folder if needed
  - creates a new `/etc/smfc/smfc.conf` file and collects the names of all hard disks to the `hd_names=` configuration parameter (if no `--keep-config` option was specified) 
  - creates a new `/etc/default/smfc` file
  - creates a new `/etc/systemd/system/smfc.service` file

The default locations of the installation files: 

| Files           | Installation folder                               | Description                     |
|-----------------|---------------------------------------------------|---------------------------------|
| `smfc.service`  | `/etc/systemd/system`                             | systemd service definition file |
| `smfc`          | `/etc/default`                                    | service command line options    |
| `smfc.conf`     | `/etc/smfc`                                       | service configuration file      |
| `smfc package`  | `/usr/local/bin`<br/> `/usr/local/lib/python3.xx` | python package                  |


After running the installation script and editing your new configuration, `smfc` can be executed as a standard `systemd` service.

**Although this way of the installation is safe, it is not recommended.** Systemd-wide installation of Python packages with `pip` is not recommended by newest Linux distributions.

## 2. Docker installation
