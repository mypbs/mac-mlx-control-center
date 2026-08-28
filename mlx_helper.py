#!/usr/bin/env python3
import os, sys, json, subprocess, re, urllib.request, urllib.parse, socket, time

_REPO_SIZE_CACHE = {}
_SPEED_CACHE = {}
PAUSED_FILE = os.path.expanduser("~/.mlx_pids/paused_downloads.json")
SETTINGS_FILE = os.path.expanduser("~/.mlx_pids/settings.json")

def load_global_settings():
    default_settings = {
        "default_port": 9999,
        "default_host": "127.0.0.1",
        "default_temp": 0.0,
        "default_max_tokens": 4096,
        "auto_sync_agents": True
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                st = json.load(f)
                default_settings.update(st)
        except Exception:
            pass
    return default_settings

def save_global_settings(settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass

def parse_hf_identifier(input_str, explicit_subfolder=""):
    """Parses any Hugging Face URL, repo ID with subfolder, or raw path into structured components."""
    s = (input_str or "").strip()
    subfolder = (explicit_subfolder or "").strip()
    revision = "main"
    s = re.sub(r"/+$", "", s)

    if "huggingface.co/" in s:
        path_part = s.split("huggingface.co/")[-1].strip("/")
        m_tree = re.match(r"^([^/]+/[^/]+)/tree/([^/]+)(?:/(.+))?$", path_part)
        m_blob = re.match(r"^([^/]+/[^/]+)/blob/([^/]+)(?:/(.+))?$", path_part)
        if m_tree:
            repo_id = m_tree.group(1)
            revision = m_tree.group(2)
            if m_tree.group(3):
                subfolder = m_tree.group(3).strip("/")
        elif m_blob:
            repo_id = m_blob.group(1)
            revision = m_blob.group(2)
            if m_blob.group(3):
                rest = m_blob.group(3).strip("/")
                if "/" in rest:
                    subfolder = os.path.dirname(rest)
                elif not any(rest.endswith(ext) for ext in [".json", ".safetensors", ".bin", ".md", ".jinja", ".txt"]):
                    subfolder = rest
        else:
            parts = path_part.split("/")
            if len(parts) >= 2:
                repo_id = f"{parts[0]}/{parts[1]}"
                if len(parts) > 2 and not subfolder:
                    subfolder = "/".join(parts[2:])
            else:
                repo_id = path_part
    elif ":" in s:
        repo_id, sf = s.split(":", 1)
        subfolder = sf.strip()
    else:
        parts = s.split("/")
        if len(parts) > 2:
            repo_id = f"{parts[0]}/{parts[1]}"
            if not subfolder:
                subfolder = "/".join(parts[2:])
        else:
            repo_id = s

    display_name = f"{repo_id} ({subfolder})" if subfolder else repo_id
    download_id = f"{repo_id}:{subfolder}" if subfolder else repo_id

    return {
        "repo_id": repo_id,
        "subfolder": subfolder,
        "revision": revision,
        "display_name": display_name,
        "download_id": download_id
    }

def get_repo_files_size(repo_id, subfolder=""):
    cache_key = f"{repo_id}:{subfolder}" if subfolder else repo_id
    if cache_key in _REPO_SIZE_CACHE:
        return _REPO_SIZE_CACHE[cache_key]
    try:
        url = f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id)}/tree/main?recursive=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            files = json.loads(resp.read().decode())
            total = 0
            sf_prefix = f"{subfolder.strip('/')}/" if subfolder else ""
            for f in files:
                if isinstance(f, dict) and "size" in f:
                    path = f.get("path", "")
                    sz = f.get("size", 0)
                    if subfolder:
                        if path.startswith(sf_prefix) or path == subfolder:
                            total += sz
                    else:
                        total += sz
            if total > 0:
                _REPO_SIZE_CACHE[cache_key] = total
                return total
    except Exception:
        pass
    return 0

def get_repo_quant_variants(repo_id):
    """Detects if a repo has multiple quantization subfolders (e.g. 2-bit, 4-bit, 6-bit, 8-bit)."""
    try:
        url = f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id)}/tree/main"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            items = json.loads(resp.read().decode())
            dirs = [it.get("path", "") for it in items if it.get("type") == "directory"]
            
            quant_dirs = []
            for d in dirs:
                dl = d.lower()
                if any(q in dl for q in ["bit", "quant", "bf16", "fp16", "q4", "q8", "int4", "int8", "awq", "gptq", "mlx"]):
                    quant_dirs.append(d)
                elif re.match(r"^\d+(-|_)?bit$", dl):
                    quant_dirs.append(d)
            
            variants = []
            for qd in (quant_dirs if quant_dirs else dirs):
                sz = get_repo_files_size(repo_id, subfolder=qd)
                sz_gb = sz / (1024**3)
                sz_str = f"{sz_gb:.1f} GB" if sz_gb >= 1 else f"{sz/(1024**2):.1f} MB"
                label = qd
                if "4-bit" in qd.lower() or "4bit" in qd.lower():
                    label = f"{qd} (Recommended)"
                variants.append({
                    "subfolder": qd,
                    "label": label,
                    "size_bytes": sz,
                    "size_str": sz_str,
                    "size_gb": round(sz_gb, 2)
                })
            return variants
    except Exception:
        return []

def load_paused_downloads():
    if os.path.exists(PAUSED_FILE):
        try:
            with open(PAUSED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_paused_downloads(data):
    try:
        with open(PAUSED_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def sync_pi_and_opencode(active_model, port=9999):
    """Automatically updates Pi Code and OpenCode configurations to auto-detect the active MLX model under provider 'MyMac'."""
    try:
        # 1. Update Pi settings.json
        pi_settings_file = os.path.expanduser("~/.pi/agent/settings.json")
        if os.path.exists(pi_settings_file):
            try:
                with open(pi_settings_file, "r") as f:
                    st = json.load(f)
                st["defaultProvider"] = "MyMac"
                st["defaultModel"] = "default_model"
                with open(pi_settings_file, "w") as f:
                    json.dump(st, f, indent=2)
            except Exception:
                pass

        # 2. Update Pi models.json
        pi_models_file = os.path.expanduser("~/.pi/agent/models.json")
        if os.path.exists(pi_models_file):
            try:
                with open(pi_models_file, "r") as f:
                    md = json.load(f)
                if "providers" not in md:
                    md["providers"] = {}
                
                md["providers"]["MyMac"] = {
                    "baseUrl": f"http://127.0.0.1:{port}/v1",
                    "api": "openai-completions",
                    "apiKey": "local",
                    "name": "MyMac",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False
                    },
                    "models": [
                        {
                            "id": "default_model",
                            "name": "⚡ Active MLX Model (Auto-Detect)",
                            "reasoning": True,
                            "input": ["text"],
                            "contextWindow": 131072,
                            "maxTokens": 8192,
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
                        },
                        {
                            "id": active_model,
                            "name": f"{active_model} (Local)",
                            "reasoning": True,
                            "input": ["text"],
                            "contextWindow": 131072,
                            "maxTokens": 8192,
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
                        }
                    ]
                }
                with open(pi_models_file, "w") as f:
                    json.dump(md, f, indent=2)
            except Exception:
                pass

        # 3. Update OpenCode configs
        opencode_files = [
            os.path.expanduser("~/.config/opencode/opencode.jsonc"),
            os.path.expanduser("~/opencode.jsonc")
        ]
        for opf in opencode_files:
            if os.path.exists(opf):
                try:
                    with open(opf, "r") as f:
                        opd = json.load(f)
                    opd["model"] = "MyMac/default_model"
                    if "provider" not in opd:
                        opd["provider"] = {}
                    
                    opd["provider"]["MyMac"] = {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "MyMac",
                        "options": {
                            "baseURL": f"http://127.0.0.1:{port}/v1"
                        },
                        "models": {
                            "default_model": {
                                "name": "⚡ Active MLX Model (Auto-Detect)"
                            },
                            active_model: {
                                "name": active_model
                            }
                        }
                    }
                    with open(opf, "w") as f:
                        json.dump(opd, f, indent=2)
                except Exception:
                    pass
    except Exception:
        pass

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
            has_config = "config.json" in files
            has_gguf = any(f.endswith(".gguf") for f in files)

            if (has_config or has_gguf) and "1_Pooling" not in root:
                real_path = os.path.realpath(root)
                if real_path in seen_paths:
                    continue

                parent_hub_dir = root
                parts = root.split(os.sep)
                base_name = ""
                for p in parts:
                    if p.startswith("models--"):
                        base_name = p.replace("models--", "").replace("--", "/")
                        parent_hub_dir = root[:root.find(p) + len(p)]
                        break
                if not base_name:
                    base_name = os.path.basename(root)

                # Check if this model is inside a quantization subfolder (e.g. snapshots/<hash>/4-bit)
                subfolder = ""
                if "snapshots" in parts:
                    snap_idx = parts.index("snapshots")
                    if len(parts) > snap_idx + 2:
                        subfolder = "/".join(parts[snap_idx + 2:])

                display_name = f"{base_name} ({subfolder})" if subfolder else base_name

                model_type = "unknown"
                supported = True
                arch_tag = "MLX Compatible"

                if has_config:
                    try:
                        with open(os.path.join(root, "config.json"), "r", errors="ignore") as f:
                            cfg = json.load(f)
                            model_type = str(cfg.get("model_type", "unknown")).lower()
                            if model_type in ["bert", "xlm-roberta", "mpnet"]:
                                supported = False
                                arch_tag = f"Embedding Model ({model_type})"
                            elif model_type in ["gemma4_unified", "gemma4_unified_audio"]:
                                supported = False
                                arch_tag = f"Experimental Arch ({model_type})"
                            else:
                                arch_tag = f"MLX ({model_type})"
                    except Exception:
                        pass
                elif has_gguf:
                    supported = False
                    arch_tag = "GGUF Format"

                seen_paths.add(real_path)

                # Calculate accurate model size by resolving symlinks in this model directory
                size_bytes = 0
                for r, d, f in os.walk(root):
                    for file in f:
                        fp = os.path.join(r, file)
                        try:
                            size_bytes += os.stat(fp).st_size
                        except Exception:
                            pass
                
                # If size resolved to 0 (e.g. non-symlink blobs folder), fallback to walking parent
                if size_bytes == 0:
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

                target_stat_dir = parent_hub_dir if "models--" in parent_hub_dir else root
                try:
                    st_obj = os.stat(target_stat_dir)
                    model_ts = getattr(st_obj, "st_birthtime", st_obj.st_mtime)
                    if model_ts <= 0:
                        model_ts = st_obj.st_mtime
                except Exception:
                    model_ts = time.time()

                date_added_str = time.strftime("%b %d, %Y", time.localtime(model_ts))

                models.append({
                    "name": display_name,
                    "base_name": base_name,
                    "subfolder": subfolder,
                    "size": size_str,
                    "size_gb": round(size_gb, 2),
                    "path": root,
                    "delete_target": root if subfolder else (parent_hub_dir if "models--" in parent_hub_dir else root),
                    "supported": supported,
                    "arch_tag": arch_tag,
                    "model_type": model_type,
                    "created_ts": round(model_ts, 1),
                    "date_added": date_added_str
                })
    return models

def get_running_servers():
    servers = []
    st = load_global_settings()
    default_p = str(st.get("default_port", 9999))
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
                port = port_match.group(1) if port_match else default_p
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

def get_active_downloads():
    downloads = []
    now = time.time()
    try:
        output = subprocess.check_output(["ps", "aux"], text=True)
        for line in output.splitlines():
            if ("hf download" in line or "huggingface-cli download" in line) and "grep" not in line:
                parts = line.split()
                pid = parts[1]
                repo_match = re.search(r"download\s+([^\s]+)", line)
                raw_repo = repo_match.group(1) if repo_match else "unknown"

                include_match = re.search(r"--include\s+[\"']?([^\"'\s]+)[\"']?", line)
                explicit_sf = include_match.group(1).replace("/*", "").strip() if include_match else ""

                parsed = parse_hf_identifier(raw_repo, explicit_sf)
                repo_id = parsed["repo_id"]
                subfolder = parsed["subfolder"]
                download_id = parsed["download_id"]
                display_name = parsed["display_name"]

                cache_dir = ""
                if "/" in repo_id:
                    org, repo = repo_id.split("/", 1)
                    cache_dir = os.path.expanduser(f"~/.cache/huggingface/hub/models--{org}--{repo}")

                downloaded_bytes = 0
                if cache_dir and os.path.exists(cache_dir):
                    for r, d, f in os.walk(cache_dir):
                        for file in f:
                            fp = os.path.join(r, file)
                            if not os.path.islink(fp):
                                try:
                                    downloaded_bytes += os.path.getsize(fp)
                                except Exception:
                                    pass

                total_bytes = get_repo_files_size(repo_id, subfolder=subfolder)
                percent = round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
                percent = min(100.0, percent)

                speed_str = "Calculating..."
                eta_str = "--"
                if download_id in _SPEED_CACHE:
                    prev_bytes, prev_time = _SPEED_CACHE[download_id]
                    dt = now - prev_time
                    if dt > 0.5:
                        dbytes = downloaded_bytes - prev_bytes
                        speed_bps = dbytes / dt
                        speed_mb = speed_bps / (1024**2)
                        if speed_mb > 0.05:
                            speed_str = f"{speed_mb:.1f} MB/s"
                            rem_bytes = max(0, total_bytes - downloaded_bytes)
                            if rem_bytes > 0 and speed_bps > 0:
                                rem_sec = int(rem_bytes / speed_bps)
                                if rem_sec < 60:
                                    eta_str = f"{rem_sec}s"
                                else:
                                    eta_str = f"{rem_sec//60}m {rem_sec%60}s"
                        else:
                            speed_str = "0 MB/s"
                _SPEED_CACHE[download_id] = (downloaded_bytes, now)

                dl_gb = downloaded_bytes / (1024**3)
                dl_str = f"{dl_gb:.2f} GB" if dl_gb >= 1 else f"{downloaded_bytes/(1024**2):.1f} MB"

                tot_gb = total_bytes / (1024**3)
                tot_str = f"{tot_gb:.2f} GB" if tot_gb >= 1 else (f"{total_bytes/(1024**2):.1f} MB" if total_bytes > 0 else "Unknown")

                downloads.append({
                    "pid": pid,
                    "repo_id": repo_id,
                    "subfolder": subfolder,
                    "download_id": download_id,
                    "display_name": display_name,
                    "downloaded_bytes": downloaded_bytes,
                    "downloaded_size": dl_str,
                    "total_bytes": total_bytes,
                    "total_size": tot_str,
                    "percent": percent,
                    "speed": speed_str,
                    "eta": eta_str,
                    "status": "DOWNLOADING",
                    "cache_dir": cache_dir
                })
    except Exception:
        pass

    # Add Paused Downloads to list
    paused = load_paused_downloads()
    active_ids = {d["download_id"] for d in downloads}

    for dl_id, pinfo in list(paused.items()):
        if dl_id not in active_ids:
            if isinstance(pinfo, str):
                pinfo = {"repo_id": pinfo, "subfolder": "", "cache_dir": ""}
            repo_id = pinfo.get("repo_id", dl_id)
            subfolder = pinfo.get("subfolder", "")
            display_name = f"{repo_id} ({subfolder})" if subfolder else repo_id
            cache_dir = pinfo.get("cache_dir", "")
            downloaded_bytes = 0
            if cache_dir and os.path.exists(cache_dir):
                for r, d, f in os.walk(cache_dir):
                    for file in f:
                        fp = os.path.join(r, file)
                        if not os.path.islink(fp):
                            try:
                                downloaded_bytes += os.path.getsize(fp)
                            except Exception:
                                pass
            total_bytes = get_repo_files_size(repo_id, subfolder=subfolder)
            percent = round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
            percent = min(100.0, percent)

            dl_gb = downloaded_bytes / (1024**3)
            dl_str = f"{dl_gb:.2f} GB" if dl_gb >= 1 else f"{downloaded_bytes/(1024**2):.1f} MB"

            tot_gb = total_bytes / (1024**3)
            tot_str = f"{tot_gb:.2f} GB" if tot_gb >= 1 else (f"{total_bytes/(1024**2):.1f} MB" if total_bytes > 0 else "Unknown")

            downloads.append({
                "pid": None,
                "repo_id": repo_id,
                "subfolder": subfolder,
                "download_id": dl_id,
                "display_name": display_name,
                "downloaded_bytes": downloaded_bytes,
                "downloaded_size": dl_str,
                "total_bytes": total_bytes,
                "total_size": tot_str,
                "percent": percent,
                "speed": "Paused",
                "eta": "Paused",
                "status": "PAUSED",
                "cache_dir": cache_dir
            })

    return downloads

def get_system_stats():
    total_ram = 32 * 1024**3
    try:
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        total_ram = int(out.strip())
    except Exception:
        pass

    used_ram = 0
    free_ram = 0
    cached_ram = 0
    try:
        vm = subprocess.check_output(["vm_stat"], text=True)
        page_size = 16384
        vm_dict = {}
        for line in vm.splitlines():
            if "page size of" in line:
                m = re.search(r"page size of (\d+) bytes", line)
                if m:
                    page_size = int(m.group(1))
            elif ":" in line:
                parts = line.split(":")
                k = parts[0].strip()
                val_m = re.search(r"(\d+)", parts[1])
                if val_m:
                    vm_dict[k] = int(val_m.group(1))

        # Accurate Activity Monitor / HTOP calculation for macOS:
        # Memory Used = Anonymous pages (App memory) + Wired pages + Compressed pages
        anonymous = vm_dict.get("Anonymous pages", 0) * page_size
        wired = vm_dict.get("Pages wired down", 0) * page_size
        compressor = vm_dict.get("Pages occupied by compressor", 0) * page_size
        purgeable = vm_dict.get("Pages purgeable", 0) * page_size
        file_backed = vm_dict.get("File-backed pages", 0) * page_size

        used_ram = anonymous + wired + compressor
        cached_ram = file_backed + purgeable
        free_ram = max(0, total_ram - used_ram)
    except Exception:
        anonymous = int(total_ram * 0.4)
        wired = int(total_ram * 0.1)
        compressor = int(total_ram * 0.1)
        used_ram = int(total_ram * 0.6)
        cached_ram = int(total_ram * 0.2)
        free_ram = total_ram - used_ram

    mlx_ram = 0
    servers = get_running_servers()
    pids = [s["pid"] for s in servers]
    if pids:
        try:
            ps_out = subprocess.check_output(["ps", "-o", "pid,rss", "-p", ",".join(pids)], text=True)
            for line in ps_out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    mlx_ram += int(parts[1]) * 1024
        except Exception:
            pass

    cpu_percent = 0.0
    try:
        out = subprocess.check_output(["ps", "-A", "-o", "%cpu"], text=True)
        total_cpu = sum(float(line.strip()) for line in out.splitlines()[1:] if line.strip())
        cores = os.cpu_count() or 8
        cpu_percent = min(100.0, round(total_cpu / cores, 1))
    except Exception:
        pass

    return {
        "total_ram_gb": round(total_ram / (1024**3), 1),
        "used_ram_gb": round(used_ram / (1024**3), 1),
        "free_ram_gb": round(free_ram / (1024**3), 1),
        "cached_ram_gb": round(cached_ram / (1024**3), 1),
        "app_ram_gb": round(anonymous / (1024**3), 1),
        "wired_ram_gb": round(wired / (1024**3), 1),
        "compressed_ram_gb": round(compressor / (1024**3), 1),
        "ram_percent": round((used_ram / total_ram) * 100, 1) if total_ram else 0,
        "mlx_ram_gb": round(mlx_ram / (1024**3), 2),
        "cpu_percent": cpu_percent,
        "active_models": len(servers)
    }

def classify_process(pid, user, args, active_server_pids=None):
    if active_server_pids is None:
        active_server_pids = set()
    
    args_lower = args.lower()
    base = os.path.basename(args.split()[0]) if args.strip() else 'unknown'
    
    m_app = re.search(r'/([^/]+)\.app(?:/|$)', args)
    app_name = m_app.group(1) if m_app else None
    
    category = 'App'
    display_name = app_name or base
    is_system = False
    is_mlx = str(pid) in active_server_pids or pid in active_server_pids
    
    if is_mlx or 'mlx_lm.server' in args or 'mlx_lm' in args or 'mlx_gui_server' in args:
        category = 'AI Model'
        m_model = re.search(r'--model\s+([^\s]+)', args)
        if m_model:
            display_name = f'MLX: {os.path.basename(m_model.group(1))}'
        elif 'mlx_gui_server' in args:
            display_name = 'MLX Control Center GUI'
        else:
            display_name = f'MLX: {base}'
    elif any(k in args_lower for k in ['ollama', 'lmstudio', 'llama.cpp', 'vllm', 'text-generation']):
        category = 'AI Model'
        display_name = f'AI: {app_name or base}'
    elif any(k in args_lower for k in ['brave', 'chrome', 'firefox', 'safari', 'arc', 'edge', 'webkit']):
        category = 'Browser'
        if app_name:
            if 'helper' in args_lower or 'renderer' in args_lower:
                display_name = f'{app_name} (Tab)'
            elif 'gpu' in args_lower:
                display_name = f'{app_name} (GPU)'
            else:
                display_name = app_name
    elif any(k in args_lower for k in ['docker', 'code', 'cursor', 'node', 'python', 'git', 'xcode', 'iterm', 'terminal', 'agy']):
        category = 'Dev Tool'
        if 'agy' in args_lower:
            display_name = 'Antigravity CLI (agy)'
        elif app_name:
            display_name = app_name
        else:
            display_name = base
    elif user == 'root' or any(k in base.lower() for k in ['windowserver', 'kernel_task', 'launchd', 'loginwindow', 'spotlight', 'mediaanalysisd', 'mds', 'core', 'daemon']):
        category = 'macOS System'
        is_system = True
        display_name = base

    PROTECTED = {'windowserver', 'kernel_task', 'launchd', 'loginwindow', 'systemstats', 'opendirectoryd', 'syslogd', 'securityd', 'mds', 'cfprefsd', 'distnoted', 'fseventsd', 'trustd', 'runningboardd', 'diskarbitrationd', 'coreauthd'}
    if base.lower() in PROTECTED or pid in [0, 1] or user == 'root':
        is_system = True
        
    return display_name, category, is_system, is_mlx

def get_top_memory_processes(limit=35):
    try:
        servers = get_running_servers()
        server_pids = {str(s.get("pid", "")) for s in servers}
        
        out = subprocess.check_output(["ps", "-A", "-o", "pid,user,%mem,rss,args"], text=True)
        lines = out.strip().splitlines()
        procs = []
        for line in lines[1:]:
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            pid_str, user, mem_pct_str, rss_kb_str, args = parts
            try:
                pid = int(pid_str)
                rss_kb = int(rss_kb_str)
                mem_pct = float(mem_pct_str)
            except ValueError:
                continue
                
            if rss_kb < 15360:  # Skip < 15 MB
                continue
                
            rss_bytes = rss_kb * 1024
            rss_gb = rss_bytes / (1024**3)
            rss_mb = rss_bytes / (1024**2)
            rss_str = f"{rss_gb:.2f} GB" if rss_gb >= 1.0 else f"{rss_mb:.0f} MB"
            
            dname, cat, is_sys, is_mlx = classify_process(pid, user, args, server_pids)
            
            procs.append({
                "pid": pid,
                "user": user,
                "name": dname,
                "command": args,
                "rss_bytes": rss_bytes,
                "rss_gb": round(rss_gb, 2),
                "rss_str": rss_str,
                "mem_pct": mem_pct,
                "category": cat,
                "is_system": is_sys,
                "is_mlx": is_mlx
            })
            
        procs.sort(key=lambda x: x["rss_bytes"], reverse=True)
        return procs[:limit]
    except Exception as e:
        return []

def kill_process_by_pid(pid):
    PROTECTED_PIDS = {0, 1}
    try:
        pid = int(pid)
        if pid in PROTECTED_PIDS or pid <= 0:
            return {"error": "Cannot terminate system PID"}
        
        try:
            comm = subprocess.check_output(["ps", "-p", str(pid), "-o", "comm="], text=True).strip()
            base = os.path.basename(comm).lower()
            if base in ['windowserver', 'kernel_task', 'launchd', 'loginwindow']:
                return {"error": f"Cannot terminate protected system process '{base}'"}
        except Exception:
            pass

        servers = get_running_servers()
        for s in servers:
            if str(s.get("pid")) == str(pid):
                stop_server(str(pid))
                return {"status": "ok", "pid": pid, "stopped_mlx": True}

        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
            
        return {"status": "ok", "pid": pid}
    except Exception as e:
        return {"error": str(e)}

def estimate_ram_requirement(repo_id):
    """Estimate RAM requirement in GB based on model parameter count in repo ID."""
    rid = repo_id.lower()
    if "70b" in rid or "72b" in rid:
        return 42.0
    elif "32b" in rid or "35b" in rid or "33b" in rid:
        return 20.0
    elif "14b" in rid or "13b" in rid or "12b" in rid or "15b" in rid:
        return 9.5
    elif "8b" in rid or "7b" in rid or "9b" in rid:
        return 5.5
    elif "4b" in rid or "3b" in rid or "2b" in rid:
        return 3.2
    elif "1b" in rid or "0.5b" in rid:
        return 1.5
    return 6.0

def search_hf_api(query, limit=50, sort="downloads", direction=-1, filter_tag="mlx"):
    q = urllib.parse.quote(query)
    url = f"https://huggingface.co/api/models?search={q}&limit={limit}&sort={sort}&direction={direction}"
    if filter_tag and filter_tag != "all":
        url += f"&filter={filter_tag}"
        
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                repo_id = item.get("id", "")
                tags = item.get("tags", [])
                est_ram = estimate_ram_requirement(repo_id)
                results.append({
                    "id": repo_id,
                    "downloads": item.get("downloads", 0),
                    "likes": item.get("likes", 0),
                    "lastModified": item.get("lastModified", "")[:10] if item.get("lastModified") else "",
                    "tags": tags[:4],
                    "est_ram_gb": est_ram,
                    "pipeline_tag": item.get("pipeline_tag", "text-generation")
                })
    except Exception:
        pass
    return results

def compare_models_ai(repo_ids):
    """Generates expert technical AI comparison matrix between selected models for Apple Silicon Mac."""
    comparisons = []
    mac_stats = get_system_stats()
    free_ram = mac_stats.get("free_ram_gb", 16.0)

    for rid in repo_ids:
        rid_lower = rid.lower()
        
        quant = "Standard 4-Bit (Q4_K_M)"
        quant_desc = "Sweet spot for quality, speed, and memory size on Apple Silicon."
        if "2bit" in rid_lower or "2-bit" in rid_lower or "2bit-dq" in rid_lower:
            quant = "Ultra-Low 2-Bit (DQ)"
            quant_desc = "Extreme memory compression (saves 50%+ RAM). Ideal for fitting 32B+ models in smaller Mac RAM, but with slight accuracy tradeoff."
        elif "3bit" in rid_lower or "3-bit" in rid_lower:
            quant = "Compact 3-Bit (Q3_K_M)"
            quant_desc = "Saves ~25% RAM over 4-bit while maintaining 95% of standard quality."
        elif "8bit" in rid_lower or "8-bit" in rid_lower:
            quant = "High-Precision 8-Bit (Q8_0)"
            quant_desc = "Near lossless precision, requires ~2x RAM compared to 4-bit."
        elif "optiq" in rid_lower:
            quant = "OptiQ 4-Bit"
            quant_desc = "Quantized with per-layer optimization for higher reasoning benchmark scores."

        est_ram = estimate_ram_requirement(rid)
        
        if est_ram <= free_ram * 0.8:
            fit_status = f"🟢 Fits Smoothly ({est_ram} GB RAM needed)"
        elif est_ram <= free_ram:
            fit_status = f"🟡 High RAM Pressure ({est_ram} GB RAM needed)"
        else:
            fit_status = f"🔴 Swap Danger ({est_ram} GB RAM exceeds free {free_ram} GB)"

        spec = "General Chat & Instruction"
        if "code" in rid_lower or "coder" in rid_lower:
            spec = "💻 Coding Agent & Software Engineering"
        elif "reasoning" in rid_lower or "distilled" in rid_lower or "r1" in rid_lower:
            spec = "🧠 Chain-of-Thought Reasoning & Math"
        elif "flash" in rid_lower:
            spec = "⚡ High-Speed Low Latency Inference"

        if "2bit" in rid_lower:
            verdict = "Best choice if RAM is constrained. Allows running large models (32B) without memory paging."
        elif "code" in rid_lower or "coder" in rid_lower:
            verdict = "Top choice for Pi Code & OpenCode programming tasks."
        elif est_ram <= free_ram * 0.8:
            verdict = "🌟 Recommended Top Pick: Excellent quality and zero RAM paging."
        else:
            verdict = "Requires closing heavy background apps to prevent memory swapping."

        comparisons.append({
            "repo_id": rid,
            "quant": quant,
            "quant_desc": quant_desc,
            "est_ram_gb": est_ram,
            "fit_status": fit_status,
            "specialization": spec,
            "verdict": verdict
        })

    return {"comparisons": comparisons, "free_ram_gb": free_ram}

def run_model_benchmark(prompt, model, port=9999, host="127.0.0.1"):
    url = f"http://{host}:{port}/v1/chat/completions"
    test_model_name = "default_model"
    if model and "/" in model:
        test_model_name = model

    req_data = json.dumps({
        "model": test_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256
    }).encode("utf-8")

    t0 = time.time()
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            t1 = time.time()
            res_data = json.loads(resp.read().decode("utf-8"))
            tot_sec = round(t1 - t0, 2)
            
            usage = res_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            msg = res_data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning", "") or msg.get("reasoning_content", "")
            
            tok_per_sec = round(completion_tokens / tot_sec, 2) if tot_sec > 0 and completion_tokens > 0 else 0.0

            stats = get_system_stats()

            return {
                "status": "ok",
                "model": model,
                "port": port,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_sec": tot_sec,
                "tok_per_sec": tok_per_sec,
                "response_text": content or reasoning,
                "mlx_ram_gb": stats.get("mlx_ram_gb", 0.0)
            }
    except Exception as e:
        return {"error": str(e)}

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
    elif cmd == "active_downloads":
        print(json.dumps(get_active_downloads()))
    elif cmd == "system_stats":
        print(json.dumps(get_system_stats()))
    elif cmd == "sync_configs":
        mname = sys.argv[2] if len(sys.argv) > 2 else "default_model"
        sync_pi_and_opencode(mname)
        print(f"Synced configs for {mname}")
    elif cmd == "search_hf":
        q = sys.argv[2] if len(sys.argv) > 2 else "mlx"
        print(json.dumps(search_hf_api(q)))
    elif cmd == "free_port":
        p = sys.argv[2] if len(sys.argv) > 2 else "9999"
        print(find_free_port(p))
