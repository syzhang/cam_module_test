cmake_minimum_required(VERSION 3.5)
project(cam_recorder CXX)
set(CMAKE_CXX_STANDARD 14)

find_package(xvsdk REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc highgui)

add_executable(cam_recorder cam_recorder.cpp)
target_include_directories(cam_recorder PRIVATE ${xvsdk_INCLUDE_DIRS}/xvsdk ${OpenCV_INCLUDE_DIRS})
target_link_libraries(cam_recorder ${xvsdk_LIBRARIES} ${OpenCV_LIBS} -pthread)
