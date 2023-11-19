#!/bin/bash

version="3.3.0"

docker build . -t petersulyok/smfc:$version -t petersulyok/smfc:latest --label "org.opencontainers.image.version=$version" -f Dockerfile
