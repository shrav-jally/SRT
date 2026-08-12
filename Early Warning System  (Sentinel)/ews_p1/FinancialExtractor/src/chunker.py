from __future__ import annotations

import logging
import re
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def reconstruct_table_like_text(text: str) -> str:
    """Reconstruct table-like line groups into label/value rows while preserving page references."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        return ""

    reconstructed_lines: List[str] = []
    current_row: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_row:
                reconstructed_lines.append(" | ".join(current_row))
                current_row = []
            continue

        if re.match(r"^page\s+\d+", stripped, flags=re.IGNORECASE):
            if current_row:
                reconstructed_lines.append(" | ".join(current_row))
                current_row = []
            reconstructed_lines.append(stripped)
            continue

        if re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", stripped) and len(stripped.split()) >= 2:
            if current_row:
                reconstructed_lines.append(" | ".join(current_row))
                current_row = []
            reconstructed_lines.append(stripped)
            continue

        if current_row:
            current_row.append(stripped)
        else:
            current_row = [stripped]

    if current_row:
        reconstructed_lines.append(" | ".join(current_row))

    return "\n".join(reconstructed_lines)


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[str]:
    """Split extracted text into overlapping chunks using LangChain's recursive splitter.

    Args:
        text: The full extracted text to split.
        chunk_size: Maximum size of each chunk in characters.
        chunk_overlap: Number of overlapping characters between adjacent chunks.

    Returns:
        A list of text chunks preserving order.

    Raises:
        ValueError: If the text is empty or the chunk parameters are invalid.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not text.strip():
        raise ValueError("text must not be empty")

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    structured_text = reconstruct_table_like_text(text)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks = splitter.split_text(structured_text)
    logger.info("Split text into %d chunks", len(chunks))
    return chunks
