"""iPhone Remote Gamepad ブリッジ + joy_node を単独で起動する。

    ros2 launch remote_gamepad remote_gamepad.launch.py
    ros2 launch remote_gamepad remote_gamepad.launch.py src_ip:=$IPHONEIP
    # 別ネットワークの手元 PC から転送を受けるとき (remote_gamepad_forward.py)
    ros2 launch remote_gamepad remote_gamepad.launch.py mode:=listen port:=$NUMBER

- PC 用 Remote Gamepad ソフトは起動したままにする (ソフトがないとアプリが送信しない)
- ブリッジは /dev/uinput と生パケット受信のため root が必要なので `sudo -n` で起動する
  (パスワードなしで sudo できること)
- この launch も /joy_node を起動するので、main_exec を併用するときは
  main_params.yaml の launch.joy を false にしておくこと (/joy が 2 系統になる)
"""
import os

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def bridge_process(context):
    cfg = lambda name: LaunchConfiguration(name).perform(context)  # noqa: E731
    bridge = os.path.realpath(os.path.join(
        get_package_prefix("remote_gamepad"), "lib", "remote_gamepad",
        "remote_gamepad_bridge.py"))
    # setsid: sudo は「同じプロセスグループから来たシグナル」を中継しないため、
    # グループを分けて launch の SIGINT/SIGTERM がブリッジまで届くようにする
    cmd = ["setsid", "sudo", "-n", "python3", "-u", bridge,
           "--name", cfg("device_name"), "--timeout", cfg("timeout"),
           "--layout", cfg("layout"), "--mode", cfg("mode")]
    if cfg("src_ip"):
        cmd += ["--src", cfg("src_ip")]
    if cfg("port") != "0":
        cmd += ["--port", cfg("port")]
    return [ExecuteProcess(cmd=cmd, name="remote_gamepad_bridge", output="screen",
                           sigterm_timeout="3")]


def generate_launch_description():
    args = [
        DeclareLaunchArgument("device_name", default_value="Remote Gamepad ROS",
                              description="仮想デバイス名 (joy_node の device_name)"),
        DeclareLaunchArgument("layout", default_value="ps",
                              description="/joy の並び。ps: controller_node と同じ / xbox"),
        DeclareLaunchArgument("mode", default_value="sniff",
                              description="sniff: PC 用ソフトと共存 / listen: port を自分で受信 (転送を受けるとき)"),
        DeclareLaunchArgument("src_ip", default_value="",
                              description="iPhone の IP (空ならすべて受け付ける)"),
        DeclareLaunchArgument("port", default_value="0",
                              description="UDP ポート (0 = 自動。listen では必須)"),
        DeclareLaunchArgument("timeout", default_value="0.5",
                              description="途切れたらニュートラルに戻すまでの秒数"),
        DeclareLaunchArgument("deadzone", default_value="0.05"),
        DeclareLaunchArgument("autorepeat_rate", default_value="20.0"),
    ]
    # joy_node はデバイスの後からの接続 (hotplug) に対応しているので起動順は気にしなくてよい
    joy = Node(
        package="joy", executable="joy_node", name="joy_node", output="screen",
        parameters=[{
            "device_name": LaunchConfiguration("device_name"),
            "deadzone": ParameterValue(LaunchConfiguration("deadzone"), value_type=float),
            "autorepeat_rate": ParameterValue(LaunchConfiguration("autorepeat_rate"),
                                              value_type=float),
        }],
    )
    return LaunchDescription(args + [OpaqueFunction(function=bridge_process), joy])
