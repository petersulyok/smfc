#!/bin/bash
#
#   docker-push.sh (C) 2023-2024, Peter Sulyok
#   This script will push `smfc` docker image to dockerhub.
#
set -e
docker push petersulyok/smfc --all-tags
