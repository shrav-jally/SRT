# Voice Agent Pipeline

A production-ready, highly modular real-time voice agent pipeline built with FastAPI and WebSockets.

## Architecture

This project is built to handle low-latency, real-time audio streams. It consists of:
- **FastAPI**: Handles WebSocket connections and routing.
- **Pipeline Orchestrator**: Manages the flow of audio and text between different services.
- **VAD (Voice Activity Detection)**: Detects user speech and silence.
- **STT (Speech-to-Text)**: Transcribes user audio.
- **LLM (Large Language Model)**: Generates conversational responses.
- **TTS (Text-to-Speech)**: Synthesizes audio responses.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
uvicorn src.main:app --reload
```

## Modular Design

The `Pipeline` class in `src.core.pipeline` orchestrates the different components. Each component is abstracted so you can easily swap out the mock implementations for real engines like `faster-whisper`, `llama-cpp-python`, or `kokoro-onnx`.
