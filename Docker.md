# smfc in docker
This is a docker image for `smfc`. Please visit the [GitHub repository](https://github.com/petersulyok/smfc) of `smfc` for more details or for reporting issues.

# Content
This image contains the following components: 
- `Alpine Linux` 3.21.0
- `Python` 3.12.8
- `ipmitool` 1.8.19
- `smartmontools` 7.4
- `hddtemp` 0.4.3 (forked here https://github.com/vitlav/hddtemp.git) 

Some further notes:
  1. `smfc` will be executed as a simple foreground process here (not as a `systemd` service).
  2. Currently, the image does not require any networking, it is disabled.
  3. `ipmitool` and `smartctl` require read-only access to host's `/dev/` and `/run` folders and admin privilege.
  4. The `/sys` filesystem can be accessed in the container, but the proper kernel module (i.e. `coretemp`, `k10temp`, or `drivetemp`) needs to be loaded on host side.
  5. The container can send log messages to the host's `journald` daemon (as it is configured in _Usage chapter_), but feel free to configure [other logging drivers](https://docs.docker.com/config/containers/logging/configure/). 

# Usage 

## docker CLI
The service can be started:
```
docker run \
  -d \
  --rm \
  --log-driver=journald \
  --privileged=true \
  --name "smfc" \
  -v /dev:/dev:ro \
  -v /run:/run:ro \
  -v /etc/timezone:/etc/timezone:ro
  -v /etc/localtime:/etc/localtime:ro
  -v /opt/smfc/smfc.conf:/opt/smfc/smfc.conf:ro \
  -e SMFC_ARGS="-l 3" \
  petersulyok/smfc
```
(sample script can be found [here](https://github.com/petersulyok/smfc/blob/main/docker/docker-start.sh)), 
and can be terminated:
```
docker stop smfc  
```

## docker-compose (recommended)
`docker-compose` requires this file:
```
version: "2"
services:
  smfc:
    image: petersulyok/smfc
    container_name: smfc
    network_mode: none
    logging:
        driver: journald
    privileged: true
    environment:
      - SMFC_ARGS=-l 3
    volumes:
      - /dev:/dev:ro
      - /run:/run:ro
      - /opt/smfc/smfc.conf:/opt/smfc/smfc.conf:ro
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
```
(sample yaml file can be found [here](https://github.com/petersulyok/smfc/blob/main/docker/docker-compose.yaml)), 
and docker image can be started/stopped this way:
```commandline
docker-compose up -d
docker-compose down
```

## Parameters for `smfc`
Use the following parameters to configure `smfc`:

| Parameter   | type                 | function                                                        |
|-------------|----------------------|-----------------------------------------------------------------|
| `SMFC_ARGS` | environment variable | command-line arguments for `smfc` (only for -o, -l parameters!) |
| `smfc.conf` | volume (ro)          | configuration file for `smfc`, mapped from host side            |

# Build image locally
The image can be built locally in the following way:
```commandline
git clone https://github.com/petersulyok/smfc.git
cd smfc
./docker/docker-build.sh 3.4.0 
```

# Versions
  - **3.6.0** (2024.12.12): Updated to smfc version 3.6.0 and alpine 3.21
  - **3.5.1** (2024.08.23): Updated to smfc version 3.5.1 and alpine 3.20
  - **3.5.0** (2024.03.21): Updated to smfc version 3.5.0 and alpine 3.19
  - **3.4.0** (2023.11.28): Documentation updated 
  - **3.3.0** (2023.11.19): Initial release
