#!/bin/bash
# ⚡ macOS MLX Control Center - 1-Click Installer & Launcher
set -e

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:$HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

echo "========================================================"
echo "⚡ macOS MLX Control Center - 1-Click Launcher & Setup"
echo "========================================================"

TARGET_DIR="$HOME/mac-mlx-control-center"
LOG_DIR="$HOME/.mlx_logs"
PID_DIR="$HOME/.mlx_pids"
MODEL_DIR="$HOME/mlx_models"

mkdir -p "$LOG_DIR" "$PID_DIR" "$MODEL_DIR"

# 1. Check Python 3
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif [ -f "/opt/homebrew/bin/python3" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3"
elif [ -f "/usr/local/bin/python3" ]; then
    PYTHON_BIN="/usr/local/bin/python3"
elif [ -f "/usr/bin/python3" ]; then
    PYTHON_BIN="/usr/bin/python3"
else
    echo "❌ Error: Python 3 is required. Please install Python 3 (via https://brew.sh or Xcode Tools)."
    exit 1
fi

# 2. Check / Install uv (ultra-fast zero-config MLX runner)
if ! command -v uv >/dev/null 2>&1 && ! command -v uvx >/dev/null 2>&1; then
    echo "⚡ Setting up uv runner for Apple Silicon MLX..."
    curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null || true
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# 3. Clone or Update Repository
if [ ! -d "$TARGET_DIR" ]; then
    echo "📦 Cloning macOS MLX Control Center to $TARGET_DIR..."
    git clone https://github.com/mypbs/mac-mlx-control-center.git "$TARGET_DIR"
else
    echo "🔄 Updating repository in $TARGET_DIR..."
    cd "$TARGET_DIR" && git pull origin main 2>/dev/null || true
fi

cd "$TARGET_DIR"

# 4. Set Execution Permissions & Sync Files
chmod +x "$TARGET_DIR"/*.sh "$TARGET_DIR"/*.command "$TARGET_DIR"/mlx_gui_server.py 2>/dev/null || true
cp "$TARGET_DIR/mlx_gui_server.py" "$HOME/mlx_gui_server.py" 2>/dev/null || true
cp "$TARGET_DIR/mlx_helper.py" "$HOME/mlx_helper.py" 2>/dev/null || true
cp "$TARGET_DIR/mlx.sh" "$HOME/mlx.sh" 2>/dev/null || true
cp "$TARGET_DIR/mlx_helper.py" "$PID_DIR/mlx_helper.py" 2>/dev/null || true

# 5. Stop any existing GUI server on port 9998
lsof -t -i :9998 | xargs kill -9 2>/dev/null || true
sleep 0.5

# 6. Launch Server in Background
echo "🚀 Starting MLX GUI Server on http://127.0.0.1:9998..."
nohup "$PYTHON_BIN" "$TARGET_DIR/mlx_gui_server.py" >> "$LOG_DIR/server.log" 2>&1 &

# Wait for server port to open
for i in {1..20}; do
    if lsof -i :9998 >/dev/null 2>&1; then
        break
    fi
    sleep 0.15
done

# 7. Open Web Dashboard
echo "✓ Success! Opening macOS MLX Control Center in your browser..."
open "http://127.0.0.1:9998"

echo ""
echo "--------------------------------------------------------"
echo "🎉 MLX Control Center is running at http://127.0.0.1:9998"
echo "📁 Location: $TARGET_DIR"
echo "💡 Double-click start.command anytime to relaunch!"
echo "--------------------------------------------------------"
