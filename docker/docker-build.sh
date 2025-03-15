#!/usr/bin/env bash
#
#   docker-build.sh (C) 2023-2025, Peter Sulyok
#   This script will build `smfc` docker image.
#

if [ -z "$1" ];
then
    echo "Usage: docker-build.sh version [version]"
    echo "Example: docker-build.sh 3.4.0 latest"
    exit 1
fi
docker image build . --debug -t petersulyok/smfc:$1 --label "org.opencontainers.image.version=$1" -f Dockerfile
if [ -n "$2" ];
then
    docker image tag petersulyok/smfc:$1 petersulyok/smfc:$2
fi
