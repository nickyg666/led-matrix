cmake_minimum_required(VERSION 3.13)
include(pico_sdk_import.cmake)

project(ledmatrix C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(ledmatrix main.c)

pico_generate_pio_header(ledmatrix ${CMAKE_CURRENT_SOURCE_DIR}/ws2812.pio)

target_link_libraries(ledmatrix pico_stdlib hardware_pio)

pico_enable_stdio_usb(ledmatrix 1)
pico_enable_stdio_uart(ledmatrix 0)

pico_add_extra_outputs(ledmatrix)
