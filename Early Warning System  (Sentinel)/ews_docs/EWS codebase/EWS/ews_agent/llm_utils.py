"""
LLM Utilities Module

Common utilities for LLM interactions across the pipeline:
    - Structured output parsing (JSON from LLM responses)
    - Retry logic with exponential backoff
    - Prompt construction helpers
    - Response validation

All LLM calls in the EWS agent go through this module to ensure
consistent error handling, retry behavior, and output parsing.
"""

import json
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# RETRY LOGIC
# ============================================================================


def llm_call_with_retry(
    llm,
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> Optional[str]:
    """
    Call the LLM with retry logic and exponential backoff.
    
    Args:
        llm: LangChain ChatOpenAI instance.
        prompt: The prompt string to send.
        max_retries: Maximum number of retry attempts.
        retry_delay: Initial delay between retries (seconds).
        backoff_factor: Multiplier for delay after each retry.
    
    Returns:
        LLM response text, or None if all retries fail.
    """
    from langchain_core.messages import HumanMessage
    
    for attempt in range(max_retries):
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            if text:
                return text
        except Exception as e:
            logger.warning(
                f"LLM call attempt {attempt + 1}/{max_retries} failed: {e}"
            )
            if attempt < max_retries - 1:
                delay = retry_delay * (backoff_factor ** attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries} LLM call attempts failed")
    
    return None


# ============================================================================
# STRUCTURED OUTPUT PARSING
# ============================================================================


def extract_json_from_response(response_text: str) -> Optional[Any]:
    """
    Extract JSON from an LLM response that may contain markdown code blocks
    or other formatting around the JSON.
    
    Handles:
        - Pure JSON response
        - JSON wrapped in ```json ... ``` code blocks
        - JSON wrapped in ``` ... ``` code blocks
        - JSON with leading/trailing text
    
    Args:
        response_text: Raw LLM response text.
    
    Returns:
        Parsed JSON object (dict or list), or None if parsing fails.
    """
    if not response_text:
        return None
    
    text = response_text.strip()
    
    # Try 1: Direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try 2: Extract from markdown code block
    # Match ```json ... ``` or ``` ... ``` patterns
    code_block_patterns = [
        r'```json\s*\n?(.*?)\n?\s*```',
        r'```\s*\n?(.*?)\n?\s*```',
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
    
    # Try 3: Find JSON object or array in the text
    # Look for outermost { ... } or [ ... ]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        
        # Find matching closing bracket
        depth = 0
        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    json_str = text[start_idx:i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break
    
    # Try 4: Fix common JSON issues (trailing commas, single quotes)
    # Replace single quotes with double quotes (common LLM mistake)
    fixed = text.replace("'", '"')
    # Remove trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    logger.warning(f"Could not extract JSON from LLM response: {text[:200]}...")
    return None


def extract_key_value_pairs(response_text: str) -> dict[str, str]:
    """
    Extract key-value pairs from an LLM response in non-JSON formats.
    
    Handles formats like:
        - KEY: value
        - KEY = value
        - KEY -> value
        - | KEY | value |
    
    Args:
        response_text: Raw LLM response text.
    
    Returns:
        Dict of key-value pairs.
    """
    result = {}
    
    for line in response_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Try different separators
        for sep in [':', '=', '->']:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    key = parts[0].strip().strip('|').strip()
                    value = parts[1].strip().strip('|').strip()
                    if key and value:
                        result[key] = value
                    break
    
    return result


# ============================================================================
# PROMPT CONSTRUCTION HELPERS
# ============================================================================


def build_table_summary(
    table,
    max_rows: int = 10,
    max_cell_len: int = 50,
) -> str:
    """
    Build a concise text summary of an extracted table for LLM prompts.
    
    Truncates long cells and limits row count to keep prompts compact.
    
    Args:
        table: ExtractedTable object.
        max_rows: Maximum number of data rows to include.
        max_cell_len: Maximum length of each cell value.
    
    Returns:
        Formatted table summary string.
    """
    lines = []
    
    # Headers
    if table.headers:
        header_str = " | ".join(
            str(h)[:max_cell_len] for h in table.headers
        )
        lines.append(f"Headers: {header_str}")
    
    # Rows
    for i, row in enumerate(table.rows[:max_rows]):
        row_str = " | ".join(
            str(cell)[:max_cell_len] for cell in row
        )
        lines.append(f"Row {i+1}: {row_str}")
    
    if len(table.rows) > max_rows:
        lines.append(f"... ({len(table.rows) - max_rows} more rows)")
    
    # Page context (truncated)
    if table.page_text:
        # Get first 200 chars of page text for context
        page_context = table.page_text[:200].replace('\n', ' ')
        lines.append(f"Page context: {page_context}...")
    
    return "\n".join(lines)


def build_template_items_list(
    template: dict,
    indent: str = "  ",
) -> str:
    """
    Build a formatted list of template items for LLM prompts.
    
    Args:
        template: Template dict (e.g., BALANCE_SHEET_TEMPLATE).
        indent: Indentation prefix for sub-items.
    
    Returns:
        Formatted string listing all template items with sections.
    """
    lines = []
    item_num = 0
    
    for key, value in template.items():
        if isinstance(value, dict) and value is not None:
            lines.append(f"SECTION: {key}")
            for sub_key in value.keys():
                item_num += 1
                lines.append(f"{indent}{item_num}. {sub_key}")
        else:
            item_num += 1
            lines.append(f"{item_num}. {key}")
    
    return "\n".join(lines)


# ============================================================================
# RESPONSE VALIDATION
# ============================================================================


def validate_classification_response(
    response: dict,
    valid_types: list[str] = None,
) -> Optional[str]:
    """
    Validate an LLM classification response.
    
    Args:
        response: Parsed JSON response from LLM.
        valid_types: List of valid table type strings.
    
    Returns:
        Validated table type string, or None if invalid.
    """
    if valid_types is None:
        valid_types = ["balance_sheet", "profit_and_loss", "cash_flow", "other"]
    
    if not isinstance(response, dict):
        return None
    
    table_type = response.get("type") or response.get("table_type") or response.get("classification")
    if not table_type:
        return None
    
    table_type = str(table_type).lower().strip()
    
    # Normalize common variations
    type_map = {
        "balance_sheet": "balance_sheet",
        "balancesheet": "balance_sheet",
        "balance sheet": "balance_sheet",
        "bs": "balance_sheet",
        "profit_and_loss": "profit_and_loss",
        "profitandloss": "profit_and_loss",
        "profit and loss": "profit_and_loss",
        "p&l": "profit_and_loss",
        "pl": "profit_and_loss",
        "income_statement": "profit_and_loss",
        "cash_flow": "cash_flow",
        "cashflow": "cash_flow",
        "cash flow": "cash_flow",
        "cf": "cash_flow",
        "other": "other",
        "notes": "other",
        "schedule": "other",
    }
    
    return type_map.get(table_type)


def validate_mapping_response(
    response: dict,
    template_items: list[str],
) -> list[dict]:
    """
    Validate an LLM mapping response.
    
    Expected response format:
    {
        "mappings": [
            {"template_item": "...", "value": "...", "row_label": "...", "confidence": 0.9},
            ...
        ]
    }
    
    Or a simpler format:
    {
        "Template Item Name": "value",
        ...
    }
    
    Args:
        response: Parsed JSON response from LLM.
        template_items: List of valid template item names.
    
    Returns:
        List of validated mapping dicts with keys:
        template_item, value, row_label, confidence
    """
    mappings = []
    
    if not isinstance(response, dict):
        return mappings
    
    # Handle "mappings" key format
    if "mappings" in response:
        raw_mappings = response["mappings"]
        if isinstance(raw_mappings, list):
            for m in raw_mappings:
                if not isinstance(m, dict):
                    continue
                item = m.get("template_item", "")
                value = m.get("value", "")
                row_label = m.get("row_label", "")
                confidence = m.get("confidence", 0.7)
                
                if item and value:
                    mappings.append({
                        "template_item": item,
                        "value": str(value),
                        "row_label": str(row_label),
                        "confidence": float(confidence),
                    })
    
    # Handle simple key-value format
    else:
        for key, value in response.items():
            # Skip metadata keys
            if key.lower() in ("type", "table_type", "notes", "explanation"):
                continue
            if isinstance(value, (str, int, float)) and value:
                mappings.append({
                    "template_item": key,
                    "value": str(value),
                    "row_label": "",
                    "confidence": 0.7,
                })
    
    return mappings
