"""
PDF Parser for RAG Pipeline

Extracts text from PDF files page-by-page and creates chunks suitable
for vector store embedding. Each page becomes one chunk (or multiple
sub-chunks if the page is very long).

Uses PyMuPDF (fitz) for fast, reliable text extraction — same library
as the main extraction pipeline.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF

from . import config

logger = logging.getLogger(__name__)


@dataclass
class PageChunk:
    """A single chunk of text from a PDF page."""
    text: str
    page_number: int        # 1-based page number
    pdf_filename: str
    chunk_index: int        # 0-based sub-chunk index within the page (0 = whole page)
    total_chunks: int       # Total sub-chunks for this page

    @property
    def chunk_id(self) -> str:
        """Unique ID for this chunk: filename::page::subchunk."""
        return f"{self.pdf_filename}::page{self.page_number}::chunk{self.chunk_index}"

    @property
    def metadata(self) -> dict:
        """Metadata dict for ChromaDB storage."""
        return {
            "pdf_filename": self.pdf_filename,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "chunk_id": self.chunk_id,
        }


def extract_pages(pdf_path: str) -> list[PageChunk]:
    """
    Extract text from a PDF file, page by page.

    Each page becomes at least one chunk. If a page exceeds CHUNK_MAX_CHARS,
    it is split into sub-chunks with CHUNK_OVERLAP_CHARS overlap.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of PageChunk objects.
    """
    filename = os.path.basename(pdf_path)
    chunks = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"Failed to open PDF '{filename}': {e}")
        return chunks

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")

            if not text or not text.strip():
                continue

            # Clean up text: collapse whitespace, remove non-printable chars
            text = _clean_text(text)

            if not text.strip():
                continue

            # Split into sub-chunks if page is too long
            if len(text) <= config.CHUNK_MAX_CHARS:
                chunks.append(PageChunk(
                    text=text,
                    page_number=page_num + 1,  # 1-based
                    pdf_filename=filename,
                    chunk_index=0,
                    total_chunks=1,
                ))
            else:
                sub_chunks = _split_text(text, config.CHUNK_MAX_CHARS, config.CHUNK_OVERLAP_CHARS)
                for i, sub_text in enumerate(sub_chunks):
                    chunks.append(PageChunk(
                        text=sub_text,
                        page_number=page_num + 1,
                        pdf_filename=filename,
                        chunk_index=i,
                        total_chunks=len(sub_chunks),
                    ))

        logger.info(
            f"Parsed '{filename}': {len(doc)} pages, {len(chunks)} chunks created"
        )
    finally:
        doc.close()

    return chunks


def _clean_text(text: str) -> str:
    """
    Clean extracted PDF text for better embedding quality.

    - Remove non-printable characters
    - Collapse excessive whitespace
    - Remove common PDF artifacts (CID font references, etc.)
    """
    # Remove CID font placeholders like [CID:74]
    text = re.sub(r'\[CID:\d+\]', ' ', text)
    # Remove non-printable characters (keep newlines, tabs, standard whitespace)
    text = re.sub(r'[^\x20-\x7E\n\r\t]', ' ', text)
    # Collapse multiple spaces (but keep newlines for structure)
    text = re.sub(r'[ \t]+', ' ', text)
    # Collapse multiple newlines to max 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    Split text into sub-chunks of max_chars with overlap.

    Tries to split at sentence boundaries (period + space) for better
    embedding quality. Falls back to word boundaries if no sentence
    boundary is found within the chunk.

    Args:
        text: The text to split.
        max_chars: Maximum characters per sub-chunk.
        overlap: Number of characters to overlap between sub-chunks.

    Returns:
        List of text sub-chunks.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to find a sentence boundary near the end
        # Look for ". " within the last 20% of the chunk
        search_start = start + int(max_chars * 0.8)
        search_end = end
        best_split = -1

        # Search for sentence boundary
        for i in range(search_end, search_start, -1):
            if i < len(text) and text[i-1:i+1] == ". ":
                best_split = i + 1
                break

        if best_split == -1:
            # No sentence boundary found — try word boundary
            for i in range(search_end, search_start, -1):
                if i < len(text) and text[i] == ' ':
                    best_split = i + 1
                    break

        if best_split == -1:
            # No good boundary — hard split at max_chars
            best_split = end

        chunk_text = text[start:best_split].strip()
        if chunk_text:
            chunks.append(chunk_text)

        # Move start with overlap
        start = best_split - overlap
        if start <= 0:
            start = best_split  # No overlap if we'd go backwards

    return chunks


def get_pdf_info(pdf_path: str) -> Optional[dict]:
    """
    Get basic info about a PDF file.

    Returns:
        Dict with 'filename', 'num_pages', 'file_size_bytes', or None on error.
    """
    try:
        doc = fitz.open(pdf_path)
        info = {
            "filename": os.path.basename(pdf_path),
            "num_pages": len(doc),
            "file_size_bytes": os.path.getsize(pdf_path),
        }
        doc.close()
        return info
    except Exception as e:
        logger.error(f"Failed to get PDF info for '{pdf_path}': {e}")
        return None
