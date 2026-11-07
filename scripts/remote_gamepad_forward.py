#!/usr/bin/env python3
"""iPhone "Remote Gamepad" のパケットを別ネットワークの車両 PC へ UDP で転送する。

手元の PC (iPhone と同じ Wi-Fi) で動かす。車両 PC とは Tailscale などの VPN でつなぐ。
Linux と Windows で動く (WSL は不可。Windows の Python を使う)。

    # 手元の PC: PC 用 Remote Gamepad ソフトを起動して iPhone を接続してから
    sudo python3 remote_gamepad_forward.py --to $IP:$NUMBER   # Linux
    python remote_gamepad_forward.py --to $IP:$NUMBER        # Windows (管理者)

    # 車両 PC: ブリッジを listen モードで起動する
    ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:=$NUMBER

- PC 用ソフトが受けたパケットを横から読む (sniff) ので、ソフトのポートが毎回変わってもよい
- 届いた 19 バイトをそのまま送る。順序の入れ替わりや途切れの処理は車両側のブリッジが行う
- 標準ライブラリだけで動く単体のファイル (手元の PC に ROS は不要)
"""
import argparse
import select
import socket
import struct
import sys
import time

# パケット形式は remote_gamepad_bridge.py と同じ。
# bridge は Linux 専用 (fcntl, uinput) で Windows では import できないので、ここに持つ
PKT_LEN = 19
PKT_HDR = bytes([0x13, 0x00, 0x01, 0x15])


def udp_payload_from_ip(ip):
    """IPv4 パケットから (src_ip, src_port, payload) を取り出す (UDP のみ)。"""
    if len(ip) < 28 or ip[0] >> 4 != 4 or ip[9] != 17:
        return None
    udp = (ip[0] & 0x0F) * 4
    sport, _, length = struct.unpack_from("!HHH", ip, udp)
    return socket.inet_ntoa(ip[12:16]), sport, ip[udp + 8:udp + length]


def local_ip():
    """既定の経路の自分の IP (Wi-Fi 側)。UDP の connect は実際には送信しない。"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def open_sniffer(bind_ip):
    """recv() -> IPv4 パケット (bytes) or None を返す受信関数とソケット。"""
    if sys.platform == "win32":
        # Windows: 生ソケット + SIO_RCVALL で bind_ip のインターフェースの全パケットを読む
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
        sock.bind((bind_ip, 0))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)

        def recv():
            return sock.recv(65535)
    else:
        # Linux: AF_PACKET で全インターフェースの受信パケットを読む
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))

        def recv():
            frame, addr = sock.recvfrom(2048)
            return None if addr[2] == socket.PACKET_OUTGOING else frame[14:]
    return sock, recv


def parse_host_port(text):
    host, sep, port = text.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise argparse.ArgumentTypeError("HOST:PORT の形式で指定してください")
    return host, int(port)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[1:]))
    ap.add_argument("--to", type=parse_host_port, required=True,
                    help="転送先 (車両 PC) の HOST:PORT。")
    ap.add_argument("--src", help="この送信元 IP (iPhone) からのパケットだけ転送する")
    ap.add_argument("--bind", help="Windows のみ: 読むインターフェースの IP (既定: Wi-Fi 側を自動)")
    ap.add_argument("-v", "--verbose", action="store_true", help="1 秒ごとに転送数を表示")
    args = ap.parse_args()

    me = args.bind or local_ip()
    try:
        rx, recv = open_sniffer(me)
    except PermissionError:
        sys.exit("生パケットを受信できません。sudo (Windows では管理者) で実行してください。")
    except OSError as e:
        sys.exit(f"生パケットを受信できません ({e})。"
                 "Windows では管理者で実行し、--bind に Wi-Fi の IP を指定してください。")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"forwarding Remote Gamepad packets ({me}) -> {args.to[0]}:{args.to[1]}", flush=True)

    peer, count, last_report = None, 0, time.monotonic()
    try:
        while True:
            r, _, _ = select.select([rx], [], [], 1.0)
            if r:
                ip = recv()
                got = None if ip is None else udp_payload_from_ip(ip)
                if got is not None:
                    src, sport, pkt = got
                    # Windows では自分の送信も見えるので送信元が自分のものは除く
                    if src != me and (not args.src or src == args.src) and \
                            len(pkt) == PKT_LEN and pkt[:4] == PKT_HDR:
                        try:
                            tx.sendto(pkt, args.to)
                            count += 1
                        except OSError as e:  # VPN 切断中など。復帰したら再開する
                            print(f"send failed: {e}", flush=True)
                        if (src, sport) != peer:
                            peer = (src, sport)
                            print(f"receiving from {src}:{sport}", flush=True)
            now = time.monotonic()
            if args.verbose and now - last_report >= 1.0:
                print(f"{count} packets/s", flush=True)
                count, last_report = 0, now
    except KeyboardInterrupt:
        pass
    finally:
        if sys.platform == "win32":
            rx.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        rx.close()
        tx.close()


if __name__ == "__main__":
    main()
