cmake_minimum_required(VERSION 3.16)
project(NetworkMonitorCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(NetworkMonitorCpp
  src/main.cpp
  src/paths.cpp
  src/config.cpp
  src/ping.cpp
  src/network.cpp
  src/monitor.cpp
)

target_include_directories(NetworkMonitorCpp PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

if(MSVC)
  target_compile_definitions(NetworkMonitorCpp PRIVATE UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
  target_compile_options(NetworkMonitorCpp PRIVATE /W4 /utf-8 /EHsc)
  target_link_libraries(NetworkMonitorCpp PRIVATE iphlpapi ws2_32 advapi32)
else()
  target_compile_definitions(NetworkMonitorCpp PRIVATE UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
  target_compile_options(NetworkMonitorCpp PRIVATE -Wall -Wextra)
  target_link_libraries(NetworkMonitorCpp PRIVATE iphlpapi ws2_32 advapi32)
endif()

set_target_properties(NetworkMonitorCpp PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/bin"
  OUTPUT_NAME "NetworkMonitorCpp"
)
