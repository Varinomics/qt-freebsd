cmake_minimum_required(VERSION 3.24)
project(qt_freebsd_sdk_smoke LANGUAGES CXX)

find_package(Qt6 6.12 REQUIRED COMPONENTS
    Core Gui GuiPrivate Qml Quick QuickControls2 QuickLayouts QuickShapes ShaderTools Test)

add_executable(qt_freebsd_sdk_smoke main.cpp)
target_compile_features(qt_freebsd_sdk_smoke PRIVATE cxx_std_20)
target_link_libraries(qt_freebsd_sdk_smoke PRIVATE
    Qt6::Core Qt6::Gui Qt6::GuiPrivate Qt6::Qml Qt6::Quick Qt6::Test)
