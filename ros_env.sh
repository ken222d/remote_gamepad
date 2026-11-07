# ros2 と remote_gamepad が使えるように ROS 2 とワークスペースを読み込む
if ! ros2 pkg prefix remote_gamepad > /dev/null 2>&1; then
  set +u  # setup.bash は未定義の変数を参照するため
  source /opt/ros/humble/setup.bash
  source "$(cd "$DIR/../.." && pwd)/install/setup.bash"
  set -u
fi
