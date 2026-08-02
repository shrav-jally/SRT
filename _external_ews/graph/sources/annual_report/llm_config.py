"""
On-Prem LLM configuration for the EWS Extraction Agent.

This module provides a LangChain-compatible ChatOpenAI instance configured
to use the deployed VLM endpoint exposed by the on-prem Qwen model.

The endpoint is OpenAI-compatible, so we can reuse ChatOpenAI for standard
text tasks while using a direct HTTP adapter for multimodal requests that need
to target the batch-compatible chat completions endpoint.

Environment Variables:
    LLM_BASE_URL: The on-prem LLM API base URL
    LLM_MODEL: The model name to use
    LLM_API_KEY: API key for the on-prem endpoint
    LLM_MAX_TOKENS: Maximum tokens for generation
    LLM_TEMPERATURE: Temperature for generation
    LLM_VERIFY_SSL: Whether to verify SSL certificates (default: "false")
"""

import logging
import os
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

DEFAULT_LLM_BASE_URL = (
    "https://llm-qwen-7b-route-srt-innovation.apps.inmumocpcl.atrapa.deloitte.com/v1"
)
DEFAULT_LLM_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_LLM_API_KEY = "9f86d081884c7d659a2feaa0c55ad015"
DEFAULT_LLM_MAX_TOKENS = 4096
DEFAULT_LLM_TEMPERATURE = 0.0


def _get_http_client(request_timeout: int) -> httpx.Client:
    """Build an httpx client that skips certificate verification for the on-prem endpoint."""
    verify_ssl = os.getenv("LLM_VERIFY_SSL", "false").lower() in {"true", "1", "yes"}
    return httpx.Client(
        verify=verify_ssl,
        timeout=httpx.Timeout(request_timeout, connect=30.0),
        follow_redirects=True,
    )


def _extract_content_from_response(payload: Any) -> str | None:
    """Extract assistant text from an OpenAI-compatible completion payload."""
    if not isinstance(payload, dict):
        return None

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else None

    if isinstance(content, str):
        return content

    return None


def invoke_vlm_chat_completion(
    messages: list[dict[str, Any]] | list[list[dict[str, Any]]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    request_timeout: int | None = None,
    use_batch: bool = True,
) -> str | None:
    """Invoke the on-prem chat completions API and return the assistant text."""
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/")
    model = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    api_key = os.getenv("LLM_API_KEY", DEFAULT_LLM_API_KEY)

    if max_tokens is None:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(DEFAULT_LLM_MAX_TOKENS)))
    if temperature is None:
        temperature = float(os.getenv("LLM_TEMPERATURE", str(DEFAULT_LLM_TEMPERATURE)))
    if request_timeout is None:
        request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "180"))

    endpoint = f"{base_url}/chat/completions/batch" if use_batch else f"{base_url}/chat/completions"

    payload_messages: Any
    if use_batch and isinstance(messages, list) and messages and isinstance(messages[0], dict):
        payload_messages = [messages]
    elif use_batch and isinstance(messages, list) and messages and isinstance(messages[0], list):
        payload_messages = messages
    else:
        payload_messages = messages

    payload = {
        "model": model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    with _get_http_client(request_timeout) as client:
        try:
            response = client.post(endpoint, headers=headers, json=payload, timeout=request_timeout)
            response.raise_for_status()
            return _extract_content_from_response(response.json())
        except Exception as exc:
            logger.error("VLM completion request failed: %s", exc)
            return None


def get_llm(temperature: float | None = None, max_tokens: int | None = None,
            request_timeout: int | None = None) -> ChatOpenAI:
    """Get a LangChain ChatOpenAI instance configured for the VLM endpoint."""
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    model = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    api_key = os.getenv("LLM_API_KEY", DEFAULT_LLM_API_KEY)
    if max_tokens is None:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(DEFAULT_LLM_MAX_TOKENS)))
    if request_timeout is None:
        request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "180"))

    if temperature is None:
        temperature = float(os.getenv("LLM_TEMPERATURE", str(DEFAULT_LLM_TEMPERATURE)))

    http_client = _get_http_client(request_timeout)

    logger.info(
        f"Initializing LLM: model={model}, base_url={base_url}, "
        f"temperature={temperature}, max_tokens={max_tokens}, "
        f"request_timeout={request_timeout}"
    )

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        request_timeout=request_timeout,
        http_client=http_client,
    )