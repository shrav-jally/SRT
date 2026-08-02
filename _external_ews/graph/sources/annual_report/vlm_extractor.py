"""VLM-powered financial statement extraction from page images.

Uses the Qwen3-VL-8B-Instruct Vision Language Model to extract structured
financial data from rendered PDF page images.  The VLM reads balance sheets,
profit & loss, cash flow statements, and notes to accounts directly from
images and returns JSON that is mapped into the same dict format consumed
by ``excel_builder.py``.

Pipeline
--------
1. Run the existing word-position-clustering extractor to *identify* which
   pages contain which financial statements (page numbers only) **and** to
   extract Notes to Accounts (which are text-heavy and well-suited to the
   existing method).
2. Render those pages as PNG images via PyMuPDF (fitz).
3. For each statement, send page images to the VLM **one page at a time**
   (to avoid 504 Gateway Timeout on the on-prem server) with carefully
   crafted prompts that request structured JSON output.
4. Merge rows from per-page VLM responses into a single statement.
5. Parse and validate the VLM response, then normalise into the
   ``extraction_result`` dict format.
6. Add Notes to Accounts from the word-clustering extractor (which works
   well for text-based notes) and optionally re-extract via VLM for
   image-based / scanned pages.
7. Optionally build the Excel workbook via ``excel_builder.build_excel()``.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ===================================================================
# VLM client helpers
# ===================================================================

def _get_vlm_client(temperature: float = 0.0, max_tokens: int = 8192,
                     request_timeout: int = 300):
    """Get a LangChain ChatOpenAI instance configured for the VLM.

    The direct HTTP adapter in ``llm_config`` handles the multimodal endpoint
    and batch-compatible route, while LangChain remains available for other
    text-based LLM workflows.
    """
    from .llm_config import get_llm
    return get_llm(temperature=temperature, max_tokens=max_tokens,
                   request_timeout=request_timeout)


def _encode_image_base64(img_bytes: bytes, content_type: str = "image/png") -> str:
    """Encode raw image bytes to a base64 data-URI string."""
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{content_type};base64,{b64}"


def _call_vlm_with_images(
    prompt: str,
    images: list[bytes],
    system_prompt: str | None = None,
    json_schema: dict | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    request_timeout: int = 300,
) -> str | None:
    """Send images + prompt to the VLM and return the raw text response.

    Parameters
    ----------
    prompt : str
        The text prompt instructing the VLM what to extract.
    images : list[bytes]
        List of raw PNG image bytes (one per page).
    max_tokens : int
        Maximum tokens for the VLM response.
    temperature : float
        Sampling temperature.
    request_timeout : int
        Timeout in seconds (default 300 for on-prem server).

    Returns
    -------
    str | None
        The VLM response text, or None on failure.
    """
    try:
        from .llm_config import invoke_vlm_chat_completion

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        for img_bytes in images:
            if img_bytes[:2] == b'\xff\xd8':
                content_type = "image/jpeg"
            else:
                content_type = "image/png"
            data_uri = _encode_image_base64(img_bytes, content_type=content_type)
            content.append({
                "type": "image_url",
                "image_url": {"url": data_uri},
            })

        messages.append({"role": "user", "content": content})
        return invoke_vlm_chat_completion(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            request_timeout=request_timeout,
            use_batch=True,
        )

    except Exception as exc:
        logger.error(f"VLM call failed: {exc}")
        return None


def _is_504_response(text: str | None) -> bool:
    """Check if a VLM response is actually a 504 Gateway Timeout HTML page."""
    if not text:
        return False
    lower = text[:500].lower()
    # Must contain HTML tag AND a gateway/timeout indicator to avoid
    # false positives on legitimate financial data that mentions "504"
    has_html = "<html>" in lower or "<body>" in lower or "<h1>" in lower
    has_gateway = "504" in lower or "gateway" in lower or "time-out" in lower or "timeout" in lower
    return has_html and has_gateway


# ===================================================================
# JSON parsing from VLM response
# ===================================================================

def _extract_json_from_response(text: str) -> dict | list | None:
    """Extract JSON from a VLM response that may contain markdown fences.

    Handles:
    - Pure JSON response
    - JSON wrapped in ```json ... ``` fences
    - JSON embedded within prose (looks for first ``{`` / ``[`` to last ``}`` / ``]``)
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    m = fence_pattern.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding outermost JSON object or array
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Try repairing common issues (trailing commas)
                repaired = _repair_trailing_commas(candidate)
                if repaired:
                    try:
                        return json.loads(repaired)
                    except json.JSONDecodeError:
                        pass

    # Try repairing truncated JSON cut off at max_tokens limit
    repaired_truncated = _repair_truncated_json(text)
    if repaired_truncated is not None:
        logger.info("Successfully recovered truncated VLM JSON response!")
        return repaired_truncated

    logger.warning("Could not extract JSON from VLM response")
    return None


def _repair_trailing_commas(text: str) -> str | None:
    """Remove trailing commas before } or ] in JSON text."""
    try:
        return re.sub(r",\s*([}\]])", r"\1", text)
    except Exception:
        return None


def _repair_truncated_json(text: str) -> dict | list | None:
    """Repair JSON strings truncated mid-stream by token limit cutoff."""
    if not text:
        return None

    clean_text = text.strip()
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[-1]
    if "```" in clean_text:
        clean_text = clean_text.split("```")[0]

    clean_text = clean_text.strip()
    start_pos = clean_text.find("{")
    if start_pos == -1:
        start_pos = clean_text.find("[")
    if start_pos == -1:
        return None

    clean_text = clean_text[start_pos:]

    # Truncate at last complete closing brace '}'
    last_brace = clean_text.rfind("}")
    if last_brace != -1:
        truncated_part = clean_text[:last_brace + 1]

        open_braces = truncated_part.count("{") - truncated_part.count("}")
        open_brackets = truncated_part.count("[") - truncated_part.count("]")

        repaired = truncated_part + ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            repaired_commas = _repair_trailing_commas(repaired)
            if repaired_commas:
                try:
                    return json.loads(repaired_commas)
                except json.JSONDecodeError:
                    pass

    return None


# ===================================================================
# Prompt templates
# ===================================================================

_BALANCE_SHEET_PROMPT = """\
You are a expert financial data extractor. Carefully read the attached image(s) of a **Balance Sheet** from an Indian company's annual report and extract ALL line items into structured JSON.

## Output Format

Return a JSON object with exactly this structure:

```json
{{
  "title": "The full title text from the document",
  "currency": "The currency unit shown (e.g. 'Rs. in lakhs', 'Rs. in crores', '₹ in millions')",
  "periods": ["Current period end date", "Previous period end date"],
  "column_headers": ["Note No.", "Current period column header", "Previous period column header"],
  "rows": [
    {{
      "section": "ASSETS > Non-Current Assets",
      "line_item": "Property, plant & equipment",
      "note_no": "2",
      "current_period": 6527.97,
      "previous_period": 6643.50
    }}
  ]
}}
```

## Rules

1. **Section hierarchy**: Use " > " to separate section levels. Typical Balance Sheet sections:
   - ASSETS > Non-Current Assets
   - ASSETS > Current Assets
   - EQUITY AND LIABILITIES > Shareholders' Funds
   - EQUITY AND LIABILITIES > Non-Current Liabilities
   - EQUITY AND LIABILITIES > Current Liabilities
   - Use the EXACT section names visible in the image.

2. **line_item**: The exact name of each line item as shown. Include sub-headings (e.g. "Property, plant & equipment" as a parent row with null values, then its sub-items).

3. **note_no**: The note reference number shown next to the line item. Use empty string "" if none.

4. **current_period / previous_period**: Numeric values as floats. Use `null` for:
   - Section heading rows (no numeric value)
   - Dashes (—) indicating zero or not applicable
   - Brackets indicate negative values: (1,234) → -1234.0

5. **Number parsing**: Remove commas from Indian-style numbers before converting:
   - "1,59,690.91" → 159690.91
   - "36,25,599.26" → 3625599.26
   - Do NOT multiply or divide — use the raw numeric value shown.

6. **Completeness**: Extract EVERY row visible in the image, including:
   - Sub-total rows (e.g. "Total Non-Current Assets")
   - Grand total rows (e.g. "TOTAL")
   - Header rows for sections that have no amount themselves

7. **Multi-page**: If multiple pages are provided, combine ALL rows from all pages into a single list, maintaining the order they appear.

8. Return ONLY the JSON object — no additional commentary.
"""

_PROFIT_AND_LOSS_PROMPT = """\
You are an expert financial data extractor. Carefully read the attached image(s) of a **Statement of Profit and Loss** from an Indian company's annual report and extract ALL line items into structured JSON.

## Output Format

Return a JSON object with exactly this structure:

```json
{{
  "title": "The full title text from the document",
  "currency": "The currency unit shown (e.g. 'Rs. in lakhs', '₹ in crores')",
  "periods": ["Current period", "Previous period"],
  "column_headers": ["Note No.", "Current period column header", "Previous period column header"],
  "rows": [
    {{
      "section": "I. Revenue from operations",
      "line_item": "Sale of products",
      "note_no": "14",
      "current_period": 1000000.50,
      "previous_period": 950000.25
    }}
  ]
}}
```

## Rules

1. **Section hierarchy**: Use " > " for sub-sections. Typical P&L sections:
   - I. Revenue from operations
   - II. Other income
   - III. Total Revenue (I + II)
   - IV. Expenses (with sub-sections for each expense type)
   - V. Profit before exceptional items and tax
   - VI. Exceptional items
   - VII. Profit before tax
   - VIII. Tax expense
   - IX. Profit/(Loss) for the period from continuing operations
   - X. Profit/(Loss) from discontinuing operations
   - XI. Tax expense of discontinuing operations
   - XII. Profit/(Loss) for the period
   - Other Comprehensive Income section
   - Total Comprehensive Income
   Use the EXACT section numbering/names from the image.

2. **line_item**: The exact name of each line item.

3. **note_no**: The note reference number. Empty string "" if none.

4. **current_period / previous_period**: Numeric floats. `null` for heading rows, dashes, or rows with no value. Brackets = negative.

5. **Number parsing**: Remove Indian comma formatting: "1,59,690.91" → 159690.91. Use raw values — do NOT scale.

6. **Completeness**: Extract EVERY row including sub-totals and totals.

7. **Multi-page**: Combine rows from all pages maintaining order.

8. Return ONLY the JSON object.
"""

_CASH_FLOW_PROMPT = """\
You are an expert financial data extractor. Carefully read the attached image(s) of a **Cash Flow Statement** from an Indian company's annual report and extract ALL line items into structured JSON.

## Output Format

Return a JSON object with exactly this structure:

```json
{{
  "title": "The full title text from the document",
  "currency": "The currency unit shown (e.g. 'Rs. in lakhs')",
  "periods": ["Current period", "Previous period"],
  "column_headers": ["Note No.", "Current period column header", "Previous period column header"],
  "rows": [
    {{
      "section": "A. Cash flow from operating activities",
      "line_item": "Net profit before tax",
      "note_no": "",
      "current_period": 500000.0,
      "previous_period": 450000.0
    }}
  ]
}}
```

## Rules

1. **Section hierarchy**: Typical Cash Flow sections:
   - A. Cash flow from operating activities > Direct/Indirect method
   - B. Cash flow from investing activities
   - C. Cash flow from financing activities
   - Net increase/(decrease) in cash and cash equivalents
   - Opening balance
   - Closing balance
   Use the EXACT section labels from the image.

2. **line_item**: Exact name of each line item.

3. **note_no**: Note reference number, or "" if none.

4. **current_period / previous_period**: Numeric floats. `null` for heading rows. Brackets = negative (cash outflows).

5. **Number parsing**: Remove Indian comma formatting. Use raw values.

6. **Completeness**: Extract EVERY row including sub-totals and totals.

7. **Multi-page**: Combine all pages.

8. Return ONLY the JSON object.
"""

_NOTES_PROMPT = """\
You are an expert financial data extractor. Carefully read the attached image of a **Notes to Accounts** page from an Indian company's annual report and extract ALL tabular data into structured JSON.

## Output Format

Return a JSON object with exactly this structure:

```json
{{
  "notes": [
    {{
      "note_no": "2",
      "title": "Property, Plant and Equipment",
      "rows": [
        ["Description", "Gross carrying amount", "Accumulated depreciation", "Net carrying amount"],
        ["Land", "1000.00", "0.00", "1000.00"],
        ["Buildings", "5000.00", "2000.00", "3000.00"]
      ]
    }}
  ]
}}
```

## Rules

1. **note_no**: The note number shown at the top of the section (e.g. "2", "10A").

2. **title**: The full title/heading of the note section.

3. **rows**: A list of lists. The first sub-list is the table header row. Subsequent sub-lists are data rows. All values should be strings.

4. **Multiple notes per page**: If the page contains more than one note, include each as a separate entry in the "notes" array.

5. **Number formatting**: Keep numbers as shown in the image (with commas, brackets, etc.) — do NOT convert to floats.

6. **Non-table content**: If a note contains only narrative text (no table), include it with a single-row table:
   ```json
   {{
     "note_no": "15",
     "title": "Contingent Liabilities",
     "rows": [["Details"], ["The narrative text content of the note..."]]
   }}
   ```

7. **Completeness**: Extract EVERY note and EVERY row visible on the page.

8. Return ONLY the JSON object.
"""

_STATEMENT_PROMPTS = {
    "balance_sheet": _BALANCE_SHEET_PROMPT,
    "profit_and_loss": _PROFIT_AND_LOSS_PROMPT,
    "cash_flow": _CASH_FLOW_PROMPT,
    "notes_to_accounts": _NOTES_PROMPT,
}

_GENERIC_TABLE_PROMPT = """\
You are an expert financial data extractor. Carefully read the attached image(s) of a table from an annual report.
The table is categorized as: **{table_name}**.

Extract ALL data from the table into structured JSON.

## Output Format
Return a JSON object with exactly this structure:
```json
{{
  "title": "The exact title of the table shown",
  "column_headers": ["Header 1", "Header 2", "..."],
  "rows": [
    ["Row 1 Col 1", "Row 1 Col 2", "..."],
    ["Row 2 Col 1", "Row 2 Col 2", "..."]
  ]
}}
```

## Rules
1. **Title**: The title of the table or section.
2. **column_headers**: Extract all column headers exactly as they appear.
3. **rows**: Extract all rows as arrays of strings. Ensure the number of elements in each row matches the number of column_headers. Use null or empty string for blank cells.
4. If there are merged cells or hierarchical sections, repeat the label or place it in the first column as appropriate.

Output ONLY valid JSON.
"""

# ===================================================================
# Amount parsing helpers
# ===================================================================

def _parse_indian_amount(text: str | None) -> float | None:
    """Parse an Indian-format amount string to float.

    Handles: "1,59,690.91", "(1,234.56)", "—", "-", "", None
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    if not isinstance(text, str):
        return None

    text = text.strip()
    if text in ("", "—", "–", "-", "Nil", "nil", "N.A.", "N/A"):
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
        text = text[1:]

    # Remove commas and spaces
    text = text.replace(",", "").replace(" ", "").strip()

    try:
        val = float(text)
        return -val if negative else val
    except (ValueError, TypeError):
        return None


def _normalise_rows(rows: list[dict]) -> list[dict]:
    """Normalise VLM-extracted rows into the standard format.

    VLM may return rows with 'current_period' / 'previous_period' as strings,
    or with 'values' dict.  Normalise everything to the canonical format::

        {
            "section": "ASSETS > Non-Current Assets",
            "line_item": "Property, plant & equipment",
            "note_no": "2",
            "values": {"current_period": 6527.97, "previous_period": 6643.50}
        }
    """
    normalised = []
    for row in rows:
        # Extract section
        section = row.get("section", "") or ""

        # Extract line_item
        line_item = row.get("line_item", "") or row.get("particulars", "") or row.get("description", "")

        # Extract note_no
        note_no = str(row.get("note_no", "") or row.get("note", "") or "").strip()

        # Extract current_period and previous_period
        # VLM may return them at top level or inside a 'values' dict
        if "values" in row and isinstance(row["values"], dict):
            cp = row["values"].get("current_period")
            pp = row["values"].get("previous_period")
        else:
            cp = row.get("current_period")
            pp = row.get("previous_period")

        # Parse amounts
        cp_val = _parse_indian_amount(cp)
        pp_val = _parse_indian_amount(pp)

        normalised.append({
            "section": section,
            "line_item": line_item.strip(),
            "note_no": note_no,
            "values": {
                "current_period": cp_val,
                "previous_period": pp_val,
            },
        })

    return normalised

def extract_generic_table(
    pdf_path: str | Path,
    table_name: str,
    page_numbers: list[int],
    dpi: int = 150,
    progress_callback=None,
    use_mock: bool = False,
) -> dict[str, Any] | None:
    """Extract an arbitrary table via VLM."""
    import fitz  # type: ignore[import-not-found]
    
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
            
    if use_mock:
        return {
            "title": table_name,
            "column_headers": ["Particulars", "Amount"],
            "rows": [["Item 1", "100.00"], ["Item 2", "200.00"]]
        }
        
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None
        
    images: list[bytes] = []
    try:
        doc = fitz.open(pdf_path)
        for p_num in page_numbers:
            if 1 <= p_num <= len(doc):
                page = doc[p_num - 1]
                pix = page.get_pixmap(dpi=dpi)
                images.append(pix.tobytes("png"))
        doc.close()
    except Exception as exc:
        _log(f"Error rendering pages {page_numbers} for {table_name}: {exc}")
        return None
        
    if not images:
        return None
        
    prompt = _GENERIC_TABLE_PROMPT.format(table_name=table_name)
    _log(f"Running VLM extraction for {table_name} on {len(images)} pages...")
    
    response = _call_vlm_with_images(prompt, images)
    if _is_504_response(response):
        _log("VLM returned 504 Gateway Timeout.")
        return None
        
    parsed = _extract_json_from_response(response or "")
    if isinstance(parsed, dict):
        return parsed
    return None

# ===================================================================
# Main Extractor Entry Pointpeline
# ===================================================================

def render_page_images(
    pdf_path: Path,
    page_numbers: list[int],
    dpi: int = 150,
    max_pixels: int = 1500,
    format: str = "jpeg",
    quality: int = 80,
) -> list[bytes]:
    """Render specific PDF pages as compressed image bytes.

    Uses JPEG format by default for much smaller file sizes compared to PNG.
    Images are resized if they exceed ``max_pixels`` on their longest side.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file.
    page_numbers : list[int]
        1-based page numbers to render.
    dpi : int
        Resolution for rendering (default 150, reduced from 200 to avoid 504 timeouts).
    max_pixels : int
        Maximum dimension (width or height) in pixels. Images larger than this
        are downscaled to fit. Default 1500.
    format : str
        Output format: ``"jpeg"`` (default) or ``"png"``.
    quality : int
        JPEG quality (1-100, default 80). Ignored for PNG.

    Returns
    -------
    list[bytes]
        List of image bytes (JPEG or PNG), one per page.
    """
    import fitz  # PyMuPDF
    from PIL import Image
    import io as _io

    images = []
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    for pg_num in page_numbers:
        if pg_num < 1 or pg_num > total_pages:
            logger.warning(f"Page {pg_num} out of range (1-{total_pages}), skipping")
            continue
        page = doc[pg_num - 1]  # 0-based index

        # Render at specified DPI
        pix = page.get_pixmap(dpi=dpi)

        # Convert to PIL Image for reliable resize and format conversion
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Downscale if image exceeds max_pixels on any dimension
        if max(img.size) > max_pixels:
            scale = max_pixels / max(img.size)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info(f"  Resized page {pg_num} from {pix.width}x{pix.height} to {new_size[0]}x{new_size[1]}")

        # Save to bytes
        buf = _io.BytesIO()
        if format == "jpeg":
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buf, format="PNG", optimize=True)
        img_bytes = buf.getvalue()

        images.append(img_bytes)
        logger.info(f"Rendered page {pg_num} ({len(img_bytes):,} bytes, {format}, {img.width}x{img.height})")

    doc.close()
    return images


def vlm_extract_statement(
    statement_type: str,
    images: list[bytes],
    entity: str = "standalone",
    max_retries: int = 5,
    per_page: bool = True,
) -> dict[str, Any] | None:
    """Extract a single financial statement from page images using the VLM.

    Parameters
    ----------
    statement_type : str
        One of "balance_sheet", "profit_and_loss", "cash_flow".
    images : list[bytes]
        PNG image bytes for the statement pages.
    entity : str
        "standalone" or "consolidated" (used for logging / fallback prompt).
    max_retries : int
        Number of retry attempts on VLM failure (default 5).
    per_page : bool
        If True, send each page image separately to the VLM and merge the
        results.  This avoids 504 Gateway Timeout from the on-prem server
        when multiple large images are sent at once (default True).

    Returns
    -------
    dict | None
        Statement dict with keys: title, currency, periods, column_headers,
        rows (normalised), or None on failure.
    """
    prompt = _STATEMENT_PROMPTS.get(statement_type)
    if not prompt:
        logger.error(f"Unknown statement type: {statement_type}")
        return None

    if not images:
        logger.warning(f"No images provided for {entity}_{statement_type}")
        return None

    logger.info(
        f"VLM extracting {entity}_{statement_type} from {len(images)} page image(s) "
        f"(per_page={per_page})..."
    )

    if per_page and len(images) > 1:
        # ── Per-page extraction: send one image at a time ──────────
        return _vlm_extract_statement_per_page(
            statement_type=statement_type,
            images=images,
            entity=entity,
            max_retries=max_retries,
        )

    # ── Single-call extraction (1 image or per_page=False) ─────────
    return _vlm_extract_statement_single(
        statement_type=statement_type,
        images=images,
        entity=entity,
        max_retries=max_retries,
    )


def _vlm_extract_statement_single(
    statement_type: str,
    images: list[bytes],
    entity: str,
    max_retries: int,
) -> dict[str, Any] | None:
    """Extract a statement by sending ALL images in one VLM call."""
    prompt = _STATEMENT_PROMPTS[statement_type]

    parsed_dict = _call_vlm_with_retry(
        prompt=prompt,
        images=images,
        entity=entity,
        stmt_key=statement_type,
        max_retries=max_retries,
    )

    if not parsed_dict:
        return None

    return _parse_statement_response(parsed_dict, statement_type, entity)


def _vlm_extract_statement_per_page(
    statement_type: str,
    images: list[bytes],
    entity: str,
    max_retries: int,
) -> dict[str, Any] | None:
    """Extract a statement by sending one page at a time and merging rows.

    This avoids 504 Gateway Timeout when the on-prem VLM server cannot
    process multiple large images within its timeout window.
    """
    prompt = _STATEMENT_PROMPTS[statement_type]

    # Add continuation instruction for pages 2+
    continuation_suffix = (

        "\n\n**IMPORTANT**: This is ONE page of a multi-page statement. "
        "Extract ALL rows visible on THIS page. Do NOT repeat rows from "
        "previous pages. Return ONLY the JSON object."
    )

    all_rows: list[dict] = []
    metadata: dict[str, Any] = {}

    for page_idx, page_image in enumerate(images):
        page_num = page_idx + 1
        logger.info(f"  Processing page {page_num}/{len(images)}...")

        # For the first page, use the full prompt; for subsequent pages,
        # add a continuation instruction
        if page_idx == 0:
            page_prompt = prompt
        else:
            page_prompt = prompt + continuation_suffix

        parsed = _call_vlm_with_retry(
            prompt=page_prompt,
            images=[page_image],  # single image only
            entity=entity,
            stmt_key=f"{statement_type}_page{page_num}",
            max_retries=max_retries,
        )

        if not parsed:
            logger.warning(f"  Page {page_num} extraction failed, skipping")
            continue

        # Collect metadata from first successful page
        if not metadata:
            metadata = {
                "title": parsed.get("title", ""),
                "currency": parsed.get("currency", ""),
                "periods": parsed.get("periods", []),
                "column_headers": parsed.get("column_headers", ["Note No.", "Current Period", "Previous Period"]),
            }

        # Collect rows
        page_rows = parsed.get("rows", [])
        if page_rows:
            all_rows.extend(page_rows)
            logger.info(f"  Page {page_num}: extracted {len(page_rows)} rows")
        else:
            logger.warning(f"  Page {page_num}: no rows found")

        # Pause between page calls
        if page_idx < len(images) - 1:
            time.sleep(5)

    if not all_rows:
        logger.error(f"No rows extracted for {entity}_{statement_type} from any page")
        return None

    # Normalise rows
    normalised_rows = _normalise_rows(all_rows)
    logger.info(f"  Total merged rows for {entity}_{statement_type}: {len(normalised_rows)}")

    # Build statement dict
    statement = {
        "statement": f"{entity}_{statement_type}",
        **metadata,
        "extraction_method": "vlm_qwen3_vl_per_page",
        "rows": normalised_rows,
    }

    return statement


def _call_vlm_with_retry(
    prompt: str,
    images: list[bytes],
    entity: str,
    stmt_key: str,
    max_retries: int = 5,
) -> dict[str, Any] | None:
    """Call the VLM with robust retry logic for 504 timeouts and malformed JSON.

    Uses progressive backoff: 10s, 20s, 30s, 45s, 60s.
    """
    for attempt in range(1, max_retries + 1):
        logger.info(f"  Attempt {attempt}/{max_retries} for {entity}_{stmt_key}...")

        response_text = _call_vlm_with_images(
            prompt=prompt,
            images=images,
            max_tokens=4096,
            temperature=0.0,
            request_timeout=300,  # 5 minutes per call
        )

        if response_text:
            # Check if response is a 504 gateway timeout HTML page
            if _is_504_response(response_text):
                logger.warning(f"  VLM returned 504 gateway timeout page, retrying...")
                backoff = min(10 * attempt + 5 * (attempt - 1), 90)
                logger.info(f"  Waiting {backoff}s before retry...")
                time.sleep(backoff)
                continue
                
            # Attempt JSON extraction immediately so we can retry on failure
            parsed = _extract_json_from_response(response_text)
            if parsed and isinstance(parsed, dict):
                logger.info(f"  VLM response length: {len(response_text)} chars")
                return parsed
            else:
                logger.error(f"  Could not parse VLM response as JSON on attempt {attempt}")
                logger.error(f"  Raw response snippet: {response_text[:500]}")
                # Treat malformed JSON as a failure and retry
                backoff = 10
                logger.info(f"  Waiting {backoff}s before retry...")
                time.sleep(backoff)
                continue

        logger.warning(f"  VLM returned no response, retrying...")
        backoff = min(10 * attempt + 5 * (attempt - 1), 90)
        logger.info(f"  Waiting {backoff}s before retry...")
        time.sleep(backoff)

    logger.error(f"VLM extraction failed for {entity}_{stmt_key} after {max_retries} attempts")
    return None


def _parse_statement_response(
    parsed: dict[str, Any],
    statement_type: str,
    entity: str,
) -> dict[str, Any] | None:
    """Parse a VLM response into a statement dict."""
    # Normalise rows
    raw_rows = parsed.get("rows", [])
    if not raw_rows:
        logger.warning(f"VLM returned no rows for {entity}_{statement_type}")
        return None

    normalised_rows = _normalise_rows(raw_rows)
    logger.info(f"  Extracted {len(normalised_rows)} rows from VLM response")

    # Build the statement dict in the format expected by excel_builder
    statement = {
        "statement": f"{entity}_{statement_type}",
        "title": parsed.get("title", ""),
        "currency": parsed.get("currency", ""),
        "periods": parsed.get("periods", []),
        "column_headers": parsed.get("column_headers", ["Note No.", "Current Period", "Previous Period"]),
        "extraction_method": "vlm_qwen3_vl",
        "rows": normalised_rows,
    }

    return statement


# ===================================================================
# Notes to Accounts extraction
# ===================================================================

def vlm_extract_notes(
    images: list[bytes],
    entity: str = "standalone",
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Extract Notes to Accounts from page images using the VLM.

    Parameters
    ----------
    images : list[bytes]
        PNG image bytes for the notes pages.
    entity : str
        "standalone" or "consolidated".
    max_retries : int
        Retry attempts per page.

    Returns
    -------
    list[dict]
        List of note entries: [{"note_no": ..., "title": ..., "rows": [[...], ...]}]
    """
    if not images:
        logger.warning(f"No images provided for {entity} notes")
        return []

    logger.info(f"VLM extracting {entity} notes from {len(images)} page image(s)...")

    all_notes: list[dict[str, Any]] = []
    seen_note_nos: set[str] = set()

    for page_idx, page_image in enumerate(images):
        page_num = page_idx + 1
        logger.info(f"  Processing notes page {page_num}/{len(images)}...")

        parsed = _call_vlm_with_retry(
            prompt=_NOTES_PROMPT,
            images=[page_image],
            entity=entity,
            stmt_key=f"notes_page{page_num}",
            max_retries=max_retries,
        )

        if not parsed:
            logger.warning(f"  Notes page {page_num} extraction failed, skipping")
            continue

        page_notes = parsed.get("notes", [])
        if not page_notes:
            # Maybe the VLM returned a single note (not wrapped in a list)
            if "note_no" in parsed:
                page_notes = [parsed]

        for note in page_notes:
            if not isinstance(note, dict):
                continue
            note_no = str(note.get("note_no", "")).strip()
            # Deduplicate notes (same note appearing on consecutive pages)
            if note_no and note_no in seen_note_nos:
                continue
            if note_no:
                seen_note_nos.add(note_no)

            title = note.get("title", "")
            rows = note.get("rows", [])

            # Validate rows: must be list of lists
            if rows and isinstance(rows, list):
                valid_rows = []
                for r in rows:
                    if isinstance(r, list):
                        valid_rows.append([str(c) if c is not None else "" for c in r])
                    elif isinstance(r, dict):
                        # VLM sometimes returns rows as dicts; convert to list
                        valid_rows.append([str(v) if v is not None else "" for v in r.values()])
                    else:
                        valid_rows.append([str(r)])
                all_notes.append({
                    "note_no": note_no,
                    "title": title,
                    "rows": valid_rows,
                })

        logger.info(f"  Notes page {page_num}: extracted {len(page_notes)} note(s)")

        # Pause between page calls
        if page_idx < len(images) - 1:
            time.sleep(5)

    logger.info(f"  Total {entity} notes extracted: {len(all_notes)}")
    return all_notes


# ===================================================================
# Full pipeline
# ===================================================================

def vlm_extract_all(
    pdf_path: Path,
    dpi: int = 150,
    page_hints: dict[str, list[int]] | None = None,
    method: str = "word_position_clustering",
    progress_callback=None,
) -> dict[str, Any]:
    """Full VLM extraction pipeline: identify pages → render → VLM extract → build result.

    Parameters
    ----------
    pdf_path : Path
        Path to the annual report PDF.
    dpi : int
        Image resolution for rendering (default 200).
    page_hints : dict, optional
        Page hints from TOC parser.
    method : str
        Method for initial page identification (default word_position_clustering).
    progress_callback : callable, optional
        Callback for progress updates.

    Returns
    -------
    dict
        Extraction result dict compatible with ``excel_builder.build_excel()``.
        Includes: metadata, standalone, consolidated (each with balance_sheet,
        profit_and_loss, cash_flow, notes_to_accounts).
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[VLM] Starting VLM extraction for: {pdf_path.name}")

    # ── Step 1: Parse PDF metadata ──────────────────────────────────
    _log("[VLM] Step 1/5: Parsing PDF metadata...")
    try:
        import fitz
        with fitz.open(str(pdf_path)) as doc:
            parsed = {"metadata": {"source_file": str(pdf_path), "page_count": len(doc)}}
    except Exception as exc:
        logger.warning(f"PDF parsing failed: {exc}, using minimal metadata")
        parsed = {"metadata": {"source_file": str(pdf_path), "page_count": 0}}

    metadata = parsed.get("metadata", {})
    metadata["extraction_method"] = "vlm_qwen3_vl"
    metadata["extraction_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # ── Step 2: Identify statement pages ────────────────────────────
    # PRIMARY: New multi-stage discovery pipeline (bookmarks, TOC,
    # heading detection, confidence scoring, sequence validation).
    # FALLBACK: Legacy word-position-clustering if discovery fails.
    _log("[VLM] Step 2/5: Identifying financial statement pages (discovery pipeline)...")

    _STMT_KEYS = ("balance_sheet", "profit_and_loss", "cash_flow")
    pages_map: dict[str, dict[str, list[int]]] = {
        "standalone": {},
        "consolidated": {},
    }
    page_result = {}  # kept for notes extraction fallback later

    discovery_used = False
    try:
        from .discovery.pipeline import run_discovery

        discovery_result = run_discovery(
            pdf_path,
            page_hints=page_hints,
            progress_callback=progress_callback,
        )

        # Convert DiscoveryResult into pages_map
        discovery_hints = discovery_result.to_page_hints()
        if discovery_hints:
            for entity in ("standalone", "consolidated"):
                for stmt_key in _STMT_KEYS:
                    flat_key = f"{entity}_{stmt_key}"
                    hint_pages = discovery_hints.get(flat_key, [])
                    if hint_pages:
                        pages_map[entity][stmt_key] = hint_pages
            discovery_used = True
            _log(f"[VLM] Discovery pipeline found pages: "
                 f"{ {e: {s: p for s, p in stmts.items()} for e, stmts in pages_map.items()} }")
        else:
            _log("[VLM] Discovery pipeline returned no pages — falling back to legacy extractor")
    except Exception as exc:
        logger.warning(f"Discovery pipeline failed: {exc} — falling back to legacy extractor")

    # FALLBACK: Legacy word-position-clustering removed (table_extractor deleted)
    if not discovery_used or not any(pages_map[e] for e in pages_map):
        _log("[VLM] No pages found via discovery, and legacy extraction is removed.")
        return {
            "metadata": metadata,
            "standalone": {},
            "consolidated": {},
        }

    _log(f"[VLM] Final pages: { {e: {s: p for s, p in stmts.items()} for e, stmts in pages_map.items()} }")

    # ── Step 3: Render page images and extract via VLM ──────────────
    _log("[VLM] Step 3/5: Rendering pages and extracting statements with VLM...")

    result: dict[str, Any] = {
        "metadata": metadata,
        "standalone": {},
        "consolidated": {},
    }

    for entity in ("standalone", "consolidated"):
        entity_pages = pages_map[entity]
        if not entity_pages:
            continue

        _log(f"[VLM] Processing {entity} statements...")

        for stmt_key in _STMT_KEYS:
            page_nums = entity_pages.get(stmt_key, [])
            if not page_nums:
                continue

            _log(f"[VLM]   Rendering {stmt_key} pages {page_nums}...")
            try:
                images = render_page_images(pdf_path, page_nums, dpi=dpi)
            except Exception as exc:
                logger.error(f"Failed to render pages for {entity}_{stmt_key}: {exc}")
                continue

            if not images:
                logger.warning(f"No images rendered for {entity}_{stmt_key}")
                continue

            _log(f"[VLM]   Calling VLM for {entity}_{stmt_key} ({len(images)} image(s))...")
            try:
                stmt_data = vlm_extract_statement(
                    statement_type=stmt_key,
                    images=images,
                    entity=entity,
                    max_retries=5,
                    per_page=True,  # Always use per-page to avoid 504
                )
            except Exception as exc:
                logger.error(f"VLM extraction failed for {entity}_{stmt_key}: {exc}")
                stmt_data = None

            if stmt_data:
                # Add page info from the initial extractor
                stmt_data["page"] = page_nums[0] if page_nums else None
                stmt_data["pages"] = page_nums
                result[entity][stmt_key] = stmt_data
                _log(f"[VLM]   [+] {entity}_{stmt_key}: {len(stmt_data.get('rows', []))} rows extracted")
            else:
                # Fallback: use word-clustering result if VLM failed
                flat_key = f"{entity}_{stmt_key}"
                _log(f"[VLM]   [-] {entity}_{stmt_key}: VLM extraction returned no data.")

            # Pause between VLM calls to avoid overloading the on-prem server
            time.sleep(5)

    # ── Step 4: Extract Notes to Accounts ───────────────────────────
    _log("[VLM] Step 4/5: Extracting Notes to Accounts...")
    _log("[VLM]   Legacy notes extraction removed; returning empty notes.")
    result["standalone"]["notes_to_accounts"] = []
    result["consolidated"]["notes_to_accounts"] = []

    # ── Step 5: Post-processing and validation ──────────────────────
    _log("[VLM] Step 5/5: Post-processing and validation...")

    # Add validation summary for each statement
    for entity in ("standalone", "consolidated"):
        entity_data = result.get(entity, {})
        for stmt_key in _STMT_KEYS:
            stmt = entity_data.get(stmt_key, {})
            if not stmt:
                continue
            rows = stmt.get("rows", [])
            total_rows = len(rows)
            rows_with_values = sum(
                1 for r in rows
                if r.get("values", {}).get("current_period") is not None
                or r.get("values", {}).get("previous_period") is not None
            )
            stmt["validation"] = {
                "total_rows": total_rows,
                "rows_with_values": rows_with_values,
                "extraction_method": stmt.get("extraction_method", "vlm_qwen3_vl"),
            }

    # Summary log
    for entity in ("standalone", "consolidated"):
        entity_data = result.get(entity, {})
        for stmt_key in _STMT_KEYS:
            stmt = entity_data.get(stmt_key, {})
            if stmt:
                _log(f"[VLM] {entity}_{stmt_key}: {len(stmt.get('rows', []))} rows, "
                     f"currency={stmt.get('currency', 'N/A')}")
        notes = entity_data.get("notes_to_accounts", [])
        if notes:
            _log(f"[VLM] {entity}_notes: {len(notes)} notes")

    _log("[VLM] Extraction complete!")
    return result


def vlm_extract_to_excel(
    pdf_path: Path,
    dpi: int = 200,
    page_hints: dict[str, list[int]] | None = None,
    method: str = "word_position_clustering",
    progress_callback=None,
) -> bytes:
    """Run the full VLM pipeline and return Excel workbook bytes.

    Convenience wrapper that calls :func:`vlm_extract_all` then
    :func:`excel_builder.build_excel`.
    """
    from .excel_builder import build_excel

    result = vlm_extract_all(
        pdf_path=pdf_path,
        dpi=dpi,
        page_hints=page_hints,
        method=method,
        progress_callback=progress_callback,
    )
    return build_excel(result)
