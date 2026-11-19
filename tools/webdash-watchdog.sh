#!/usr/bin/env bash
while true; do
    python3 /home/sh/ledmatrix/tools/webdash.py >> /tmp/opencode/webdash-matrix.log 2>&1
    sleep 2
done
