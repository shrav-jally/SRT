import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from contextlib import asynccontextmanager

from src.core.config import settings
from src.api.websockets import router as websocket_router
from src.api.test_endpoints import router as test_router

from src.services.stt import SpeechToText
from src.services.llm import LLMManager
from src.services.tts import TextToSpeech

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Global instances for the pipeline to use without reinitializing
class AppState:
    stt: SpeechToText = None
    llm: LLMManager = None
    tts: TextToSpeech = None

app_state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logging.info(f"Starting {settings.app_name} and initializing models globally...")
    app_state.stt = SpeechToText()
    app_state.llm = LLMManager()
    app_state.tts = TextToSpeech()
    logging.info("Models initialized successfully. Ready to accept connections.")
    yield
    # Shutdown actions
    logging.info(f"Shutting down {settings.app_name}")

app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS — allow dashboard served from file:// or Live Server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Audio-Duration-Ms", "X-Synthesis-Latency-Ms", "X-Audio-Bytes"],
)

# Include routers
app.include_router(websocket_router)
app.include_router(test_router)

@app.get("/")
async def root():
    return {"message": f"Welcome to the {settings.app_name}. Connect via WebSocket at {settings.websocket_route}"}

# Serve the diagnostic dashboard
DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "index.html"

@app.get("/dashboard")
async def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)
