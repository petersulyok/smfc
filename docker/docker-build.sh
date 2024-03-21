#!/bin/bash
#
#   docker-build.sh (C) 2023-2024, Peter Sulyok
#   This script will build `smfc` image.
#
set -e
if [ "$1" == "" ];
then
   echo "Usage: docker-build.sh version"
   echo "Example: docker-build.sh 3.4.0"
   exit 1
fi
version=$1
docker build . -t petersulyok/smfc:$version --label "org.opencontainers.image.version=$version" -f Dockerfile
docker tag petersulyok/smfc:$version petersulyok/smfc:latest
docker push petersulyok/smfc --all-tags
