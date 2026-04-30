#!/usr/bin/env bash
#
#   docker-start-amd.sh (C) 2023-2026, Peter Sulyok
#   This script will start `smfc` AMD docker image.
#
docker run \
    -d \
    --rm \
    --device /dev/kfd \
    --device /dev/dri \
    --group-add video \
    --group-add render \
    --security-opt seccomp=unconfined \
    --log-driver=journald \
    --privileged=true \
    --name "smfc" \
    -v /dev:/dev:ro \
    -v /run:/run:ro \
    -v /etc/timezone:/etc/timezone:ro \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/smfc/smfc.conf:/etc/smfc/smfc.conf:ro \
    -e SMFC_ARGS="-l 3" \
    petersulyok/smfc:latest-amd