#!/bin/bash
# ⚡ Double-Click Launcher for macOS MLX Control Center
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:$HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif [ -f "/opt/homebrew/bin/python3" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3"
elif [ -f "/usr/local/bin/python3" ]; then
    PYTHON_BIN="/usr/local/bin/python3"
else
    PYTHON_BIN="python3"
fi

mkdir -p "$HOME/.mlx_logs" "$HOME/.mlx_pids" "$HOME/mlx_models"

echo "⚡ Starting macOS MLX Control Center..."
lsof -t -i :9998 | xargs kill -9 2>/dev/null || true
sleep 0.3

nohup "$PYTHON_BIN" "$DIR/mlx_gui_server.py" >> "$HOME/.mlx_logs/server.log" 2>&1 &

for i in {1..20}; do
    if lsof -i :9998 >/dev/null 2>&1; then
        break
    fi
    sleep 0.15
done

open "http://127.0.0.1:9998"
