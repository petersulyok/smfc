# smfc in docker
This page describes the most important docker-specific information for `smfc`. Please visit the [GitHub repository](https://github.com/petersulyok/smfc) of `smfc` for more details or for reporting issues.

# Content
There are two images created for `smfc`:

- **Standard image** is an Alpine Linux-based image with the small image size, but the GPU zone is not supported.
- **GPU-enabled image** is a Debian-based image with larger image size, but the GPU zone is working (i.e. with the help of NVIDIA Container Toolkit, the `nvidia-smi` command is available in the container and can report GPU data running on the host).

Generic notes for the docker images:
  1. `smfc` is executed here as a simple foreground process (not as a `systemd` service).
  2. `ipmitool` and `smartctl` require read-only access to host's `/dev/` and `/run` folders and admin privilege.
  3. The `/sys` filesystem can be accessed in the container, but the proper kernel module (i.e. `coretemp`, `k10temp`, and `drivetemp`) needs to be loaded on host side.
  4. The container can send log messages to the host's `journald` daemon (as it is configured in _Usage chapter_), but feel free to configure [other logging drivers](https://docs.docker.com/config/containers/logging/configure/).
  5. IPMI remote access can be used (see `[IPMI] remote_parameters=-U USERNAME -P PASSWORD -H HOST` parameter in the configuration file) if IPMI interface is not accessible from docker container.
  6. Networking is enabled again for IPMI remote access. 

# Standard image
This image contains the following components: 
- `Alpine Linux` 3.22.1
- `Python` 3.12.11-r0
- `ipmitool` 1.8.19-r1
- `smartmontools` 7.5-r0

## Usage #1: docker CLI
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
  -v /etc/smfc/smfc.conf:/etc/smfc/smfc.conf:ro \
  -e SMFC_ARGS="-l 3" \
  petersulyok/smfc:latest
```
(sample script can be found [here](https://github.com/petersulyok/smfc/blob/main/docker/docker-start.sh)), 
and can be terminated:
```commandline
docker stop smfc  
```

## Usage #2: docker-compose (recommended)
`docker-compose` requires this file:
```
version: "2"
services:
  smfc:
    image: petersulyok/smfc:latest
    container_name: smfc
    logging:
        driver: journald
    privileged: true
    environment:
      - SMFC_ARGS=-l 3
    volumes:
      - /dev:/dev:ro
      - /run:/run:ro
      - /etc/smfc/smfc.conf:/etc/smfc/smfc.conf:ro
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

# GPU-enabled image
This image contains the following components: 
- `Debian Linux` 12 (slim)
- `Python` 3.11.2
- `ipmitool` 1.8.19-4
- `smartmontools` 7.3-1

## How to enable nvidia GPU in the docker image?
Install the NVIDIA driver and the NVIDIA Container Toolkit on your host as it is [described here](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). 
After a successful installation, execute the following commands:

```commandline
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
```

Restart is needed because NVIDIA Container Toolkit modified the `/etc/docker/daemon.json` file, and added the nvidia runtime parameters.

## Usage #1: docker CLI
The service can be started:
```
docker run \
    -d \
    --rm \
    --runtime=nvidia \
    --gpus all \
    --log-driver=journald \
    --privileged=true \
    --name "smfc" \
    -v /dev:/dev:ro \
    -v /run:/run:ro \
    -v /etc/timezone:/etc/timezone:ro \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/smfc/smfc.conf:/etc/smfc/smfc.conf:ro \
    -e SMFC_ARGS="-l 3" \
    petersulyok/smfc:latest-gpu
```
(sample script can be found [here](https://github.com/petersulyok/smfc/blob/main/docker/docker-start-gpu.sh)), 
and can be terminated:
```
docker stop smfc  
```

## usage #2: docker-compose (recommended)
`docker-compose` requires this file:
```
version: "2"
services:
  smfc:
    image: petersulyok/smfc:latest-gpu
    container_name: smfc
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]
    logging:
        driver: journald
    privileged: true
    environment:
      - SMFC_ARGS=-l 3
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all
    volumes:
      - /dev:/dev:ro
      - /run:/run:ro
      - /etc/smfc/smfc.conf:/etc/smfc/smfc.conf:ro
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
```
(sample yaml file can be found [here](https://github.com/petersulyok/smfc/blob/main/docker/docker-compose-gpu.yaml)), 
and docker image can be started/stopped this way:
```commandline
docker-compose -f docker-compose-gpu.yaml up -d
docker-compose -f docker-compose-gpu.yaml down
```

# Parameters for `smfc`
Use the following parameters to configure `smfc`:

| Parameter   | type                 | function                                                        |
|-------------|----------------------|-----------------------------------------------------------------|
| `SMFC_ARGS` | environment variable | command-line arguments for `smfc` (only for -o, -l parameters!) |
| `smfc.conf` | volume (ro)          | configuration file for `smfc`, mapped from host side            |

# Build image locally
The images can be built locally in the following way:
```commandline
git clone https://github.com/petersulyok/smfc.git
cd smfc
./docker/docker-build.sh 3.4.0
```
Please note that the dockerfile will install `smfc` from `pypi.org`, so the version must refer an official `smfc` release.

# Versions
See [CHANGELOG.md](https://github.com/petersulyok/smfc/blob/main/CHANGELOG.md) for more details:
  - **4.1.0** (2025.08.28): Updated to smfc 4.1.0 (Alpine 3.22.1/Debian 12) - beta releases deleted
  - **4.0.0** (2025.07.08): Updated to smfc 4.0.0 (Alpine 3.22/Debian 12) - beta releases deleted
  - **3.8.0** (2025.03.15): Updated to smfc 3.8.0 and (Alpine 3.20.6)
  - **3.7.0** (2025.01.27): Updated to smfc 3.7.0 and (Alpine 3.20.5) 
  - **3.6.0** (2024.12.12): Updated to smfc 3.6.0 and (Alpine 3.20.3)
  - **3.5.1** (2024.08.23): Updated to smfc 3.5.1 and (Alpine 3.20)
  - **3.5.0** (2024.03.21): Updated to smfc 3.5.0 and (Alpine 3.19)
  - **3.4.0** (2023.11.28): Documentation updated 
  - **3.3.0** (2023.11.19): Initial release
