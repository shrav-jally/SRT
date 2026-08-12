"""
REST API endpoints for testing each pipeline component in isolation.

These bypass the WebSocket entirely so you can verify STT, LLM, and TTS
independently from the browser dashboard.
"""

import asyncio
import logging
import time
import traceback

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["diagnostics"])


# ── Request / Response models ────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str = "Hello! I am your voice assistant. How can I help you today?"
    voice: str = "af_bella"

class LLMRequest(BaseModel):
    prompt: str = "Say hello and introduce yourself in one sentence."
    mode: str = "interview"

class STTRequest(BaseModel):
    """For STT we generate a known TTS clip then transcribe it."""
    text: str = "The quick brown fox jumps over the lazy dog."

class SelfTalkRequest(BaseModel):
    """Full round-trip: TTS → STT → LLM → TTS"""
    seed_text: str = "Hello, I am ready for the interview."
    mode: str = "interview"
    rounds: int = 2

class LLMBackendRequest(BaseModel):
    backend: str = "groq"   # "local" | "groq"
    api_key: str = ""
    model: str = "llama-3.1-8b-instant"


# ── TTS test ─────────────────────────────────────────────────────────────

@router.post("/tts")
async def test_tts(req: TTSRequest):
    """Synthesize text → return raw 16-bit PCM audio."""
    from src.main import app_state

    if app_state.tts is None or app_state.tts.kokoro is None:
        raise HTTPException(503, "TTS engine not loaded")

    logger.info(f"[test/tts] Synthesizing: \"{req.text[:60]}\"")
    t0 = time.perf_counter()

    try:
        loop = asyncio.get_running_loop()
        pcm_bytes = await loop.run_in_executor(
            None, app_state.tts._sync_synthesize, req.text
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        duration_s = (len(pcm_bytes) / 2) / 16000

        logger.info(
            f"[test/tts] Done — {len(pcm_bytes)} bytes, "
            f"{duration_s:.2f}s audio, {elapsed_ms:.0f}ms latency"
        )

        return Response(
            content=pcm_bytes,
            media_type="application/octet-stream",
            headers={
                "X-Audio-Duration-Ms": str(int(duration_s * 1000)),
                "X-Synthesis-Latency-Ms": str(int(elapsed_ms)),
                "X-Audio-Bytes": str(len(pcm_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"[test/tts] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ── LLM test ─────────────────────────────────────────────────────────────

@router.post("/llm")
async def test_llm(req: LLMRequest):
    """Stream LLM tokens and return full text + timing."""
    from src.main import app_state

    if app_state.llm is None:
        raise HTTPException(503, "LLM engine not loaded")

    logger.info(f"[test/llm] Prompt: \"{req.prompt[:60]}\"")
    t0 = time.perf_counter()
    tokens = []
    ttft = None

    try:
        async for token in app_state.llm.generate_response(req.prompt, req.mode):
            if ttft is None:
                ttft = (time.perf_counter() - t0) * 1000
            tokens.append(token)

        total_ms = (time.perf_counter() - t0) * 1000
        full_text = "".join(tokens)

        logger.info(
            f"[test/llm] Done — {len(tokens)} tokens, "
            f"TTFT={ttft:.0f}ms, total={total_ms:.0f}ms"
        )

        return {
            "text": full_text,
            "token_count": len(tokens),
            "ttft_ms": round(ttft, 1) if ttft else None,
            "total_ms": round(total_ms, 1),
            "backend": app_state.llm.backend,
        }
    except Exception as e:
        logger.error(f"[test/llm] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ── STT test (generate known audio via TTS, then transcribe) ─────────────

@router.post("/stt")
async def test_stt(req: STTRequest):
    """Generate audio via TTS, then transcribe it. Shows expected vs actual."""
    from src.main import app_state

    if app_state.tts is None or app_state.tts.kokoro is None:
        raise HTTPException(503, "TTS engine not loaded")
    if app_state.stt is None or app_state.stt.model is None:
        raise HTTPException(503, "STT engine not loaded")

    logger.info(f"[test/stt] Generating audio for: \"{req.text[:60]}\"")

    try:
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        pcm_bytes = await loop.run_in_executor(
            None, app_state.tts._sync_synthesize, req.text
        )
        tts_ms = (time.perf_counter() - t0) * 1000
        duration_s = (len(pcm_bytes) / 2) / 16000

        logger.info(
            f"[test/stt] TTS produced {len(pcm_bytes)} bytes ({duration_s:.2f}s) "
            f"in {tts_ms:.0f}ms"
        )

        t0 = time.perf_counter()
        transcription = await app_state.stt.transcribe(pcm_bytes)
        stt_ms = (time.perf_counter() - t0) * 1000

        logger.info(f"[test/stt] STT result ({stt_ms:.0f}ms): \"{transcription}\"")

        return {
            "expected": req.text,
            "transcription": transcription or "(empty)",
            "audio_duration_s": round(duration_s, 2),
            "tts_latency_ms": round(tts_ms, 1),
            "stt_latency_ms": round(stt_ms, 1),
            "match": (
                transcription.lower().strip().rstrip(".")
                == req.text.lower().strip().rstrip(".")
            ) if transcription else False,
        }
    except Exception as e:
        logger.error(f"[test/stt] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ── Mic STT: accept raw PCM from browser and transcribe ──────────────────

@router.post("/mic-stt")
async def test_mic_stt(request: Request):
    """
    Accept raw 16-bit PCM audio bytes from the browser mic recording.
    Transcribe and return the text + timing.
    """
    from src.main import app_state

    if app_state.stt is None or app_state.stt.model is None:
        raise HTTPException(503, "STT engine not loaded")

    pcm_bytes = await request.body()
    if not pcm_bytes or len(pcm_bytes) < 1024:
        raise HTTPException(400, "Audio too short")

    duration_s = (len(pcm_bytes) / 2) / 16000
    logger.info(f"[test/mic-stt] Received {len(pcm_bytes)} bytes ({duration_s:.2f}s)")

    try:
        t0 = time.perf_counter()
        transcription = await app_state.stt.transcribe(pcm_bytes)
        stt_ms = (time.perf_counter() - t0) * 1000

        logger.info(f"[test/mic-stt] STT result ({stt_ms:.0f}ms): \"{transcription}\"")

        return {
            "transcription": transcription or "(empty)",
            "audio_duration_s": round(duration_s, 2),
            "stt_latency_ms": round(stt_ms, 1),
        }
    except Exception as e:
        logger.error(f"[test/mic-stt] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ── Self-talk: full round-trip loop ──────────────────────────────────────

@router.post("/self-talk")
async def test_self_talk(req: SelfTalkRequest):
    """Full pipeline without microphone: TTS → STT → LLM → TTS, repeated."""
    from src.main import app_state

    if not all([
        app_state.tts and app_state.tts.kokoro,
        app_state.stt and app_state.stt.model,
        app_state.llm,
    ]):
        raise HTTPException(503, "Not all engines loaded")

    logger.info(
        f"[test/self-talk] Starting {req.rounds}-round conversation. "
        f"Seed: \"{req.seed_text[:60]}\""
    )

    conversation = []
    current_text = req.seed_text
    loop = asyncio.get_running_loop()

    try:
        for i in range(req.rounds):
            round_data = {"round": i + 1, "steps": []}

            # User turn (TTS → STT)
            t0 = time.perf_counter()
            pcm = await loop.run_in_executor(
                None, app_state.tts._sync_synthesize, current_text
            )
            tts_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            transcription = await app_state.stt.transcribe(pcm)
            stt_ms = (time.perf_counter() - t0) * 1000

            round_data["steps"].append({
                "role": "user",
                "original_text": current_text,
                "tts_audio_bytes": len(pcm),
                "tts_latency_ms": round(tts_ms, 1),
                "stt_transcription": transcription or "(empty)",
                "stt_latency_ms": round(stt_ms, 1),
            })

            logger.info(
                f"[self-talk] Round {i+1} user: "
                f"\"{current_text[:40]}\" → STT: \"{transcription}\""
            )

            if not transcription:
                round_data["steps"].append({"error": "STT returned empty"})
                conversation.append(round_data)
                break

            # Bot turn (LLM → TTS)
            t0 = time.perf_counter()
            tokens = []
            async for token in app_state.llm.generate_response(
                transcription, req.mode
            ):
                tokens.append(token)
            llm_text = "".join(tokens)
            llm_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            bot_pcm = await loop.run_in_executor(
                None, app_state.tts._sync_synthesize, llm_text
            )
            bot_tts_ms = (time.perf_counter() - t0) * 1000

            round_data["steps"].append({
                "role": "assistant",
                "llm_response": llm_text,
                "llm_tokens": len(tokens),
                "llm_latency_ms": round(llm_ms, 1),
                "tts_audio_bytes": len(bot_pcm),
                "tts_latency_ms": round(bot_tts_ms, 1),
            })

            logger.info(
                f"[self-talk] Round {i+1} bot: "
                f"\"{llm_text[:60]}\" ({len(tokens)} tokens, {llm_ms:.0f}ms)"
            )

            conversation.append(round_data)
            current_text = llm_text

        return {"conversation": conversation}

    except Exception as e:
        logger.error(f"[test/self-talk] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ── LLM backend configuration ───────────────────────────────────────────

@router.post("/llm-backend")
async def set_llm_backend(req: LLMBackendRequest):
    """Switch LLM backend between local and Groq at runtime."""
    from src.main import app_state

    if app_state.llm is None:
        raise HTTPException(503, "LLM manager not initialized")

    try:
        app_state.llm.set_backend(req.backend, req.api_key, req.model)
        return {
            "status": "ok",
            **app_state.llm.get_status(),
        }
    except Exception as e:
        logger.error(f"[test/llm-backend] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(400, str(e))


@router.get("/llm-backend")
async def get_llm_backend():
    """Get current LLM backend status."""
    from src.main import app_state

    if app_state.llm is None:
        raise HTTPException(503, "LLM manager not initialized")

    return app_state.llm.get_status()
