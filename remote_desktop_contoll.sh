#!/bin/bash
# 自宅の PC で実行する。手元の PC から転送を受けるとき (transport_sign.* と組で使う)
#   ./remote_desktop_contoll.sh
# PC 用 Remote Gamepad ソフトは不要。src_ip は付けない (送信元は iPhone ではなく手元の PC になるため)
set -eu

NUMBER="${NUMBER:-40000}"   # 受信する UDP ポート。transport_sign.* の NUMBER と同じにする

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/ros_env.sh"
exec ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:="$NUMBER"
