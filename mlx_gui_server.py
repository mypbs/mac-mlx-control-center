#!/usr/bin/env python3
#
# mlx_gui_server.py - REST API & Web Dashboard Server for MLX Models
#

import os
import sys
import json
import urllib.request
import urllib.parse
import subprocess
import re
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PID_DIR = os.path.expanduser("~/.mlx_pids")
LOG_DIR = os.path.expanduser("~/.mlx_logs")
MODEL_DIR = os.path.expanduser("~/mlx_models")

sys.path.insert(0, PID_DIR)
import mlx_helper

PORT = 9998

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class MLXGuiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_html(self, html_content, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_html(INDEX_HTML)
        elif path == "/api/status":
            servers = mlx_helper.get_running_servers()
            stats = mlx_helper.get_system_stats()
            downloads = mlx_helper.get_active_downloads()
            config = mlx_helper.load_global_settings()
            self.send_json({"servers": servers, "stats": stats, "downloads": downloads, "config": config})
        elif path == "/api/config":
            config = mlx_helper.load_global_settings()
            self.send_json(config)
        elif path == "/api/models":
            models = mlx_helper.find_local_models()
            self.send_json({"models": models})
        elif path == "/api/search":
            q = query.get("q", ["mlx"])[0]
            limit = int(query.get("limit", ["50"])[0])
            sort = query.get("sort", ["downloads"])[0]
            filter_tag = query.get("filter", ["mlx"])[0]
            results = mlx_helper.search_hf_api(q, limit=limit, sort=sort, filter_tag=filter_tag)
            stats = mlx_helper.get_system_stats()
            self.send_json({"results": results, "free_ram_gb": stats.get("free_ram_gb", 16.0)})
        elif path == "/api/logs":
            log_files = []
            if os.path.exists(LOG_DIR):
                for f in sorted(os.listdir(LOG_DIR), reverse=True):
                    if f.endswith(".log"):
                        fp = os.path.join(LOG_DIR, f)
                        size_bytes = os.path.getsize(fp)
                        log_files.append({"name": f, "size": f"{size_bytes/1024:.1f} KB"})
            
            selected_log = query.get("name", [""])[0]
            hide_polling = query.get("hide_polling", ["true"])[0].lower() in ["true", "1", "yes"]
            content = ""
            errors = []
            if selected_log:
                safe_name = os.path.basename(selected_log)
                target_path = os.path.join(LOG_DIR, safe_name)
                if os.path.exists(target_path):
                    try:
                        with open(target_path, "r", errors="ignore") as lf:
                            lines = lf.readlines()
                            if hide_polling:
                                filtered_lines = [l for l in lines if "GET /v1/models" not in l]
                            else:
                                filtered_lines = lines
                            content = "".join(filtered_lines[-250:])
                            
                            full_text = "".join(lines)
                            err_matches = re.findall(r"(Traceback[\s\S]*?(?:ValueError|ModuleNotFoundError|Exception|Error|OSError):[^\n]+)", full_text)
                            if err_matches:
                                errors = err_matches[-5:]
                            else:
                                for line in lines:
                                    if any(k in line for k in ["Error:", "Exception:", "ValueError:", "ModuleNotFoundError:"]):
                                        errors.append(line.strip())
                    except Exception as e:
                        content = f"Error reading log: {e}"

            self.send_json({"logs": log_files, "content": content, "errors": errors})
        else:
            self.send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/config":
            st = mlx_helper.load_global_settings()
            if "default_port" in payload: st["default_port"] = int(payload["default_port"])
            if "default_host" in payload: st["default_host"] = str(payload["default_host"])
            if "default_temp" in payload: st["default_temp"] = float(payload["default_temp"])
            if "default_max_tokens" in payload: st["default_max_tokens"] = int(payload["default_max_tokens"])
            if "auto_sync_agents" in payload: st["auto_sync_agents"] = bool(payload["auto_sync_agents"])
            
            mlx_helper.save_global_settings(st)
            self.send_json({"status": "ok", "config": st})

        elif path == "/api/start":
            st = mlx_helper.load_global_settings()
            default_p = st.get("default_port", 9999)
            default_h = st.get("default_host", "127.0.0.1")

            model_name = payload.get("model", "")
            mode = payload.get("mode", "swap")
            port = payload.get("port")
            host = payload.get("host", default_h)
            temp = str(payload.get("temp", st.get("default_temp", 0.0)))
            max_tokens = str(payload.get("max_tokens", st.get("default_max_tokens", 4096)))
            thinking = payload.get("thinking", True)
            draft_model = payload.get("draft", "")

            if not model_name:
                self.send_json({"error": "No model name provided"}, 400)
                return

            if mode == "concurrent":
                port = mlx_helper.find_free_port(10000)
            elif not port or mode == "swap":
                port = default_p

            try:
                out = subprocess.check_output(["lsof", "-t", "-i", f":{port}"], text=True)
                for pid_str in out.splitlines():
                    pid_str = pid_str.strip()
                    if pid_str:
                        os.kill(int(pid_str), 9)
            except Exception:
                pass

            local_models = mlx_helper.find_local_models()
            model_path = model_name
            for m in local_models:
                if m["name"] == model_name or model_name in m["path"]:
                    model_path = m["path"]
                    break

            extra_args = []
            if not thinking:
                extra_args.extend(["--chat-template-args", '{"enable_thinking":false}'])
            if draft_model:
                extra_args.extend(["--draft-model", draft_model, "--num-draft-tokens", "3"])

            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", model_name)
            log_file = os.path.join(LOG_DIR, f"{safe_name}_{port}.log")

            cmd = [
                "uvx", "--from", "mlx-lm", "mlx_lm.server",
                "--model", model_path,
                "--host", str(host),
                "--port", str(port),
                "--temp", str(temp),
                "--max-tokens", str(max_tokens)
            ] + extra_args

            env = os.environ.copy()
            env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/bin')}:{env.get('PATH', '')}"

            with open(log_file, "a") as lf:
                proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, env=env)

            pid_file = os.path.join(PID_DIR, f"{safe_name}_{port}.pid")
            with open(pid_file, "w") as pf:
                pf.write(str(proc.pid))

            if st.get("auto_sync_agents", True):
                mlx_helper.sync_pi_and_opencode(model_name, port=port)

            self.send_json({
                "status": "ok",
                "message": f"Started {model_name} on port {port}",
                "pid": proc.pid,
                "port": port,
                "host": host
            })

        elif path == "/api/stop":
            pid = payload.get("pid")
            port = payload.get("port")
            stop_all = payload.get("all", False)
            stop_unresponsive = payload.get("unresponsive", False)

            servers = mlx_helper.get_running_servers()
            stopped = []

            if stop_all:
                for s in servers:
                    try:
                        os.kill(int(s["pid"]), 9)
                        stopped.append(s["pid"])
                    except Exception:
                        pass
                try:
                    out = subprocess.check_output(["lsof", "-t", "-i", ":9999"], text=True)
                    for pid_str in out.splitlines():
                        pid_str = pid_str.strip()
                        if pid_str:
                            os.kill(int(pid_str), 9)
                except Exception:
                    pass
            elif stop_unresponsive:
                for s in servers:
                    if "UNRESPONSIVE" in s["status"]:
                        try:
                            os.kill(int(s["pid"]), 9)
                            stopped.append(s["pid"])
                        except Exception:
                            pass
            elif pid:
                try:
                    os.kill(int(pid), 9)
                    stopped.append(pid)
                except Exception:
                    pass
            elif port:
                try:
                    out = subprocess.check_output(["lsof", "-t", "-i", f":{port}"], text=True)
                    for pid_str in out.splitlines():
                        pid_str = pid_str.strip()
                        if pid_str:
                            os.kill(int(pid_str), 9)
                            stopped.append(pid_str)
                except Exception:
                    pass

            self.send_json({"status": "ok", "stopped": stopped})

        elif path == "/api/clear_logs":
            target_log = payload.get("name", "")
            clear_all = payload.get("all", False)
            if clear_all:
                if os.path.exists(LOG_DIR):
                    for f in os.listdir(LOG_DIR):
                        if f.endswith(".log"):
                            fp = os.path.join(LOG_DIR, f)
                            with open(fp, "w") as lf:
                                lf.write("")
                self.send_json({"status": "ok", "cleared": "all"})
            elif target_log:
                safe_name = os.path.basename(target_log)
                target_path = os.path.join(LOG_DIR, safe_name)
                if os.path.exists(target_path):
                    with open(target_path, "w") as lf:
                        lf.write("")
                self.send_json({"status": "ok", "cleared": safe_name})
            else:
                self.send_json({"error": "No log target specified"}, 400)

        elif path == "/api/pause_download":
            pid = payload.get("pid")
            repo_id = payload.get("repo_id")
            if pid:
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            if repo_id:
                cache_dir = ""
                if "/" in repo_id:
                    org, repo = repo_id.split("/", 1)
                    cache_dir = os.path.expanduser(f"~/.cache/huggingface/hub/models--{org}--{repo}")
                paused = mlx_helper.load_paused_downloads()
                paused[repo_id] = {"cache_dir": cache_dir, "paused_at": os.path.getmtime(cache_dir) if os.path.exists(cache_dir) else 0}
                mlx_helper.save_paused_downloads(paused)
                self.send_json({"status": "paused", "repo_id": repo_id})
            else:
                self.send_json({"error": "No repo_id provided"}, 400)

        elif path == "/api/cancel_download":
            pid = payload.get("pid")
            repo_id = payload.get("repo_id")
            if pid:
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            if repo_id:
                paused = mlx_helper.load_paused_downloads()
                if repo_id in paused:
                    del paused[repo_id]
                    mlx_helper.save_paused_downloads(paused)
            self.send_json({"status": "ok", "cancelled": repo_id or pid})

        elif path == "/api/restart_download" or path == "/api/resume_download":
            pid = payload.get("pid")
            repo_id = payload.get("repo_id")
            if pid:
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            if repo_id:
                paused = mlx_helper.load_paused_downloads()
                if repo_id in paused:
                    del paused[repo_id]
                    mlx_helper.save_paused_downloads(paused)

                env = os.environ.copy()
                env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/bin')}:{env.get('PATH', '')}"
                env["PYTHONUNBUFFERED"] = "1"
                env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
                env["HF_XET_HIGH_PERFORMANCE"] = "1"
                cmd = ["hf", "download", repo_id]
                proc = subprocess.Popen(cmd, env=env)
                self.send_json({"status": "resumed", "repo_id": repo_id, "new_pid": proc.pid})
            else:
                self.send_json({"error": "No repo_id provided"}, 400)

        elif path == "/api/delete":
            delete_target = payload.get("delete_target")
            if delete_target and os.path.exists(delete_target):
                subprocess.run(["rm", "-rf", delete_target])
                self.send_json({"status": "ok", "deleted": delete_target})
            else:
                self.send_json({"error": "Target path not found"}, 400)

        elif path == "/api/download":
            repo_id = payload.get("repo_id")
            if not repo_id:
                self.send_json({"error": "No repo_id specified"}, 400)
                return

            paused = mlx_helper.load_paused_downloads()
            if repo_id in paused:
                del paused[repo_id]
                mlx_helper.save_paused_downloads(paused)

            env = os.environ.copy()
            env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/bin')}:{env.get('PATH', '')}"
            env["PYTHONUNBUFFERED"] = "1"
            env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
            env["HF_XET_HIGH_PERFORMANCE"] = "1"

            cmd = ["hf", "download", repo_id]
            proc = subprocess.Popen(cmd, env=env)
            self.send_json({"status": "started", "repo_id": repo_id, "pid": proc.pid})

        elif path == "/api/compare_models":
            repos = payload.get("repos", [])
            if not repos:
                self.send_json({"error": "No model repositories selected for comparison"}, 400)
                return
            res = mlx_helper.compare_models_ai(repos)
            self.send_json(res)

        elif path == "/api/test":
            st = mlx_helper.load_global_settings()
            prompt = payload.get("prompt", "Hello!")
            model = payload.get("model", "default_model")
            port = payload.get("port", st.get("default_port", 9999))
            host = payload.get("host", "127.0.0.1")

            url = f"http://{host}:{port}/v1/chat/completions"
            test_model_name = "default_model"
            if model and "/" in model:
                test_model_name = model

            req_data = json.dumps({
                "model": test_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300
            }).encode("utf-8")

            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    msg = res_data.get("choices", [{}])[0].get("message", {})
                    content = msg.get("content", "")
                    reasoning = msg.get("reasoning", "") or msg.get("reasoning_content", "")

                    full_output = ""
                    if reasoning:
                        full_output += f"🧠 THINKING PROCESS:\n{reasoning}\n\n"
                    if content:
                        full_output += f"💬 RESPONSE:\n{content}"
                    elif not full_output:
                        full_output = json.dumps(msg, indent=2)

                    self.send_json({"status": "ok", "response": full_output})
            except Exception as e:
                self.send_json({"error": f"API request failed on http://{host}:{port}: {e}"}, 500)

        elif path == "/api/benchmark":
            st = mlx_helper.load_global_settings()
            prompt = payload.get("prompt", "Write a Python script to calculate Fibonacci sequence up to 100 elements.")
            model = payload.get("model", "default_model")
            port = payload.get("port", st.get("default_port", 9999))
            host = payload.get("host", "127.0.0.1")

            res = mlx_helper.run_model_benchmark(prompt, model, port=port, host=host)
            self.send_json(res)
        else:
            self.send_json({"error": "Not Found"}, 404)

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>macOS MLX Control Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #151c2c;
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-glow: rgba(99, 102, 241, 0.35);
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.25);
      --warning: #f59e0b;
      --danger: #ef4444;
      --danger-glow: rgba(239, 68, 68, 0.3);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', system-ui, -apple-system, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5; min-height: 100vh; padding-bottom: 90px; }

    /* GLOBAL DARK THEME INPUT CONTROLS */
    select, input[type="text"], input[type="number"], textarea {
      background: rgba(11, 15, 25, 0.8) !important;
      border: 1px solid rgba(255, 255, 255, 0.12) !important;
      border-radius: 8px !important;
      color: #f3f4f6 !important;
      padding: 12px 16px !important;
      font-size: 14px !important;
      outline: none !important;
      transition: all 0.2s ease !important;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3) !important;
    }
    select:focus, input[type="text"]:focus, input[type="number"]:focus, textarea:focus {
      border-color: var(--accent) !important;
      box-shadow: 0 0 12px var(--accent-glow), inset 0 2px 4px rgba(0, 0, 0, 0.4) !important;
    }
    select option {
      background: #151c2c !important;
      color: #f3f4f6 !important;
      padding: 10px !important;
    }
    
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 24px; background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 36px; height: 36px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 18px; color: #fff; }
    .brand-title { font-size: 20px; font-weight: 700; background: linear-gradient(90deg, #fff, #93c5fd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    
    .status-pill {
      display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
      border-radius: 20px; font-size: 13px; font-weight: 600; border: 1px solid var(--card-border);
    }
    .status-pill.ready { background: var(--success-glow); color: #34d399; border-color: rgba(16, 185, 129, 0.4); }
    .status-pill.downloading { background: rgba(99, 102, 241, 0.2); color: #818cf8; border-color: rgba(99, 102, 241, 0.4); }
    .status-pill.paused { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border-color: rgba(245, 158, 11, 0.4); }
    .status-pill.none { background: rgba(156, 163, 175, 0.1); color: var(--text-muted); }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    .status-dot.pulse { animation: pulseAnim 1.5s infinite ease-in-out; }
    @keyframes pulseAnim { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

    /* HTOP RESOURCE MONITOR BAR */
    .htop-bar {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;
      background: rgba(21, 28, 44, 0.7); border: 1px solid var(--card-border); border-radius: 12px;
      padding: 16px 20px; margin-bottom: 20px; backdrop-filter: blur(8px);
    }
    .htop-item { display: flex; flex-direction: column; gap: 6px; }
    .htop-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .htop-val { font-size: 18px; font-weight: 700; color: #fff; }
    .htop-progress { width: 100%; height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; }
    .htop-fill { height: 100%; background: linear-gradient(90deg, #6366f1, #34d399); transition: width 0.3s ease; }

    nav { display: flex; gap: 8px; margin-bottom: 24px; background: rgba(21, 28, 44, 0.6); padding: 6px; border-radius: 10px; border: 1px solid var(--card-border); }
    .nav-btn {
      flex: 1; padding: 10px 16px; border: none; background: transparent; color: var(--text-muted);
      font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s ease;
    }
    .nav-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
    .nav-btn.active { color: #fff; background: var(--accent); box-shadow: 0 0 12px var(--accent-glow); }
    
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px;
      padding: 20px; transition: transform 0.2s ease, border-color 0.2s ease; position: relative;
    }
    .card:hover { border-color: rgba(99, 102, 241, 0.5); transform: translateY(-2px); }
    .card-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; word-break: break-all; }
    .card-meta { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }
    
    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 9px 16px;
      font-size: 13px; font-weight: 600; border-radius: 8px; border: none; cursor: pointer; transition: all 0.2s ease;
      text-decoration: none;
    }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-primary:hover { background: var(--accent-hover); box-shadow: 0 0 12px var(--accent-glow); }
    .btn-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .btn-warning:hover { background: var(--warning); color: #fff; }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .btn-danger:hover { background: var(--danger); color: #fff; box-shadow: 0 0 12px var(--danger-glow); }
    .btn-secondary { background: rgba(255, 255, 255, 0.08); color: var(--text); }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.15); }
    
    /* FEATURE CHIPS & SEARCH FILTER BAR */
    .filter-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .chip {
      padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
      background: rgba(255,255,255,0.05); color: var(--text-muted); border: 1px solid var(--card-border);
      cursor: pointer; transition: all 0.2s ease;
    }
    .chip:hover { color: #fff; border-color: rgba(255,255,255,0.2); }
    .chip.active { background: rgba(99, 102, 241, 0.2); color: #818cf8; border-color: var(--accent); }

    /* CAN I RUN IT RAM BADGES */
    .ram-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; margin-bottom: 8px; }
    .ram-badge.fit { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .ram-badge.warn { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .ram-badge.heavy { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }

    /* STICKY BOTTOM AI COMPARISON BAR */
    .compare-bar {
      position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
      background: rgba(21, 28, 44, 0.95); border: 1px solid var(--accent);
      box-shadow: 0 8px 32px rgba(0,0,0,0.6), 0 0 20px var(--accent-glow);
      border-radius: 40px; padding: 12px 24px; display: flex; align-items: center; gap: 16px;
      z-index: 999; backdrop-filter: blur(12px); animation: slideUp 0.3s ease;
    }
    @keyframes slideUp { from { transform: translate(-50%, 40px); opacity: 0; } to { transform: translate(-50%, 0); opacity: 1; } }

    /* WIDER HF SEARCH INPUT BOX */
    .search-box { display: flex; gap: 12px; margin-bottom: 16px; width: 100%; max-width: 980px; }
    .search-input-wide { flex: 1; min-width: 420px; font-size: 15px !important; }
    
    .chat-box { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; margin-top: 16px; }
    .chat-output { background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 8px; padding: 16px; min-height: 140px; font-family: monospace; white-space: pre-wrap; margin-top: 12px; color: #a7f3d0; font-size: 13px; }
    .log-output { background: #05070f; border: 1px solid var(--card-border); border-radius: 8px; padding: 16px; height: 350px; overflow-y: auto; font-family: monospace; font-size: 12px; color: #94a3b8; }
    .error-box { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; color: #fca5a5; font-family: monospace; font-size: 12px; white-space: pre-wrap; }

    /* MODAL OVERLAY */
    .modal-overlay {
      display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(4px);
      z-index: 1000; align-items: center; justify-content: center;
    }
    .modal-overlay.active { display: flex; }
    .modal {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px;
      padding: 24px; width: 100%; max-width: 960px; max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    .modal-header { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: #fff; }
    .strategy-option {
      display: flex; align-items: flex-start; gap: 12px; padding: 14px;
      border: 1px solid var(--card-border); border-radius: 10px; margin-bottom: 12px;
      cursor: pointer; transition: all 0.2s ease; background: rgba(255,255,255,0.02);
    }
    .strategy-option:hover { border-color: var(--accent); background: rgba(99,102,241,0.08); }
    .strategy-option input[type="radio"] { margin-top: 4px; accent-color: var(--accent); }
    .strategy-title { font-weight: 600; font-size: 14px; color: #fff; }
    .strategy-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

    /* PRESET BUTTONS */
    .preset-btn {
      display: flex; flex-direction: column; gap: 4px; padding: 10px 14px; border-radius: 8px;
      background: rgba(255,255,255,0.04); border: 1px solid var(--card-border); cursor: pointer; text-align: left;
      transition: all 0.2s ease; flex: 1;
    }
    .preset-btn:hover { border-color: var(--accent); background: rgba(99,102,241,0.12); }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon">⚡</div>
      <div>
        <div class="brand-title">macOS MLX Control Center</div>
        <div style="font-size: 12px; color: var(--text-muted);">Apple Silicon Local Model Manager</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px;">
      <button class="btn btn-secondary" style="padding: 8px 14px; font-size: 13px;" onclick="openConfigModal()">⚙️ API Settings</button>
      <div id="statusHeader">
        <div class="status-pill none"><span class="status-dot"></span> Checking Status...</div>
      </div>
    </div>
  </header>

  <!-- HTOP RESOURCE MONITOR BAR -->
  <div class="htop-bar">
    <div class="htop-item">
      <div class="htop-label">Mac System RAM</div>
      <div class="htop-val" id="htopRamVal">-- / -- GB</div>
      <div class="htop-progress"><div class="htop-fill" id="htopRamFill" style="width: 0%;"></div></div>
    </div>
    <div class="htop-item">
      <div class="htop-label">MLX Models Memory</div>
      <div class="htop-val" id="htopMlxVal">-- GB</div>
      <div style="font-size: 12px; color: var(--text-muted);" id="htopMlxMeta">0 Active Models</div>
    </div>
    <div class="htop-item">
      <div class="htop-label">CPU Utilization</div>
      <div class="htop-val" id="htopCpuVal">-- %</div>
      <div class="htop-progress"><div class="htop-fill" id="htopCpuFill" style="width: 0%; background: #a855f7;"></div></div>
    </div>
  </div>

  <nav>
    <button class="nav-btn active" onclick="switchTab('dashboard')">Dashboard</button>
    <button class="nav-btn" onclick="switchTab('models')">Downloaded Models</button>
    <button class="nav-btn" onclick="switchTab('search')">Search Hugging Face</button>
    <button class="nav-btn" onclick="switchTab('test')">API & Chat Test</button>
    <button class="nav-btn" onclick="switchTab('bench')">📊 Speed Benchmark</button>
    <button class="nav-btn" onclick="switchTab('logs')">Server Logs</button>
  </nav>

  <!-- LIVE DOWNLOAD QUEUE BANNER -->
  <div id="liveDownloadBanner" style="display: none; margin-bottom: 24px;"></div>

  <!-- TAB 1: DASHBOARD -->
  <div id="tab-dashboard" class="tab-content active">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="font-size: 18px; font-weight: 600;">Active MLX Model Servers</h2>
      <button class="btn btn-danger" onclick="killAllServers()">⚡ KILL SWITCH (Stop All)</button>
    </div>
    <div id="activeServerContainer" class="grid" style="margin-bottom: 24px;"></div>

    <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 16px;">Launch a Model</h2>
    <div id="fastSwapGrid" class="grid"></div>
  </div>

  <!-- TAB 2: DOWNLOADED MODELS -->
  <div id="tab-models" class="tab-content">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="font-size: 18px; font-weight: 600;">Downloaded Models</h2>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-warning" onclick="clearCompareSelection()">🧹 Clear Checkmarks</button>
        <button class="btn btn-secondary" onclick="loadModels()">🔄 Refresh Models</button>
      </div>
    </div>
    <div id="modelsGrid" class="grid"></div>
  </div>

  <!-- TAB 3: SEARCH HF (SUPERCHARGED SEARCH WITH FILTERS & RAM ESTIMATOR) -->
  <div id="tab-search" class="tab-content">
    <div class="search-box">
      <input type="text" id="searchInput" class="search-input-wide" placeholder="Search Hugging Face (e.g. gemma 4, qwen 2.5 coder, llama 3)..." value="gemma 4" onkeyup="if(event.key==='Enter') doSearch()">
      <button class="btn btn-primary" style="padding: 14px 24px; font-size: 15px;" onclick="doSearch()">Search HF</button>
      <button class="btn btn-warning" style="padding: 14px 18px; font-size: 14px;" onclick="clearCompareSelection()">🧹 Clear Checkmarks</button>
    </div>

    <!-- FILTER & SORT BAR -->
    <div class="filter-bar">
      <div class="chip active" id="filter-mlx" onclick="setFilter('mlx')">⚡ MLX Models (Default)</div>
      <div class="chip" id="filter-4bit" onclick="setFilter('4bit')">🎯 4-Bit Quantized</div>
      <div class="chip" id="filter-code" onclick="setFilter('code')">💻 Code Models</div>
      <div class="chip" id="filter-all" onclick="setFilter('all')">🌐 All HF Repos</div>
      
      <div style="margin-left: auto; display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 12px; color: var(--text-muted);">Sort By:</span>
        <select id="sortSelect" onchange="doSearch()" style="padding: 6px 12px !important; font-size: 12px !important;">
          <option value="downloads">Most Downloads</option>
          <option value="likes">Most Liked</option>
          <option value="lastModified">Recently Updated</option>
        </select>
        <select id="limitSelect" onchange="doSearch()" style="padding: 6px 12px !important; font-size: 12px !important;">
          <option value="50">50 Results</option>
          <option value="100">100 Results</option>
        </select>
      </div>
    </div>

    <div id="searchMetaHeader" style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;"></div>
    <div id="searchResultsGrid" class="grid"></div>
  </div>

  <!-- TAB 4: API & CHAT TEST -->
  <div id="tab-test" class="tab-content">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="font-size: 18px; font-weight: 600;">Test Active MLX Model Server</h2>
      <button class="btn btn-secondary" onclick="loadTestServers()">🔄 Refresh Server List</button>
    </div>
    <div class="chat-box">
      <div style="margin-bottom: 16px;">
        <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-muted);">
          Select Target Model Server:
        </label>
        <select id="testServerSelect" style="width: 100%; font-weight: 500;"></select>
      </div>
      <div style="margin-bottom: 16px;">
        <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-muted);">
          Test Prompt:
        </label>
        <input type="text" id="promptInput" style="width: 100%; font-weight: 500;" placeholder="Enter prompt to test..." value="Hello! State your model name and what you can do.">
      </div>
      <button class="btn btn-primary" style="padding: 12px 24px; font-size: 14px;" onclick="sendTestPrompt()">🚀 Send Test Prompt</button>
      <div id="chatOutput" class="chat-output">Response will appear here...</div>
    </div>
  </div>

  <!-- TAB 5: SPEED BENCHMARK & COMPARISON -->
  <div id="tab-bench" class="tab-content">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="font-size: 18px; font-weight: 600;">📊 MLX Tokens/Second Benchmark</h2>
    </div>
    <div class="chat-box">
      <div style="margin-bottom: 16px;">
        <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-muted);">
          Benchmark Test Prompt:
        </label>
        <input type="text" id="benchPromptInput" style="width: 100%; font-weight: 500;" value="Write a Python script to calculate Fibonacci sequence up to 100 elements with memoization.">
      </div>
      <button class="btn btn-primary" style="padding: 12px 24px; font-size: 14px;" onclick="runBenchmark()">⚡ Run Speed Benchmark Test</button>
      
      <div id="benchMetricsCard" style="display: none; margin-top: 20px;" class="card">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 16px;">
          <div>
            <div style="font-size: 12px; color: var(--text-muted);">Generation Speed</div>
            <div style="font-size: 24px; font-weight: 700; color: #34d399;" id="benchTokSec">-- tok/s</div>
          </div>
          <div>
            <div style="font-size: 12px; color: var(--text-muted);">Total Execution Time</div>
            <div style="font-size: 24px; font-weight: 700; color: #60a5fa;" id="benchTotSec">-- s</div>
          </div>
          <div>
            <div style="font-size: 12px; color: var(--text-muted);">Tokens (Prompt / Gen)</div>
            <div style="font-size: 18px; font-weight: 700; color: #f3f4f6;" id="benchTokensMeta">-- / --</div>
          </div>
          <div>
            <div style="font-size: 12px; color: var(--text-muted);">MLX GPU RAM Used</div>
            <div style="font-size: 18px; font-weight: 700; color: #a855f7;" id="benchRamVal">-- GB</div>
          </div>
        </div>
        <div id="benchTextOutput" style="background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; max-height: 250px; overflow-y: auto; color: #93c5fd; white-space: pre-wrap;"></div>
      </div>
    </div>
  </div>

  <!-- TAB 6: LOGS -->
  <div id="tab-logs" class="tab-content">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="font-size: 18px; font-weight: 600;">Server Logs Inspector</h2>
      <div style="display: flex; gap: 12px; align-items: center;">
        <label style="font-size: 12px; color: var(--text-muted); cursor: pointer;">
          <input type="checkbox" id="hidePollingCheck" checked onchange="loadLogContent()"> Hide GET /v1/models polling
        </label>
        <select id="logSelect" onchange="loadLogContent()"></select>
        <button class="btn btn-warning" onclick="clearCurrentLog()">🗑️ Clear Selected Log</button>
        <button class="btn btn-danger" onclick="clearAllLogs()">🧹 Clear All Logs</button>
      </div>
    </div>
    <div id="errorHighlightContainer" style="display: none;" class="error-box"></div>
    <div id="logContent" class="log-output">Loading log output...</div>
  </div>

  <!-- FLOATING STICKY AI COMPARISON BAR -->
  <div id="floatingCompareBar" class="compare-bar" style="display: none;">
    <div style="font-size: 13px; font-weight: 600; color: #fff;">
      <span id="compareCountLabel">Selected Models (0):</span>
    </div>
    <button class="btn btn-primary" style="padding: 8px 18px; font-size: 13px;" onclick="runAiComparison()">🤖 Compare Selected Models with AI</button>
    <button class="btn btn-secondary" style="padding: 8px 14px; font-size: 12px;" onclick="clearCompareSelection()">🧹 Clear Checkmarks</button>
  </div>

  <!-- AI MODEL COMPARISON MATRIX MODAL -->
  <div id="compareModal" class="modal-overlay">
    <div class="modal">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div class="modal-header" style="margin-bottom: 0;">🤖 Antigravity AI Model Comparison Breakdown</div>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="closeCompareModal()">✕ Close</button>
      </div>

      <div id="compareModalContent">Loading comparison matrix...</div>
    </div>
  </div>

  <!-- GLOBAL CONFIGURATION MODAL WITH RAM & TOKEN GUIDE -->
  <div id="configModal" class="modal-overlay">
    <div class="modal" style="max-width: 560px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div class="modal-header" style="margin-bottom: 0;">⚙️ Global API & Server Settings</div>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="closeConfigModal()">✕ Close</button>
      </div>

      <div style="margin-bottom: 14px;">
        <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted);">
          Default MLX Server Port:
        </label>
        <input type="number" id="cfgPortInput" style="width: 100%;" value="9999">
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Default port for OpenAI-compatible endpoint (e.g. 9999, 8888, 8080).</div>
      </div>

      <div style="margin-bottom: 14px;">
        <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted);">
          Server Host Binding:
        </label>
        <select id="cfgHostSelect" style="width: 100%;">
          <option value="127.0.0.1">127.0.0.1 (Localhost Only - Secure)</option>
          <option value="0.0.0.0">0.0.0.0 (LAN Access - Allow Home Devices)</option>
        </select>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Select 0.0.0.0 if you want other PCs or phones on Wi-Fi to query your Mac.</div>
      </div>

      <div style="display: flex; gap: 12px; margin-bottom: 14px;">
        <div style="flex: 1;">
          <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted);">Default Temp:</label>
          <input type="text" id="cfgTempInput" style="width: 100%;" value="0.0">
        </div>
        <div style="flex: 1;">
          <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted);">Max Output Tokens:</label>
          <input type="number" id="cfgMaxTokensInput" style="width: 100%;" value="4096">
        </div>
      </div>

      <!-- RICH TOOLTIP & RAM GUIDANCE CARD -->
      <div style="background: rgba(0,0,0,0.35); border: 1px solid var(--card-border); border-radius: 10px; padding: 14px; margin-bottom: 16px; font-size: 12px; color: #94a3b8; line-height: 1.5;">
        <strong style="color: #60a5fa; font-size: 13px;">💡 What is "Max Output Tokens"?</strong><br>
        This specifies the maximum number of <strong>NEW tokens (generated response + thinking tokens)</strong> the server will produce in a single request. It does <em>not</em> limit your input prompt size.<br><br>
        <strong style="color: #34d399;">🧠 Recommended Token Settings for Apple Silicon:</strong>
        <table style="width: 100%; margin-top: 6px; border-collapse: collapse; font-size: 11px; color: #cbd5e1;">
          <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
            <th style="text-align: left; padding: 4px;">Model Size</th>
            <th style="text-align: left; padding: 4px;">Rec. Max Tokens</th>
            <th style="text-align: left; padding: 4px;">KV Cache RAM Impact</th>
          </tr>
          <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
            <td style="padding: 4px;"><strong>2B – 8B Models</strong></td>
            <td style="padding: 4px; color: #34d399;">4096 – 8192</td>
            <td style="padding: 4px;">Light (~0.5 GB RAM)</td>
          </tr>
          <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
            <td style="padding: 4px;"><strong>14B – 35B Models</strong></td>
            <td style="padding: 4px; color: #fbbf24;">4096</td>
            <td style="padding: 4px;">Moderate (~1.5 – 3 GB)</td>
          </tr>
          <tr>
            <td style="padding: 4px;"><strong>70B+ Models</strong></td>
            <td style="padding: 4px; color: #f87171;">2048 – 4096</td>
            <td style="padding: 4px;">High (~4 GB+ RAM)</td>
          </tr>
        </table>
      </div>

      <div style="margin-bottom: 16px;">
        <label style="font-size: 13px; color: #fff; cursor: pointer; display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="cfgAutoSyncCheck" checked> Auto-sync Pi Code & OpenCode under provider 'MyMac'
        </label>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px;">
        <button class="btn btn-secondary" onclick="closeConfigModal()">Cancel</button>
        <button class="btn btn-primary" onclick="saveConfigModal()">💾 Save & Apply Settings</button>
      </div>
    </div>
  </div>

  <!-- LAUNCH MODAL WITH PRESET PROFILES -->
  <div id="launchModal" class="modal-overlay">
    <div class="modal" style="max-width: 560px;">
      <div class="modal-header" id="modalModelTitle">Start Model</div>
      
      <!-- PRESET PROFILES BAR -->
      <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #fff;">1-Click Preset Profiles:</div>
      <div style="display: flex; gap: 8px; margin-bottom: 16px;">
        <div class="preset-btn" onclick="applyPreset('code')">
          <div style="font-weight:600; font-size:12px; color:#60a5fa;">💻 Coding Agent</div>
          <div style="font-size:11px; color:var(--text-muted);">Temp 0.0 | Max 8192</div>
        </div>
        <div class="preset-btn" onclick="applyPreset('reason')">
          <div style="font-weight:600; font-size:12px; color:#a855f7;">🧠 Deep Reasoning</div>
          <div style="font-size:11px; color:var(--text-muted);">Temp 0.6 | Thinking ON</div>
        </div>
        <div class="preset-btn" onclick="applyPreset('fast')">
          <div style="font-weight:600; font-size:12px; color:#34d399;">⚡ Fast Chat</div>
          <div style="font-size:11px; color:var(--text-muted);">Temp 0.7 | Thinking OFF</div>
        </div>
      </div>

      <div style="margin-bottom: 16px; font-size: 13px; color: var(--text-muted);">
        Select launch mode:
      </div>

      <label class="strategy-option">
        <input type="radio" name="launchStrategy" value="swap" checked onclick="toggleCustomFields(false)">
        <div>
          <div class="strategy-title">⚡ Fast Swap (Port 9999)</div>
          <div class="strategy-desc">Stops active model on port 9999 and launches this model immediately. (Recommended)</div>
        </div>
      </label>

      <label class="strategy-option">
        <input type="radio" name="launchStrategy" value="concurrent" onclick="toggleCustomFields(false)">
        <div>
          <div class="strategy-title">🔀 Run Concurrently</div>
          <div class="strategy-desc">Keeps existing model(s) running and launches on new free port.</div>
        </div>
      </label>

      <label class="strategy-option">
        <input type="radio" name="launchStrategy" value="custom" onclick="toggleCustomFields(true)">
        <div>
          <div class="strategy-title">⚙️ Custom Parameters</div>
          <div class="strategy-desc">Configure custom port, temperature, max tokens, and thinking tokens.</div>
        </div>
      </label>

      <div id="customFields" style="display: none; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; margin-bottom: 16px;">
        <div style="display: flex; gap: 12px; margin-bottom: 8px;">
          <input type="number" id="customPort" placeholder="Port" value="9999" style="flex:1;">
          <input type="text" id="customTemp" placeholder="Temp (0.0)" value="0.0" style="flex:1;">
        </div>
        <div style="display: flex; gap: 12px; align-items: center;">
          <input type="number" id="customMaxTokens" placeholder="Max Tokens" value="4096" style="flex:1;">
          <label style="font-size: 12px; color: #fff; cursor: pointer;">
            <input type="checkbox" id="customThinking" checked> Thinking Tokens
          </label>
        </div>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px;">
        <button class="btn btn-secondary" onclick="closeLaunchModal()">Cancel</button>
        <button class="btn btn-primary" onclick="confirmLaunch()">Confirm Launch</button>
      </div>
    </div>
  </div>

  <script>
    let activeServers = [];
    let activeDownloads = [];
    let targetModelForLaunch = '';
    let currentFilter = 'mlx';
    let currentFreeRam = 16.0;
    let selectedForCompare = new Set();
    let globalConfig = { default_port: 9999, default_host: '127.0.0.1', default_temp: 0.0, default_max_tokens: 4096, auto_sync_agents: true };

    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      document.getElementById('tab-' + tabId).classList.add('active');
      
      const activeNav = Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick').includes(tabId));
      if (activeNav) activeNav.classList.add('active');

      if (tabId === 'models' || tabId === 'dashboard') loadModels();
      if (tabId === 'logs') loadLogs();
      if (tabId === 'test') loadTestServers();
      if (tabId === 'search') doSearch();
    }

    async function openConfigModal() {
      const res = await fetch('/api/config');
      globalConfig = await res.json();
      document.getElementById('cfgPortInput').value = globalConfig.default_port || 9999;
      document.getElementById('cfgHostSelect').value = globalConfig.default_host || '127.0.0.1';
      document.getElementById('cfgTempInput').value = globalConfig.default_temp || 0.0;
      document.getElementById('cfgMaxTokensInput').value = globalConfig.default_max_tokens || 4096;
      document.getElementById('cfgAutoSyncCheck').checked = globalConfig.auto_sync_agents !== false;
      document.getElementById('configModal').classList.add('active');
    }

    function closeConfigModal() {
      document.getElementById('configModal').classList.remove('active');
    }

    async function saveConfigModal() {
      const port = parseInt(document.getElementById('cfgPortInput').value) || 9999;
      const host = document.getElementById('cfgHostSelect').value;
      const temp = parseFloat(document.getElementById('cfgTempInput').value) || 0.0;
      const maxTokens = parseInt(document.getElementById('cfgMaxTokensInput').value) || 4096;
      const autoSync = document.getElementById('cfgAutoSyncCheck').checked;

      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_port: port, default_host: host, default_temp: temp, default_max_tokens: maxTokens, auto_sync_agents: autoSync })
      });

      closeConfigModal();
      alert(`Settings saved! Default port set to ${port} on ${host}.`);
      updateStatus();
    }

    function toggleCompareSelection(repoId) {
      if (selectedForCompare.has(repoId)) {
        selectedForCompare.delete(repoId);
      } else {
        selectedForCompare.add(repoId);
      }
      updateCompareBar();
    }

    function clearCompareSelection() {
      selectedForCompare.clear();
      document.querySelectorAll('.compare-check').forEach(el => el.checked = false);
      updateCompareBar();
    }

    function updateCompareBar() {
      const bar = document.getElementById('floatingCompareBar');
      const label = document.getElementById('compareCountLabel');
      if (selectedForCompare.size > 0) {
        bar.style.display = 'flex';
        label.innerText = `Selected Models (${selectedForCompare.size}):`;
      } else {
        bar.style.display = 'none';
      }
    }

    async function runAiComparison() {
      if (selectedForCompare.size === 0) return;
      const repos = Array.from(selectedForCompare);
      
      document.getElementById('compareModal').classList.add('active');
      const content = document.getElementById('compareModalContent');
      content.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">🤖 Antigravity AI is evaluating model architecture, quantization precision, and RAM requirements...</div>';

      try {
        const res = await fetch('/api/compare_models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repos: repos })
        });
        const data = await res.json();
        const comparisons = data.comparisons || [];
        
        let gridHtml = `
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 16px; margin-top: 16px;">`;

        comparisons.forEach(c => {
          const hfUrl = `https://huggingface.co/${c.repo_id}`;
          gridHtml += `
            <div class="card" style="border-color: rgba(99, 102, 241, 0.4); background: rgba(15, 23, 42, 0.8);">
              <div class="card-title" style="color: #60a5fa; font-size: 15px;">${c.repo_id}</div>
              
              <div style="margin-bottom: 12px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Quantization & Precision</div>
                <div style="font-weight: 700; font-size: 13px; color: #f3f4f6;">${c.quant}</div>
                <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">${c.quant_desc}</div>
              </div>

              <div style="margin-bottom: 12px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Specialization</div>
                <div style="font-weight: 600; font-size: 13px; color: #a7f3d0;">${c.specialization}</div>
              </div>

              <div style="margin-bottom: 12px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Mac RAM Compatibility</div>
                <div>${c.fit_status}</div>
              </div>

              <div style="padding: 10px; background: rgba(0,0,0,0.3); border-radius: 8px; border: 1px solid var(--card-border); margin-bottom: 14px;">
                <div style="font-size: 11px; font-weight: 700; color: #fbbf24; margin-bottom: 2px;">🌟 AI VERDICT:</div>
                <div style="font-size: 12px; color: #e2e8f0;">${c.verdict}</div>
              </div>

              <div style="display: flex; gap: 8px;">
                <button class="btn btn-primary" style="flex: 1;" onclick="closeCompareModal(); downloadRepo('${c.repo_id}')">⚡ Download</button>
                <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
              </div>
            </div>`;
        });

        gridHtml += `</div>`;
        content.innerHTML = gridHtml;

      } catch (e) {
        content.innerHTML = `<div style="color: #f87171;">Error running AI comparison: ${e}</div>`;
      }
    }

    function closeCompareModal() {
      document.getElementById('compareModal').classList.remove('active');
    }

    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        activeServers = data.servers || [];
        activeDownloads = data.downloads || [];
        globalConfig = data.config || globalConfig;
        const stats = data.stats || {};
        
        if (stats.free_ram_gb) currentFreeRam = stats.free_ram_gb;

        // Render Rich Download Progress Tracker Banner with Pause / Resume / Kick / Cancel Controls
        const dlBanner = document.getElementById('liveDownloadBanner');
        if (activeDownloads.length > 0) {
          dlBanner.style.display = 'block';
          dlBanner.innerHTML = '';
          activeDownloads.forEach(d => {
            const isPaused = d.status === 'PAUSED';
            dlBanner.innerHTML += `
              <div class="card" style="border-color: ${isPaused ? '#f59e0b' : '#6366f1'}; background: ${isPaused ? 'rgba(245, 158, 11, 0.1)' : 'rgba(99, 102, 241, 0.12)'};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                  <div style="flex: 1; margin-right: 16px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                      <span class="status-pill ${isPaused ? 'paused' : 'downloading'}">
                        <span class="status-dot ${isPaused ? '' : 'pulse'}"></span> ${isPaused ? '⏸️ DOWNLOAD PAUSED (SAVED)' : '⚡ RUST ACCELERATED HF DOWNLOAD'}
                      </span>
                      <strong style="font-size: 15px; color: #fff;">${d.repo_id}</strong>
                    </div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">
                      ${isPaused ? 'Saved on Disk' : 'PID: ' + d.pid} | Downloaded: <strong style="color: #34d399;">${d.downloaded_size}</strong> of <strong>${d.total_size}</strong> (<strong style="color: #93c5fd;">${d.percent}%</strong>)
                      | Speed: <strong style="color: ${isPaused ? '#fbbf24' : '#60a5fa'};">${d.speed}</strong> | ETA: <strong style="color: ${isPaused ? '#fbbf24' : '#f472b6'};">${d.eta}</strong>
                    </div>
                    <div style="width: 100%; height: 10px; background: rgba(255,255,255,0.1); border-radius: 5px; overflow: hidden;">
                      <div style="height: 100%; width: ${d.percent}%; background: ${isPaused ? 'linear-gradient(90deg, #f59e0b, #fbbf24)' : 'linear-gradient(90deg, #6366f1, #34d399)'}; transition: width 0.4s ease;"></div>
                    </div>
                  </div>
                  <div style="display: flex; gap: 8px; flex-shrink: 0;">
                    ${isPaused ? `
                      <button class="btn btn-primary" onclick="restartDownload('${d.pid}', '${d.repo_id}')">▶️ Resume Download</button>
                    ` : `
                      <button class="btn btn-warning" onclick="pauseDownload('${d.pid}', '${d.repo_id}')">⏸️ Pause</button>
                      <button class="btn btn-primary" onclick="restartDownload('${d.pid}', '${d.repo_id}')" title="Restarts connection with Rust multi-threaded acceleration">🔄 Kick / Re-connect</button>
                    `}
                    <button class="btn btn-danger" onclick="cancelDownload('${d.pid}', '${d.repo_id}')">🛑 Cancel</button>
                  </div>
                </div>
              </div>`;
          });
        } else {
          dlBanner.style.display = 'none';
          dlBanner.innerHTML = '';
        }

        if (stats.total_ram_gb) {
          document.getElementById('htopRamVal').innerText = stats.used_ram_gb + ' / ' + stats.total_ram_gb + ' GB (' + stats.ram_percent + '%)';
          document.getElementById('htopRamFill').style.width = stats.ram_percent + '%';
          document.getElementById('htopMlxVal').innerText = stats.mlx_ram_gb + ' GB';
          document.getElementById('htopMlxMeta').innerText = stats.active_models + ' Active Model(s)';
          document.getElementById('htopCpuVal').innerText = stats.cpu_percent + '%';
          document.getElementById('htopCpuFill').style.width = Math.min(stats.cpu_percent, 100) + '%';
        }

        const statusHeader = document.getElementById('statusHeader');
        const serverContainer = document.getElementById('activeServerContainer');

        if (activeServers.length > 0) {
          const readyCount = activeServers.filter(s => s.status === 'READY').length;
          statusHeader.innerHTML = `
            <div class="status-pill ${readyCount > 0 ? 'ready' : 'none'}">
              <span class="status-dot"></span> ${activeServers.length} Active MLX Server(s) (${readyCount} Ready)
            </div>`;
          
          serverContainer.innerHTML = '';
          activeServers.forEach(s => {
            const isReady = s.status === 'READY';
            serverContainer.innerHTML += `
              <div class="card" style="border-color: ${isReady ? '#10b981' : '#f59e0b'};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                  <div>
                    <div class="card-title">${s.model}</div>
                    <div class="card-meta">
                      Host: http://${s.host}:${s.port}/v1<br>
                      PID: ${s.pid} | Status: <span style="color: ${isReady ? '#34d399' : '#f59e0b'}; font-weight:600;">[${s.status}]</span>
                    </div>
                  </div>
                  <button class="btn btn-danger" onclick="stopServer('${s.pid}')">Stop Server</button>
                </div>
              </div>`;
          });
        } else {
          statusHeader.innerHTML = `<div class="status-pill none"><span class="status-dot"></span> No MLX Model Running</div>`;
          serverContainer.innerHTML = `<div class="card" style="grid-column: 1 / -1; text-align: center; color: var(--text-muted);">No model currently running. Click "Start Model" on any downloaded model below!</div>`;
        }

        loadTestServers();
      } catch (e) {
        console.error(e);
      }
    }

    async function loadTestServers() {
      const select = document.getElementById('testServerSelect');
      if (!select) return;

      const currentVal = select.value;
      select.innerHTML = '';

      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const servers = data.servers || [];

        if (servers.length === 0) {
          select.innerHTML = '<option value="">(No active MLX servers running)</option>';
          return;
        }

        servers.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.port;
          opt.setAttribute('data-model', s.model);
          opt.setAttribute('data-host', s.host || '127.0.0.1');
          opt.innerText = `[Port ${s.port}] ${s.model} (${s.status})`;
          if (String(s.port) === String(currentVal)) {
            opt.selected = true;
          }
          select.appendChild(opt);
        });
      } catch (e) {
        console.error(e);
      }
    }

    function getRamBadge(estGb, freeGb) {
      if (estGb <= freeGb * 0.8) {
        return `<span class="ram-badge fit">🟢 Fits Smoothly (Est: ${estGb} GB RAM)</span>`;
      } else if (estGb <= freeGb) {
        return `<span class="ram-badge warn">🟡 High RAM Pressure (Est: ${estGb} GB RAM)</span>`;
      } else {
        return `<span class="ram-badge heavy">🔴 Excess RAM Needed (Est: ${estGb} GB RAM)</span>`;
      }
    }

    async function loadModels() {
      try {
        const res = await fetch('/api/models');
        const data = await res.json();
        const models = data.models || [];
        
        const fastSwapGrid = document.getElementById('fastSwapGrid');
        const modelsGrid = document.getElementById('modelsGrid');
        
        fastSwapGrid.innerHTML = '';
        modelsGrid.innerHTML = '';

        models.forEach(m => {
          const isRunning = activeServers.some(s => s.model === m.name);
          const runningServer = activeServers.find(s => s.model === m.name);

          let badgeColor = m.supported ? '#6366f1' : '#f59e0b';
          const tagBadge = m.arch_tag ? `<span style="font-size:11px; padding: 2px 8px; border-radius: 12px; background: rgba(255,255,255,0.08); color: ${badgeColor}; margin-left: 6px;">${m.arch_tag}</span>` : '';
          const ramBadge = getRamBadge(m.size_gb || 6.0, currentFreeRam);
          const isChecked = selectedForCompare.has(m.name) ? 'checked' : '';
          const hfUrl = `https://huggingface.co/${m.name}`;

          const fastSwapCard = `
            <div class="card">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div class="card-title">${m.name} ${tagBadge}</div>
                <label style="font-size: 11px; cursor: pointer; color: var(--text-muted);">
                  <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${m.name}')"> Compare
                </label>
              </div>
              <div class="card-meta">Size: ${m.size}</div>
              ${ramBadge}
              <div style="display: flex; gap: 8px; margin-top: 10px;">
                <button class="btn ${isRunning ? 'btn-secondary' : 'btn-primary'}" style="flex: 1;" onclick="openLaunchModal('${m.name}')">
                  ${isRunning ? `✓ Active on Port ${runningServer.port}` : '🚀 Start Model'}
                </button>
                <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
              </div>
            </div>`;
          fastSwapGrid.innerHTML += fastSwapCard;

          const modelCard = `
            <div class="card">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div class="card-title">${m.name} ${tagBadge}</div>
                <label style="font-size: 11px; cursor: pointer; color: var(--text-muted);">
                  <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${m.name}')"> Compare
                </label>
              </div>
              <div class="card-meta">Size: ${m.size}<br><span style="font-size: 11px;">Path: ${m.path}</span></div>
              ${ramBadge}
              <div style="display: flex; gap: 8px; margin-top: 12px;">
                <button class="btn btn-primary" onclick="openLaunchModal('${m.name}')">Start Model</button>
                <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
                <button class="btn btn-danger" onclick="deleteModel('${m.delete_target}')">Delete</button>
              </div>
            </div>`;
          modelsGrid.innerHTML += modelCard;
        });
      } catch (e) {
        console.error(e);
      }
    }

    function setFilter(tag) {
      currentFilter = tag;
      document.querySelectorAll('.chip').forEach(el => el.classList.remove('active'));
      const chip = document.getElementById('filter-' + tag);
      if (chip) chip.classList.add('active');
      doSearch();
    }

    async function doSearch() {
      const query = document.getElementById('searchInput').value || 'gemma 4';
      const sort = document.getElementById('sortSelect').value || 'downloads';
      const limit = document.getElementById('limitSelect').value || '50';
      const resultsGrid = document.getElementById('searchResultsGrid');
      const metaHeader = document.getElementById('searchMetaHeader');

      resultsGrid.innerHTML = '<div style="color: var(--text-muted);">Searching Hugging Face repositories...</div>';

      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&sort=${sort}&limit=${limit}&filter=${currentFilter}`);
      const data = await res.json();
      const results = data.results || [];
      currentFreeRam = data.free_ram_gb || currentFreeRam;

      metaHeader.innerText = `Showing ${results.length} model repositories for '${query}' (Filter: ${currentFilter.toUpperCase()} | Free RAM: ${currentFreeRam} GB)`;
      resultsGrid.innerHTML = '';

      if (results.length === 0) {
        resultsGrid.innerHTML = `<div class="card" style="grid-column: 1 / -1; text-align: center; color: var(--text-muted);">No models found for '${query}'. Try relaxing filters or typing 'mlx'.</div>`;
        return;
      }

      results.forEach(r => {
        const ramBadge = getRamBadge(r.est_ram_gb, currentFreeRam);
        const tagsHtml = (r.tags || []).map(t => `<span style="font-size:10px; padding:2px 6px; border-radius:4px; background:rgba(255,255,255,0.06); color:var(--text-muted); margin-right:4px;">${t}</span>`).join('');
        const isChecked = selectedForCompare.has(r.id) ? 'checked' : '';
        const hfUrl = `https://huggingface.co/${r.id}`;

        resultsGrid.innerHTML += `
          <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <div class="card-title">${r.id}</div>
              <label style="font-size: 11px; cursor: pointer; color: var(--text-muted);">
                <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${r.id}')"> Compare
              </label>
            </div>
            <div class="card-meta">
              Downloads: <strong>${r.downloads.toLocaleString()}</strong> | Likes: <strong>${r.likes}</strong><br>
              Updated: ${r.lastModified || 'Recent'}<br>
              <div style="margin-top: 6px;">${tagsHtml}</div>
            </div>
            ${ramBadge}
            <div style="display: flex; gap: 8px; margin-top: 10px;">
              <button class="btn btn-primary" style="flex: 1;" onclick="downloadRepo('${r.id}')">⚡ Download</button>
              <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
            </div>
          </div>`;
      });
    }

    function applyPreset(type) {
      document.querySelector('input[name="launchStrategy"][value="custom"]').checked = true;
      toggleCustomFields(true);

      if (type === 'code') {
        document.getElementById('customTemp').value = '0.0';
        document.getElementById('customMaxTokens').value = '8192';
        document.getElementById('customThinking').checked = true;
      } else if (type === 'reason') {
        document.getElementById('customTemp').value = '0.6';
        document.getElementById('customMaxTokens').value = '4096';
        document.getElementById('customThinking').checked = true;
      } else if (type === 'fast') {
        document.getElementById('customTemp').value = '0.7';
        document.getElementById('customMaxTokens').value = '2048';
        document.getElementById('customThinking').checked = false;
      }
    }

    function openLaunchModal(modelName) {
      targetModelForLaunch = modelName;
      document.getElementById('modalModelTitle').innerText = `Start '${modelName}'`;
      document.getElementById('launchModal').classList.add('active');
    }

    function closeLaunchModal() {
      document.getElementById('launchModal').classList.remove('active');
    }

    function toggleCustomFields(show) {
      document.getElementById('customFields').style.display = show ? 'block' : 'none';
    }

    async function confirmLaunch() {
      const strategy = document.querySelector('input[name="launchStrategy"]:checked').value;
      closeLaunchModal();

      let payload = { model: targetModelForLaunch, mode: strategy };

      if (strategy === 'custom') {
        payload.port = parseInt(document.getElementById('customPort').value) || globalConfig.default_port || 9999;
        payload.temp = parseFloat(document.getElementById('customTemp').value) || globalConfig.default_temp || 0.0;
        payload.max_tokens = parseInt(document.getElementById('customMaxTokens').value) || globalConfig.default_max_tokens || 4096;
        payload.thinking = document.getElementById('customThinking').checked;
      }

      alert(`Launching ${targetModelForLaunch}...`);

      await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      setTimeout(() => { updateStatus(); loadModels(); }, 2000);
    }

    async function runBenchmark() {
      const prompt = document.getElementById('benchPromptInput').value;
      const select = document.getElementById('testServerSelect');
      if (!select || !select.value) {
        alert("Please start an active MLX model server first to run benchmark.");
        return;
      }
      const port = parseInt(select.value);
      const selectedOption = select.options[select.selectedIndex];
      const model = selectedOption ? selectedOption.getAttribute('data-model') : '';
      const host = selectedOption ? selectedOption.getAttribute('data-host') : '127.0.0.1';

      const metricsCard = document.getElementById('benchMetricsCard');
      metricsCard.style.display = 'block';
      document.getElementById('benchTokSec').innerText = 'Benchmarking...';
      document.getElementById('benchTotSec').innerText = '-- s';
      document.getElementById('benchTokensMeta').innerText = '-- / --';
      document.getElementById('benchRamVal').innerText = '-- GB';
      document.getElementById('benchTextOutput').innerText = '⏳ Benchmarking model prompt processing and generation speed on Apple Silicon GPU...';

      try {
        const res = await fetch('/api/benchmark', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: prompt, model: model, port: port, host: host })
        });
        const data = await res.json();
        
        if (data.tok_per_sec !== undefined) {
          document.getElementById('benchTokSec').innerText = `${data.tok_per_sec} tok/s`;
          document.getElementById('benchTotSec').innerText = `${data.total_sec} s`;
          document.getElementById('benchTokensMeta').innerText = `${data.prompt_tokens} / ${data.completion_tokens}`;
          document.getElementById('benchRamVal').innerText = `${data.mlx_ram_gb} GB`;
          document.getElementById('benchTextOutput').innerText = `[Model: ${model}]\n\n` + data.response_text;
        } else {
          document.getElementById('benchTextOutput').innerText = "Benchmark Error: " + (data.error || "Failed");
        }
      } catch (e) {
        document.getElementById('benchTextOutput').innerText = "Benchmark Error: " + e;
      }
    }

    async function stopServer(pid) {
      await fetch('/api/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid })
      });
      updateStatus(); loadModels();
    }

    async function pauseDownload(pid, repoId) {
      await fetch('/api/pause_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid, repo_id: repoId })
      });
      updateStatus();
    }

    async function restartDownload(pid, repoId) {
      alert(`Resuming download for ${repoId} with Rust acceleration... Resuming from saved downloaded cache!`);
      await fetch('/api/restart_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid, repo_id: repoId })
      });
      setTimeout(updateStatus, 1000);
    }

    async function cancelDownload(pid, repoId) {
      if (confirm("Cancel and stop tracking this Hugging Face download?")) {
        await fetch('/api/cancel_download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid: pid, repo_id: repoId })
        });
        updateStatus();
      }
    }

    async function killAllServers() {
      if (confirm("Kill all running MLX servers?")) {
        await fetch('/api/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ all: true })
        });
        updateStatus(); loadModels();
      }
    }

    async function deleteModel(deleteTarget) {
      if (confirm(`Permanently delete model at ${deleteTarget}?`)) {
        await fetch('/api/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delete_target: deleteTarget })
        });
        loadModels();
      }
    }

    async function downloadRepo(repoId) {
      alert(`Started downloading ${repoId} via Rust Accelerated Hugging Face CLI!`);
      await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_id: repoId })
      });
      setTimeout(updateStatus, 1000);
    }

    async function sendTestPrompt() {
      const prompt = document.getElementById('promptInput').value;
      const select = document.getElementById('testServerSelect');
      if (!select || !select.value) {
        alert("Please select a running MLX model server from the dropdown to test.");
        return;
      }
      const port = parseInt(select.value);
      const selectedOption = select.options[select.selectedIndex];
      const model = selectedOption ? selectedOption.getAttribute('data-model') : '';
      const host = selectedOption ? selectedOption.getAttribute('data-host') : '127.0.0.1';

      const chatOutput = document.getElementById('chatOutput');
      chatOutput.innerText = `⏳ Sending query to '${model}' on port ${port}... (Generating thinking & response tokens)`;

      try {
        const res = await fetch('/api/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: prompt, model: model, port: port, host: host })
        });
        const data = await res.json();
        if (data.response) {
          chatOutput.innerText = `[Model: ${model} | Port: ${port}]\n\n` + data.response;
        } else {
          chatOutput.innerText = "Error: " + (data.error || "No response");
        }
      } catch (e) {
        chatOutput.innerText = "Error requesting server: " + e;
      }
    }

    async function loadLogs() {
      const res = await fetch('/api/logs');
      const data = await res.json();
      const select = document.getElementById('logSelect');
      select.innerHTML = '';
      (data.logs || []).forEach(l => {
        select.innerHTML += `<option value="${l.name}">${l.name} (${l.size})</option>`;
      });
      loadLogContent();
    }

    async function loadLogContent() {
      const select = document.getElementById('logSelect');
      const logName = select.value || '';
      const hidePolling = document.getElementById('hidePollingCheck').checked;
      const errBox = document.getElementById('errorHighlightContainer');

      const res = await fetch(`/api/logs?name=${encodeURIComponent(logName)}&hide_polling=${hidePolling}`);
      const data = await res.json();
      
      if (data.errors && data.errors.length > 0) {
        errBox.style.display = 'block';
        errBox.innerText = "⚠️ ERROR TRACEBACK FOUND IN THIS LOG:\\n\\n" + data.errors.join("\\n---\\n");
      } else {
        errBox.style.display = 'none';
        errBox.innerText = '';
      }

      document.getElementById('logContent').innerText = data.content || "(empty log)";
    }

    async function clearCurrentLog() {
      const select = document.getElementById('logSelect');
      const logName = select.value || '';
      if (!logName) return;
      if (confirm(`Clear content of '${logName}'?`)) {
        await fetch('/api/clear_logs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: logName })
        });
        loadLogContent();
      }
    }

    async function clearAllLogs() {
      if (confirm("Clear all server logs?")) {
        await fetch('/api/clear_logs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ all: true })
        });
        loadLogs();
      }
    }

    setInterval(updateStatus, 3000);
    updateStatus();
    loadModels();
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    server = ThreadedHTTPServer(("127.0.0.1", PORT), MLXGuiHandler)
    print(f"macOS MLX Control Center GUI Server running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down GUI Server...")
        server.shutdown()
