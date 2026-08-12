from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pdfplumber


def preprocess_pdf_text(text: str) -> str:
    """Clean extracted PDF text to reduce noise before chunking and LLM prompting."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not text.strip():
        return ""

    lines = [line.rstrip() for line in text.splitlines()]
    cleaned_lines: List[str] = []
    seen_lines: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r"^page\s+\d+(?:\s+of\s+\d+)?$", stripped, flags=re.IGNORECASE):
            continue
        if re.match(r"^\d+\s+of\s+\d+$", stripped):
            continue
        if re.fullmatch(r"annual report(?:\s+\d{4})?", stripped, flags=re.IGNORECASE):
            continue
        if re.fullmatch(r"company name", stripped, flags=re.IGNORECASE):
            continue

        normalized_line = re.sub(r"\s+", " ", stripped)
        if normalized_line.lower() in {"page 1", "page 2", "page 3", "page 4", "page 5"}:
            continue
        if normalized_line in seen_lines:
            continue

        seen_lines.add(normalized_line)
        cleaned_lines.append(normalized_line)

    if not cleaned_lines:
        return text.strip()

    merged_lines: List[str] = []
    for line in cleaned_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue

        prev_line = merged_lines[-1]
        if re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", prev_line) and re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", line):
            merged_lines[-1] = f"{prev_line} | {line}"
            continue

        if not re.search(r"[.!?]$", prev_line) and not re.search(r"^\d", line) and not re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", line):
            merged_lines[-1] = f"{prev_line} {line}"
            continue

        merged_lines.append(line)

    return "\n".join(merged_lines).strip()


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    text_chunks: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_chunks.append(f"Page {page_number}\n{page_text}")

    extracted_text = "\n\n".join(text_chunks).strip()
    extracted_text = preprocess_pdf_text(extracted_text)
    if not extracted_text:
        raise ValueError(f"No text could be extracted from PDF: {path}")

    return extracted_text
