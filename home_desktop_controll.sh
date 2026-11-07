#!/bin/bash

$IPHONEIP="192.168.x.x"
eval "ros2 launch remote_gamepad remote_gamepad.launch.py src_ip:=$IPHONEIP"
