
# ⚡ macOS MLX Control Center `v0.4` (Vision & Multimodal Edition)

> **The simplest, fastest 1-click Web GUI & CLI Control Center to search, download, compare, benchmark, and run local Multimodal Vision & Text LLMs on Apple Silicon M-Series processors.**

Designed specifically for macOS, **macOS MLX Control Center** bridges Apple's high-performance `mlx-lm` (text) and `mlx-vlm` (vision) frameworks with a dark glassmorphic web dashboard and terminal interface. It turns any Mac powered by Apple Silicon M-Series processors into a local AI power-station with zero configuration hassle.

### Dashboard Screenshot
<img width="3522" height="2344" alt="mlx1" src="https://github.com/user-attachments/assets/1a99830a-f565-41df-bc51-399e7f94e568" />
Search Models
<img width="3522" height="2046" alt="mlx2" src="https://github.com/user-attachments/assets/a98012ea-dfbb-4111-8892-3ed57d534f92" />
Compare Models
<img width="2028" height="1098" alt="mlx3" src="https://github.com/user-attachments/assets/129e06b4-a381-47b6-a50c-bda2788fde16" />
Customize API for Local Coders like OpenCode or Pi Code
<img width="1230" height="1512" alt="mlx4" src="https://github.com/user-attachments/assets/d0bf01ba-561b-4e90-adfb-52cff084c617" />


---

## ⚡ 1-Click Launch Options (No Tech Experience Needed!)

### Option A: 1-Line Terminal Instant Launcher (Recommended)
Open Terminal and paste this single command:
```bash
curl -sSL https://raw.githubusercontent.com/mypbs/mac-mlx-control-center/main/install.sh | bash
```

---

### Option B: Double-Click Launcher
1. Download or clone this repository to your Mac.
2. Double-click **`start.command`** in Finder.
3. The server launches and automatically opens the dashboard in your default browser (`http://127.0.0.1:9998`)!

---

## 🌟 Why macOS MLX Control Center?

Most local LLM runners are either overly complex, hog system menubars, or require manual hand-editing of configuration JSON files for coding tools. **macOS MLX Control Center** solves this with:

* 👁️ **Vision & Multimodal Image Recognition (v0.4)**: Full native integration with `mlx-vlm`! Run Gemma 4, Qwen 2.5/3.8 VL, PaliGemma, Pixtral, LLaVA, SmolVLM, and more with full image analysis, OCR, visual question answering, and chart understanding.
* 🖼️ **Interactive Vision Test Chat (v0.4)**: Upload and preview images directly in the GUI test bench to test OpenAI-compatible multimodal payloads.
* ⚙️ **Dual-Engine Auto-Detection (`mlx-vlm` + `mlx-lm`) (v0.4)**: Automatically detects model architectures and chooses the optimal inference engine without manual flags.
* 🔌 **LibreChat & Coding Agent Multi-Modal Sync (v0.4)**: Direct compatibility with LibreChat (`host.docker.internal:9999/v1`), Pi Code, and OpenCode for image recognition and coding workflows.
* 🧠 **macOS Memory & Process Manager (v0.3)**: Real-time visual breakdown of Apple Silicon Unified Memory (App, Wired, Compressed, Available Cache) with an interactive top process scanner (`🔍 Manage RAM`) and 1-click process termination to free up memory for larger models.
* 🔤 **Model Sorting & Date Added (v0.3)**: Sort local and downloaded models by Name (A-Z / Z-A), Size (Largest / Smallest), and Date Added (Newest / Oldest) with exact timestamps on all model cards.
* 📱 **Horizontal List Mode vs. Card Mode (v0.3)**: Toggle seamlessly between sleek horizontal list rows and spacious square card grid views across all model and search views.
* 🟢 **Activity Monitor-Aligned RAM Accounting (v0.3)**: Accurate unified memory metrics matching Activity Monitor, `htop`, and `mactop`.
* 🚀 **1-Click Model Launching & Hot Swapping**: Instantly switch between MLX models without terminal commands.
* 📦 **Multi-Quant & Subfolder HF Support**: Direct support for repositories with multiple quantizations (e.g. `orcarouter/Qwen3.8-27B-Uncensored-MLX/tree/main/4-bit`). Pick exact bit precision (`2-bit`, `4-bit`, `6-bit`, `8-bit`) and download only the weights you need instead of 80+ GB!
* 🌐 **Supercharged Hugging Face Search**: Search thousands of model weights directly with instant filter chips (`⚡ MLX Models`, `👁️ Vision & Multimodal`, `🎯 4-Bit Quantized`, `💻 Code Models`) and sorting (`Most Downloads`, `Most Liked`, `Recently Updated`).
* 🤖 **Built-In AI Model Comparison Engine**: Select 2 to 4 models to generate an instant technical breakdown comparing quantization precision (`2bit-DQ`, `OptiQ-4bit`), RAM compatibility, and specialization — *works 100% locally out-of-the-box with zero API keys or accounts required!*
* 🟢 **"Can I Run It?" Apple Silicon RAM Calculator**: Live color-coded RAM budget badges (`🟢 Fits Smoothly`, `🟡 High RAM Pressure`, `🔴 Swap Danger`) computed against your Mac's actual available memory.
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

---

## 💬 Integrating with LibreChat (Local ChatGPT Web UI with Vision)

The combo of **macOS MLX Control Center** and **[LibreChat](https://github.com/danny-avila/LibreChat)** gives you a completely private, self-hosted ChatGPT-like experience with full multimodal vision support on your Mac.

### 🌟 Key Benefits:
* 🔒 **100% Local & Private**: No data leaves your Mac; runs entirely on Apple Silicon GPU & Unified Memory.
* 👁️ **Full Multimodal Vision**: Attach screenshots, PDFs, documents, diagrams, and photos in LibreChat for instant analysis with models like Gemma 4 and Qwen 2.5/3.8 VL.
* ⚡ **Hot-Swapping**: Switch models in MLX Control Center with 1 click; LibreChat dynamically routes to the active model via `default_model` without restarting containers.
* 💰 **Zero Cost**: No OpenAI/Anthropic API subscriptions needed.

### 🛠️ Setup Guide:

#### 1. Configure `librechat.yaml`
Add the custom MLX endpoint to your `librechat.yaml` file:

```yaml
version: 1.2.0

endpoints:
  custom:
    - name: "MacBook MLX"
      apiKey: "local"
      baseURL: "http://host.docker.internal:9999/v1" # Use http://127.0.0.1:9999/v1 if running LibreChat natively without Docker
      models:
        default:
          - "default_model"
          - "mlx-community/gemma-4-e4b-it-OptiQ-4bit"
          - "lmstudio-community/Qwen3.8-27B-MLX-4bit"
          - "mlx-community/Llama-3.2-3B-Instruct-4bit"
        fetch: true
      titleConvo: true
      modelDisplayLabel: "MacBook MLX"
```

> **Note for Docker users:** `host.docker.internal` allows Docker containers on macOS to seamlessly communicate with the MLX server running directly on macOS.

#### 2. Restart LibreChat
If running via Docker:
```bash
docker compose restart
```

#### 3. Chat & Analyze Images
1. Open LibreChat (e.g. `http://localhost:3080` or `http://localhost:3081`).
2. Select **`MacBook MLX`** from the model dropdown.
3. Drag & drop images directly into the chat to perform OCR, code transcription, and visual reasoning!

---

## 🤖 Agentic AI Pairing Instructions (Antigravity, ChatGPT, Claude, Cursor & Codex)

You can use an AI coding assistant (like **Google Antigravity**, **ChatGPT / Codex**, **Claude Code**, or **Cursor**) to completely automate managing, launching, and integrating this system on your Mac.

Here are ready-to-use prompt templates you can copy and paste into your AI assistant:

### 📋 Prompt 1: 1-Click Setup & Launcher
> *"I want to run local AI models on my Apple Silicon Mac using macOS MLX Control Center. Please run `curl -sSL https://raw.githubusercontent.com/mypbs/mac-mlx-control-center/main/install.sh | bash` to set up the repository, start the GUI dashboard on port 9998, and verify that the server is responding."*

### 📋 Prompt 2: Auto-Configure LibreChat with MLX Vision
> *"Please configure my local LibreChat setup to connect to my MLX Control Center. Update `librechat.yaml` with a custom endpoint named 'MacBook MLX' pointing to `http://host.docker.internal:9999/v1` with `fetch: true` and models list containing `default_model` and `mlx-community/gemma-4-e4b-it-OptiQ-4bit`. Then restart the LibreChat docker container and confirm health."*

### 📋 Prompt 3: Auto-Configure Coding Agents (Pi Code / OpenCode / Cline)
> *"Please configure my local coding agent (Pi Code / OpenCode) to use my local MLX server as the default provider under the name 'MyMac' at `http://127.0.0.1:9999/v1` with model ID `default_model` and reasoning tokens enabled."*

### 📋 Prompt 4: Diagnostic & Vision Troubleshooting
> *"Check the status of my MLX server on port 9999 and GUI on port 9998 using `curl http://127.0.0.1:9998/api/status`. If I'm using a vision model (like Gemma 4), verify that it is running via `mlx-vlm` so image uploads work in LibreChat."*

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
* **Apple MLX Team**: Powered by Apple's open-source `mlx-lm` & `mlx-vlm` frameworks.

---

## 📜 License

MIT License — free to use, modify, and share!
