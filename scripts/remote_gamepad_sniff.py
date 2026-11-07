#!/usr/bin/env python3
"""Remote Gamepad の通信内容を調べるためのパケットスニッファ。

使い方:
    sudo python3 tools/sniff.py [--src 192.168.3.x] [--seconds 60]

LAN 内の他ホスト (iPhone) からこの PC に届く UDP/TCP パケットを表示する。
ポート番号やペイロードの形式を調べるために使う。
"""
import argparse
import os
import socket
import struct
import time
from collections import Counter

ETH_P_ALL = 0x0003
IGNORE_PORTS = {22, 53, 5353, 1900, 41641}  # ssh, dns, mdns, ssdp, tailscale



def local_ips():
    """この PC の IP (既定の経路の IP と、環境変数 IP の Tailscale IP)。"""
    ips = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))  # UDP の connect は実際には送信しない
            ips.add(s.getsockname()[0])
        except OSError:
            pass
    if os.environ.get("IP"):
        ips.add(os.environ["IP"])
    return ips


LOCAL_IPS = local_ips()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="この送信元 IP だけ表示 (iPhone の IP)")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--max-bytes", type=int, default=96)
    ap.add_argument("--both", action="store_true",
                    help="この PC から送信したパケットも表示 (--src は送受信どちらにも一致)")
    args = ap.parse_args()

    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(ETH_P_ALL))
    s.settimeout(0.5)
    end = time.time() + args.seconds
    stats = Counter()
    print(f"capturing for {args.seconds:.0f}s ... iPhone のアプリを操作してください")

    while time.time() < end:
        try:
            frame, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        if addr[2] == socket.PACKET_OUTGOING and not args.both:
            continue
        if len(frame) < 34 or struct.unpack("!H", frame[12:14])[0] != 0x0800:
            continue  # IPv4 only
        ip = frame[14:]
        ihl = (ip[0] & 0x0F) * 4
        proto = ip[9]
        src = socket.inet_ntoa(ip[12:16])
        dst = socket.inet_ntoa(ip[16:20])
        if args.src and args.src not in ((src, dst) if args.both else (src,)):
            continue
        if not args.src and (src.startswith("127.") or src.startswith("172.17.")
                             or src in LOCAL_IPS):
            continue
        l4 = ip[ihl:]
        if proto == 17 and len(l4) >= 8:
            sport, dport = struct.unpack("!HH", l4[:4])
            payload = l4[8:]
            kind = "UDP"
        elif proto == 6 and len(l4) >= 20:
            sport, dport = struct.unpack("!HH", l4[:4])
            off = (l4[12] >> 4) * 4
            payload = l4[off:]
            kind = "TCP"
        else:
            continue
        if dport in IGNORE_PORTS or sport in IGNORE_PORTS:
            continue
        stats[(kind, src, dport)] += 1
        p = payload[: args.max_bytes]
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in p)
        print(f"{time.strftime('%H:%M:%S')} {kind} {src}:{sport} -> {dst}:{dport} "
              f"len={len(payload)}\n    hex : {p.hex(' ')}\n    text: {text}")

    print("\n=== summary (proto, src, dst_port): count ===")
    for k, v in stats.most_common(20):
        print(k, v)


if __name__ == "__main__":
    main()
