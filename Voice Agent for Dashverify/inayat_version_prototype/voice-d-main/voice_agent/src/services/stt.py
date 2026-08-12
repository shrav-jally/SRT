import asyncio
import logging
import traceback
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Minimum audio length in seconds to bother transcribing
MIN_AUDIO_SECONDS = 0.3
SAMPLE_RATE = 16000


class SpeechToText:
    """
    Speech-to-Text engine using faster-whisper.

    Key design decisions:
    - `faster_whisper` is a synchronous C++ library.  Every call to
      `model.transcribe()` blocks the calling thread.  We MUST run it
      inside `loop.run_in_executor()` so the asyncio event loop stays free
      for WebSocket I/O.
    - Very short audio clips (< 300 ms) are filtered out before hitting the
      model to avoid hallucinated single-word outputs from near-silence.
    """

    def __init__(self):
        self.model: Optional[WhisperModel] = None
        try:
            logger.info("Initializing faster-whisper STT engine (CPU, int8)...")
            self.model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("faster-whisper STT engine ready.")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Public async interface (called by pipeline.processing_task)
    # ------------------------------------------------------------------
    async def transcribe(self, audio_buffer: bytes) -> Optional[str]:
        """
        Transcribes raw 16-bit PCM audio bytes to text.
        Returns None on empty / too-short / failed input.
        """
        if self.model is None:
            logger.warning("STT model not loaded — skipping transcription.")
            return None

        if not audio_buffer:
            logger.warning("STT received empty audio buffer.")
            return None

        # Quick sanity: minimum viable audio length
        num_samples = len(audio_buffer) // 2          # 16-bit = 2 bytes/sample
        duration_sec = num_samples / SAMPLE_RATE
        if duration_sec < MIN_AUDIO_SECONDS:
            logger.warning(
                f"STT audio too short ({duration_sec:.2f}s / {num_samples} samples). "
                f"Skipping to avoid hallucination."
            )
            return None

        logger.info(
            f"STT: Transcribing {len(audio_buffer)} bytes "
            f"({duration_sec:.2f}s, {num_samples} samples)..."
        )

        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._sync_transcribe, audio_buffer)
            return text
        except Exception as e:
            logger.error(f"STT transcription error: {e}\n{traceback.format_exc()}")
            return None

    # ------------------------------------------------------------------
    # Synchronous work (runs inside thread-pool executor)
    # ------------------------------------------------------------------
    def _sync_transcribe(self, audio_buffer: bytes) -> Optional[str]:
        # Convert 16-bit PCM → float32 in [-1.0, 1.0]
        audio_array = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0

        segments, info = self.model.transcribe(
            audio_array,
            beam_size=5,
            language="en",
            vad_filter=True,           # Let Whisper's internal VAD trim silence
        )

        text = " ".join(seg.text for seg in segments).strip()

        if text:
            logger.info(f"STT result: \"{text}\"")
        else:
            logger.info("STT result: (empty transcription)")

        return text if text else None
