#!/usr/bin/env python3
"""Local STT bridge: WAV/audio clip -> Vosk -> MQTT text for the LED matrix."""
import base64
import http.server
import io
import json
import os
import subprocess
import threading
import time
import wave

import numpy as np
import paho.mqtt.client as mqtt
from vosk import KaldiRecognizer, Model

PORT = int(os.getenv("PORT", "8090"))
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
NODE_ID = os.getenv("NODE_ID", "led_matrix")
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "default")
MODEL_PATH = os.getenv("MODEL_PATH", "/home/sh/ledmatrix/models/vosk-en-us")
TOKEN = os.getenv("STT_TOKEN", "")
SAMPLE_RATE = 16000

print("Loading Vosk model...", flush=True)
MODEL = Model(MODEL_PATH)
print("Vosk ready", flush=True)

MQ = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    MQ.connect(MQTT_HOST, MQTT_PORT, 60)
    MQ.loop_start()
except Exception as e:
    print("MQTT connect failed: %s" % e, flush=True)


def pcm16(data):
    a = np.frombuffer(data, dtype="<i2").astype(np.float32)
    return a


def resample(a, src, dst):
    if src == dst:
        return a
    n = int(len(a) * dst / src)
    x = np.linspace(0, len(a), n, endpoint=False)
    return np.interp(x, np.arange(len(a)), a).astype(np.float32)


def transcribe_wav(raw):
    try:
        w = wave.open(io.BytesIO(raw), "rb")
    except Exception as e:
        return "ERR: invalid WAV: %s" % e
    ch = w.getnchannels()
    sw = w.getsampwidth()
    sr = w.getframerate()
    frames = w.readframes(w.getnframes())
    w.close()
    if sw != 2:
        return "ERR: only 16-bit PCM supported"
    a = pcm16(frames)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    a = resample(a, sr, SAMPLE_RATE)
    pcm = np.clip(a, -32768, 32767).astype("<i2").tobytes()
    rec = KaldiRecognizer(MODEL, SAMPLE_RATE)
    rec.SetWords(False)
    chunks = []
    for i in range(0, len(pcm), 4000):
        if rec.AcceptWaveform(pcm[i:i + 4000]):
            r = json.loads(rec.Result())
            if r.get("text"):
                chunks.append(r["text"])
    final = json.loads(rec.FinalResult())
    if final.get("text"):
        chunks.append(final["text"])
    return " ".join(chunks).strip()


def publish(text):
    if not text or text.startswith("ERR:"):
        return
    payload = "".join(c for c in text if 32 <= ord(c) < 127)
    if not payload:
        return
    MQ.publish("%s/message/set" % NODE_ID, payload, retain=False)
    MQ.publish("%s/stt/state" % NODE_ID, payload, retain=True)
    print("STT -> %s" % payload, flush=True)


def record(duration):
    path = "/tmp/opencode/stt-capture.wav"
    cmd = ["arecord", "-D", AUDIO_DEVICE, "-f", "S16_LE",
           "-r", str(SAMPLE_RATE), "-c", "1", "-d", str(duration), path]
    subprocess.run(cmd, capture_output=True, timeout=duration + 10)
    with open(path, "rb") as f:
        return f.read()


class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if not TOKEN:
            return True
        return self.headers.get("X-Token") == TOKEN

    def do_GET(self):
        if self.path == "/status":
            self.reply({"status": "ok", "model": MODEL_PATH, "node": NODE_ID})
        else:
            self.reply({"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            self.reply({"error": "unauthorized"})
            return
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n) if n else b""
        if self.path.startswith("/api/listen"):
            duration = 6
            try:
                data = json.loads(body) if body else {}
                duration = int(data.get("duration", 6))
            except Exception:
                pass
            duration = max(1, min(30, duration))
            text = transcribe_wav(record(duration))
            publish(text)
            self.reply({"text": text})
        elif self.path.startswith("/api/transcribe"):
            ctype = self.headers.get("Content-Type", "")
            if "application/json" in ctype:
                try:
                    data = json.loads(body)
                    raw = base64.b64decode(data.get("wav_b64", ""))
                except Exception as e:
                    self.reply({"error": str(e)})
                    return
            else:
                raw = body
            text = transcribe_wav(raw)
            publish(text)
            self.reply({"text": text})
        else:
            self.reply({"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("STT bridge on http://0.0.0.0:%d" % PORT, flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
