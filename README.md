
# ⚡ macOS MLX Control Center

> **The simplest, fastest 1-click Web GUI & CLI Control Center to search, download, compare, benchmark, and run local LLMs on Apple Silicon M-Series processors.**

Designed specifically for macOS, **macOS MLX Control Center** bridges Apple's high-performance `mlx-lm` framework with a dark glassmorphic web dashboard and terminal interface. It turns any Mac powered by Apple Silicon M-Series processors into a local AI power-station with zero configuration hassle.
<img width="3522" height="2344" alt="mlx1" src="https://github.com/user-attachments/assets/1a99830a-f565-41df-bc51-399e7f94e568" />
---

## ⚡ 1-Click Launch Options (No Tech Experience Needed!)

### Option A: Double-Click Launcher (Easiest)
1. Download or clone this repository to your Mac.
2. Double-click **`start.command`** in Finder.
3. The server launches and automatically opens the dashboard in your default browser (`http://127.0.0.1:9998`)!

---

### Option B: 1-Line Terminal Instant Launcher
Open Terminal and paste this single command:
```bash
curl -sSL https://raw.githubusercontent.com/mypbs/mac-mlx-control-center/main/install.sh | bash
```

---

## 🌟 Why macOS MLX Control Center?

Most local LLM runners are either overly complex, hog system menubars, or require manual hand-editing of configuration JSON files for coding tools. **macOS MLX Control Center** solves this with:

* 🚀 **1-Click Model Launching & Hot Swapping**: Instantly switch between MLX models without terminal commands.
* 🌐 **Supercharged Hugging Face Search**: Search thousands of model weights directly with instant filter chips (`⚡ MLX Models`, `🎯 4-Bit Quantized`, `💻 Code Models`) and sorting (`Most Downloads`, `Most Liked`, `Recently Updated`).
* 🤖 **Built-In AI Model Comparison Engine**: Select 2 to 4 models to generate an instant technical breakdown comparing quantization precision (`2bit-DQ`, `OptiQ-4bit`), RAM compatibility, and specialization — *works 100% locally out-of-the-box with zero API keys or accounts required!*
* 🟢 **"Can I Run It?" Apple Silicon RAM Calculator**: Live color-coded RAM budget badges (`🟢 Fits Smoothly`, `🟡 High RAM Pressure`, `🔴 Swap Danger`) computed against your Mac's actual free memory.
* 🤖 **Auto-Sync Pi Code & OpenCode Agents**: Automatically configures [Pi Code](https://github.com/) and [OpenCode](https://github.com/) under provider `MyMac` (`http://127.0.0.1:9999/v1`). Whenever you swap models in the GUI, your coding agents automatically route to the newly loaded model!
* 📊 **Tokens/Second Speed Benchmark**: Measure generation speed (`tok/s`), execution time, token counts, and GPU memory usage on Apple Silicon.
* ⚙️ **Custom API Settings**: Change default ports (`9999`, `8888`, `8080`), host binding (`127.0.0.1` or `0.0.0.0` for LAN access across home Wi-Fi), and max output token budgets with built-in memory guidelines.

---

## 🛠️ Prerequisites

Running local AI on your Mac has never been easier. You only need:
1. **Any Mac with Apple Silicon M-Series Processors** (with Unified Memory).
2. **macOS** (12.0 or newer).
3. **Python 3.10+** (pre-installed on macOS or available via Homebrew/Xcode).

> *Note:* Dependencies like `mlx-lm` and `hf` CLI are automatically installed on-demand via `uvx`. You do not need to pre-install heavy ML environments! Zero API keys or account sign-ups are required.

---

## 🖥️ Terminal CLI Mode

Prefer working in the terminal? You can also use `mlx.sh` directly:

```bash
./mlx.sh
```

### Key CLI Commands:
* `./mlx.sh list`: View all downloaded local models and RAM sizes.
* `./mlx.sh search <query>`: Search Hugging Face repositories directly from terminal.
* `./mlx.sh start`: Interactive launcher with Fast Swap and Concurrent port options.
* `./mlx.sh stop`: Emergency kill-switch for running servers.

---

## 💡 How Token Limits & RAM Work on Mac

In the **`⚙️ API Settings`** panel, you can configure your **Max Output Tokens**:

* **Max Output Tokens**: Specifies the maximum number of *generated response + reasoning tokens* the server produces. It does not limit your input prompt size.
* **RAM Guidelines for Apple Silicon**:
  * **2B – 8B Models** *(Gemma 4 4B, Qwen 7B)*: Set to `4096 – 8192` (Light KV Cache RAM impact ~0.5 GB).
  * **14B – 35B Models** *(Qwen 32B, DeepSeek 35B)*: Set to `4096` (Moderate RAM impact ~1.5–3 GB).
  * **70B+ Models**: Set to `2048 – 4096` to prevent memory swapping.

---

## 🤝 Agent Integration (Pi Code & OpenCode)

When auto-sync is enabled in **`⚙️ API Settings`**, launching any model automatically updates your local coding agent configs:

* **Pi Code**: `~/.pi/agent/settings.json` & `~/.pi/agent/models.json`
* **OpenCode**: `~/.config/opencode/opencode.jsonc`

Provider Name: **`MyMac`**  
Model ID: **`default_model`** (Auto-Detect Active MLX Endpoint)

---

## 🤖 Acknowledgements

* **Google Antigravity AI**: Pair-programmed, engineered, and designed with Antigravity AI.
* **Apple MLX Team**: Powered by Apple's open-source `mlx-lm` framework.

---

## 📜 License

MIT License — free to use, modify, and share!
