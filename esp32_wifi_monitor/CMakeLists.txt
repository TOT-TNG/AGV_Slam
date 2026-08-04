cmake_minimum_required(VERSION 3.16)

# Đặt version cố định thay vì để ESP-IDF tự "git describe" — project này nằm
# trong 1 thư mục con của repo AGVmqtt lớn hơn, bước tự phát hiện Git của
# ESP-IDF (grabRef.cmake) bị lệch thứ tự với CMake bản mới, gây lỗi build
# không liên quan gì tới code.
set(PROJECT_VER "1.0.0")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(wifi_signal_monitor)
