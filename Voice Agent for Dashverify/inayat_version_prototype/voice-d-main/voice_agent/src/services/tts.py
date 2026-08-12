import asyncio
import logging
import re
import traceback

import numpy as np
from kokoro_onnx import Kokoro

from src.core.config import settings

logger = logging.getLogger(__name__)

# Kokoro outputs 24 kHz audio; we need 16 kHz PCM to match the WebSocket contract.
KOKORO_SAMPLE_RATE = 24000
OUTPUT_SAMPLE_RATE = 16000


class TextToSpeech:
    """
    Streaming TTS engine using kokoro-onnx.

    Design:
    - LLM tokens arrive one-by-one ("Hel", "lo", "!", " How", ...).
    - We accumulate them into `self.text_buffer` until we hit a sentence
      boundary (`.?!`) or exceed 100 chars, then synthesize the whole clause.
    - `flush()` synthesizes whatever remains after the LLM stream ends.
    - Synthesis is blocking (ONNX inference), so we run it in an executor.
    """

    def __init__(self):
        self.text_buffer = ""
        self.kokoro: Kokoro | None = None

        try:
            logger.info(f"Initializing Kokoro TTS from {settings.tts_model_path}...")

            # ---------------------------------------------------------------
            # Kokoro-ONNX internally calls `np.load(voices_path)` which fails
            # when voices_path is a .json file.  We pre-load the JSON ourselves,
            # convert to a dict of np arrays, and monkey-patch np.load for the
            # duration of the Kokoro constructor.
            # ---------------------------------------------------------------
            import json as _json

            with open(settings.tts_voices_path, "r", encoding="utf-8") as f:
                voices_raw = _json.load(f)

            voices_dict = {
                k: np.array(v, dtype=np.float32) for k, v in voices_raw.items()
            }

            _original_np_load = np.load

            def _patched_load(file, *a, **kw):
                if str(file).endswith("voices.json"):
                    return voices_dict
                return _original_np_load(file, *a, **kw)

            np.load = _patched_load
            try:
                self.kokoro = Kokoro(settings.tts_model_path, settings.tts_voices_path)
            finally:
                np.load = _original_np_load

            # Pick first available voice
            available = self.kokoro.get_voices()
            self.voice_name = "af_bella" if "af_bella" in available else available[0]
            logger.info(
                f"Kokoro TTS ready. Using voice '{self.voice_name}'. "
                f"Available: {available[:5]}{'...' if len(available) > 5 else ''}"
            )

        except Exception as e:
            logger.error(f"Failed to load Kokoro TTS: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------
    async def synthesize(self, text_chunk: str) -> bytes:
        """
        Accumulates tokens.  Synthesizes when a sentence boundary or
        length threshold is reached.  Returns raw 16-bit PCM bytes
        (16 kHz mono) or b"" if nothing to synthesize yet.
        """
        if not self.kokoro:
            return b""

        self.text_buffer += text_chunk

        # Fire when we hit sentence-end punctuation or get long enough
        if re.search(r'[.?!]\s*$', self.text_buffer) or len(self.text_buffer) > 100:
            return await self._synthesize_buffer()

        return b""

    async def flush(self) -> bytes:
        """Synthesize whatever remains in the buffer."""
        if not self.kokoro or not self.text_buffer.strip():
            self.text_buffer = ""
            return b""
        return await self._synthesize_buffer()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _synthesize_buffer(self) -> bytes:
        text = self.text_buffer.strip()
        self.text_buffer = ""

        if not text:
            return b""

        logger.info(f"TTS synthesizing: \"{text[:60]}{'...' if len(text)>60 else ''}\"")

        try:
            loop = asyncio.get_running_loop()
            pcm_bytes = await loop.run_in_executor(None, self._sync_synthesize, text)
            logger.info(f"TTS produced {len(pcm_bytes)} bytes of audio.")
            return pcm_bytes
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}\n{traceback.format_exc()}")
            return b""

    def _sync_synthesize(self, text: str) -> bytes:
        audio, sr = self.kokoro.create(
            text, voice=self.voice_name, speed=1.0, lang="en-us"
        )

        # Kokoro outputs at 24 kHz; resample to 16 kHz to match WebSocket contract
        if sr != OUTPUT_SAMPLE_RATE:
            ratio = OUTPUT_SAMPLE_RATE / sr
            new_len = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
            audio = audio[indices]

        # float32 → int16 PCM
        pcm = (audio * 32767).astype(np.int16).tobytes()
        return pcm
