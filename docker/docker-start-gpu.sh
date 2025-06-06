#!/usr/bin/env bash
#
#   docker-start-gpu.sh (C) 2023-2025, Peter Sulyok
#   This script will start `smfc` GPU enabled docker image.
#
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
