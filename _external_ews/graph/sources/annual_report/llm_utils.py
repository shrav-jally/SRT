import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def llm_call_with_retry(llm: Any, prompt: str, max_retries: int = 2, retry_delay: float = 3.0) -> str | None:
    """Call an LLM with a simple retry loop."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                return response.content
            if isinstance(response, str):
                return response
            return str(response)
        except Exception as exc:  # pragma: no cover - defensive fallback
            last_error = exc
            logger.warning("LLM call attempt %s failed: %s", attempt + 1, exc)
            if attempt < max_retries:
                import time
                time.sleep(retry_delay)
    if last_error is not None:
        raise last_error
    return None


def extract_json_from_response(response_text: str) -> dict | list | None:
    """Extract JSON from an LLM response that may contain markdown fences."""
    if not response_text or not str(response_text).strip():
        return None

    text = str(response_text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

    return None
