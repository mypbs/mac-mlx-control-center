#!/bin/bash
# 1-Line Installer & Launcher for macOS MLX Control Center
set -e

echo "⚡ macOS MLX Control Center - Automatic 1-Click Launcher"
echo "--------------------------------------------------------"

TARGET_DIR="$HOME/mac-mlx-control-center"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Cloning repository to $TARGET_DIR..."
    git clone https://github.com/mypbs/mac-mlx-control-center.git "$TARGET_DIR"
else
    echo "Updating repository in $TARGET_DIR..."
    cd "$TARGET_DIR" && git pull origin main 2>/dev/null || true
fi

cd "$TARGET_DIR"
lsof -t -i :9998 | xargs kill -9 2>/dev/null || true

echo "Starting GUI server and opening browser..."
python3 mlx_gui_server.py >/dev/null 2>&1 &
sleep 1
open "http://127.0.0.1:9998"

echo "✓ Running! Opening http://127.0.0.1:9998 in your default browser."
