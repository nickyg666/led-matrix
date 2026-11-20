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

## Voice to marquee with local STT

Google Home does **not** expose its microphone audio to Home Assistant. The
Assistant integration only exposes device control, not arbitrary speech/audio
clips. To display arbitrary spoken text you must capture audio locally and run
local STT yourself.

Architecture used here:
1. Google Home routine / HA script `script.matrix_listen` calls
   `rest_command.matrix_listen` on HA.
2. HA POSTs to `http://<host>:8090/api/listen` on `tools/stt-bridge.py`.
3. STT bridge records from a local mic via `arecord`, transcribes with Vosk
   (`models/vosk-en-us`), publishes text to MQTT `<NODE_ID>/message/set`.
4. `tools/ha-bridge.py` receives that topic, sends `TEXT ...` over serial to
   the matrix. The HA text entity also updates.

Endpoints:
- `GET /status`
- `POST /api/listen` JSON `{"duration": 6}` — record local mic, transcribe, publish.
- `POST /api/transcribe` raw 16-bit PCM WAV body, or JSON `{"wav_b64": "..."}`
  to hand an already-captured audio clip to HA and get text on the marquee.

Portability env for `stt-bridge.py`:
- `PORT` (8090), `MQTT_HOST`, `MQTT_PORT`, `NODE_ID`
- `AUDIO_DEVICE` (ALSA device, default `default`)
- `MODEL_PATH` (Vosk model), `STT_TOKEN` (optional shared secret)

Note: pass an audio clip from any client to `/api/transcribe` if you capture
audio outside HA; HA itself cannot pull raw audio off a Google Home device.
