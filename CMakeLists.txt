cmake_minimum_required(VERSION 3.8)
project(remote_gamepad)

find_package(ament_cmake REQUIRED)

# ブリッジは ROS ノードではなく単体の Python スクリプト (root で実行する)
install(PROGRAMS
  scripts/remote_gamepad_bridge.py
  scripts/remote_gamepad_forward.py
  scripts/remote_gamepad_sniff.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
