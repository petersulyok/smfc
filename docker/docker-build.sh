#!/bin/bash
#
#   docker-build.sh (C) 2023-2025, Peter Sulyok
#   This script will build `smfc` docker image.
#
set -e
if [ "$1" == "" ];
then
   echo "Usage: docker-build.sh version"
   echo "Example: docker-build.sh 3.4.0"
   exit 1
fi
version=$1
docker build . --debug -t petersulyok/smfc:$version --label "org.opencontainers.image.version=$version" -f Dockerfile
docker tag petersulyok/smfc:$version petersulyok/smfc:latest
