# remote_gamepad

iPhone Remote Gamepad → ROS 2 `joy_node`

## ビルド

```bash
cd ~/formula_ws
colcon build --symlink-install --packages-select remote_gamepad
source install/setup.bash
```

## main_exec との関係

**main_exec.launch.py には組み込んでいない。単独で起動する。**
この launch も `/joy_node` を起動するので、`main_exec` と併用するときは
`main_executor/config/main_params.yaml` の `launch.joy` を `false` にしておくこと。
`true` のままだと `/joy_node` が 2 つになり、`/joy` も 2 系統になる。
そうなると `controller_node` の Share（自動・手動の切り替え）や Options（再稼働）が誤動作する。

iPhone アプリ「Remote Gamepad」の入力を Linux の仮想ゲームパッドにして、
実機と同じく `joy_node` から `/joy`（`sensor_msgs/Joy`）を出す。

## launch で起動（ブリッジ + joy_node）

PC 用の Remote Gamepad ソフトを起動して iPhone を接続してから:

```bash
ros2 launch remote_gamepad remote_gamepad.launch.py
# 引数の例
ros2 launch remote_gamepad remote_gamepad.launch.py src_ip:=$IPHONEIP deadzone:=0.1
```

| 引数 | 既定値 | 内容 |
|---|---|---|
| `device_name` | `Remote Gamepad ROS` | 仮想デバイス名（joy_node の `device_name` にも渡す） |
| `mode` | `sniff` | `sniff`: PC 用ソフトと共存 / `listen`: `port` を自分で受信（転送を受けるとき） |
| `src_ip` | （空） | iPhone の IP（転送を受けるときは手元 PC の IP）。空ならすべて受け付ける |
| `port` | `0` | UDP ポート。0 は自動（`listen` では必須） |
| `timeout` | `0.5` | パケットが途切れたらニュートラルに戻すまでの秒数 |
| `deadzone` | `0.05` | joy_node の deadzone |
| `autorepeat_rate` | `20.0` | joy_node の autorepeat_rate |

ブリッジは root が必要なので、launch 内では `sudo -n` で起動する。
**パスワードなしで sudo できる必要がある。** 必要なら `/etc/sudoers.d/` に
このスクリプト専用の NOPASSWD 設定を入れる。

既存の launch に組み込む場合は `IncludeLaunchDescription` で読み込む:

```python
import os
from ament_index_python.packages import get_package_share_directory
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

IncludeLaunchDescription(
    PythonLaunchDescriptionSource(os.path.join(
        get_package_share_directory("remote_gamepad"), "launch", "remote_gamepad.launch.py")),
    launch_arguments={"src_ip": "$IPHONEIP"}.items(),
)
```

## 手動で起動

1. PC 用の Remote Gamepad ソフトを起動し、iPhone アプリを接続する
   （ソフトがないとアプリが送信しないため、起動したままにする）
2. ブリッジを起動する（`/dev/uinput` と生パケット受信のため sudo が必要）
   ```bash
   sudo python3 $(ros2 pkg prefix remote_gamepad)/lib/remote_gamepad/remote_gamepad_bridge.py
   ```
3. `joy_node` を起動する
   ```bash
   ros2 run joy joy_node --ros-args -p device_name:="Remote Gamepad ROS"
   ```

formula_ws の `controller_node` が期待するボタン・軸の並び（PS 系）で出力する。

## 別ネットワークから操作する（転送）

車両 PC と手元の PC が別の Wi-Fi にあり、iPhone は手元の PC と同じ Wi-Fi にあるとき。
手元の PC がパケットを車両 PC へ UDP で転送する。

```
iPhone --(同じ Wi-Fi)--> 手元 PC [PC 用ソフト + remote_gamepad_forward.py]
                          --(Tailscale, UDP)--> 車両 PC [ブリッジ(listen) + joy_node]
```

1. 両方の PC を同じ Tailscale ネットワークに参加させる
   （`tailscale ip -4` で車両 PC の IP を確認する。）
2. 車両 PC: ブリッジを listen モードで起動する（PC 用ソフトは不要）
   ```bash
   ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:=$NUMBER
   ```
3. 手元の PC: PC 用 Remote Gamepad ソフトを起動して iPhone を接続し、転送を始める
   ```bash
   sudo python3 remote_gamepad_forward.py --to $IP:$NUMBER  # Linux
   python remote_gamepad_forward.py --to $IP:$NUMBER         # Windows（管理者の PowerShell）
   ```
   手元の PC に ROS は不要。`scripts/remote_gamepad_forward.py` 1 ファイルだけで動く（標準ライブラリのみ）。
   - Windows では WSL ではなく Windows の Python で動かす（PC 用ソフトが受けたパケットは WSL から見えない）
   - Windows ファイアウォールの許可を聞かれたら Python を許可する
   - Wi-Fi 以外の経路が既定になっていると iPhone のパケットを読めない。そのときは `--bind <Wi-Fi の IP>` を付ける

- 通信が `timeout`（既定 0.5 秒）途切れると、車両側のブリッジが入力をニュートラルに戻す
- 経路が中継（DERP）になると遅延が増える。`tailscale ping <車両 PC>` で直結か確認する
- 送信元を絞るときは、車両側の `src_ip` に手元 PC の Tailscale IP を指定する

## 仕組み

- アプリは Wi-Fi 経由で UDP の 19 バイトのパケットを送る（約 80Hz、一方向）。
  送り先のポートは PC 用ソフトが起動のたびに決めるので固定ではない。
- ブリッジはポートを開かず、届いたパケットを横から読む（sniff モード）。
  パケットの形で見分けるので、ポートが変わっても自動で追従する。
- 仮想デバイスのボタン・軸の並びは `--layout` で切り替える（既定は ps）。
  - PC 用ソフトも「Remote Gamepad」という仮想デバイスを作るが、
    入力イベントが出ない。しかも SDL 上では本物の Xbox 360 と同じ名前に見える。
  - 取り違えないよう、ブリッジは別の VID/PID と名前（`Remote Gamepad ROS`）で作る。
- 0.5 秒パケットが途切れると、全入力をニュートラルに戻す。

パケット形式（little endian）:

| byte | 内容 |
|---|---|
| 0–3 | `13 00 01 15`（長さ 19 とヘッダ） |
| 4–5 | uint16 シーケンス番号 |
| 6 | `01` |
| 7–8 | uint16 ボタン（XInput の `wButtons` と同じビット配置） |
| 9–16 | int16 ×4: LX, LY, RX, RY（右・上が +） |
| 17, 18 | uint8: LT, RT |

## `/joy` の割り当て

既定（`--layout ps`）は、formula_ws の `controller_node`（`controller_node.hpp` の
`Axes` / `Buttons`）と同じ並び。アプリの Xbox 配置のボタンを PS のボタンに読み替える。

| index | buttons（アプリのボタン） | axes |
|---|---|---|
| 0 | Cross（A） | L_x 左スティック左右（左 +） |
| 1 | Circle（B） | L_y 左スティック上下（上 +） |
| 2 | Triangle（Y） | R_x 右スティック左右（左 +） |
| 3 | Square（X） | L2（離す 1.0 → 押す -1.0） |
| 4 | L1（LB） | R2（離す 1.0 → 押す -1.0） |
| 5 | R1（RB） | R_y 右スティック上下（上 +） |
| 6 | L2（LT） | 十字キー左右（左 +） |
| 7 | R2（RT） | 十字キー上下（上 +） |
| 8 | Share（Back） | |
| 9 | Options（Start） | |
| 10 | PS（Guide） | |
| 11 | L3（左スティック押し込み） | |
| 12 | R3（右スティック押し込み） | |

`--layout xbox` にすると Xbox 360 pad（xpad）と同じ並びになる
（buttons: A B X Y LB RB Back Start Guide LS RS / axes: LX LY LT RX RY RT 十字左右 十字上下）。
**controller_node では xbox の並びを使わないこと。** `axes[2]` が LT になり、
何も触っていないときに +1.0 になるので、ステアリングが最大まで切れる。

## オプション

```
--mode listen --port N   PC 用ソフトなしで、ポート N を自分で受信する
--src $IPHONEIP        この送信元 IP（iPhone）だけ受け付ける
--timeout 0.5            パケットが途切れたらニュートラルに戻すまでの秒数
--name NAME              仮想デバイス名（joy_node の device_name）
--layout ps|xbox         /joy の並び（既定 ps = controller_node と同じ）
--xbox-id                VID/PID を本物の Xbox 360（045e:028e）にする
-v                       受信値を表示
```

`scripts/remote_gamepad_sniff.py` は、通信内容を調べるためのパケットキャプチャ。
