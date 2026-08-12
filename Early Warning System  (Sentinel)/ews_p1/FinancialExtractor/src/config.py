from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

DEFAULTS = {
    "LLM_PROVIDER": "groq",
    "LLM_MODEL": "llama-3.1-8b-instant",
    "EMBEDDING_PROVIDER": "huggingface",
    "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
    "INPUT_FOLDER": "input",
    "OUTPUT_FOLDER": "output",
    "TEMPLATE_FOLDER": "templates",
}


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    llm_provider: str
    llm_api_key: str
    llm_model: str
    input_folder: Path
    output_folder: Path
    template_folder: Path


def _get_required_env_var(name: str) -> str:
    """Return a required environment variable or raise a helpful error."""
    value = os.getenv(name)
    if value is None or not value.strip():
        if name in DEFAULTS:
            return str(DEFAULTS[name])
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def _resolve_path(value: str, description: str) -> Path:
    """Resolve a filesystem path from an environment variable."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def load_config() -> AppConfig:
    """Load and validate application configuration from the environment."""
    llm_provider = _get_required_env_var("LLM_PROVIDER")
    llm_api_key = os.getenv("LLM_API_KEY", "").strip()
    if not llm_api_key:
        raise ValueError(
            "LLM_API_KEY is required but was not found or is empty in the environment. "
            "Set LLM_API_KEY in your .env file or environment variables."
        )
    llm_model = _get_required_env_var("LLM_MODEL")

    logger.info("Loaded provider: %s", llm_provider)
    logger.info("Loaded model: %s", llm_model)

    input_folder = _resolve_path(_get_required_env_var("INPUT_FOLDER"), "input folder")
    output_folder = _resolve_path(_get_required_env_var("OUTPUT_FOLDER"), "output folder")
    template_folder = _resolve_path(_get_required_env_var("TEMPLATE_FOLDER"), "template folder")

    return AppConfig(
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        input_folder=input_folder,
        output_folder=output_folder,
        template_folder=template_folder,
    )


def get_config() -> AppConfig:
    """Return the loaded application configuration."""
    return load_config()


def get_input_folder() -> Path:
    """Return the configured input folder path."""
    return get_config().input_folder


def get_output_folder() -> Path:
    """Return the configured output folder path."""
    return get_config().output_folder


def get_template_folder() -> Path:
    """Return the configured template folder path."""
    return get_config().template_folder
