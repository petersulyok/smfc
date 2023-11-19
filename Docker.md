# smfc in docker
This file explains how `smfc` image can be executed in docker environment.

Visit the [GitHub repository](https://github.com/petersulyok/smfc) of `smfc` for more details or reporting issues.

# Usage 

## docker CLI
```
$ docker run \
    -d \
    --rm \
    --log-driver=journald \
    --privileged=true \
    --name "smfc" \
    -v /dev:/dev:ro \
    -v /run:/run:ro \
    -v /opt/smfc/smfc.conf:/opt/smfc/smfc.conf:ro \
    -e SMFC_ARGS="-l 3" \
    petersulyok/smfc
```
(see this example in `docker/docker-start.sh`)

## docker-compose
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
(see this example in `docker/docker-compose.yaml`)

## Parameters
Use the following parameters to configure `smfc`:

| Parameter   | type                 | function                                             |
|-------------|----------------------|------------------------------------------------------|
| `SMFC_ARGS` | environment variable | command-line arguments for `smfc` (-o, -l)           |
| `smfc.conf` | volume               | configuration file for `smfc`, mapped from host side |

Please also note:
1. this image should be executed in `privileged` mode with access of `/dev` and `/run` folders
because of the tools (i.e. `ipmitool`, `smartctl` and `hddtemp`)
2. `smfc` log messages are forwarded to the host's `journald` daemon. Feel free to use a different [log driver](https://docs.docker.com/config/containers/logging/configure/) for docker.

