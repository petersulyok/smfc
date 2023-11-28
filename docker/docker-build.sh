#!/bin/bash
#
#   docker-build.sh (C) 2023, Peter Sulyok
#   This script will build `smfc` image.
#

if [ "$1" == "" ]; then
   echo "Usage: docker-build.sh version"
   echo "Example: docker-build.sh 3.4.0"
   exit -1
fi
version=$1
docker build . -t petersulyok/smfc:$version -t petersulyok/smfc:latest --label "org.opencontainers.image.version=$version" -f Dockerfile
#docker push  petersulyok/smfc:$version

