import asyncio
import logging
import time
import traceback
from typing import Optional

from fastapi import WebSocket

from src.models.state import SessionContext, PipelineState
from src.services.vad import process_vad
from src.services.stt import SpeechToText
from src.services.llm import LLMManager
from src.services.tts import TextToSpeech
from src.tools.guardrails import Guardrails

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
# At 16 kHz with a browser ScriptProcessor buffer of 4096 samples
# downsampled to 16 kHz → ~1365 samples/chunk → ~85 ms per chunk.
# 15 consecutive silence chunks ≈ 1.3 seconds of silence before we
# declare the utterance complete.
SILENCE_HANGOVER_CHUNKS = 15


class Pipeline:
    """
    Orchestrator pipeline that manages the full-duplex voice loop:
        mic → WebSocket → VAD → STT → LLM → TTS → WebSocket → speaker
    """

    def __init__(
        self,
        websocket: WebSocket,
        context: SessionContext,
        stt: SpeechToText,
        llm: LLMManager,
        tts: TextToSpeech,
    ):
        self.websocket = websocket
        self.context = context
        self.state = PipelineState()

        # Services (pre-initialized in main.py lifespan)
        self.stt = stt
        self.llm = llm
        self.tts = tts

        # Inter-task queues
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue()

        self._tasks: list[asyncio.Task] = []

    # ==================================================================
    # Lifecycle
    # ==================================================================
    async def start(self):
        logger.info(
            f"[pipeline] Starting session {self.context.session_id} "
            f"(mode={self.context.mode})"
        )
        self._tasks = [
            asyncio.create_task(self._inbound_task(), name="inbound"),
            asyncio.create_task(self._processing_task(), name="processing"),
            asyncio.create_task(self._outbound_task(), name="outbound"),
            asyncio.create_task(self._greeting_task(), name="greeting"),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        logger.info(f"[pipeline] Stopping session {self.context.session_id}")
        for t in self._tasks:
            t.cancel()

    def _flush_outbound_queue(self):
        while not self.audio_out_queue.empty():
            try:
                self.audio_out_queue.get_nowait()
                self.audio_out_queue.task_done()
            except asyncio.QueueEmpty:
                break

    # ==================================================================
    # Task 1 — Greeting
    # ==================================================================
    async def _greeting_task(self):
        """Generate and stream an initial greeting when the user connects."""
        self.state.is_bot_speaking = True
        prompt = (
            f"Greet the user briefly and ask if they are ready to "
            f"start the {self.context.mode}."
        )
        logger.info(f"[greeting] Generating initial greeting...")
        t0 = time.perf_counter()

        try:
            async for text_chunk in self.llm.generate_response(prompt, self.context.mode):
                if self.state.is_interrupted:
                    logger.info("[greeting] Interrupted by user speech.")
                    break
                audio = await self.tts.synthesize(text_chunk)
                if audio:
                    await self.audio_out_queue.put(audio)

            if not self.state.is_interrupted:
                audio = await self.tts.flush()
                if audio:
                    await self.audio_out_queue.put(audio)

            elapsed = time.perf_counter() - t0
            logger.info(f"[greeting] Done in {elapsed:.2f}s.")
        except Exception as e:
            logger.error(f"[greeting] Error: {e}\n{traceback.format_exc()}")
        finally:
            self.state.is_bot_speaking = False

    # ==================================================================
    # Task 2 — Inbound (WebSocket → VAD → audio buffer → STT queue)
    # ==================================================================
    async def _inbound_task(self):
        """
        Continuously reads binary audio from the WebSocket, runs VAD,
        and accumulates speech frames.  When the user stops talking
        (silence hangover exceeded), the accumulated buffer is pushed
        to the STT processing queue.
        """
        logger.info("[inbound] Task started — listening for mic audio.")
        buffer = bytearray()
        silence_count = 0
        total_chunks = 0

        try:
            while True:
                data = await self.websocket.receive_bytes()
                total_chunks += 1

                is_speech = process_vad(data)

                if is_speech:
                    # -- Handle barge-in / interruption --
                    if self.state.is_bot_speaking:
                        logger.warning("[inbound] User barge-in detected! Interrupting bot.")
                        self.state.is_interrupted = True
                        self._flush_outbound_queue()

                    if not self.state.is_speaking:
                        logger.info("[inbound] >>> Speech started.")
                        self.state.is_speaking = True

                    buffer.extend(data)
                    silence_count = 0

                else:
                    if self.state.is_speaking:
                        # Still inside the hangover window — keep buffering
                        buffer.extend(data)
                        silence_count += 1

                        if silence_count >= SILENCE_HANGOVER_CHUNKS:
                            self.state.is_speaking = False
                            buf_bytes = len(buffer)
                            buf_sec = (buf_bytes / 2) / 16000
                            logger.info(
                                f"[inbound] <<< Speech ended. "
                                f"Buffer: {buf_bytes} bytes ({buf_sec:.2f}s). "
                                f"Sending to STT queue."
                            )
                            await self.audio_in_queue.put(bytes(buffer))
                            buffer.clear()
                            silence_count = 0

        except Exception as e:
            logger.error(f"[inbound] Error (after {total_chunks} chunks): {e}")

    # ==================================================================
    # Task 3 — Processing (STT → LLM → TTS → outbound queue)
    # ==================================================================
    async def _processing_task(self):
        logger.info("[processing] Task started — waiting for utterances.")

        try:
            while True:
                audio_data = await self.audio_in_queue.get()
                self.state.is_interrupted = False

                # -- STT ------------------------------------------------
                t0 = time.perf_counter()
                logger.info(f"[processing] Running STT on {len(audio_data)} bytes...")
                transcription = await self.stt.transcribe(audio_data)
                stt_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    f"[processing] STT result ({stt_ms:.0f}ms): "
                    f"\"{transcription}\""
                )

                if not transcription:
                    logger.warning("[processing] Empty transcription — skipping.")
                    self.audio_in_queue.task_done()
                    continue

                if not Guardrails.validate_input(transcription):
                    logger.warning("[processing] Guardrails blocked input — skipping.")
                    self.audio_in_queue.task_done()
                    continue

                # -- LLM → TTS streaming ---------------------------------
                self.state.is_bot_speaking = True
                t0 = time.perf_counter()
                logger.info(f"[processing] Sending to LLM: \"{transcription}\"")

                token_count = 0
                async for text_chunk in self.llm.generate_response(
                    transcription, mode=self.context.mode
                ):
                    if self.state.is_interrupted:
                        logger.info("[processing] Interrupted mid-generation.")
                        break

                    token_count += 1

                    if Guardrails.validate_output(text_chunk):
                        audio = await self.tts.synthesize(text_chunk)
                        if audio:
                            await self.audio_out_queue.put(audio)

                # Flush remaining TTS buffer
                if not self.state.is_interrupted:
                    audio = await self.tts.flush()
                    if audio:
                        await self.audio_out_queue.put(audio)

                elapsed = time.perf_counter() - t0
                self.state.is_bot_speaking = False
                logger.info(
                    f"[processing] Response complete — "
                    f"{token_count} tokens in {elapsed:.2f}s."
                )
                self.audio_in_queue.task_done()

        except Exception as e:
            logger.error(f"[processing] Error: {e}\n{traceback.format_exc()}")

    # ==================================================================
    # Task 4 — Outbound (audio queue → WebSocket)
    # ==================================================================
    async def _outbound_task(self):
        logger.info("[outbound] Task started — streaming audio to client.")
        chunks_sent = 0

        try:
            while True:
                audio_chunk = await self.audio_out_queue.get()

                if not self.state.is_interrupted:
                    await self.websocket.send_bytes(audio_chunk)
                    chunks_sent += 1

                self.audio_out_queue.task_done()

        except Exception as e:
            logger.error(
                f"[outbound] Error (after {chunks_sent} chunks sent): {e}"
            )
