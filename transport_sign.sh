#!/bin/bash
# 手元の PC (Linux) で実行する。iPhone の入力を自宅の PC へ転送する
# 先に手元の PC で PC 用 Remote Gamepad ソフトを起動し、iPhone を接続しておく
set -eu

IP="${IP:-x.x.x.x}"            # 自宅の PC の Tailscale IP (自宅の PC で tailscale ip -4)
NUMBER="${NUMBER:-x}"             # remote_desktop_contoll.sh の NUMBER と同じにする
IPHONEIP="${IPHONEIP:-x.x.x.x}"   # iPhone の IP (手元の Wi-Fi での IP)

DIR="$(cd "$(dirname "$0")" && pwd)"
exec sudo python3 "$DIR/scripts/remote_gamepad_forward.py" \
  --to "$IP:$NUMBER" --src "$IPHONEIP" -v