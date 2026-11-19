#!/usr/bin/env python3
"""Static font probe: draws each glyph column-by-column on the matrix."""
import serial, sys, time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM1"
s = serial.Serial(PORT, 115200, timeout=2)
time.sleep(0.5)

def send(cmd):
    s.write((cmd + "\r\n").encode())
    time.sleep(0.15)
    out = s.read(200)
    return out.decode(errors="replace").strip()

print(send("PING"))
print(send("CLEAR"))
print(send("BRIGHT 128"))
print(send("RAINBOWTEXTOFF"))
print(send("TEXT T"))
print("Drawn T")
s.close()
