#!/bin/bash
# 自宅の PC で実行する。手元の PC から転送を受けるとき (transport_sign.* と組で使う)
# PC 用 Remote Gamepad ソフトは不要。src_ip は付けない (送信元は iPhone ではなく手元の PC になるため)
# 使う設定 (remote_gamepad.env): NUMBER
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"
require NUMBER "転送に使う UDP ポート"

source "$DIR/ros_env.sh"
exec ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:="$NUMBER"
