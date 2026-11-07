#!/bin/bash
# 手元の PC (Linux) で実行する。iPhone の入力を自宅の PC へ転送する
# 手元の PC が Windows のときは transport_sign.ps1 を使う (WSL ではパケットが見えない)
# 先に手元の PC で PC 用 Remote Gamepad ソフトを起動し、iPhone を接続しておく
# 使う設定 (remote_gamepad.env): IP, NUMBER, IPHONEIP
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"
require IP "自宅の PC の Tailscale IP"
require NUMBER "転送に使う UDP ポート"
require IPHONEIP "iPhone の IP"

exec sudo python3 "$DIR/scripts/remote_gamepad_forward.py" \
  --to "$IP:$NUMBER" --src "$IPHONEIP" -v
