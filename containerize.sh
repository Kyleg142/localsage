#!/usr/bin/env bash

IMAGE_NAME="python-localsage"
CONTAINER_NAME="localsage"
HOST_DATA_DIR="/var/lib/LocalSage"
CONTAINER_DATA_DIR="/root/.local/share/LocalSage"

if [[ "$1" == "build" ]]; then
    docker image build -t python-localsage .
elif [[ "$1" == "run" ]]; then
    if [[ "$2" == "local" ]]; then
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            NET_CONFIG="--network host"
        else
            NET_CONFIG="--add-host=host.docker.internal:host-gateway"
        fi
    fi
    docker run -it --rm \
        --name $CONTAINER_NAME \
        $NET_CONFIG \
        -e OPENAI_API_KEY \
        -v "$HOST_DATA_DIR:$CONTAINER_DATA_DIR" \
        $IMAGE_NAME
elif [[ "$1" = "uninstall" ]]; then
    docker image rm $IMAGE_NAME
else
    echo "Usage: ./sage.sh [build|run|uninstall]"
    exit 1
fi
exit 0
