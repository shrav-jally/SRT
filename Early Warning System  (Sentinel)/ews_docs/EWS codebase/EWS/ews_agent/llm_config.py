"""
On-Prem LLM configuration for the EWS Extraction Agent.

This module provides a LangChain-compatible ChatOpenAI instance configured
to use the on-prem deployed LLM (Qwen/Qwen2.5-7B-Instruct) instead of
OpenAI's cloud API.

The on-prem LLM exposes an OpenAI-compatible API endpoint, so we can
reuse ChatOpenAI with a custom base_url and httpx client that skips
SSL verification (self-signed certificates).

Environment Variables:
    LLM_BASE_URL: The on-prem LLM API base URL
    LLM_MODEL: The model name to use
    LLM_API_KEY: API key (defaults to "not-needed" for on-prem)
    LLM_MAX_TOKENS: Maximum tokens for generation
    LLM_TEMPERATURE: Temperature for generation
    LLM_VERIFY_SSL: Whether to verify SSL certificates (default: "false")
"""

import os
import logging
import httpx
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# Default on-prem LLM configuration
DEFAULT_LLM_BASE_URL = (
    "https://llm-qwen-7b-route-srt-innovation.apps.inmumocpcl.atrapa.deloitte.com/v1"
)
DEFAULT_LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_LLM_MAX_TOKENS = 15000
DEFAULT_LLM_TEMPERATURE = 0.0


def get_llm(temperature: float | None = None, max_tokens: int | None = None,
            request_timeout: int | None = None) -> ChatOpenAI:
    """
    Get a LangChain ChatOpenAI instance configured for the on-prem LLM.

    Reads configuration from environment variables with sensible defaults:
        - LLM_BASE_URL: The on-prem LLM API base URL
        - LLM_MODEL: The model name to use
        - LLM_API_KEY: API key (defaults to "not-needed" for on-prem)
        - LLM_MAX_TOKENS: Maximum tokens for generation
        - LLM_VERIFY_SSL: Whether to verify SSL certificates (default: "false")

    Args:
        temperature: Override temperature for this call. If None, uses
                     LLM_TEMPERATURE env var or 0.0 default.
        max_tokens: Override max_tokens for this call. If None, uses
                    LLM_MAX_TOKENS env var or 15000 default. Use lower
                    values (e.g., 500) for short-answer agents to avoid
                    exceeding the model's context window limit.
        request_timeout: Timeout in seconds for each LLM request. If None,
                         defaults to 120 seconds. Increase for slow on-prem LLMs.

    Returns:
        ChatOpenAI instance pointing to the on-prem LLM.
    """
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    model = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    api_key = os.getenv("LLM_API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
    if max_tokens is None:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(DEFAULT_LLM_MAX_TOKENS)))
    if request_timeout is None:
        request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
    verify_ssl = os.getenv("LLM_VERIFY_SSL", "false").lower() in ("true", "1", "yes")

    if temperature is None:
        temperature = float(os.getenv("LLM_TEMPERATURE", str(DEFAULT_LLM_TEMPERATURE)))

    # Build httpx client with SSL verification setting and timeout
    # For on-prem deployments with self-signed certs, verify=False is needed
    # (equivalent to curl -k or requests.post(..., verify=False))
    http_client = httpx.Client(
        verify=verify_ssl,
        timeout=httpx.Timeout(request_timeout, connect=30.0),
    )

    logger.info(
        f"Initializing on-prem LLM: model={model}, base_url={base_url}, "
        f"temperature={temperature}, max_tokens={max_tokens}, "
        f"request_timeout={request_timeout}, verify_ssl={verify_ssl}"
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
