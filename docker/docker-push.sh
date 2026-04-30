#!/usr/bin/env bash
#
#   docker-push.sh (C) 2023-2026, Peter Sulyok
#   This script will push `smfc` docker images to dockerhub.
#

# If no version parameter specified.
if [ -z "$1" ];
then
    echo "Usage: docker-push.sh version [version]"
    echo "Example: docker-push.sh 3.4.0 latest"
    exit 1
fi

# Set name and version variables.
BUILD_IMAGE_VERSION=$1
BUILD_IMAGE_NAME="petersulyok/smfc"

# Push all three image variants.
docker image push ${BUILD_IMAGE_NAME}:${BUILD_IMAGE_VERSION}
docker image push ${BUILD_IMAGE_NAME}:${BUILD_IMAGE_VERSION}-nvidia
docker image push ${BUILD_IMAGE_NAME}:${BUILD_IMAGE_VERSION}-amd

# Push secondary version tags (e.g. latest) if specified.
if [ -n "$2" ];
then
    docker image push ${BUILD_IMAGE_NAME}:$2
    docker image push ${BUILD_IMAGE_NAME}:$2-nvidia
    docker image push ${BUILD_IMAGE_NAME}:$2-amd
fi