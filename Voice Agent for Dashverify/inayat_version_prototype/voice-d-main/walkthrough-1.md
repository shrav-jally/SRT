# Voice Agent Pipeline Walkthrough

I have successfully created the voice agent pipeline structure as requested, following an industry-standard format in the `c:/Users/inayat/Desktop/voice@d/voice_agent/` directory.

## What Was Accomplished

1. **Project Infrastructure**:
   - Created `voice_agent/` root directory.
   - Initialized a `.gitignore` tailored for Python projects.
   - Generated a `requirements.txt` with essential dependencies (`fastapi`, `uvicorn`, `websockets`, `pydantic`).
   - Drafted a `README.md` with setup and running instructions.

2. **Application Architecture (`src/`)**:
   - **`main.py`**: Sets up the FastAPI app with lifespan events for startup/shutdown logging.
   - **`api/websockets.py`**: Implements the `/ws/voice` WebSocket route with dynamic parameter extraction (e.g. `?mode=interview`) and session management using `uuid`.

3. **Orchestration (`src/core/`)**:
   - **`config.py`**: Manages environment variables and application settings using Pydantic `BaseSettings`.
   - **`pipeline.py`**: The core logic handling concurrent `asyncio` tasks (`inbound_task`, `processing_task`, `outbound_task`). Includes logic to handle state interruptions (flushing the outbound queue when VAD detects speech while generating output).

4. **Service Mocks (`src/services/`)**:
   - **`vad.py`**: Lightweight Voice Activity Detection simulating silence detection based on buffer lengths.
   - **`stt.py`**: A `SpeechToText` stub ready for Whisper integrations.
   - **`llm.py`**: An `LLMManager` that returns an asynchronous generator, simulating token streaming from an LLM.
   - **`tts.py`**: A `TextToSpeech` stub simulating continuous audio payload rendering.

5. **Models and Tools (`src/models/`, `src/tools/`)**:
   - **`models/state.py`**: Pydantic models to track `SessionContext` and `PipelineState`.
   - **`tools/db.py`**: Mock asynchronous Database class for reading and writing user information.
   - **`tools/guardrails.py`**: Mock `Guardrails` logic to validate inbound transcription and outbound generation.

## How to Verify

You can navigate to your new directory and start the server:

```powershell
cd c:\Users\inayat\Desktop\voice@d\voice_agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

Once running, the WebSocket endpoint `ws://localhost:8000/ws/voice` is ready to accept binary streams for full-duplex communication.
