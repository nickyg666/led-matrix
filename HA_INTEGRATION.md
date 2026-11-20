# LED Matrix -> Home Assistant -> Google Home

The matrix exposes a Home Assistant `light` entity and a `text` entity over MQTT.
The bridge is hardware-agnostic: copy the firmware to any RP2040-zero with an
8x64 WS2811 matrix wired to GPIO 10, then run `tools/ha-bridge.py` with env vars.

## HA entities
- `light.led_matrix` — on/off, brightness (0-255 maps to fine dim), effects.
- `text.led_matrix_message` — set arbitrary text from HA UI / automations.

## Voice via Google Home
Google Home cannot pass arbitrary spoken text into a Home Assistant text entity.
Two reliable patterns:
1. Predefined message effects: add names to `messages.json`, e.g. "hello". Then say
   "Hey Google, set LED Matrix effect to hello".
2. Automations / routines: trigger a HA automation that writes to
   `text.led_matrix_message` with a fixed or templated string.

After adding new message names, call `google_assistant.request_sync` in HA so
Google Home learns the new effect list.

## Portability / env vars
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS`
- `SERIAL_PORT` (default /dev/rp2040-matrix)
- `DEVICE_NAME`, `NODE_ID` (multiple boards => unique IDs)
- `MESSAGES_FILE`, `BRIGHT_MAX`

## Brightness
Firmware caps BRIGHT at 26/255 (~10%). DIM 0-255 provides sub-brightness with
spatial Bayer dithering so low levels do not blink while retaining color mix.
