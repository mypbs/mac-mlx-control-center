#!/bin/bash
# Double-Click Launcher for macOS MLX Control Center
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "⚡ Starting macOS MLX Control Center..."
lsof -t -i :9998 | xargs kill -9 2>/dev/null || true
python3 mlx_gui_server.py >/dev/null 2>&1 &
sleep 1
open "http://127.0.0.1:9998"
