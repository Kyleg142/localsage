#!/usr/bin/env bash

if [ "$1" = "build" ]; then
    docker image build -t python-localsage .
elif [ "$1" = "run" ]; then
    docker run -it --rm \
        --name localsage \
        --network host \
        -e OPENAI_API_KEY \
        -v /var/lib/LocalSage:/root/.local/share/LocalSage \
        python-localsage
elif [ "$1" = "uninstall" ]; then
    docker image rm python-localsage
else
    echo "Usage: ./sage.sh [build|run|uninstall]"
fi
exit 0
