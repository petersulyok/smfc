#!/usr/bin/env bash
#
#   docker-push.sh (C) 2023-2025, Peter Sulyok
#   This script will push `smfc` docker image to dockerhub.
#
if [ -z "$1" ];
then
    echo "Usage: docker-push.sh version [version]"
    echo "Example: docker-push.sh 3.4.0 latest"
    exit 1
fi
docker image push petersulyok/smfc:$1
if [ -n "$2" ];
then
    docker image push petersulyok/smfc:$2
fi
