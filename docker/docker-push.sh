#!/usr/bin/env bash
#
#   docker-push.sh (C) 2023-2025, Peter Sulyok
#   This script will push `smfc` docker image to dockerhub.
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

# Push the new version tag to docker hub.
docker image push ${BUILD_IMAGE_NAME}:${BUILD_IMAGE_VERSION}

# Push the secondary version tag (i.e. latest) too, if specified.
if [ -n "$2" ];
then
    docker image push ${BUILD_IMAGE_NAME}:$2
fi
