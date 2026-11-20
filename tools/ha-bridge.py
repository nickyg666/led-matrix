#!/usr/bin/env python3
"""Portable MQTT/Home Assistant bridge for the RP2040 LED Matrix.

Configuration is entirely via environment variables so the same script works
for any number of identical boards.

Env:
  MQTT_HOST        (default 127.0.0.1)
  MQTT_PORT        (default 1883)
  MQTT_USER/PASS   optional
  SERIAL_PORT      (default /dev/rp2040-matrix, then /dev/ttyACM*)
  DEVICE_NAME      (default "LED Matrix")
  NODE_ID          (default led_matrix)
  MESSAGES_FILE    (default ./messages.json next to this script)
  BRIGHT_MAX       (default 26 -> 10% hardware cap)
"""
import glob
import json
import os
import select
import termios
import threading
import time

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
DEVICE_NAME = os.getenv("DEVICE_NAME", "LED Matrix")
NODE_ID = os.getenv("NODE_ID", "led_matrix")
BRIGHT_MAX = int(os.getenv("BRIGHT_MAX", "26"))
HERE = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.getenv("MESSAGES_FILE", os.path.join(os.path.dirname(HERE), "messages.json"))

EFFECTS = ["text", "rainbow", "pulse", "wave", "fire", "matrix", "plasma", "sparkle"]
SERIAL = None
SERIAL_LOCK = threading.Lock()
STATE = {"on": False, "brightness": 255, "effect": "text", "message": "", "layout": "8x64"}


def find_serial():
    for p in ("/dev/rp2040-matrix", "/dev/rp2040-rgb"):
        if os.path.exists(p):
            return p
    ds = sorted(glob.glob("/dev/ttyACM*"))
    return ds[0] if ds else None


def load_messages():
    try:
        with open(MESSAGES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def serial_cmd(cmd, expect=False):
    global SERIAL
    with SERIAL_LOCK:
        if SERIAL is None:
            SERIAL = find_serial()
        if not SERIAL:
            return "no device"
        try:
            fd = os.open(SERIAL, os.O_RDWR | os.O_NOCTTY)
        except OSError as e:
            SERIAL = None
            return "open err: %s" % e
        try:
            a = termios.tcgetattr(fd)
            a[1] = termios.OPOST | termios.ONLCR
            a[3] = termios.CREAD | termios.CLOCAL
            a[6][termios.VMIN] = 0
            a[6][termios.VTIME] = 1
            termios.tcsetattr(fd, termios.TCSANOW, a)
            while True:
                r, _, _ = select.select([fd], [], [], 0.05)
                if not r:
                    break
                os.read(fd, 4096)
            os.write(fd, (cmd + "\r\n").encode())
            time.sleep(0.05)
            resp = b""
            if expect:
                while True:
                    r, _, _ = select.select([fd], [], [], 0.2)
                    if not r:
                        break
                    n = os.read(fd, 4096)
                    if not n:
                        break
                    resp += n
            return resp.decode(errors="replace").strip()
        except OSError as e:
            SERIAL = None
            return "err: %s" % e
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


def apply_state():
    b = max(0, min(255, STATE["brightness"]))
    dim = b
    serial_cmd("BRIGHT %d" % BRIGHT_MAX)
    serial_cmd("DIM %d" % dim)
    if not STATE["on"]:
        serial_cmd("OFF")
    elif STATE["effect"] == "text":
        msg = STATE["message"] or load_messages().get("default", "HELLO")
        safe = "".join(c for c in msg if 32 <= ord(c) < 127)
        serial_cmd("TEXT %s" % safe)
        serial_cmd("EFFECT text")
    elif STATE["effect"] in EFFECTS:
        serial_cmd("EFFECT %s" % STATE["effect"])
    else:
        msg = load_messages().get(STATE["effect"])
        if msg is not None:
            safe = "".join(c for c in msg if 32 <= ord(c) < 127)
            serial_cmd("TEXT %s" % safe)
            serial_cmd("EFFECT text")
    publish_state()


def publish_state():
    if not CLIENT:
        return
    base = "homeassistant/%s/%s" % (NODE_ID, "light")
    CLIENT.publish(base + "/state", json.dumps({
        "state": "ON" if STATE["on"] else "OFF",
        "brightness": STATE["brightness"],
        "effect": STATE["effect"],
        "color_mode": "brightness",
    }), retain=True)
    CLIENT.publish("homeassistant/text/%s_message/state" % NODE_ID,
                   STATE["message"], retain=True)


CLIENT = None


def on_connect(client, userdata, flags, rc, props=None):
    msgs = load_messages()
    effect_list = EFFECTS + [k for k in msgs if k != "default"]
    light = {
        "name": DEVICE_NAME,
        "unique_id": NODE_ID + "_light",
        "command_topic": "%s/%s/set" % (NODE_ID, "light"),
        "state_topic": "%s/%s/state" % (NODE_ID, "light"),
        "brightness": True,
        "brightness_scale": 255,
        "color_mode": "brightness",
        "supported_color_modes": ["brightness"],
        "effect": True,
        "effect_list": effect_list,
        "schema": "json",
        "device": {"identifiers": [NODE_ID], "name": DEVICE_NAME,
                   "model": "RP2040 8x64 Matrix", "manufacturer": "DIY"},
    }
    client.publish("homeassistant/light/%s/config" % NODE_ID,
                   json.dumps(light), retain=True)
    text = {
        "name": DEVICE_NAME + " Message",
        "unique_id": NODE_ID + "_message",
        "command_topic": "%s/message/set" % NODE_ID,
        "state_topic": "%s/message/state" % NODE_ID,
        "mode": "text",
        "max": 128,
        "device": {"identifiers": [NODE_ID]},
    }
    client.publish("homeassistant/text/%s_message/config" % NODE_ID,
                   json.dumps(text), retain=True)
    client.subscribe("%s/light/set" % NODE_ID)
    client.subscribe("%s/message/set" % NODE_ID)
    client.subscribe("%s/command" % NODE_ID)
    publish_state()


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode(errors="replace")
    try:
        data = json.loads(payload) if payload.strip().startswith("{") else {}
    except Exception:
        data = {}
    if topic == "%s/light/set" % NODE_ID:
        if "state" in data:
            STATE["on"] = data["state"] == "ON"
        if "brightness" in data:
            STATE["brightness"] = int(data["brightness"])
        if "effect" in data:
            STATE["effect"] = data["effect"]
        if data.get("state") == "ON" and not data.get("effect") and not STATE["message"]:
            STATE["effect"] = "text"
        apply_state()
    elif topic == "%s/message/set" % NODE_ID:
        STATE["message"] = payload
        STATE["on"] = True
        STATE["effect"] = "text"
        apply_state()
    elif topic == "%s/command" % NODE_ID:
        serial_cmd(payload)


def main():
    global CLIENT
    CLIENT = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        CLIENT.username_pw_set(MQTT_USER, MQTT_PASS)
    CLIENT.on_connect = on_connect
    CLIENT.on_message = on_message
    CLIENT.connect(MQTT_HOST, MQTT_PORT, 60)
    print("LED Matrix bridge: %s @ %s:%d" % (find_serial(), MQTT_HOST, MQTT_PORT), flush=True)
    CLIENT.loop_forever()


if __name__ == "__main__":
    main()
