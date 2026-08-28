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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
sys.path.insert(1, PID_DIR)
import mlx_helper

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0e1a"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
    <linearGradient id="neonGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f2fe"/>
      <stop offset="50%" stop-color="#4facfe"/>
      <stop offset="100%" stop-color="#a855f7"/>
    </linearGradient>
    <linearGradient id="sparkGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#ec4899"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#bgGrad)" stroke="#6366f1" stroke-width="2" stroke-opacity="0.4"/>
  <line x1="20" y1="2" x2="20" y2="0" stroke="#00f2fe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="32" y1="2" x2="32" y2="0" stroke="#4facfe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="44" y1="2" x2="44" y2="0" stroke="#a855f7" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="20" y1="64" x2="20" y2="62" stroke="#00f2fe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="32" y1="64" x2="32" y2="62" stroke="#4facfe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="44" y1="64" x2="44" y2="62" stroke="#a855f7" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="2" y1="20" x2="0" y2="20" stroke="#00f2fe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="2" y1="32" x2="0" y2="32" stroke="#4facfe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="2" y1="44" x2="0" y2="44" stroke="#a855f7" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="64" y1="20" x2="62" y2="20" stroke="#00f2fe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="64" y1="32" x2="62" y2="32" stroke="#4facfe" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="64" y1="44" x2="62" y2="44" stroke="#a855f7" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M 32 14 C 20 14 14 20 14 28 C 14 34 18 38 20 42 C 22 46 25 50 31 51" fill="none" stroke="url(#neonGrad)" stroke-width="3" stroke-linecap="round"/>
  <path d="M 32 14 C 44 14 50 20 50 28 C 50 34 46 38 44 42 C 42 46 39 50 33 51" fill="none" stroke="url(#neonGrad)" stroke-width="3" stroke-linecap="round"/>
  <path d="M 22 25 L 32 30 L 42 25" fill="none" stroke="#00f2fe" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 20 37 L 32 32 L 44 37" fill="none" stroke="#a855f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 32 14 L 32 50" fill="none" stroke="url(#sparkGrad)" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="22" cy="25" r="3" fill="#00f2fe"/>
  <circle cx="42" cy="25" r="3" fill="#a855f7"/>
  <circle cx="20" cy="37" r="3" fill="#00f2fe"/>
  <circle cx="44" cy="37" r="3" fill="#a855f7"/>
  <circle cx="32" cy="32" r="4.5" fill="#ffffff"/>
  <circle cx="32" cy="32" r="3" fill="#6366f1"/>
</svg>"""

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

    def send_svg(self, svg_content, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "image/svg+xml")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(svg_content.encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_html(INDEX_HTML)
        elif path == "/favicon.ico" or path == "/favicon.svg":
            self.send_svg(FAVICON_SVG)
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
        elif path == "/api/memory_processes":
            stats = mlx_helper.get_system_stats()
            procs = mlx_helper.get_top_memory_processes(limit=40)
            self.send_json({"stats": stats, "processes": procs})
        elif path == "/api/repo_variants":
            raw_repo = query.get("repo_id", [""])[0]
            parsed = mlx_helper.parse_hf_identifier(raw_repo)
            variants = mlx_helper.get_repo_quant_variants(parsed["repo_id"])
            self.send_json({"repo_id": parsed["repo_id"], "variants": variants})
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
                if m["name"] == model_name or m.get("base_name") == model_name or model_name in m["path"]:
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
            raw_repo = payload.get("repo_id", "")
            explicit_subfolder = payload.get("subfolder", "")
            parsed = mlx_helper.parse_hf_identifier(raw_repo, explicit_subfolder)
            repo_id = parsed["repo_id"]
            subfolder = parsed["subfolder"]
            download_id = parsed["download_id"]

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
                paused[download_id] = {
                    "repo_id": repo_id,
                    "subfolder": subfolder,
                    "cache_dir": cache_dir,
                    "paused_at": os.path.getmtime(cache_dir) if os.path.exists(cache_dir) else 0
                }
                mlx_helper.save_paused_downloads(paused)
                self.send_json({"status": "paused", "repo_id": repo_id, "subfolder": subfolder, "download_id": download_id})
            else:
                self.send_json({"error": "No repo_id provided"}, 400)

        elif path == "/api/cancel_download":
            pid = payload.get("pid")
            raw_repo = payload.get("repo_id", "")
            explicit_subfolder = payload.get("subfolder", "")
            parsed = mlx_helper.parse_hf_identifier(raw_repo, explicit_subfolder)
            repo_id = parsed["repo_id"]
            download_id = parsed["download_id"]

            if pid:
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            if repo_id:
                paused = mlx_helper.load_paused_downloads()
                if download_id in paused:
                    del paused[download_id]
                    mlx_helper.save_paused_downloads(paused)
                elif repo_id in paused:
                    del paused[repo_id]
                    mlx_helper.save_paused_downloads(paused)
            self.send_json({"status": "ok", "cancelled": download_id or pid})

        elif path == "/api/restart_download" or path == "/api/resume_download":
            pid = payload.get("pid")
            raw_repo = payload.get("repo_id", "")
            explicit_subfolder = payload.get("subfolder", "")
            if pid:
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            if raw_repo:
                parsed = mlx_helper.parse_hf_identifier(raw_repo, explicit_subfolder)
                repo_id = parsed["repo_id"]
                subfolder = parsed["subfolder"]
                revision = parsed["revision"]
                download_id = parsed["download_id"]
                display_name = parsed["display_name"]

                paused = mlx_helper.load_paused_downloads()
                if download_id in paused:
                    del paused[download_id]
                    mlx_helper.save_paused_downloads(paused)
                elif repo_id in paused:
                    del paused[repo_id]
                    mlx_helper.save_paused_downloads(paused)

                env = os.environ.copy()
                env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/bin')}:{env.get('PATH', '')}"
                env["PYTHONUNBUFFERED"] = "1"
                env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
                env["HF_XET_HIGH_PERFORMANCE"] = "1"

                cmd = ["hf", "download", repo_id]
                if subfolder:
                    cmd.extend(["--include", f"{subfolder}/*"])
                if revision and revision != "main":
                    cmd.extend(["--revision", revision])

                proc = subprocess.Popen(cmd, env=env)
                self.send_json({
                    "status": "resumed",
                    "repo_id": repo_id,
                    "subfolder": subfolder,
                    "download_id": download_id,
                    "display_name": display_name,
                    "new_pid": proc.pid
                })
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
            raw_repo = payload.get("repo_id", "")
            explicit_subfolder = payload.get("subfolder", "")
            if not raw_repo:
                self.send_json({"error": "No repo_id specified"}, 400)
                return

            parsed = mlx_helper.parse_hf_identifier(raw_repo, explicit_subfolder)
            repo_id = parsed["repo_id"]
            subfolder = parsed["subfolder"]
            revision = parsed["revision"]
            download_id = parsed["download_id"]
            display_name = parsed["display_name"]

            paused = mlx_helper.load_paused_downloads()
            if download_id in paused:
                del paused[download_id]
                mlx_helper.save_paused_downloads(paused)
            elif repo_id in paused:
                del paused[repo_id]
                mlx_helper.save_paused_downloads(paused)

            env = os.environ.copy()
            env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.path.expanduser('~/bin')}:{env.get('PATH', '')}"
            env["PYTHONUNBUFFERED"] = "1"
            env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
            env["HF_XET_HIGH_PERFORMANCE"] = "1"

            cmd = ["hf", "download", repo_id]
            if subfolder:
                cmd.extend(["--include", f"{subfolder}/*"])
            if revision and revision != "main":
                cmd.extend(["--revision", revision])

            proc = subprocess.Popen(cmd, env=env)
            self.send_json({
                "status": "started",
                "repo_id": repo_id,
                "subfolder": subfolder,
                "download_id": download_id,
                "display_name": display_name,
                "pid": proc.pid
            })

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
        elif path == "/api/kill_process":
            pid = payload.get("pid")
            res = mlx_helper.kill_process_by_pid(pid)
            self.send_json(res)
        else:
            self.send_json({"error": "Not Found"}, 404)

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>macOS MLX Control Center v0.3</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="alternate icon" href="/favicon.ico">
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
    .htop-item.htop-clickable {
      cursor: pointer;
      border-radius: 8px;
      padding: 6px 8px;
      margin: -6px -8px;
      transition: background 0.2s ease, transform 0.2s ease;
    }
    .htop-item.htop-clickable:hover {
      background: rgba(99, 102, 241, 0.12);
      transform: translateY(-1px);
    }
    .manage-ram-pill {
      font-size: 10px;
      font-weight: 700;
      color: #818cf8;
      background: rgba(99, 102, 241, 0.2);
      border: 1px solid rgba(99, 102, 241, 0.4);
      border-radius: 12px;
      padding: 2px 8px;
      letter-spacing: 0.3px;
      text-transform: none;
      transition: all 0.2s ease;
    }
    .htop-item.htop-clickable:hover .manage-ram-pill {
      background: var(--accent);
      color: #fff;
      box-shadow: 0 0 10px var(--accent-glow);
    }
    .htop-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .htop-val { font-size: 18px; font-weight: 700; color: #fff; }
    .htop-progress { width: 100%; height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; }
    .htop-fill { height: 100%; background: linear-gradient(90deg, #6366f1, #34d399); transition: width 0.3s ease; }

    /* MEMORY MANAGER BREAKDOWN METER & PROCESS TABLE */
    .mem-breakdown-bar {
      display: flex;
      width: 100%;
      height: 14px;
      border-radius: 7px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.08);
      margin: 12px 0 16px 0;
    }
    .mem-segment {
      height: 100%;
      transition: width 0.3s ease;
    }
    .mem-seg-app { background: #3b82f6; }
    .mem-seg-wired { background: #f97316; }
    .mem-seg-comp { background: #a855f7; }
    .mem-seg-cache { background: #10b981; }

    .proc-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }
    .proc-table th {
      padding: 10px 14px;
      background: rgba(0, 0, 0, 0.3);
      color: var(--text-muted);
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--card-border);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .proc-table td {
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
    }
    .proc-table tr:hover td {
      background: rgba(255, 255, 255, 0.03);
    }
    .cat-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 6px;
    }
    .cat-ai { background: rgba(99, 102, 241, 0.2); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.4); }
    .cat-browser { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .cat-dev { background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.3); }
    .cat-app { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .cat-system { background: rgba(156, 163, 175, 0.1); color: var(--text-muted); border: 1px solid rgba(156, 163, 175, 0.2); }

    nav { display: flex; gap: 8px; margin-bottom: 24px; background: rgba(21, 28, 44, 0.6); padding: 6px; border-radius: 10px; border: 1px solid var(--card-border); }
    .nav-btn {
      flex: 1; padding: 10px 16px; border: none; background: transparent; color: var(--text-muted);
      font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s ease;
    }
    .nav-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
    .nav-btn.active { color: #fff; background: var(--accent); box-shadow: 0 0 12px var(--accent-glow); }
    
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    
    /* VIEW MODE TOGGLE BUTTONS (CARDS / LIST) */
    .view-toggle-group {
      display: inline-flex;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 3px;
      gap: 3px;
    }
    .view-toggle-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s ease;
      user-select: none;
    }
    .view-toggle-btn:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
    }
    .view-toggle-btn.active {
      background: var(--accent);
      color: #fff;
      box-shadow: 0 0 10px var(--accent-glow);
    }

    /* CARD STRUCTURE FOR BOTH MODES */
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px;
      padding: 18px 20px; transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease; position: relative;
    }
    .card:hover { border-color: rgba(99, 102, 241, 0.5); transform: translateY(-2px); }
    .card-title { font-size: 15px; font-weight: 600; word-break: break-all; color: #fff; }
    .card-meta { font-size: 13px; color: var(--text-muted); }

    /* CARD GRID MODE SPECIFIC STYLES */
    .grid:not(.list-view) .card {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .grid:not(.list-view) .card-header-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
      gap: 8px;
      flex-wrap: wrap;
    }
    .grid:not(.list-view) .card-meta {
      margin-bottom: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .grid:not(.list-view) .path-meta {
      font-size: 11px;
      word-break: break-all;
      color: var(--text-muted);
      opacity: 0.8;
      font-family: monospace;
    }
    .grid:not(.list-view) .card-actions {
      display: flex;
      gap: 8px;
      margin-top: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .grid:not(.list-view) .card-actions .btn {
      flex: 1;
    }

    /* LIST VIEW MODE (VERTICAL LIST WITH HORIZONTAL CARDS) */
    .grid.list-view {
      display: flex !important;
      flex-direction: column !important;
      gap: 10px !important;
    }
    .grid.list-view .card {
      display: flex !important;
      flex-direction: row !important;
      align-items: center !important;
      justify-content: space-between !important;
      padding: 14px 20px !important;
      gap: 16px !important;
      border-radius: 10px !important;
    }
    .grid.list-view .card:hover {
      border-color: rgba(99, 102, 241, 0.5);
      background: rgba(25, 34, 54, 0.95);
      transform: translateX(3px) !important;
    }
    .grid.list-view .card-main {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .grid.list-view .card-header-row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 2px;
    }
    .grid.list-view .card-title {
      font-size: 14px;
      margin-bottom: 0;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .grid.list-view .card-meta {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      font-size: 12px;
      margin-bottom: 0;
    }
    .grid.list-view .path-meta {
      max-width: 420px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 11px;
      opacity: 0.8;
      font-family: monospace;
    }
    .grid.list-view .ram-badge {
      margin-bottom: 0 !important;
      padding: 2px 8px !important;
      font-size: 11px !important;
    }
    .grid.list-view .card-actions {
      display: flex !important;
      align-items: center !important;
      gap: 8px !important;
      flex-shrink: 0 !important;
      margin-top: 0 !important;
    }
    .grid.list-view .card-actions .btn {
      padding: 8px 14px;
      font-size: 12px;
      white-space: nowrap;
    }
    .grid.list-view .card-actions .compare-label {
      margin-right: 6px;
    }

    @media (max-width: 768px) {
      .grid.list-view .card {
        flex-direction: column !important;
        align-items: flex-start !important;
      }
      .grid.list-view .card-actions {
        width: 100% !important;
        justify-content: flex-start !important;
        margin-top: 8px !important;
      }
    }
    
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
        <div class="brand-title" style="display: flex; align-items: center; gap: 8px;">
          macOS MLX Control Center
          <span style="font-size: 11px; padding: 2px 8px; border-radius: 6px; background: rgba(99, 102, 241, 0.25); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); font-weight: 600; letter-spacing: 0.5px;">v0.3</span>
        </div>
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
    <div class="htop-item htop-clickable" onclick="openMemoryModal()" title="Click to view memory breakdown and free RAM">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="htop-label">Mac System RAM</div>
        <span class="manage-ram-pill">🔍 Manage RAM</span>
      </div>
      <div class="htop-val" id="htopRamVal">-- / -- GB</div>
      <div class="htop-progress"><div class="htop-fill" id="htopRamFill" style="width: 0%;"></div></div>
      <div style="font-size: 12px; color: var(--text-muted);" id="htopRamMeta">-- GB Available</div>
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
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
      <h2 style="font-size: 18px; font-weight: 600;">Active MLX Model Servers</h2>
      <button class="btn btn-danger" onclick="killAllServers()">⚡ KILL SWITCH (Stop All)</button>
    </div>
    <div id="activeServerContainer" class="grid" style="margin-bottom: 24px;"></div>

    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
      <h2 style="font-size: 18px; font-weight: 600;">Launch a Model</h2>
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <span style="font-size: 12px; color: var(--text-muted);">Sort:</span>
        <select id="dashboardModelSortSelect" onchange="handleModelSortChange(this.value)" style="padding: 6px 12px !important; font-size: 12px !important;">
          <option value="name-asc">🔤 Name (A → Z)</option>
          <option value="name-desc">🔤 Name (Z → A)</option>
          <option value="size-desc">📦 Size (Largest)</option>
          <option value="size-asc">📦 Size (Smallest)</option>
          <option value="date-desc">📅 Date Added (Newest)</option>
          <option value="date-asc">📅 Date Added (Oldest)</option>
        </select>
        <div class="view-toggle-group">
          <button class="view-toggle-btn active" data-view="grid" onclick="setViewMode('grid')" title="Card Grid View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z"/></svg> Cards
          </button>
          <button class="view-toggle-btn" data-view="list" onclick="setViewMode('list')" title="Horizontal List View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v3H3V4zm0 7h18v3H3v-3zm0 7h18v3H3v-3z"/></svg> List
          </button>
        </div>
      </div>
    </div>
    <div id="fastSwapGrid" class="grid"></div>
  </div>

  <!-- TAB 2: DOWNLOADED MODELS -->
  <div id="tab-models" class="tab-content">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
      <h2 style="font-size: 18px; font-weight: 600;">Downloaded Models</h2>
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <span style="font-size: 12px; color: var(--text-muted);">Sort:</span>
        <select id="modelSortSelect" onchange="handleModelSortChange(this.value)" style="padding: 6px 12px !important; font-size: 12px !important;">
          <option value="name-asc">🔤 Name (A → Z)</option>
          <option value="name-desc">🔤 Name (Z → A)</option>
          <option value="size-desc">📦 Size (Largest)</option>
          <option value="size-asc">📦 Size (Smallest)</option>
          <option value="date-desc">📅 Date Added (Newest)</option>
          <option value="date-asc">📅 Date Added (Oldest)</option>
        </select>
        <div class="view-toggle-group">
          <button class="view-toggle-btn active" data-view="grid" onclick="setViewMode('grid')" title="Card Grid View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z"/></svg> Cards
          </button>
          <button class="view-toggle-btn" data-view="list" onclick="setViewMode('list')" title="Horizontal List View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v3H3V4zm0 7h18v3H3v-3zm0 7h18v3H3v-3z"/></svg> List
          </button>
        </div>
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
      
      <div style="margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
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
        <div class="view-toggle-group">
          <button class="view-toggle-btn active" data-view="grid" onclick="setViewMode('grid')" title="Card Grid View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z"/></svg> Cards
          </button>
          <button class="view-toggle-btn" data-view="list" onclick="setViewMode('list')" title="Horizontal List View">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v3H3V4zm0 7h18v3H3v-3zm0 7h18v3H3v-3z"/></svg> List
          </button>
        </div>
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

  <!-- QUANTIZATION SELECTION MODAL FOR MULTI-QUANT REPOSITORIES -->
  <div id="quantModal" class="modal-overlay">
    <div class="modal" style="max-width: 600px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
        <div class="modal-header" style="margin-bottom: 0;">⚡ Select Quantization / Bit Precision</div>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="closeQuantModal()">✕ Close</button>
      </div>
      <div id="quantModalSubtitle" style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.5;"></div>
      <div id="quantModalVariants" style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; max-height: 380px; overflow-y: auto;"></div>
      <div style="display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--card-border); padding-top: 14px;">
        <button class="btn btn-secondary" onclick="closeQuantModal()">Cancel</button>
        <button class="btn btn-warning" id="quantDownloadAllBtn">Download Full Repo (All Quantizations)</button>
      </div>
    </div>
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

  <!-- MACOS MEMORY & PROCESS MANAGER MODAL -->
  <div id="memoryModal" class="modal-overlay">
    <div class="modal" style="max-width: 880px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div class="modal-header" style="margin-bottom: 0; display: flex; align-items: center; gap: 8px;">
          <span>🧠 macOS Memory & Process Manager</span>
        </div>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="closeMemoryModal()">✕ Close</button>
      </div>

      <!-- RAM BREAKDOWN SECTION -->
      <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <strong style="font-size: 14px; color: #fff;">Unified Memory Allocation</strong>
          <span style="font-size: 13px; font-weight: 700; color: #60a5fa;" id="memModalTotalVal">-- / -- GB Used</span>
        </div>

        <div class="mem-breakdown-bar">
          <div class="mem-segment mem-seg-app" id="memSegApp" style="width: 45%;" title="App Memory"></div>
          <div class="mem-segment mem-seg-wired" id="memSegWired" style="width: 10%;" title="Wired Memory"></div>
          <div class="mem-segment mem-seg-comp" id="memSegComp" style="width: 8%;" title="Compressed Memory"></div>
          <div class="mem-segment mem-seg-cache" id="memSegCache" style="width: 37%;" title="Available & Cache"></div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; font-size: 12px;">
          <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 8px; padding: 8px 12px;">
            <div style="color: #93c5fd; font-weight: 600;">📱 App Memory</div>
            <div style="font-size: 16px; font-weight: 700; color: #fff;" id="memModalAppVal">-- GB</div>
          </div>
          <div style="background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.25); border-radius: 8px; padding: 8px 12px;">
            <div style="color: #fdba74; font-weight: 600;">🔌 Wired Memory</div>
            <div style="font-size: 16px; font-weight: 700; color: #fff;" id="memModalWiredVal">-- GB</div>
          </div>
          <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 8px; padding: 8px 12px;">
            <div style="color: #d8b4fe; font-weight: 600;">🗜️ Compressed</div>
            <div style="font-size: 16px; font-weight: 700; color: #fff;" id="memModalCompVal">-- GB</div>
          </div>
          <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; padding: 8px 12px;">
            <div style="color: #6ee7b7; font-weight: 600;">🟢 Available for MLX</div>
            <div style="font-size: 16px; font-weight: 700; color: #34d399;" id="memModalAvailVal">-- GB</div>
          </div>
        </div>
      </div>

      <!-- PROCESS SEARCH & FILTER CONTROLS -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap: 10px; flex-wrap: wrap;">
        <div style="display: flex; gap: 6px; flex-wrap: wrap;" id="procFilterChips">
          <div class="chip active" onclick="filterMemoryProcesses('all', this)">All Processes</div>
          <div class="chip" onclick="filterMemoryProcesses('AI Model', this)">🤖 AI Models</div>
          <div class="chip" onclick="filterMemoryProcesses('Browser', this)">🌐 Browsers</div>
          <div class="chip" onclick="filterMemoryProcesses('Dev Tool', this)">🛠️ Dev Tools</div>
          <div class="chip" onclick="filterMemoryProcesses('App', this)">💬 Apps</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; margin-left: auto;">
          <input type="text" id="procSearchInput" placeholder="Filter by name / PID..." style="padding: 6px 12px !important; font-size: 12px !important; width: 180px;" oninput="filterMemoryProcesses()">
          <button class="btn btn-secondary" style="padding: 7px 12px; font-size: 12px;" onclick="loadMemoryProcesses()">🔄 Refresh</button>
        </div>
      </div>

      <!-- PROCESS TABLE CONTAINER -->
      <div style="max-height: 380px; overflow-y: auto; border: 1px solid var(--card-border); border-radius: 10px; background: rgba(0,0,0,0.2);">
        <table class="proc-table">
          <thead>
            <tr>
              <th>Process / App</th>
              <th>Category</th>
              <th>PID</th>
              <th>RAM Usage</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="procTableBody">
            <tr>
              <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Scanning active processes...</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px; font-size: 12px; color: var(--text-muted);">
        <span>💡 Terminating heavy background apps (e.g. browsers, background dev servers) frees memory for larger MLX models.</span>
        <button class="btn btn-secondary" onclick="closeMemoryModal()">Close</button>
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
    let currentViewMode = localStorage.getItem('mlx_view_mode') || 'grid';

    function setViewMode(mode) {
      currentViewMode = mode;
      localStorage.setItem('mlx_view_mode', mode);
      applyViewMode();
    }

    function applyViewMode() {
      const isList = currentViewMode === 'list';
      const gridIds = ['activeServerContainer', 'fastSwapGrid', 'modelsGrid', 'searchResultsGrid'];
      gridIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          if (isList) el.classList.add('list-view');
          else el.classList.remove('list-view');
        }
      });

      document.querySelectorAll('.view-toggle-btn').forEach(btn => {
        if (btn.getAttribute('data-view') === currentViewMode) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      });
    }

    let currentModelSort = localStorage.getItem('mlx_model_sort') || 'name-asc';
    let cachedDownloadedModels = [];

    function handleModelSortChange(sortVal) {
      currentModelSort = sortVal;
      localStorage.setItem('mlx_model_sort', sortVal);
      syncSortDropdowns();
      renderModelGrids();
    }

    function syncSortDropdowns() {
      const d1 = document.getElementById('modelSortSelect');
      const d2 = document.getElementById('dashboardModelSortSelect');
      if (d1) d1.value = currentModelSort;
      if (d2) d2.value = currentModelSort;
    }

    function sortModels(models, sortKey) {
      const sorted = [...models];
      switch (sortKey) {
        case 'name-asc':
          sorted.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
          break;
        case 'name-desc':
          sorted.sort((a, b) => b.name.localeCompare(a.name, undefined, { sensitivity: 'base' }));
          break;
        case 'size-desc':
          sorted.sort((a, b) => (b.size_gb || 0) - (a.size_gb || 0));
          break;
        case 'size-asc':
          sorted.sort((a, b) => (a.size_gb || 0) - (b.size_gb || 0));
          break;
        case 'date-desc':
          sorted.sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0));
          break;
        case 'date-asc':
          sorted.sort((a, b) => (a.created_ts || 0) - (b.created_ts || 0));
          break;
        default:
          sorted.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
      }
      return sorted;
    }

    let currentProcCategoryFilter = 'all';
    let cachedMemoryProcesses = [];

    function openMemoryModal() {
      document.getElementById('memoryModal').classList.add('active');
      loadMemoryProcesses();
    }

    function closeMemoryModal() {
      document.getElementById('memoryModal').classList.remove('active');
    }

    async function loadMemoryProcesses() {
      const tbody = document.getElementById('procTableBody');
      if (!tbody) return;
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Scanning active processes...</td></tr>';
      
      try {
        const res = await fetch('/api/memory_processes');
        const data = await res.json();
        const stats = data.stats || {};
        cachedMemoryProcesses = data.processes || [];

        if (stats.total_ram_gb) {
          document.getElementById('memModalTotalVal').innerText = `${stats.used_ram_gb} / ${stats.total_ram_gb} GB (${stats.ram_percent}%)`;
          document.getElementById('memModalAppVal').innerText = `${stats.app_ram_gb || '--'} GB`;
          document.getElementById('memModalWiredVal').innerText = `${stats.wired_ram_gb || '--'} GB`;
          document.getElementById('memModalCompVal').innerText = `${stats.compressed_ram_gb || '--'} GB`;
          document.getElementById('memModalAvailVal').innerText = `${stats.free_ram_gb || '--'} GB`;

          const appPct = (stats.app_ram_gb / stats.total_ram_gb) * 100;
          const wiredPct = (stats.wired_ram_gb / stats.total_ram_gb) * 100;
          const compPct = (stats.compressed_ram_gb / stats.total_ram_gb) * 100;
          const availPct = Math.max(0, 100 - appPct - wiredPct - compPct);

          document.getElementById('memSegApp').style.width = `${appPct}%`;
          document.getElementById('memSegWired').style.width = `${wiredPct}%`;
          document.getElementById('memSegComp').style.width = `${compPct}%`;
          document.getElementById('memSegCache').style.width = `${availPct}%`;
        }

        filterMemoryProcesses();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #f87171; padding: 24px;">Error loading processes: ${e}</td></tr>`;
      }
    }

    function filterMemoryProcesses(category, chipEl) {
      if (category !== undefined) {
        currentProcCategoryFilter = category;
        if (chipEl) {
          document.querySelectorAll('#procFilterChips .chip').forEach(c => c.classList.remove('active'));
          chipEl.classList.add('active');
        }
      }

      const search = (document.getElementById('procSearchInput')?.value || '').toLowerCase().trim();
      const tbody = document.getElementById('procTableBody');
      if (!tbody) return;

      const filtered = cachedMemoryProcesses.filter(p => {
        const matchCat = currentProcCategoryFilter === 'all' || p.category === currentProcCategoryFilter;
        const matchSearch = !search || p.name.toLowerCase().includes(search) || String(p.pid).includes(search) || (p.command && p.command.toLowerCase().includes(search));
        return matchCat && matchSearch;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No matching processes found.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      filtered.forEach(p => {
        let catClass = 'cat-app';
        if (p.category === 'AI Model') catClass = 'cat-ai';
        else if (p.category === 'Browser') catClass = 'cat-browser';
        else if (p.category === 'Dev Tool') catClass = 'cat-dev';
        else if (p.category === 'macOS System') catClass = 'cat-system';

        let actionBtn = '';
        if (p.is_mlx) {
          actionBtn = `<button class="btn btn-danger" style="padding: 5px 10px; font-size: 11px;" onclick="killProcess(${p.pid}, '${p.name.replace(/'/g, "\\'")}', true)">🛑 Stop Server</button>`;
        } else if (p.is_system) {
          actionBtn = `<button class="btn btn-secondary" style="padding: 5px 10px; font-size: 11px; opacity: 0.5; cursor: not-allowed;" disabled title="Protected macOS system process">🔒 Protected</button>`;
        } else {
          actionBtn = `<button class="btn btn-danger" style="padding: 5px 10px; font-size: 11px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5;" onclick="killProcess(${p.pid}, '${p.name.replace(/'/g, "\\'")}', false)">❌ End Process</button>`;
        }

        tbody.innerHTML += `
          <tr>
            <td>
              <strong style="color: #fff; font-size: 13px;">${p.name}</strong>
              <div style="font-size: 11px; color: var(--text-muted); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.command}">${p.command}</div>
            </td>
            <td><span class="cat-badge ${catClass}">${p.category}</span></td>
            <td><code style="color: #94a3b8; font-size: 12px;">${p.pid}</code></td>
            <td><strong style="color: #34d399;">${p.rss_str}</strong> <span style="font-size: 11px; color: var(--text-muted);">(${p.mem_pct}%)</span></td>
            <td style="text-align: right;">${actionBtn}</td>
          </tr>`;
      });
    }

    async function killProcess(pid, name, isMlx) {
      const msg = isMlx 
        ? `Stop MLX Server for '${name}' (PID ${pid})?`
        : `Terminate process '${name}' (PID ${pid}) to free memory?`;

      if (!confirm(msg)) return;

      try {
        const res = await fetch('/api/kill_process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid: pid })
        });
        const data = await res.json();
        if (data.error) {
          alert('Error: ' + data.error);
        } else {
          await loadMemoryProcesses();
          updateStatus();
        }
      } catch (e) {
        alert('Failed to kill process: ' + e);
      }
    }

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
        
        // Render Rich Download Progress Tracker Banner with Pause / Resume / Kick / Cancel Controls
        const dlBanner = document.getElementById('liveDownloadBanner');
        if (activeDownloads.length > 0) {
          dlBanner.style.display = 'block';
          dlBanner.innerHTML = '';
          activeDownloads.forEach(d => {
            const isPaused = d.status === 'PAUSED';
            const displayName = d.display_name || d.repo_id;
            const subfolder = d.subfolder || '';
            dlBanner.innerHTML += `
              <div class="card" style="border-color: ${isPaused ? '#f59e0b' : '#6366f1'}; background: ${isPaused ? 'rgba(245, 158, 11, 0.1)' : 'rgba(99, 102, 241, 0.12)'};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                  <div style="flex: 1; margin-right: 16px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                      <span class="status-pill ${isPaused ? 'paused' : 'downloading'}">
                        <span class="status-dot ${isPaused ? '' : 'pulse'}"></span> ${isPaused ? '⏸️ DOWNLOAD PAUSED (SAVED)' : '⚡ RUST ACCELERATED HF DOWNLOAD'}
                      </span>
                      <strong style="font-size: 15px; color: #fff;">${displayName}</strong>
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
                      <button class="btn btn-primary" onclick="restartDownload('${d.pid}', '${d.repo_id}', '${subfolder}')">▶️ Resume Download</button>
                    ` : `
                      <button class="btn btn-warning" onclick="pauseDownload('${d.pid}', '${d.repo_id}', '${subfolder}')">⏸️ Pause</button>
                      <button class="btn btn-primary" onclick="restartDownload('${d.pid}', '${d.repo_id}', '${subfolder}')" title="Restarts connection with Rust multi-threaded acceleration">🔄 Kick / Re-connect</button>
                    `}
                    <button class="btn btn-danger" onclick="cancelDownload('${d.pid}', '${d.repo_id}', '${subfolder}')">🛑 Cancel</button>
                  </div>
                </div>
              </div>`;
          });
        } else {
          dlBanner.style.display = 'none';
          dlBanner.innerHTML = '';
        }

        const stats = data.stats || {};
        if (stats.free_ram_gb) currentFreeRam = stats.free_ram_gb;

        if (stats.total_ram_gb) {
          document.getElementById('htopRamVal').innerText = stats.used_ram_gb + ' / ' + stats.total_ram_gb + ' GB (' + stats.ram_percent + '%)';
          document.getElementById('htopRamFill').style.width = stats.ram_percent + '%';
          if (document.getElementById('htopRamMeta')) {
            document.getElementById('htopRamMeta').innerText = stats.free_ram_gb + ' GB Available (' + (stats.cached_ram_gb || 0) + ' GB Cache)';
          }
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
              <div class="card">
                <div class="card-main">
                  <div class="card-header-row">
                    <div class="card-title">${s.model}</div>
                    <span class="status-pill ${isReady ? 'ready' : 'none'}">
                      <span class="status-dot ${isReady ? '' : 'pulse'}"></span> ${s.status}
                    </span>
                  </div>
                  <div class="card-meta">
                    <span>Port: <strong style="color: #f3f4f6;">${s.port}</strong></span>
                    <span>Host: <strong style="color: #f3f4f6;">${s.host}</strong></span>
                    <span>PID: <strong style="color: #f3f4f6;">${s.pid}</strong></span>
                    <span>Endpoint: <code style="color: #60a5fa;">http://${s.host}:${s.port}/v1</code></span>
                  </div>
                </div>
                <div class="card-actions">
                  <button class="btn btn-danger" onclick="stopServer('${s.pid}')">🛑 Stop Server</button>
                  <button class="btn btn-secondary" onclick="switchTab('test'); loadTestServers();">🧪 Test API</button>
                </div>
              </div>`;
          });
        } else {
          statusHeader.innerHTML = `
            <div class="status-pill none">
              <span class="status-dot"></span> 0 Active MLX Servers
            </div>`;
          serverContainer.innerHTML = `<div class="card" style="grid-column: 1 / -1; width: 100%; text-align: center; color: var(--text-muted); padding: 18px;">No model currently running. Click "Start Model" on any downloaded model below!</div>`;
        }

        applyViewMode();
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

    function renderModelGrids() {
      const fastSwapGrid = document.getElementById('fastSwapGrid');
      const modelsGrid = document.getElementById('modelsGrid');
      if (!fastSwapGrid || !modelsGrid) return;

      fastSwapGrid.innerHTML = '';
      modelsGrid.innerHTML = '';

      if (cachedDownloadedModels.length === 0) {
        const emptyHtml = `<div class="card" style="grid-column: 1 / -1; width: 100%; text-align: center; color: var(--text-muted); padding: 24px;">No models downloaded yet. Use the "Search Hugging Face" tab to download models!</div>`;
        fastSwapGrid.innerHTML = emptyHtml;
        modelsGrid.innerHTML = emptyHtml;
        applyViewMode();
        return;
      }

      const models = sortModels(cachedDownloadedModels, currentModelSort);

      models.forEach(m => {
        const isRunning = activeServers.some(s => s.model === m.name);
        const runningServer = activeServers.find(s => s.model === m.name);

        let badgeColor = m.supported ? '#6366f1' : '#f59e0b';
        const tagBadge = m.arch_tag ? `<span style="font-size:11px; padding: 2px 8px; border-radius: 12px; background: rgba(255,255,255,0.08); color: ${badgeColor}; margin-left: 6px;">${m.arch_tag}</span>` : '';
        const ramBadge = getRamBadge(m.size_gb || 6.0, currentFreeRam);
        const isChecked = selectedForCompare.has(m.name) ? 'checked' : '';
        const hfUrl = m.base_name ? `https://huggingface.co/${m.base_name}${m.subfolder ? '/tree/main/' + m.subfolder : ''}` : `https://huggingface.co/${m.name}`;

        const fastSwapCard = `
          <div class="card">
            <div class="card-main">
              <div class="card-header-row">
                <div class="card-title">${m.name} ${tagBadge}</div>
                ${ramBadge}
                <label class="compare-label" style="font-size: 11px; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; gap: 4px; margin-left: 6px;">
                  <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${m.name}')"> Compare
                </label>
              </div>
              <div class="card-meta">
                <span>📦 Size: <strong style="color: #f3f4f6;">${m.size}</strong></span>
                ${m.date_added ? `<span>📅 Added: <strong style="color: #f3f4f6;">${m.date_added}</strong></span>` : ''}
              </div>
            </div>
            <div class="card-actions">
              <button class="btn ${isRunning ? 'btn-secondary' : 'btn-primary'}" onclick="openLaunchModal('${m.name}')">
                ${isRunning ? `✓ Active on Port ${runningServer.port}` : '🚀 Start Model'}
              </button>
              <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
            </div>
          </div>`;
        fastSwapGrid.innerHTML += fastSwapCard;

        const modelCard = `
          <div class="card">
            <div class="card-main">
              <div class="card-header-row">
                <div class="card-title">${m.name} ${tagBadge}</div>
                ${ramBadge}
                <label class="compare-label" style="font-size: 11px; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; gap: 4px; margin-left: 6px;">
                  <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${m.name}')"> Compare
                </label>
              </div>
              <div class="card-meta">
                <span>📦 Size: <strong style="color: #f3f4f6;">${m.size}</strong></span>
                ${m.date_added ? `<span>📅 Added: <strong style="color: #f3f4f6;">${m.date_added}</strong></span>` : ''}
                <span class="path-meta" title="${m.path}">📁 <span style="opacity: 0.85;">${m.path}</span></span>
              </div>
            </div>
            <div class="card-actions">
              <button class="btn btn-primary" onclick="openLaunchModal('${m.name}')">🚀 Start Model</button>
              <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
              <button class="btn btn-danger" onclick="deleteModel('${m.delete_target}')">🗑️ Delete</button>
            </div>
          </div>`;
        modelsGrid.innerHTML += modelCard;
      });
      applyViewMode();
    }

    async function loadModels() {
      try {
        const res = await fetch('/api/models');
        const data = await res.json();
        cachedDownloadedModels = data.models || [];
        syncSortDropdowns();
        renderModelGrids();
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
      const query = (document.getElementById('searchInput').value || 'gemma 4').trim();
      const sort = document.getElementById('sortSelect').value || 'downloads';
      const limit = document.getElementById('limitSelect').value || '50';
      const resultsGrid = document.getElementById('searchResultsGrid');
      const metaHeader = document.getElementById('searchMetaHeader');

      resultsGrid.innerHTML = '<div style="color: var(--text-muted);">Searching Hugging Face repositories...</div>';

      // Check if user entered a direct Hugging Face URL with subfolder/tree
      if (query.includes('huggingface.co/') || query.includes('/tree/') || query.includes('/blob/')) {
        let repoPart = query.split('huggingface.co/').pop().replace(/^\/+|\/+$/g, '');
        let subfolder = '';
        let repoId = repoPart;
        if (repoPart.includes('/tree/')) {
          const m = repoPart.match(/^([^/]+\/[^/]+)\/tree\/[^/]+(?:\/(.+))?$/);
          if (m) {
            repoId = m[1];
            subfolder = m[2] || '';
          }
        } else if (repoPart.includes('/blob/')) {
          const m = repoPart.match(/^([^/]+\/[^/]+)\/blob\/[^/]+(?:\/(.+))?$/);
          if (m) {
            repoId = m[1];
            let rest = m[2] || '';
            subfolder = rest.includes('/') ? rest.substring(0, rest.lastIndexOf('/')) : rest;
          }
        }
        
        const display = subfolder ? `${repoId} (${subfolder})` : repoId;
        const hfDirectUrl = `https://huggingface.co/${repoId}${subfolder ? '/tree/main/' + subfolder : ''}`;
        
        resultsGrid.innerHTML = `
          <div class="card" style="grid-column: 1 / -1; border-color: #6366f1; background: rgba(99, 102, 241, 0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div>
                <span class="status-pill downloading" style="margin-bottom: 6px; display: inline-block;">
                  ⚡ DIRECT HUGGING FACE MODEL DETECTED
                </span>
                <div class="card-title" style="font-size: 17px; color: #fff;">${display}</div>
                <div class="card-meta" style="margin-top: 4px;">
                  Repo ID: <strong>${repoId}</strong> ${subfolder ? `| Target Subfolder: <strong style="color: #a5b4fc;">${subfolder}</strong>` : ''}
                </div>
              </div>
              <div style="display: flex; gap: 8px;">
                <button class="btn btn-primary" style="padding: 12px 24px; font-size: 14px;" onclick="executeDownload('${repoId}', '${subfolder}')">
                  ⚡ Download ${subfolder ? subfolder : 'Model'}
                </button>
                <a href="${hfDirectUrl}" target="_blank" class="btn btn-secondary" style="padding: 12px 16px; font-size: 13px;">🔗 Open on HF</a>
              </div>
            </div>
          </div>
        `;
        metaHeader.innerText = `Detected direct Hugging Face URL for '${display}'`;
        return;
      }

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
            <div class="card-main">
              <div class="card-header-row">
                <div class="card-title">${r.id}</div>
                ${ramBadge}
                <label class="compare-label" style="font-size: 11px; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; gap: 4px; margin-left: 6px;">
                  <input type="checkbox" class="compare-check" ${isChecked} onchange="toggleCompareSelection('${r.id}')"> Compare
                </label>
              </div>
              <div class="card-meta">
                <span>⬇️ <strong style="color: #f3f4f6;">${r.downloads.toLocaleString()}</strong></span>
                <span>❤️ <strong style="color: #f3f4f6;">${r.likes}</strong></span>
                <span>🕒 <strong style="color: #f3f4f6;">${r.lastModified || 'Recent'}</strong></span>
                <div style="display: inline-flex; flex-wrap: wrap; gap: 4px;">${tagsHtml}</div>
              </div>
            </div>
            <div class="card-actions">
              <button class="btn btn-primary" onclick="downloadRepo('${r.id}')">⚡ Download</button>
              <a href="${hfUrl}" target="_blank" class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;">🔗 HF Page</a>
            </div>
          </div>`;
      });
      applyViewMode();
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

    function closeQuantModal() {
      document.getElementById('quantModal').classList.remove('active');
    }

    function showQuantModal(repoId, variants) {
      document.getElementById('quantModalSubtitle').innerHTML = `
        Repository <strong style="color: #60a5fa;">${repoId}</strong> bundles multiple subfolder quantizations. Select a specific bit precision below to download only that model (saving dozens of GBs!):
      `;
      const container = document.getElementById('quantModalVariants');
      container.innerHTML = '';

      variants.forEach(v => {
        const isRec = v.label.includes('Recommended') || v.subfolder.includes('4-bit') || v.subfolder.includes('4bit');
        container.innerHTML += `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-radius: 8px; background: ${isRec ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.04)'}; border: 1px solid ${isRec ? '#6366f1' : 'rgba(255, 255, 255, 0.08)'};">
            <div>
              <strong style="font-size: 14px; color: ${isRec ? '#a5b4fc' : '#f3f4f6'};">${v.label}</strong>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Subfolder: <code>${v.subfolder}</code> | Size: <strong style="color: #34d399;">${v.size_str}</strong></div>
            </div>
            <button class="btn ${isRec ? 'btn-primary' : 'btn-secondary'}" onclick="closeQuantModal(); executeDownload('${repoId}', '${v.subfolder}')">
              ⚡ Download ${v.subfolder}
            </button>
          </div>
        `;
      });

      document.getElementById('quantDownloadAllBtn').onclick = () => {
        closeQuantModal();
        executeDownload(repoId, '');
      };

      document.getElementById('quantModal').classList.add('active');
    }

    async function executeDownload(repoId, subfolder = '') {
      const desc = subfolder ? `${repoId} (${subfolder})` : repoId;
      alert(`Started downloading ${desc} via Rust Accelerated Hugging Face CLI!`);
      await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_id: repoId, subfolder: subfolder })
      });
      setTimeout(updateStatus, 1000);
    }

    async function downloadRepo(repoId, subfolder = '') {
      if (subfolder || repoId.includes('/tree/') || repoId.includes(':') || repoId.includes('/blob/')) {
        executeDownload(repoId, subfolder);
        return;
      }

      // Check if repo has multiple quant variants
      try {
        const res = await fetch(`/api/repo_variants?repo_id=${encodeURIComponent(repoId)}`);
        const data = await res.json();
        if (data.variants && data.variants.length > 0) {
          showQuantModal(repoId, data.variants);
          return;
        }
      } catch (e) {
        console.warn("Could not check repo variants:", e);
      }

      executeDownload(repoId, '');
    }

    async function pauseDownload(pid, repoId, subfolder = '') {
      await fetch('/api/pause_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid, repo_id: repoId, subfolder: subfolder })
      });
      updateStatus();
    }

    async function restartDownload(pid, repoId, subfolder = '') {
      const desc = subfolder ? `${repoId} (${subfolder})` : repoId;
      alert(`Resuming download for ${desc} with Rust acceleration... Resuming from saved downloaded cache!`);
      await fetch('/api/restart_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid, repo_id: repoId, subfolder: subfolder })
      });
      setTimeout(updateStatus, 1000);
    }

    async function cancelDownload(pid, repoId, subfolder = '') {
      if (confirm("Cancel and stop tracking this Hugging Face download?")) {
        await fetch('/api/cancel_download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid: pid, repo_id: repoId, subfolder: subfolder })
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

    applyViewMode();
    syncSortDropdowns();
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
