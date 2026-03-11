cmake_minimum_required(VERSION 3.16)
project(firmware)
set(CMAKE_CXX_STANDARD 17)

# ESP-IDF / Arduino component list
set(COMPONENT_SRCS "main.cpp" "init.cpp")
set(COMPONENT_ADD_INCLUDEDIRS ".")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
