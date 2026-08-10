#!/bin/bash
#
# mlx.sh - Complete MLX Model Manager for MacBook
# Start, stop, list, search, download, delete, and test MLX LM models.
#

export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

MODEL_DIR="${HOME}/mlx_models"
PID_DIR="${HOME}/.mlx_pids"
LOG_DIR="${HOME}/.mlx_logs"
DEFAULT_PORT=9999
DEFAULT_HOST="127.0.0.1"

mkdir -p "$MODEL_DIR" "$PID_DIR" "$LOG_DIR"
HELPER_PY="$PID_DIR/mlx_helper.py"

# Ensure Python helper exists
if [ ! -f "$HELPER_PY" ]; then
    cat << 'EOF' > "$HELPER_PY"
#!/usr/bin/env python3
import os, sys, json, subprocess, re, urllib.request, urllib.parse, socket

def find_local_models():
    search_paths = [
        os.path.expanduser("~/.cache/huggingface/hub"),
        os.path.expanduser("~/MLXConsole/models/hub"),
        os.path.expanduser("~/.lmstudio/hub/models"),
        os.path.expanduser("~/.cache/lmstudio/models"),
        os.path.expanduser("~/mlx_models"),
    ]
    models = []
    seen_paths = set()

    for spath in search_paths:
        if not os.path.exists(spath):
            continue
        for root, dirs, files in os.walk(spath):
            if "config.json" in files and "1_Pooling" not in root:
                real_path = os.path.realpath(root)
                if real_path in seen_paths:
                    continue
                seen_paths.add(real_path)

                parent_hub_dir = root
                parts = root.split(os.sep)
                name = ""
                for p in parts:
                    if p.startswith("models--"):
                        name = p.replace("models--", "").replace("--", "/")
                        parent_hub_dir = root[:root.find(p) + len(p)]
                        break
                if not name:
                    name = os.path.basename(root)

                size_bytes = 0
                calc_dir = parent_hub_dir if "models--" in parent_hub_dir else root
                for r, d, f in os.walk(calc_dir):
                    for file in f:
                        fp = os.path.join(r, file)
                        if not os.path.islink(fp):
                            try:
                                size_bytes += os.path.getsize(fp)
                            except Exception:
                                pass
                size_gb = size_bytes / (1024**3)
                size_str = f"{size_gb:.1f} GB" if size_gb >= 1 else f"{size_bytes/(1024**2):.1f} MB"

                models.append({
                    "name": name,
                    "size": size_str,
                    "path": root,
                    "delete_target": calc_dir
                })
    return models

def get_running_servers():
    servers = []
    try:
        output = subprocess.check_output(["ps", "aux"], text=True)
        for line in output.splitlines():
            if "mlx_lm.server" in line and "grep" not in line:
                parts = line.split()
                pid = parts[1]
                cmd_start = parts[10] if len(parts) > 10 else ""

                model_match = re.search(r"--model\s+([^\s]+)", line)
                port_match = re.search(r"--port\s+([^\s]+)", line)
                host_match = re.search(r"--host\s+([^\s]+)", line)

                model = model_match.group(1) if model_match else "unknown"
                port = port_match.group(1) if port_match else "9999"
                host = host_match.group(1) if host_match else "127.0.0.1"

                if "models--" in model:
                    m = re.search(r"models--([^/]+)--(.*?)(?:/snapshots|$)", model)
                    if m:
                        model = f"{m.group(1)}/{m.group(2)}"

                status = "STARTING/UNRESPONSIVE"
                try:
                    url = f"http://{host}:{port}/v1/models"
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=1.2) as resp:
                        if resp.status == 200:
                            status = "READY"
                except Exception:
                    pass

                servers.append({
                    "pid": pid,
                    "model": model,
                    "host": host,
                    "port": port,
                    "status": status,
                    "is_python": "python" in cmd_start
                })
    except Exception:
        pass

    unique = {}
    for s in servers:
        key = (s["host"], s["port"])
        if key not in unique or s["is_python"]:
            unique[key] = s

    return list(unique.values())

def search_hf_api(query, limit=15):
    q = urllib.parse.quote(query)
    url = f"https://huggingface.co/api/models?search={q}&limit={limit}&sort=downloads&direction=-1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                results.append({
                    "id": item.get("id", ""),
                    "downloads": item.get("downloads", 0),
                    "likes": item.get("likes", 0)
                })
    except Exception:
        pass
    return results

def find_free_port(start_port=9999):
    port = int(start_port)
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "find_models":
        print(json.dumps(find_local_models()))
    elif cmd == "running_servers":
        print(json.dumps(get_running_servers()))
    elif cmd == "search_hf":
        q = sys.argv[2] if len(sys.argv) > 2 else "mlx"
        print(json.dumps(search_hf_api(q)))
    elif cmd == "free_port":
        p = sys.argv[2] if len(sys.argv) > 2 else "9999"
        print(find_free_port(p))
EOF
    chmod +x "$HELPER_PY"
fi

# Check navigation input (b = Back, e = Exit)
check_nav() {
    local val="$1"
    local input_lower
    input_lower=$(echo "$val" | tr '[:upper:]' '[:lower:]')
    if [ "$input_lower" = "e" ]; then
        echo ""
        echo "Exiting MLX Model Manager. Goodbye!"
        exit 0
    elif [ "$input_lower" = "b" ]; then
        return 1
    fi
    return 0
}

# Display running models header
show_running_header() {
    echo ""
    echo "=== Currently Running MLX Models ==="
    local running_json
    running_json=$(python3 "$HELPER_PY" running_servers)
    
    local count
    count=$(echo "$running_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo "  (none running)"
    else
        echo "$running_json" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
unresponsive = False
for i, s in enumerate(servers, 1):
    tag = f'[{s[\"status\"]}]'
    if 'UNRESPONSIVE' in s['status']:
        unresponsive = True
    print(f'  {i}. {tag:<22} {s[\"model\"]} (PID: {s[\"pid\"]}, Host: {s[\"host\"]}, Port: {s[\"port\"]})')
if unresponsive:
    print('  ⚡ Tip: Type \"k\" or \"k <#>\" (e.g. k 2) to KILL any process immediately!')
"
    fi
    echo "======================================"
    echo ""
}

# ── 1. List Models ───────────────────────────────────────────────────
list_models() {
    local interactive="${1:-true}"
    echo ""
    echo "=== Downloaded MLX Models ==="
    local local_json
    local_json=$(python3 "$HELPER_PY" find_models)

    local count
    count=$(echo "$local_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo "  (no downloaded models found)"
    else
        echo "$local_json" | python3 -c "
import sys, json
models = json.load(sys.stdin)
for i, m in enumerate(models, 1):
    print(f'  {i:2d}. {m[\"name\"]:<50} ({m[\"size\"]})')
    print(f'      Path: {m[\"path\"]}')
"
    fi
    echo ""
    if [ "$interactive" = "false" ]; then
        return
    fi

    echo "Options: Enter model number [1-$count] to Start, [b] Back, [e] Exit"
    echo -n "Select option: "
    read -r choice
    check_nav "$choice" || return

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
        local selected_name
        selected_name=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['name'])")
        start_model "$selected_name"
    fi
}

# ── 2. Search Hugging Face ───────────────────────────────────────────
search_hf() {
    local query="${1:-}"
    if [ -z "$query" ]; then
        echo ""
        echo -n "Enter search term for Hugging Face (e.g. mlx, qwen, llama) [default: mlx] (b: Back, e: Exit): "
        read -r query
        check_nav "$query" || return
        [ -z "$query" ] && query="mlx"
    fi

    echo ""
    echo "Searching Hugging Face for '$query'..."
    echo "---------------------------------------------------------"

    local results_json
    results_json=$(python3 "$HELPER_PY" search_hf "$query")

    local count
    count=$(echo "$results_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo "No results found on Hugging Face."
        echo ""
        read -r -p "Press Enter to return..."
        return
    fi

    echo "$results_json" | python3 -c "
import sys, json
results = json.load(sys.stdin)
for i, r in enumerate(results, 1):
    print(f'  {i:2d}. {r[\"id\"]:<55} Downloads: {r[\"downloads\"]:>7,} | Likes: {r[\"likes\"]:>4}')
"
    echo "---------------------------------------------------------"
    echo ""
    echo -n "Enter number [1-$count] to Download, [s] New Search, [b] Back, [e] Exit: "
    read -r choice
    check_nav "$choice" || return

    if [ "$choice" = "s" ] || [ "$choice" = "S" ]; then
        search_hf ""
    elif [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
        local selected_id
        selected_id=$(echo "$results_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['id'])")
        download_model "$selected_id"
    fi
}

# ── 3. Download / Add Model ──────────────────────────────────────────
download_model() {
    local model_repo="${1:-}"
    if [ -z "$model_repo" ]; then
        echo ""
        echo -n "Enter Hugging Face Repo ID (e.g. mlx-community/Qwen2.5-Coder-7B-Instruct-4bit) [b: Back, e: Exit]: "
        read -r model_repo
        check_nav "$model_repo" || return
    fi
    [ -z "$model_repo" ] && return

    echo ""
    echo "Downloading model '$model_repo' using High Speed Hugging Face CLI ('hf')..."
    echo "---------------------------------------------------------"

    export HF_HUB_ENABLE_HF_TRANSFER=1
    export HF_XET_HIGH_PERFORMANCE=1

    if command -v hf &>/dev/null; then
        hf download "$model_repo"
    elif command -v huggingface-cli &>/dev/null; then
        huggingface-cli download "$model_repo"
    else
        python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$model_repo')"
    fi

    echo ""
    echo "✓ Download process completed for '$model_repo'."
    echo ""
    read -r -p "Press Enter to continue..."
}

# ── 4. Start Model (Fast Swap & Concurrent Options) ──────────────────
start_model() {
    local model_arg="${1:-}"
    local model_name=""
    local model_path=""

    local local_json
    local_json=$(python3 "$HELPER_PY" find_models)

    local count
    count=$(echo "$local_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ -n "$model_arg" ]; then
        model_name="$model_arg"
        model_path=$(echo "$local_json" | python3 -c "
import sys, json
models = json.load(sys.stdin)
target = '$model_name'
found = ''
for m in models:
    if m['name'] == target or target in m['path']:
        found = m['path']
        break
print(found)
")
        [ -z "$model_path" ] && model_path="$model_name"
    else
        if [ "$count" -eq 0 ]; then
            echo ""
            echo "No local models found."
            echo -n "Enter a Hugging Face Repo ID to download and start [b: Back, e: Exit]: "
            read -r model_arg
            check_nav "$model_arg" || return
            [ -z "$model_arg" ] && return
            download_model "$model_arg"
            model_name="$model_arg"
            model_path="$model_arg"
        else
            echo ""
            echo "=== Select Model to Start ==="
            echo "$local_json" | python3 -c "
import sys, json
models = json.load(sys.stdin)
for i, m in enumerate(models, 1):
    print(f'  {i:2d}. {m[\"name\"]} ({m[\"size\"]})')
"
            echo ""
            echo -n "Select model number [1-$count] or enter Repo ID [b: Back, e: Exit]: "
            read -r choice
            check_nav "$choice" || return
            [ -z "$choice" ] && return

            if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
                model_name=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['name'])")
                model_path=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['path'])")
            else
                model_name="$choice"
                model_path="$choice"
            fi
        fi
    fi

    local running_json
    running_json=$(python3 "$HELPER_PY" running_servers)
    local run_count
    run_count=$(echo "$running_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    local target_port="$DEFAULT_PORT"
    local host="$DEFAULT_HOST"
    local temp="0.0"
    local max_tokens="4096"
    local extra_args=""

    if [ "$run_count" -gt 0 ]; then
        echo ""
        echo "---------------------------------------------------------"
        echo "⚠️ Active Model(s) Currently Running:"
        echo "$running_json" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
for i, s in enumerate(servers, 1):
    print(f'   - {s[\"model\"]} (PID {s[\"pid\"]} on port {s[\"port\"]})')
"
        echo ""
        echo "Target Model to Launch: '$model_name'"
        echo "---------------------------------------------------------"
        echo "  1. ⚡ Fast Swap (Stop active model & launch '$model_name' on port $DEFAULT_PORT) [Default]"
        echo "  2. 🔀 Run Concurrently (Keep active model & launch '$model_name' on a new port)"
        echo "  3. ⚙️ Custom Parameters (Select custom port, host, temperature, thinking mode)"
        echo ""
        echo -n "Select option [1-3, default 1] (or [b] Back, [e] Exit): "
        read -r swap_choice
        check_nav "$swap_choice" || return
        [ -z "$swap_choice" ] && swap_choice="1"

        if [ "$swap_choice" = "1" ]; then
            echo ""
            echo "⚡ Fast Swap: Stopping current model server(s) on port $DEFAULT_PORT..."
            local check_port_pid
            check_port_pid=$(lsof -t -i :"$DEFAULT_PORT" 2>/dev/null)
            if [ -n "$check_port_pid" ]; then
                kill -9 "$check_port_pid" 2>/dev/null
                sleep 1
            fi
            target_port="$DEFAULT_PORT"
        elif [ "$swap_choice" = "2" ]; then
            target_port=$(python3 "$HELPER_PY" free_port 10000)
            echo "🔀 Running Concurrently: Launching on port $target_port..."
        elif [ "$swap_choice" = "3" ]; then
            echo ""
            echo "--- Custom Launch Parameters ---"
            echo -n "Host [$DEFAULT_HOST] (b: Back, e: Exit): "
            read -r custom_host
            check_nav "$custom_host" || return
            [ -n "$custom_host" ] && host="$custom_host"

            echo -n "Port [$DEFAULT_PORT] (b: Back, e: Exit): "
            read -r custom_port
            check_nav "$custom_port" || return
            [ -n "$custom_port" ] && target_port="$custom_port"

            echo -n "Temperature [$temp] (b: Back, e: Exit): "
            read -r custom_temp
            check_nav "$custom_temp" || return
            [ -n "$custom_temp" ] && temp="$custom_temp"

            echo -n "Max Tokens [$max_tokens] (b: Back, e: Exit): "
            read -r custom_tokens
            check_nav "$custom_tokens" || return
            [ -n "$custom_tokens" ] && max_tokens="$custom_tokens"

            echo -n "Enable Thinking Tokens? (y/n, default y) [b: Back, e: Exit]: "
            read -r custom_thinking
            check_nav "$custom_thinking" || return
            if [ "$custom_thinking" = "n" ] || [ "$custom_thinking" = "N" ]; then
                extra_args="$extra_args --chat-template-args '{\"enable_thinking\":false}'"
            fi
        fi
    fi

    local check_port_pid
    check_port_pid=$(lsof -t -i :"$target_port" 2>/dev/null)
    if [ -n "$check_port_pid" ]; then
        kill -9 "$check_port_pid" 2>/dev/null
        sleep 1
    fi

    local safe_name
    safe_name=$(echo "$model_name" | tr '/' '_' | tr -cd '[:alnum:]_.-')
    local log_file="$LOG_DIR/${safe_name}_${target_port}.log"

    echo ""
    echo "Launching MLX Model Server..."
    echo "  Model: $model_name"
    echo "  Path:  $model_path"
    echo "  Host:  $host"
    echo "  Port:  $target_port"
    echo "  Log:   $log_file"
    echo "---------------------------------------------------------"

    nohup uvx --from mlx-lm mlx_lm.server \
        --model "$model_path" \
        --host "$host" \
        --port "$target_port" \
        --temp "$temp" \
        --max-tokens "$max_tokens" $extra_args > "$log_file" 2>&1 &

    local server_pid=$!
    echo "$server_pid" > "$PID_DIR/${safe_name}_${target_port}.pid"

    python3 "$HELPER_PY" sync_configs "$model_name" 2>/dev/null || true

    echo -n "Waiting for server startup..."
    local attempts=0
    local ready=0
    while [ $attempts -lt 12 ]; do
        sleep 1
        echo -n "."
        if curl -s -m 1 "http://$host:$target_port/v1/models" | grep -q "data" 2>/dev/null; then
            ready=1
            break
        fi
        if ! kill -0 "$server_pid" 2>/dev/null; then
            break
        fi
        attempts=$((attempts + 1))
    done
    echo ""

    if [ "$ready" -eq 1 ]; then
        echo "✓ Model server successfully started and READY!"
        echo "  Endpoint: http://$host:$target_port/v1"
        echo "  Curl test:"
        echo "  curl http://$host:$target_port/v1/chat/completions \\"
        echo "    -H \"Content-Type: application/json\" \\"
        echo "    -d '{\"model\": \"$model_name\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}], \"max_tokens\": 50}'"
    else
        if kill -0 "$server_pid" 2>/dev/null; then
            echo "⏳ Process PID $server_pid is running and loading model weights into memory."
            echo "   Check server log with option 8: tail -f $log_file"
        else
            echo "❌ Server failed to start. View log file: $log_file"
        fi
    fi
    echo ""
    read -r -p "Press Enter to continue..."
}

# ── 5. KILL SWITCH / Stop Model ──────────────────────────────────────
stop_model() {
    local direct_target="${1:-}"
    local running_json
    running_json=$(python3 "$HELPER_PY" running_servers)

    local count
    count=$(echo "$running_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo ""
        echo "No running MLX model servers detected."
        echo ""
        read -r -p "Press Enter to return..."
        return
    fi

    # Handle direct invocation e.g. "k 2" or "stop 2" or "stop 38961"
    if [ -n "$direct_target" ]; then
        if [[ "$direct_target" =~ ^[0-9]+$ ]] && [ "$direct_target" -ge 1 ] && [ "$direct_target" -le "$count" ]; then
            local pid
            pid=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$direct_target-1]['pid'])")
            local mname
            mname=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$direct_target-1]['model'])")
            local port
            port=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$direct_target-1]['port'])")
            echo ""
            echo "⚡ KILL SWITCH: Force killing #$direct_target: '$mname' (PID $pid on port $port)..."
            kill -9 "$pid" 2>/dev/null
            rm -f "$PID_DIR"/*_"${port}".pid 2>/dev/null
            echo "✓ Process PID $pid force-killed."
            echo ""
            sleep 1
            return
        elif [[ "$direct_target" =~ ^[0-9]+$ ]]; then
            echo ""
            echo "⚡ KILL SWITCH: Force killing PID $direct_target..."
            kill -9 "$direct_target" 2>/dev/null
            rm -f "$PID_DIR"/*.pid 2>/dev/null
            echo "✓ PID $direct_target killed."
            echo ""
            sleep 1
            return
        fi
    fi

    echo ""
    echo "⚡ KILL SWITCH: Select Process to Terminate Immediately"
    echo "---------------------------------------------------------"
    echo "$running_json" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
for i, s in enumerate(servers, 1):
    print(f'  {i:2d}. [{s[\"status\"]}] {s[\"model\"]} (PID: {s[\"pid\"]}, Host: {s[\"host\"]}, Port: {s[\"port\"]})')
"
    echo "---------------------------------------------------------"
    echo ""
    echo -n "Enter number [1-$count] to KILL (-9), [u] Kill Unresponsive, [a] Kill ALL, [b] Back, [e] Exit: "
    read -r choice
    check_nav "$choice" || return

    if [ "$choice" = "u" ] || [ "$choice" = "U" ]; then
        echo ""
        echo "⚡ KILL SWITCH: Terminating all unresponsive/stale processes..."
        echo "$running_json" | python3 -c "
import sys, json, os, signal
servers = json.load(sys.stdin)
cleaned = 0
for s in servers:
    if 'UNRESPONSIVE' in s['status']:
        try:
            os.kill(int(s['pid']), signal.SIGKILL)
            print(f'  ⚡ Killed unresponsive PID {s[\"pid\"]} ({s[\"model\"]} on port {s[\"port\"]})')
            cleaned += 1
        except Exception as e:
            print(f'  Could not kill PID {s[\"pid\"]}: {e}')
if cleaned == 0:
    print('  No unresponsive processes found.')
"
        rm -f "$PID_DIR"/*.pid 2>/dev/null
    elif [ "$choice" = "a" ] || [ "$choice" = "A" ] || [ "$choice" = "all" ]; then
        echo ""
        echo "⚡ KILL SWITCH: Terminating ALL running MLX model servers..."
        echo "$running_json" | python3 -c "
import sys, json, os, signal
servers = json.load(sys.stdin)
for s in servers:
    try:
        os.kill(int(s['pid']), signal.SIGKILL)
        print(f'  ⚡ Force-killed PID {s[\"pid\"]} ({s[\"model\"]})')
    except Exception as e:
        print(f'  Could not kill PID {s[\"pid\"]}: {e}')
"
        rm -f "$PID_DIR"/*.pid 2>/dev/null
        echo "✓ All servers stopped."
    elif [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
        local pid
        pid=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['pid'])")
        local mname
        mname=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['model'])")
        local port
        port=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['port'])")
        echo ""
        echo "⚡ KILL SWITCH: Force killing model '$mname' (PID $pid on port $port)..."
        kill -9 "$pid" 2>/dev/null
        rm -f "$PID_DIR"/*_"${port}".pid 2>/dev/null
        echo "✓ Process PID $pid force-killed."
    else
        echo "Invalid selection."
    fi
    echo ""
    read -r -p "Press Enter to continue..."
}

# ── 6. Delete Model ──────────────────────────────────────────────────
delete_model() {
    local local_json
    local_json=$(python3 "$HELPER_PY" find_models)

    local count
    count=$(echo "$local_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo ""
        echo "No downloaded models found."
        echo ""
        read -r -p "Press Enter to return..."
        return
    fi

    echo ""
    echo "=== Delete a Downloaded Model ==="
    echo "$local_json" | python3 -c "
import sys, json
models = json.load(sys.stdin)
for i, m in enumerate(models, 1):
    print(f'  {i:2d}. {m[\"name\"]} ({m[\"size\"]})')
    print(f'      Path: {m[\"delete_target\"]}')
"
    echo ""
    echo -n "Select model number to delete [1-$count] (or [b] Back, [e] Exit): "
    read -r choice
    check_nav "$choice" || return

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
        local target_name
        target_name=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['name'])")
        local target_dir
        target_dir=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['delete_target'])")
        local target_size
        target_size=$(echo "$local_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['size'])")

        echo ""
        echo "⚠️ WARNING: You are about to delete '$target_name' ($target_size)."
        echo "   Target directory: $target_dir"
        echo -n "Are you sure you want to permanently delete this model? (y/N) [b: Back, e: Exit]: "
        read -r confirm
        check_nav "$confirm" || return

        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            echo "Deleting $target_dir..."
            rm -rf "$target_dir"
            echo "✓ Model '$target_name' deleted."
        else
            echo "Deletion cancelled."
        fi
    else
        echo "Invalid selection."
    fi
    echo ""
    read -r -p "Press Enter to continue..."
}

# ── 7. View Running Models & Health ──────────────────────────────────
view_health() {
    show_running_header
    echo "API Endpoints status:"
    curl -s http://127.0.0.1:9999/v1/models 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('  http://127.0.0.1:9999/v1 -> Active Models:')
    for m in data.get('data', []):
        print(f'    - {m.get(\"id\")}')
except Exception:
    print('  http://127.0.0.1:9999/v1 -> (No active HTTP response)')
"
    echo ""
    read -r -p "Press Enter to return..."
}

# ── 8. View Server Logs ──────────────────────────────────────────────
view_logs() {
    echo ""
    echo "=== Available Server Logs ==="
    local log_files=("$LOG_DIR"/*.log)
    if [ ! -e "${log_files[0]}" ]; then
        echo "  (no log files found in $LOG_DIR)"
        echo ""
        read -r -p "Press Enter to return..."
        return
    fi

    local i=1
    for lf in "${log_files[@]}"; do
        local fname
        fname=$(basename "$lf")
        local fsize
        fsize=$(du -sh "$lf" 2>/dev/null | cut -f1)
        echo "  $i. $fname ($fsize)"
        i=$((i + 1))
    done

    echo ""
    echo -n "Select log number to view [1-$((i-1))] (or [b] Back, [e] Exit): "
    read -r choice
    check_nav "$choice" || return

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -lt "$i" ]; then
        local selected_log="${log_files[$((choice-1))]}"
        echo ""
        echo "Tailing log file (Press Ctrl+C to stop)..."
        echo "---------------------------------------------------------"
        tail -f "$selected_log"
    fi
}

# ── 9. Quick Curl Test ───────────────────────────────────────────────
test_curl() {
    local running_json
    running_json=$(python3 "$HELPER_PY" running_servers)

    local count
    count=$(echo "$running_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)

    if [ "$count" -eq 0 ]; then
        echo ""
        echo "No running MLX model servers to test."
        echo ""
        read -r -p "Press Enter to return..."
        return
    fi

    echo ""
    echo "=== Quick Curl Test ==="
    echo "$running_json" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
for i, s in enumerate(servers, 1):
    print(f'  {i:2d}. [{s[\"status\"]}] {s[\"model\"]} (Host: {s[\"host\"]}, Port: {s[\"port\"]})')
"
    echo ""
    echo -n "Select server number [1-$count] (or [b] Back, [e] Exit): "
    read -r choice
    check_nav "$choice" || return

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
        local host
        host=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['host'])")
        local port
        port=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['port'])")
        local model
        model=$(echo "$running_json" | python3 -c "import sys, json; print(json.load(sys.stdin)[$choice-1]['model'])")

        echo ""
        echo -n "Enter test prompt [default: Hello!]: "
        read -r prompt_text
        check_nav "$prompt_text" || return
        [ -z "$prompt_text" ] && prompt_text="Hello!"

        echo ""
        echo "Sending curl request to http://$host:$port/v1/chat/completions ..."
        echo "---------------------------------------------------------"
        curl -s "http://$host:$port/v1/chat/completions" \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"$model\",
                \"messages\": [{\"role\": \"user\", \"content\": \"$prompt_text\"}],
                \"max_tokens\": 100
            }" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    content = data['choices'][0]['message']['content']
    print('\nModel Response:\n' + content + '\n')
except Exception as e:
    print('Error parsing response:', e)
"
    fi
    echo ""
    read -r -p "Press Enter to return..."
}

# ── Main Menu ────────────────────────────────────────────────────────
main_menu() {
    while true; do
        clear 2>/dev/null || true
        echo "╔════════════════════════════════════════════════════════════╗"
        echo "║            MLX Model Control Center (MacBook)              ║"
        echo "╚════════════════════════════════════════════════════════════╝"
        show_running_header
        echo "  1. List Downloaded Models (Select # to Launch)"
        echo "  2. Search Hugging Face for MLX Models"
        echo "  3. Download / Add Model by HF Repo ID"
        echo "  4. Start a Model (Fast Swap or Custom Parameters)"
        echo "  5. ⚡ KILL SWITCH: Stop / Terminate a Running Process"
        echo "  6. Delete a Downloaded Model"
        echo "  7. View Running Models & Test API Health"
        echo "  8. View Server Logs"
        echo "  9. Quick Curl Test Prompt"
        echo ""
        echo "  [k <#>] Instant Kill process #    [b] Refresh / Back    [e] Exit"
        echo "--------------------------------------------------------------"
        echo -n "Select option [1-9, k, b, e]: "
        read -r choice

        case "$(echo "$choice" | tr '[:upper:]' '[:lower:]')" in
            1) list_models ;;
            2) search_hf ;;
            3) download_model ;;
            4) start_model ;;
            5|k|kill) stop_model ;;
            k*)
                local target_num
                target_num=$(echo "$choice" | sed -E 's/^[kK][[:space:]]*//')
                stop_model "$target_num"
                ;;
            6) delete_model ;;
            7) view_health ;;
            8) view_logs ;;
            9) test_curl ;;
            b) continue ;;
            e)
                echo ""
                echo "Exiting MLX Model Manager. Goodbye!"
                exit 0
                ;;
            *)
                echo "Invalid option."
                sleep 1
                ;;
        esac
    done
}

# CLI direct invocation support
case "${1:-}" in
    start) start_model "${2:-}" ;;
    stop|kill) stop_model "${2:-}" ;;
    list) list_models false ;;
    search) search_hf "${2:-}" ;;
    download) download_model "${2:-}" ;;
    delete) delete_model ;;
    status|running) view_health ;;
    logs) view_logs ;;
    test) test_curl ;;
    *) main_menu ;;
esac
