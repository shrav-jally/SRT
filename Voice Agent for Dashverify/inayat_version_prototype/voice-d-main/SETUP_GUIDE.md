# Complete Setup Guide — Voice Agent Pipeline

> **Starting from scratch?** This guide lists **every single thing** you need to install, download, and configure to run this project on Windows 11.

---

## 1. System-Level Prerequisites

These are the foundational tools you must install before anything else.

### 1.1 Python (3.10 or newer)

The project uses modern Python syntax (e.g., `SileroVADWrapper | None` union types), which requires **Python 3.10+**.

- **Download:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
- **Important:** During installation, **check the box** that says **"Add Python to PATH"**.
- Verify after install:
  ```powershell
  python --version
  pip --version
  ```

### 1.2 Git (optional but recommended)

Needed if you want to clone the repo or manage version control.

- **Download:** [https://git-scm.com/download/win](https://git-scm.com/download/win)
- Verify after install:
  ```powershell
  git --version
  ```

### 1.3 Visual Studio Build Tools (C++ Compiler)

**Critical for `llama-cpp-python`.** This package compiles C++ code during `pip install` and requires a working compiler. If you install a pre-built wheel, you may skip this — but if pip tries to build from source, you'll need it.

- **Download:** [https://visualstudio.microsoft.com/visual-cpp-build-tools/](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- During installation, select the **"Desktop development with C++"** workload.
- Ensure the **MSVC v143** compiler and **Windows SDK** components are checked.

### 1.4 Web Browser

Any modern browser (Chrome, Edge, Firefox) to open the dashboard at [`index.html`](voice_agent/index.html).

---

## 2. Python Packages (pip dependencies)

### 2.1 Core dependencies (from [`requirements.txt`](voice_agent/requirements.txt))

| Package | Min Version | Purpose |
|---|---|---|
| `fastapi` | ≥0.103.1 | Web framework & WebSocket server |
| `uvicorn` | ≥0.23.2 | ASGI server to run FastAPI |
| `websockets` | ≥11.0.3 | WebSocket protocol library |
| `pydantic` | ≥2.4.2 | Data validation & settings models |
| `pydantic-settings` | ≥2.0.3 | Environment variable / `.env` loading |
| `silero-vad` | (latest) | Voice Activity Detection (ONNX-based) |
| `faster-whisper` | (latest) | Speech-to-Text (CTranslate2 Whisper) |
| `llama-cpp-python` | (latest) | Local LLM inference (llama.cpp Python bindings) |
| `kokoro-onnx` | (latest) | Text-to-Speech (ONNX Kokoro engine) |
| `soundfile` | (latest) | Audio file I/O (used by kokoro-onnx) |
| `numpy` | (latest) | Numerical arrays (audio processing) |

### 2.2 Implicit / Transitive dependencies (imported in code but not in requirements.txt)

| Package | Purpose | Why it's needed |
|---|---|---|
| `torch` | Tensor operations for Silero VAD | Imported in [`vad.py`](voice_agent/src/services/vad.py:4) — `import torch` |
| `onnxruntime` | ONNX model inference | Silero VAD is loaded with `onnx=True`; faster-whisper also uses it |
| `ctranslate2` | Faster Whisper backend | `faster-whisper` is built on CTranslate2 (installed automatically) |
| `huggingface-hub` | Model downloading | `faster-whisper` downloads models from HuggingFace on first run |

> **Note:** `torch`, `onnxruntime`, and `ctranslate2` are typically installed automatically as transitive dependencies of `silero-vad`, `faster-whisper`, etc. But if you hit import errors, install them manually:
> ```powershell
> pip install torch onnxruntime ctranslate2 huggingface-hub
> ```

### 2.3 Optional dependency

| Package | Purpose | When needed |
|---|---|---|
| `groq` | Groq Cloud LLM API client | Only if you want to use the **Groq cloud backend** instead of local llama-cpp. Imported in [`llm.py`](voice_agent/src/services/llm.py:50) — `from groq import Groq` |

Install with:
```powershell
pip install groq
```

---

## 3. AI Model Files (must be downloaded separately)

The `.gitignore` excludes large model files. You must download them manually and place them in the correct directories.

### 3.1 LLM Model — Meta Llama 3 8B Instruct (Q4_K_M quantization)

- **File:** `Meta-Llama-3-8B-Instruct.Q4_K_M.gguf`
- **Size:** ~4.9 GB
- **Target path:** `voice_agent/models/llm/Meta-Llama-3-8B-Instruct.Q4_K_M.gguf`
- **Download from HuggingFace:** [https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF](https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF)
  - Look for the `Q4_K_M.gguf` variant

> **Alternative:** You can use any GGUF model file — just update the `llm_model_path` in [`config.py`](voice_agent/src/core/config.py:12) or set it in `.env`.

### 3.2 TTS Model — Kokoro v0.19 (ONNX)

- **File:** `kokoro-v0_19.onnx`
- **Size:** ~84 MB
- **Target path:** `voice_agent/models/tts/kokoro-v0_19.onnx`
- **Download from HuggingFace:** [https://huggingface.co/hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)

### 3.3 TTS Voices — `voices.json`

- **File:** `voices.json`
- **Target path:** `voice_agent/models/tts/voices.json`
- **Status:** ✅ Already included in the repository

### 3.4 STT Model — Whisper "base"

- **Auto-downloaded** by `faster-whisper` on first run (~140 MB from HuggingFace).
- No manual download needed. Ensure you have internet access on first startup.

### 3.5 VAD Model — Silero VAD

- **Auto-downloaded** by `silero-vad` on first run.
- No manual download needed. Ensure you have internet access on first startup.

---

## 4. Quick Install Script (PowerShell)

Run these commands in order from the project root:

```powershell
# Navigate to the voice_agent directory
cd c:\Users\shrajallepally.ext\VSC\voice-d-main\voice-d-main\voice_agent

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Upgrade pip (good practice)
pip install --upgrade pip

# Install all Python dependencies
pip install -r requirements.txt

# (Optional) Install Groq cloud backend
pip install groq

# Create the models/llm directory for the LLM model file
New-Item -ItemType Directory -Force -Path models\llm

# Download the LLM model (requires git-lfs or manual browser download)
# Option A: Use huggingface-hub CLI
pip install huggingface-hub
huggingface-cli download QuantFactory/Meta-Llama-3-8B-Instruct-GGUF Meta-Llama-3-8B-Instruct.Q4_K_M.gguf --local-dir models\llm

# Download the TTS ONNX model
huggingface-cli download hexgrad/Kokoro-82M kokoro-v0_19.onnx --local-dir models\tts

# Run the application
uvicorn src.main:app --reload
```

---

## 5. Directory Structure After Setup

```
voice_agent/
├── models/
│   ├── llm/
│   │   └── Meta-Llama-3-8B-Instruct.Q4_K_M.gguf   ← YOU DOWNLOAD THIS (~4.9 GB)
│   └── tts/
│       ├── kokoro-v0_19.onnx                        ← YOU DOWNLOAD THIS (~84 MB)
│       └── voices.json                              ← Already in repo
├── src/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── services/
│   └── tools/
├── index.html
├── requirements.txt
├── .env                                             ← Create for API keys
└── venv/                                            ← Created by python -m venv
```

---

## 6. Environment Variables (`.env` file)

Create a `.env` file in the `voice_agent/` directory if you need to override defaults or provide API keys:

```env
# Optional: Override model paths
# LLM_MODEL_PATH=models/llm/Meta-Llama-3-8B-Instruct.Q4_K_M.gguf
# TTS_MODEL_PATH=models/tts/kokoro-v0_19.onnx
# TTS_VOICES_PATH=models/tts/voices.json

# Optional: Groq API key (if using cloud LLM backend)
# GROQ_API_KEY=gsk_your_key_here
```

---

## 7. Running the Application

```powershell
cd c:\Users\shrajallepally.ext\VSC\voice-d-main\voice-d-main\voice_agent
.\venv\Scripts\Activate.ps1
uvicorn src.main:app --reload
```

- **Server:** [http://localhost:8000](http://localhost:8000)
- **WebSocket:** `ws://localhost:8000/ws/voice`
- **Dashboard:** Open [`index.html`](voice_agent/index.html) in a browser

---

## 8. Troubleshooting

| Problem | Solution |
|---|---|
| `llama-cpp-python` fails to install | Install Visual Studio Build Tools (see §1.3). Alternatively, try a pre-built wheel: `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu` |
| `torch` is too large | Install CPU-only PyTorch: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| `faster-whisper` download fails on first run | Ensure internet access. Or pre-download: `huggingface-cli download Systran/faster-whisper-base` |
| Silero VAD fails to load | Ensure `onnxruntime` is installed: `pip install onnxruntime` |
| PowerShell script execution error | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `ModuleNotFoundError: No module named 'src'` | Make sure you're running `uvicorn` from inside the `voice_agent/` directory |

---

## Complete Dependency Summary

| # | Dependency | Type | Install Method | Size |
|---|---|---|---|---|
| 1 | Python 3.10+ | System | python.org installer | ~30 MB |
| 2 | Git | System | git-scm.com installer | ~50 MB |
| 3 | Visual Studio Build Tools | System | visualstudio.microsoft.com | ~6 GB |
| 4 | fastapi | pip | `pip install fastapi` | ~1 MB |
| 5 | uvicorn | pip | `pip install uvicorn` | ~1 MB |
| 6 | websockets | pip | `pip install websockets` | <1 MB |
| 7 | pydantic | pip | `pip install pydantic` | ~2 MB |
| 8 | pydantic-settings | pip | `pip install pydantic-settings` | <1 MB |
| 9 | silero-vad | pip | `pip install silero-vad` | ~1 MB |
| 10 | faster-whisper | pip | `pip install faster-whisper` | ~5 MB |
| 11 | llama-cpp-python | pip | `pip install llama-cpp-python` | ~2 MB (build) |
| 12 | kokoro-onnx | pip | `pip install kokoro-onnx` | ~1 MB |
| 13 | soundfile | pip | `pip install soundfile` | ~1 MB |
| 14 | numpy | pip | `pip install numpy` | ~15 MB |
| 15 | torch | pip (transitive) | `pip install torch` | ~2 GB (CPU) / ~2.5 GB (GPU) |
| 16 | onnxruntime | pip (transitive) | `pip install onnxruntime` | ~5 MB |
| 17 | groq | pip (optional) | `pip install groq` | <1 MB |
| 18 | Meta-Llama-3-8B-Instruct.Q4_K_M.gguf | Model file | HuggingFace download | ~4.9 GB |
| 19 | kokoro-v0_19.onnx | Model file | HuggingFace download | ~84 MB |
| 20 | Whisper "base" model | Model file | Auto-downloaded on first run | ~140 MB |
| 21 | Silero VAD model | Model file | Auto-downloaded on first run | ~2 MB |
