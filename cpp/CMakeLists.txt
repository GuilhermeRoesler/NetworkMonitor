cmake_minimum_required(VERSION 3.16)
project(NetworkMonitorCpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(NM_CORE_SOURCES
  src/paths.cpp
  src/config.cpp
  src/ping.cpp
  src/network.cpp
  src/monitor.cpp
  src/logging.cpp
  src/win32_helpers.cpp
)

add_library(network_monitor_core STATIC ${NM_CORE_SOURCES})
target_include_directories(network_monitor_core PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

if(MSVC)
  target_compile_definitions(network_monitor_core PUBLIC UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
  target_compile_options(network_monitor_core PRIVATE /W4 /utf-8 /EHsc)
  target_link_libraries(network_monitor_core PUBLIC iphlpapi ws2_32 advapi32)
else()
  target_compile_definitions(network_monitor_core PUBLIC UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
  target_compile_options(network_monitor_core PRIVATE -Wall -Wextra)
  target_link_libraries(network_monitor_core PUBLIC iphlpapi ws2_32 advapi32)
endif()

add_executable(NetworkMonitorCpp
  src/main.cpp
  src/app_controller.cpp
  src/status_window.cpp
  src/tray_icon.cpp
  src/toast.cpp
)
target_link_libraries(NetworkMonitorCpp PRIVATE network_monitor_core user32 shell32 gdi32 comctl32 ole32 runtimeobject propsys uxtheme)

set_target_properties(NetworkMonitorCpp PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/bin"
  OUTPUT_NAME "NetworkMonitorCpp"
)

enable_testing()

add_executable(NetworkMonitorCppTests
  tests/test_main.cpp
  tests/test_network.cpp
  tests/test_config.cpp
)
target_include_directories(NetworkMonitorCppTests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/tests"
)
target_link_libraries(NetworkMonitorCppTests PRIVATE network_monitor_core)

set_target_properties(NetworkMonitorCppTests PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/bin"
)

add_test(NAME NetworkMonitorCppTests COMMAND $<TARGET_FILE:NetworkMonitorCppTests>)
