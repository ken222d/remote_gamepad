#!/bin/bash

$NUMBER="40000"
eval "ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:=$NUMBER"
