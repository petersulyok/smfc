#!/bin/bash
#
#   docker-start.sh (C) 2023-2025, Peter Sulyok
#   This script will start `smfc` docker image.
#

docker run \
    -d \
    --rm \
    --log-driver=journald \
    --privileged=true \
    --name "smfc" \
    -v /dev:/dev:ro \
    -v /run:/run:ro \
    -v /etc/timezone:/etc/timezone:ro \
    -v /etc/localtime:/etc/localtime:ro \
    -v /opt/smfc/smfc.conf:/opt/smfc/smfc.conf:ro \
    -e SMFC_ARGS="-l 3" \
    petersulyok/smfc
