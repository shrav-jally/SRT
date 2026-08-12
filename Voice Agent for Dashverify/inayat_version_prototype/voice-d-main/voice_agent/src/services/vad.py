import logging
import traceback
import numpy as np
import torch

logger = logging.getLogger(__name__)

# Constants
SAMPLE_RATE = 16000
SAMPLES_PER_FRAME = 512          # Silero requires exactly 512 samples at 16kHz
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2   # 16-bit PCM = 2 bytes per sample = 1024


class SileroVADWrapper:
    """
    Strict 512-sample accumulator wrapper around Silero VAD.
    
    Silero VAD requires input tensors of shape (1, 512) at 16kHz.
    WebSocket chunks arrive in arbitrary sizes (commonly 1365 samples
    after browser downsampling from 48kHz with a 4096-sample ScriptProcessor).
    
    This class buffers incoming raw PCM bytes and only runs inference
    when a complete 512-sample frame is available.
    """

    def __init__(self):
        self.model = None
        self.buffer = b""
        self.threshold = 0.5
        self._frame_count = 0

        try:
            logger.info("Initializing Silero VAD (ONNX)...")
            from silero_vad import load_silero_vad
            self.model = load_silero_vad(onnx=True)
            logger.info("Silero VAD initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Silero VAD: {e}\n{traceback.format_exc()}")

    def process_chunk(self, audio_chunk: bytes) -> bool:
        """
        Accumulates raw 16-bit PCM bytes and runs VAD on every complete
        512-sample frame. Returns True if ANY frame in this batch contains speech.
        """
        if self.model is None or not audio_chunk:
            return False

        # Accumulate
        self.buffer += audio_chunk
        speech_detected = False

        try:
            # Process as many complete 512-sample frames as we can
            while len(self.buffer) >= BYTES_PER_FRAME:
                # Slice exactly 1024 bytes (512 samples of 16-bit PCM)
                frame_bytes = self.buffer[:BYTES_PER_FRAME]
                self.buffer = self.buffer[BYTES_PER_FRAME:]

                # Convert to float32 in [-1.0, 1.0]
                pcm_int16 = np.frombuffer(frame_bytes, dtype=np.int16)
                pcm_float = pcm_int16.astype(np.float32) / 32768.0

                # Silero expects a 1-D tensor of exactly 512 floats
                tensor = torch.from_numpy(pcm_float)
                speech_prob = self.model(tensor, SAMPLE_RATE).item()

                self._frame_count += 1

                if speech_prob > self.threshold:
                    speech_detected = True

            return speech_detected

        except Exception as e:
            logger.error(f"VAD processing error: {e}\n{traceback.format_exc()}")
            return False

    def reset(self):
        """Resets internal state (call on new session)."""
        self.buffer = b""
        self._frame_count = 0
        if self.model is not None:
            self.model.reset_states()


# ---------------------------------------------------------------------------
# Module-level singleton so pipeline.py can call `process_vad(chunk)`
# ---------------------------------------------------------------------------
_vad_instance: SileroVADWrapper | None = None


def get_vad() -> SileroVADWrapper:
    global _vad_instance
    if _vad_instance is None:
        _vad_instance = SileroVADWrapper()
    return _vad_instance


def process_vad(audio_chunk: bytes) -> bool:
    """Convenience wrapper matching the previous interface."""
    return get_vad().process_chunk(audio_chunk)
