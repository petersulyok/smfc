#!/usr/bin/env bash
#
#   docker-build.sh (C) 2023-2026, Peter Sulyok
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

# Execute build process:
# 1. standard alpine image.
DOCKER_BUILDKIT=1 docker build -t ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION" --build-arg BUILD_IMAGE_VERSION="$BUILD_IMAGE_VERSION" -f ./docker/Dockerfile-alpine .
# 2. debian-based image for nvidia-smi.
DOCKER_BUILDKIT=1 docker build -t ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-nvidia" --build-arg BUILD_IMAGE_VERSION="$BUILD_IMAGE_VERSION-nvidia" -f ./docker/Dockerfile-gpu-nvidia .
# 3. ubuntu-based AMD image for rocm-smi.
DOCKER_BUILDKIT=1 docker build -t ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-amd" --build-arg BUILD_IMAGE_VERSION="$BUILD_IMAGE_VERSION-amd" -f ./docker/Dockerfile-gpu-amd .

# Set secondary tag (i.e. latest) if specified.
if [ -n "$2" ];
then
    docker image tag ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION" ${BUILD_IMAGE_NAME}:$2
    docker image tag ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-nvidia" ${BUILD_IMAGE_NAME}:"$2-nvidia"
    docker image tag ${BUILD_IMAGE_NAME}:"$BUILD_IMAGE_VERSION-amd" ${BUILD_IMAGE_NAME}:"$2-amd"
fi
