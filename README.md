# RP2350 8x32 LED Matrix Controller

Firmware for RP2350 (Pico 2) driving an 8x32 addressable LED matrix (WS2812/WS2811).
LEDs chained vertically: 8 LEDs per column, 32 columns.

## Features
- Scrolling text marquee (left/right)
- 7 built-in effects: rainbow, pulse, wave, fire, matrix (rain), plasma, sparkle
- Image display (32x8, send pixel data)
- Adjustable brightness, speed, direction
- Text color and background color
- Web dashboard for control and image painting

## Build
```bash
cd /home/sh/ledmatrix
PICO_SDK_PATH=/home/sh/pico/pico-sdk cmake -B build
cmake --build build
```
Output: build/ledmatrix.uf2

## Flash
1. Hold BOOT on RP2350 (Pico 2), plug USB, release
2. Copy build/ledmatrix.uf2 to RPI-RP2 drive

## Commands (via serial / matrixctl)
- TEXT <str>     Set scrolling text
- COLOR r g b    Text color
- BG r g b       Background color
- EFFECT <name>  text|rainbow|pulse|wave|fire|matrix|plasma|sparkle
- BRIGHT <0-255> Brightness
- SPEED <1-255>  Speed (1=slow)
- DIR <1|-1>     Scroll direction
- IMAGE <hex,...>  32x8 image (256 hex colors)
- CLEAR          Clear display
- OFF / ON       Power
- PING / BOOT / HELP

## Web Dashboard
```bash
python3 tools/webdash.py
# Open http://localhost:8081
```

## Wiring
- Data: GPIO 10
- Power: external 5V/12V (match strip)
- GND: common
