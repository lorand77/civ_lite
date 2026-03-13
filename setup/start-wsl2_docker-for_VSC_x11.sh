#!/bin/bash

# run it on WSL2 from the project dir    /mnt/c/Users/username/path/to/project
CONTAINER_NAME=VSC-X11-$(basename $(pwd))

docker run -d \
  --name $CONTAINER_NAME \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
  -e XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
  -e PULSE_SERVER=$PULSE_SERVER \
  --user ubuntu \
  -v ./:/workspace \
  ubuntu \
  sleep infinity
