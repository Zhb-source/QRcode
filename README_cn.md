# QRcode
二维码识别

# humble
source /opt/tros/humble/setup.bash
colcon build

source ~/DiPingXian_ws/install/setup.bash

# 运行二维码识别
ros2 run qrcode_pkg_py qrcode_scanner

# 开启截图模式
ros2 run your_package your_node --ros-args -p show_gui:=true
