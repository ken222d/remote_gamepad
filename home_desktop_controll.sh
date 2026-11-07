#!/bin/bash
# 自宅の PC で実行する。iPhone が自宅の PC と同じ Wi-Fi にあるとき (転送なし)
# 先に自宅の PC で PC 用 Remote Gamepad ソフトを起動し、iPhone を接続しておく
set -eu

IPHONEIP="${IPHONEIP:-x.x.x.x}"   # iPhone の IP (環境変数があればそちらを使う)

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/ros_env.sh"
exec ros2 launch remote_gamepad remote_gamepad.launch.py src_ip:="$IPHONEIP"
