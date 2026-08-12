import asyncio
import logging
import traceback
import queue
import threading
from typing import AsyncGenerator

from src.core.config import settings

logger = logging.getLogger(__name__)


class LLMManager:
    """
    Dual-backend LLM engine: local llama-cpp-python OR Groq Cloud API.

    Backend is swappable at runtime via `set_backend()`.
    The pipeline interface (`generate_response`) stays identical.
    """

    def __init__(self):
        self.model = None          # llama_cpp.Llama (local)
        self._groq_client = None   # groq.Groq (cloud)
        self._groq_model = settings.groq_model or "llama-3.1-8b-instant"
        self.backend = "local"     # "local" | "groq"

        # If Groq API key is configured, prefer Groq cloud backend
        if settings.groq_api_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=settings.groq_api_key)
                self.backend = "groq"
                logger.info(f"Groq cloud LLM configured (model={self._groq_model}). Using Groq backend.")
            except ImportError:
                logger.warning("groq package not installed. Run: pip install groq. Falling back to local.")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")

        # Try to load the local model (needed as fallback even with Groq)
        try:
            from llama_cpp import Llama
            logger.info(f"Initializing local LLM from {settings.llm_model_path}...")
            self.model = Llama(
                model_path=settings.llm_model_path,
                n_ctx=2048,
                n_gpu_layers=0,
                verbose=False,
            )
            logger.info("Local LLM engine ready.")
        except Exception as e:
            logger.error(f"Failed to initialize local LLM: {e}\n{traceback.format_exc()}")
            if self.backend == "local":
                logger.warning("No local LLM and no Groq — LLM will be unavailable.")

    # ------------------------------------------------------------------
    # Runtime backend switching
    # ------------------------------------------------------------------
    def set_backend(self, backend: str, api_key: str = "", model: str = ""):
        """Switch between 'local' and 'groq' at runtime."""
        if backend == "groq":
            if not api_key:
                raise ValueError("Groq API key is required")
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=api_key)
                if model:
                    self._groq_model = model
                self.backend = "groq"
                logger.info(f"LLM backend switched to Groq (model={self._groq_model})")
            except ImportError:
                raise ImportError("groq package not installed. Run: pip install groq")
        elif backend == "local":
            if self.model is None:
                raise ValueError("Local LLM model not loaded")
            self.backend = "local"
            self._groq_client = None
            logger.info("LLM backend switched to local llama-cpp")
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def get_status(self) -> dict:
        return {
            "backend": self.backend,
            "local_loaded": self.model is not None,
            "groq_configured": self._groq_client is not None,
            "groq_model": self._groq_model,
        }

    # ------------------------------------------------------------------
    # Public async interface (identical for both backends)
    # ------------------------------------------------------------------
    async def generate_response(
        self, prompt: str, mode: str
    ) -> AsyncGenerator[str, None]:
        system_context = (
            f"You are a helpful voice assistant. Current mode: {mode}. "
            f"Keep responses brief and conversational."
        )
        if self.backend == "groq" and self._groq_client:
            async for token in self._stream_groq(prompt, system_context):
                yield token
        else:
            async for token in self._stream_local(prompt, system_context):
                yield token

    # ------------------------------------------------------------------
    # Groq Cloud streaming
    # ------------------------------------------------------------------
    async def _stream_groq(
        self, prompt: str, system_context: str
    ) -> AsyncGenerator[str, None]:
        logger.info(f"[groq] Generating for: \"{prompt[:80]}\"")

        token_queue: queue.Queue[str | None] = queue.Queue()

        def _produce():
            try:
                stream = self._groq_client.chat.completions.create(
                    model=self._groq_model,
                    messages=[
                        {"role": "system", "content": system_context},
                        {"role": "user", "content": prompt},
                    ],
                    stream=True,
                    max_tokens=256,
                )
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        token_queue.put(content)
            except Exception as e:
                logger.error(f"[groq] Producer error: {e}\n{traceback.format_exc()}")
            finally:
                token_queue.put(None)

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()

        loop = asyncio.get_running_loop()
        token_count = 0

        try:
            while True:
                token = await loop.run_in_executor(None, token_queue.get)
                if token is None:
                    break
                token_count += 1
                yield token
        except Exception as e:
            logger.error(f"[groq] Consumer error: {e}\n{traceback.format_exc()}")
        finally:
            logger.info(f"[groq] Generation complete — {token_count} tokens.")
            thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # Local llama-cpp streaming
    # ------------------------------------------------------------------
    async def _stream_local(
        self, prompt: str, system_context: str
    ) -> AsyncGenerator[str, None]:
        if self.model is None:
            yield "I'm sorry, my language model is currently unavailable."
            return

        logger.info(f"[local] Generating for: \"{prompt[:80]}\"")

        token_queue: queue.Queue[str | None] = queue.Queue()

        def _produce():
            try:
                messages = [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt},
                ]
                stream = self.model.create_chat_completion(
                    messages=messages,
                    stream=True,
                    max_tokens=256,
                )
                for chunk in stream:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        token_queue.put(content)
            except Exception as e:
                logger.error(f"[local] Producer error: {e}\n{traceback.format_exc()}")
            finally:
                token_queue.put(None)

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()

        loop = asyncio.get_running_loop()
        token_count = 0

        try:
            while True:
                token = await loop.run_in_executor(None, token_queue.get)
                if token is None:
                    break
                token_count += 1
                yield token
        except Exception as e:
            logger.error(f"[local] Consumer error: {e}\n{traceback.format_exc()}")
        finally:
            logger.info(f"[local] Generation complete — {token_count} tokens.")
            thread.join(timeout=5.0)
