#!/usr/bin/env bash
#
#   docker-build.sh (C) 2023-2025, Peter Sulyok
#   This script will build `smfc` docker image.
#

# If no version parameter specified.
if [ -z "$1" ];
then
    echo "Usage: docker-build.sh version [version]"
    echo "Example: docker-build.sh 3.4.0 latest"
    exit 1
fi

# Set name and version variables.
BUILD_IMAGE_VERSION=$1
BUILD_IMAGE_NAME="petersulyok/smfc"

# Execute build process for both images.
DOCKER_BUILDKIT=1 docker build -t ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION" --build-arg BUILD_IMAGE_VERSION="$BUILD_IMAGE_VERSION" -f ./docker/Dockerfile-alpine .
DOCKER_BUILDKIT=1 docker build -t ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-gpu" --build-arg BUILD_IMAGE_VERSION="$BUILD_IMAGE_VERSION-gpu" -f ./docker/Dockerfile-debian .

# Set secondary tag (i.e. latest) if specified.
if [ -n "$2" ];
then
    docker image tag ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION" ${BUILD_IMAGE_NAME}:$2
    docker image tag ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-gpu" ${BUILD_IMAGE_NAME}:"$2-gpu"
fi
