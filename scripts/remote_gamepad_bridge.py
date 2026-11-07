#!/usr/bin/env python3
"""iPhone "Remote Gamepad" (Wi-Fi/UDP) -> 仮想ゲームパッド (/dev/uinput)

UDP で届く入力を Linux の仮想ゲームパッドとして流すので、
実機と同じく `ros2 run joy joy_node` でそのまま /joy が出る。

    # 既定 (sniff モード): PC 用 Remote Gamepad ソフトは起動したままでよい。
    # 届いたパケットを横から読むので、ソフトがポートを毎回変えても追従する。
    sudo python3 remote_gamepad_bridge.py
    ros2 run joy joy_node --ros-args -p device_name:="Remote Gamepad ROS"

    # listen モード: PC 用ソフトなしで、指定ポートを自分で受信する
    sudo python3 remote_gamepad_bridge.py --mode listen --port $NUMBER

パケット形式 (19 bytes, little endian, 実測から解析):
    [0]    0x13 (長さ)        [1:4] 00 01 15 (ヘッダ)
    [4:6]  uint16 シーケンス  [6]   0x01
    [7:9]  uint16 ボタン (XInput wButtons と同じビット配置)
    [9:17] int16 x4  LX, LY, RX, RY  (上・右が +)
    [17]   uint8 LT  [18] uint8 RT
標準ライブラリのみ使用 (python-evdev 不要)。
"""
import argparse
import fcntl
import os
import select
import signal
import socket
import struct
import sys
import time

# ---- linux/input-event-codes.h ----
EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0
BTN_A, BTN_B, BTN_X, BTN_Y = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR = 0x136, 0x137
BTN_SELECT, BTN_START, BTN_MODE = 0x13A, 0x13B, 0x13C
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0, 1, 2, 3, 4, 5
ABS_HAT0X, ABS_HAT0Y = 0x10, 0x11

# ---- linux/uinput.h ----
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_GET_SYSNAME = 0x8040552C  # _IOC(_IOC_READ, 'U', 44, 64)
ABS_CNT = 0x40
BUS_USB = 0x03

# アプリが送るボタンビット (XInput wButtons と同じ)
APP_BITS = {
    "UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020, "LS": 0x0040, "RS": 0x0080,
    "LB": 0x0100, "RB": 0x0200, "GUIDE": 0x0400,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}
STICK = (-32768, 32767, 16, 128)   # (min, max, fuzz, flat)
TRIG = (0, 255, 0, 0)
HAT = (-1, 1, 0, 0)

# ---- レイアウト ----
# joy_node から見たボタン/軸の番号は evdev のコード順で決まる。
# ここでは「並べたい順」に昇順のコードを割り当てることで /joy の index を決める。
#   buttons: [(evdev code, ソース)]   ソース: APP_BITS のキー / "LT" "RT" (トリガーのデジタル化)
#   axes:    [(evdev code, ソース, 範囲)] ソース: LX LY RX RY LT RT HATX HATY
LAYOUTS = {
    # formula_ws controller_node (controller_node.hpp の Axes / Buttons) と同じ並び。
    # PS コントローラを汎用 HID として読んだときの並び。
    #   buttons: Cross Circle Triangle Square L1 R1 L2 R2 Share Options PS L3 R3
    #   axes   : L_x L_y R_x L2 R2 R_y 十字左右 十字上下
    "ps": {
        "buttons": [(0x130 + i, src) for i, src in enumerate(
            ["A", "B", "Y", "X", "LB", "RB", "LT", "RT", "BACK", "START", "GUIDE", "LS", "RS"])],
        "axes": [
            (ABS_X, "LX", STICK), (ABS_Y, "LY", STICK), (ABS_Z, "RX", STICK),
            (ABS_RX, "LT", TRIG), (ABS_RY, "RT", TRIG), (ABS_RZ, "RY", STICK),
            (ABS_HAT0X, "HATX", HAT), (ABS_HAT0Y, "HATY", HAT),
        ],
    },
    # 本物の Xbox 360 pad (xpad ドライバ) と同じ並び
    #   buttons: A B X Y LB RB Back Start Guide LS RS
    #   axes   : LX LY LT RX RY RT 十字左右 十字上下
    "xbox": {
        "buttons": [(BTN_A, "A"), (BTN_B, "B"), (BTN_X, "X"), (BTN_Y, "Y"),
                    (BTN_TL, "LB"), (BTN_TR, "RB"), (BTN_SELECT, "BACK"),
                    (BTN_START, "START"), (BTN_MODE, "GUIDE"),
                    (BTN_THUMBL, "LS"), (BTN_THUMBR, "RS")],
        "axes": [
            (ABS_X, "LX", STICK), (ABS_Y, "LY", STICK), (ABS_Z, "LT", TRIG),
            (ABS_RX, "RX", STICK), (ABS_RY, "RY", STICK), (ABS_RZ, "RT", TRIG),
            (ABS_HAT0X, "HATX", HAT), (ABS_HAT0Y, "HATY", HAT),
        ],
    },
}
TRIGGER_BUTTON_THRESHOLD = 128  # L2/R2 をボタンとして押したとみなす値

PKT_LEN = 19
PKT_HDR = bytes([0x13, 0x00, 0x01, 0x15])


class VirtualGamepad:
    """LAYOUTS に従ったボタン・軸を持つ uinput 仮想ゲームパッド。"""

    def __init__(self, name, vendor, product, version, layout):
        self.layout = LAYOUTS[layout]
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for code, _ in self.layout["buttons"]:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
        absmax, absmin = [0] * ABS_CNT, [0] * ABS_CNT
        absfuzz, absflat = [0] * ABS_CNT, [0] * ABS_CNT
        for code, _, (lo, hi, fuzz, flat) in self.layout["axes"]:
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            absmin[code], absmax[code] = lo, hi
            absfuzz[code], absflat[code] = fuzz, flat
        # struct uinput_user_dev
        dev = struct.pack(
            "80sHHHHi" + "i" * (ABS_CNT * 4),
            name.encode()[:79], BUS_USB, vendor, product, version, 0,
            *absmax, *absmin, *absfuzz, *absflat,
        )
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.state = {}
        self.nodes = self._open_permissions()

    def _open_permissions(self, wait=2.0):
        """作成したデバイスノードを一般ユーザー (joy_node) から読めるようにする。"""
        buf = fcntl.ioctl(self.fd, UI_GET_SYSNAME, bytes(64))
        sysdir = "/sys/devices/virtual/input/" + buf.split(b"\0", 1)[0].decode()
        nodes, deadline = [], time.monotonic() + wait
        while time.monotonic() < deadline:
            names = [n for n in os.listdir(sysdir) if n.startswith(("event", "js"))]
            nodes = ["/dev/input/" + n for n in names if os.path.exists("/dev/input/" + n)]
            if names and len(nodes) == len(names):
                break
            time.sleep(0.05)
        time.sleep(0.2)  # udev が権限を設定し終わるのを待ってから上書き
        for n in nodes:
            os.chmod(n, 0o666)
        return nodes

    def _emit(self, etype, code, value):
        sec, usec = divmod(int(time.time() * 1e6), 1_000_000)
        os.write(self.fd, struct.pack("llHHi", sec, usec, etype, code, value))

    def update(self, buttons, lx, ly, rx, ry, lt, rt):
        pressed = {k: bool(buttons & bit) for k, bit in APP_BITS.items()}
        pressed["LT"] = lt >= TRIGGER_BUTTON_THRESHOLD
        pressed["RT"] = rt >= TRIGGER_BUTTON_THRESHOLD
        # evdev では Y 軸は下が + なので反転する (xpad と同じ)
        axis = {
            "LX": lx, "LY": ~ly, "RX": rx, "RY": ~ry, "LT": lt, "RT": rt,
            "HATX": pressed["RIGHT"] - pressed["LEFT"],
            "HATY": pressed["DOWN"] - pressed["UP"],
        }
        new = {(EV_KEY, code): int(pressed[src]) for code, src in self.layout["buttons"]}
        new.update({(EV_ABS, code): axis[src] for code, src, _ in self.layout["axes"]})
        changed = False
        for key, val in new.items():
            if self.state.get(key) != val:
                self._emit(key[0], key[1], val)
                self.state[key] = val
                changed = True
        if changed:
            self._emit(EV_SYN, SYN_REPORT, 0)

    def neutral(self):
        self.update(0, 0, 0, 0, 0, 0, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


def udp_payload_from_frame(frame):
    """Ethernet フレームから (src_ip, dst_port, payload) を取り出す (IPv4/UDP のみ)。"""
    if len(frame) < 42 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
        return None
    ihl = (frame[14] & 0x0F) * 4
    udp = 14 + ihl
    sport, dport, length = struct.unpack_from("!HHH", frame, udp)
    return socket.inet_ntoa(frame[26:30]), sport, dport, frame[udp + 8:udp + length]


def parse(pkt):
    if len(pkt) != PKT_LEN or pkt[:4] != PKT_HDR:
        return None
    seq, _, buttons, lx, ly, rx, ry, lt, rt = struct.unpack("<HBH4hBB", pkt[4:])
    return seq, buttons, lx, ly, rx, ry, lt, rt


def open_receiver(args):
    """(socket, recv関数) を返す。recv() -> (src_ip, src_port, payload) or None"""
    if args.mode == "listen":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((args.bind, args.port))
        except OSError as e:
            sys.exit(f"UDP {args.port} を開けません ({e})。"
                     "PC 用ソフトかブリッジがすでに起動していませんか？ (--mode sniff を推奨)")

        def recv():
            pkt, addr = sock.recvfrom(64)
            return addr[0], addr[1], pkt
        desc = f"listening UDP {args.bind}:{args.port}"
    else:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))

        def recv():
            frame, addr = sock.recvfrom(2048)
            if addr[2] == socket.PACKET_OUTGOING:
                return None
            r = udp_payload_from_frame(frame)
            if r is None or (args.port and r[2] != args.port):
                return None
            return r[0], r[1], r[3]
        desc = "sniffing Remote Gamepad UDP packets on " + (
            f"port {args.port}" if args.port else "any port")
    return sock, recv, desc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[1:]))
    ap.add_argument("--mode", choices=["sniff", "listen"], default="sniff",
                    help="sniff: PC 用ソフトと共存して受信 (既定) / listen: 自分でポートを開く")
    ap.add_argument("--port", type=int, default=0,
                    help="UDP ポート。sniff では 0=自動 (既定)、listen では必須")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--src", help="この送信元 IP (iPhone) からのパケットだけ受け付ける")
    ap.add_argument("--timeout", type=float, default=0.5,
                    help="この秒数パケットが来なければ入力をニュートラルに戻す")
    ap.add_argument("--name", default="Remote Gamepad ROS",
                    help="仮想デバイス名 (joy_node の device_name に指定する)")
    ap.add_argument("--layout", choices=sorted(LAYOUTS), default="ps",
                    help="/joy のボタン・軸の並び。ps: formula_ws controller_node と同じ (既定)"
                         " / xbox: Xbox 360 pad と同じ")
    ap.add_argument("--xbox-id", action="store_true",
                    help="VID/PID を本物の Xbox 360 (045e:028e) にする。"
                         "SDL 上の名前は 'Xbox 360 Controller' になる")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if args.mode == "listen" and not args.port:
        ap.error("--mode listen では --port が必要です")

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # 終了時も後始末する
    # 親 (sudo / launch) が強制終了されたら自分も SIGTERM で終わる。
    # 仮想パッドが残ると次回 2 台になり、joy_node が取り違えるため。
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass
    sock, recv, desc = open_receiver(args)
    vid, pid, ver = (0x045E, 0x028E, 0x0110) if args.xbox_id else (0x1209, 0x5247, 0x0001)
    try:
        pad = VirtualGamepad(args.name, vid, pid, ver, args.layout)
    except PermissionError:
        sys.exit("/dev/uinput に書き込めません。sudo で実行してください。")
    print(f"virtual gamepad '{args.name}' {vid:04x}:{pid:04x} layout={args.layout} created "
          f"({', '.join(pad.nodes)}); {desc}", flush=True)

    last_seq, last_rx, peer, active = None, 0.0, None, False
    try:
        while True:
            r, _, _ = select.select([sock], [], [], 0.1)
            now = time.monotonic()
            if not r:
                if active and now - last_rx > args.timeout:
                    pad.neutral()
                    active, last_seq = False, None
                    print("timeout -> neutral", flush=True)
                continue
            got = recv()
            if got is None:
                continue
            src, sport, pkt = got
            if args.src and src != args.src:
                continue
            p = parse(pkt)
            if p is None:
                if args.verbose and args.mode == "listen":
                    print(f"unknown packet from {src}: {pkt.hex(' ')}")
                continue
            seq = p[0]
            # 順序が入れ替わった古いパケットは捨てる (16bit ラップアラウンド考慮)
            if last_seq is not None and 0 < (last_seq - seq) % 65536 < 32768:
                continue
            last_seq, last_rx = seq, now
            if (src, sport) != peer:
                peer = (src, sport)
                print(f"receiving from {src}:{sport}", flush=True)
            active = True
            pad.update(*p[1:])
            if args.verbose:
                print("seq=%5d btn=%04x L=(%6d,%6d) R=(%6d,%6d) LT=%3d RT=%3d" % p)
    except KeyboardInterrupt:
        pass
    finally:
        pad.neutral()
        pad.close()
        sock.close()


if __name__ == "__main__":
    main()
