from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from .config import AppConfig, get_config
from .models import FinancialEntities
from .prompts import get_extraction_prompt

SECTION_FIELDS = {
    "Balance Sheet": [
        "Non-current assets",
        "Property Plant and Equipment",
        "Capital work-in-progress",
        "Investment Property",
        "Goodwill",
        "Other Intangible Assets",
        "Intangible Assets Under Development",
        "Biological Assets",
        "Financial Assets",
        "Investments",
        "Trade Receivables",
        "Loans",
        "Deferred Tax Assets",
        "Other Non Current Assets",
        "Total Non Current Assets",
        "Total Fixed Assets",
        "Current Assets",
        "Inventories",
        "Current Investments",
        "Trade Receivables",
        "Cash and Cash Equivalents",
        "Bank Balances",
        "Loans",
        "Other Financial Assets",
        "Current Tax Assets",
        "Other Current Assets",
        "Total Current Assets",
        "Total Assets",
        "Equity Share Capital",
        "Other Equity",
        "Total Equity",
        "Profit for the Year",
        "Change in FCTR",
        "NCI Share of Loss",
        "Non Current Liabilities",
        "Borrowings",
        "Trade Payables",
        "Other Financial Liabilities",
        "Provisions",
        "Deferred Tax Liabilities",
        "Other Non Current Liabilities",
        "Total Non Current Liabilities",
        "Current Liabilities",
        "Borrowings",
        "Trade Payables",
        "Other Financial Liabilities",
        "Other Current Liabilities",
        "Current Provisions",
        "Current Tax Liabilities",
        "Total Current Liabilities",
        "Total Liabilities",
        "Total Equity and Liabilities",
        "Total Debt",
    ],
    "Profit & Loss": [
        "Revenue from Operations",
        "Other Income",
        "Total Income",
        "Current Tax",
        "Deferred Tax",
        "Tax Expense",
        "Profit for the Year",
        "Profit After Tax",
        "Profit Before Tax",
        "Profit Before Exceptional Items",
        "Exceptional Items",
        "Cost of Materials Consumed",
        "Purchases",
        "Inventory Changes",
        "Employee Benefits",
        "Finance Costs",
        "Depreciation",
        "Other Expenses",
        "Total Expenses",
        "EBITDA",
        "EBIT",
    ],
    "Cash Flow": [
        "Cash Flow from Operating Activities",
        "Cash Flow from Investing Activities",
        "Cash Flow from Financing Activities",
        "Net Increase in Cash",
        "Closing Cash Balance",
        "Opening Cash Balance",
    ],
    "Other Financial Information": [
        "Contingent Liabilities",
        "Creditors Outstanding More Than One Year",
        "Debtors Outstanding More Than One Year",
        "Inventory Outstanding More Than 180 Days",
        "Disputed Trade Receivables",
        "Advance From Customers",
        "Auditors Remuneration",
        "Power and fuel expenses",
        "Significant Impairment",
        "One-time Revenue",
        "Provision for doubtful debts",
        "Bad Debts",
        "Related Party Investments",
        "Related Party Expenses",
        "Related Party Revenues",
        "Related Party Loans and Advances",
        "Related Party Bad Debts",
        "Related Party Loan Liability",
        "Current maturities of borrowings",
        "Risk Factors",
        "Business Segments",
        "Currency",
        "Country",
        "CEO",
        "Employees",
        "Auditor",
        "Dividend",
        "Shares Outstanding",
        "Market Capitalization",
        "Notes",
        "Company Name",
        "Financial Year",
    ],
}

logger = logging.getLogger(__name__)


def _response_to_text(response: Any) -> str:
    """Extract plain text from a model response object."""
    if isinstance(response, str):
        return response

    if isinstance(response, dict):
        for key in ("content", "text", "output_text", "message"):
            value = response.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "".join(str(item) for item in value)

    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item) for item in content)

    if hasattr(response, "text"):
        return str(response.text)

    return str(response)


def _clean_json_payload(text: str) -> str:
    """Strip markdown fences and surrounding whitespace from JSON text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return cleaned.strip()


def _build_empty_result_payload() -> Dict[str, Optional[str]]:
    """Return a schema-shaped payload with all aliases initialized to None."""
    return {
        (field.alias or field_name): None
        for field_name, field in FinancialEntities.model_fields.items()
    }


def _build_llm_client(config: AppConfig, llm_client: Optional[Any] = None) -> Any:
    """Create or return a configured LLM client."""
    if llm_client is not None:
        return llm_client

    provider = config.llm_provider.lower()

    if provider == "groq":
        try:
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(
                model=config.llm_model,
                api_key=config.llm_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
            logger.info(
                "LLM initialization success: provider=%s, model=%s",
                config.llm_provider,
                config.llm_model,
            )
            return client
        except ImportError as exc:
            raise RuntimeError(
                "Install langchain-openai to use the 'groq' provider: pip install langchain-openai"
            ) from exc
        except Exception as exc:
            logger.error(
                "LLM initialization failure: provider=%s, model=%s, error=%s",
                config.llm_provider,
                config.llm_model,
                exc,
            )
            raise RuntimeError(
                f"Failed to initialize LLM client for provider '{config.llm_provider}' "
                f"with model '{config.llm_model}': {exc}"
            ) from exc

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(model=config.llm_model, api_key=config.llm_api_key)
            logger.info(
                "LLM initialization success: provider=%s, model=%s",
                config.llm_provider,
                config.llm_model,
            )
            return client
        except ImportError as exc:
            raise RuntimeError(
                "Install langchain-openai to use the 'openai' provider: pip install langchain-openai"
            ) from exc
        except Exception as exc:
            logger.error(
                "LLM initialization failure: provider=%s, model=%s, error=%s",
                config.llm_provider,
                config.llm_model,
                exc,
            )
            raise RuntimeError(
                f"Failed to initialize LLM client for provider '{config.llm_provider}' "
                f"with model '{config.llm_model}': {exc}"
            ) from exc

    if provider == "ollama":
        try:
            from langchain_community.chat_models import ChatOllama

            client = ChatOllama(model=config.llm_model)
            logger.info(
                "LLM initialization success: provider=%s, model=%s",
                config.llm_provider,
                config.llm_model,
            )
            return client
        except ImportError as exc:
            raise RuntimeError(
                "Install langchain-community to use the 'ollama' provider: pip install langchain-community"
            ) from exc
        except Exception as exc:
            logger.error(
                "LLM initialization failure: provider=%s, model=%s, error=%s",
                config.llm_provider,
                config.llm_model,
                exc,
            )
            raise RuntimeError(
                f"Failed to initialize LLM client for provider '{config.llm_provider}' "
                f"with model '{config.llm_model}': {exc}"
            ) from exc

    raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")


def _should_replace(existing: Optional[str], candidate: Optional[str]) -> bool:
    """Return True when a candidate value is more complete than the existing one."""
    if existing is None:
        return candidate is not None

    if candidate is None:
        return False

    existing_text = str(existing).strip()
    candidate_text = str(candidate).strip()
    if not existing_text:
        return bool(candidate_text)
    if not candidate_text:
        return False

    return len(candidate_text) > len(existing_text)


def _merge_results(existing: Dict[str, Optional[str]], incoming: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Merge two dictionaries without overwriting complete values unnecessarily."""
    merged = dict(existing)
    for key, value in incoming.items():
        if _should_replace(merged.get(key), value):
            merged[key] = value
    return merged


def _classify_chunk(chunk: str) -> str:
    """Classify a chunk into the most relevant report section using heading detection and keywords."""
    cleaned_chunk = re.sub(r"\s+", " ", chunk).strip()
    lowered = cleaned_chunk.lower()

    heading_candidates = [
        line.strip().lower()
        for line in cleaned_chunk.splitlines()
        if line.strip()
    ]

    for heading in heading_candidates[:6]:
        normalized_heading = re.sub(r"\s+", " ", heading)
        if normalized_heading in {
            "balance sheet",
            "statement of financial position",
            "consolidated balance sheet",
            "standalone balance sheet",
        }:
            return "Balance Sheet"
        if normalized_heading in {
            "statement of profit and loss",
            "profit and loss",
            "profit & loss",
            "income statement",
            "statement of comprehensive income",
            "statement of profit and loss account",
        }:
            return "Profit & Loss"
        if normalized_heading in {
            "cash flow statement",
            "cash flow",
            "cash flows",
        }:
            return "Cash Flow"
        if normalized_heading in {
            "notes",
            "notes to financial statements",
            "notes to accounts",
        }:
            return "Other Financial Information"
        if normalized_heading in {
            "schedules",
            "schedule",
        }:
            return "Other Financial Information"
        if normalized_heading in {
            "corporate information",
            "company information",
        }:
            return "Other Financial Information"

    if any(keyword in lowered for keyword in ["statement of financial position", "consolidated balance sheet", "standalone balance sheet", "balance sheet", "assets", "liabilities", "equity", "property plant", "ppe", "trade receivables", "trade payables"]):
        return "Balance Sheet"
    if any(keyword in lowered for keyword in ["statement of profit and loss", "profit and loss", "profit & loss", "income statement", "statement of comprehensive income", "revenue", "ebitda", "ebit", "expense", "expenses", "tax", "profit before tax", "profit after tax"]):
        return "Profit & Loss"
    if any(keyword in lowered for keyword in ["cash flow statement", "cash flow", "cash flows", "operating cash", "investing cash", "financing cash"]):
        return "Cash Flow"
    if any(keyword in lowered for keyword in ["notes to financial statements", "notes to accounts", "notes", "contingent", "auditors remuneration", "risk factors", "business segments", "dividend"]):
        return "Other Financial Information"
    if any(keyword in lowered for keyword in ["schedules", "schedule"]):
        return "Other Financial Information"
    if any(keyword in lowered for keyword in ["company", "ceo", "auditor", "employee", "shares outstanding", "market capitalization", "corporate information", "country", "currency"]):
        return "Other Financial Information"
    return "Other Financial Information"


def _is_table_like(chunk: str) -> bool:
    """Return True when a chunk appears to contain tabular or multi-column content."""
    cleaned = re.sub(r"\s+", " ", chunk).strip()
    if not cleaned:
        return False
    if "|" in cleaned or "\t" in cleaned:
        return True
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if len(lines) < 2:
        return False

    numeric_lines = sum(1 for line in lines if re.search(r"\b\d[\d,\.\-]*\b", line))
    if numeric_lines >= 2:
        return True
    return False


def _select_relevant_chunks(chunk_items: List[Dict[str, Any]], section_name: str) -> List[str]:
    """Select section-relevant chunks and include adjacent context for table-like spans."""
    relevant_indices: List[int] = []
    note_keywords = [
        "contingent", "creditors", "debtors", "inventory", "disputed", "advance from customers",
        "auditors remuneration", "power and fuel", "significant impairment", "one-time revenue",
        "doubtful debts", "bad debts", "related party", "borrowings", "impairment",
    ]

    for index, item in enumerate(chunk_items):
        text = str(item.get("text", ""))
        if item.get("section") == section_name:
            relevant_indices.append(index)
        elif section_name == "Other Financial Information" and any(keyword in text.lower() for keyword in note_keywords):
            relevant_indices.append(index)

    if not relevant_indices:
        return []

    selected_indices: set[int] = set()
    for index in relevant_indices:
        selected_indices.add(index)
        if _is_table_like(chunk_items[index]["text"]):
            for neighbor in (index - 1, index + 1):
                if 0 <= neighbor < len(chunk_items):
                    selected_indices.add(neighbor)

    ordered_chunks: List[str] = []
    seen_texts: set[str] = set()
    for index in sorted(selected_indices):
        text = chunk_items[index]["text"].strip()
        if not text:
            continue
        signature = text.lower()
        if signature in seen_texts:
            continue
        seen_texts.add(signature)
        ordered_chunks.append(text)

    return ordered_chunks


def _is_missing_value(value: Optional[str]) -> bool:
    """Return True when a value is absent or blank."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _get_note_chunks(chunk_items: List[Dict[str, Any]]) -> List[str]:
    """Return note-like chunks that are classified as other financial information."""
    note_keywords = [
        "contingent", "creditors", "debtors", "inventory", "disputed", "advance from customers",
        "auditors remuneration", "power and fuel", "significant impairment", "one-time revenue",
        "doubtful debts", "bad debts", "related party", "borrowings", "impairment", "notes",
    ]
    collected: List[str] = []
    for item in chunk_items:
        text = str(item.get("text", ""))
        if item.get("section") != "Other Financial Information":
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in note_keywords):
            collected.append(text.strip())
    return collected


def _extract_missing_fields_from_notes(
    section_name: str,
    section_result: Dict[str, Optional[str]],
    note_chunks: List[str],
    client: Any,
    max_retries: int,
) -> Dict[str, Optional[str]]:
    """Fill only missing note-relevant fields from note chunks without overwriting existing values."""
    if section_name in {"Other Financial Information"} or not note_chunks:
        return {}

    note_field_keywords = {
        "Contingent Liabilities": ["contingent", "liabilities"],
        "Creditors Outstanding More Than One Year": ["creditors", "one year"],
        "Debtors Outstanding More Than One Year": ["debtors", "one year"],
        "Inventory Outstanding More Than 180 Days": ["inventory", "180 days"],
        "Disputed Trade Receivables": ["disputed", "trade receivables"],
        "Advance From Customers": ["advance from customers", "advance"],
        "Auditors Remuneration": ["auditors remuneration", "auditor"],
        "Power and fuel expenses": ["power and fuel", "fuel"],
        "Significant Impairment": ["significant impairment", "impairment"],
        "One-time Revenue": ["one-time revenue", "one time revenue"],
        "Provision for doubtful debts": ["provision", "doubtful debts"],
        "Bad Debts": ["bad debts", "bad debt"],
        "Related Party Investments": ["related party", "investments"],
        "Related Party Expenses": ["related party", "expenses"],
        "Related Party Revenues": ["related party", "revenues"],
        "Related Party Loans and Advances": ["related party", "loans and advances"],
        "Related Party Bad Debts": ["related party", "bad debts"],
        "Related Party Loan Liability": ["related party", "loan liability"],
        "Current maturities of borrowings": ["borrowings", "maturity"],
    }

    note_context = "\n\n".join(note_chunks)
    note_context_lower = note_context.lower()
    extracted_values: Dict[str, Optional[str]] = {}

    for alias in note_field_keywords:
        if not _is_missing_value(section_result.get(alias)):
            continue
        if not any(keyword in note_context_lower for keyword in note_field_keywords[alias]):
            continue

        prompt = get_extraction_prompt(
            context=note_context,
            section_name="Notes",
            relevant_fields=[alias],
        )

        for attempt in range(1, max_retries + 1):
            try:
                response = client.invoke(prompt)
                response_text = _response_to_text(response)
                cleaned_text = _clean_json_payload(response_text)
                parsed_payload = json.loads(cleaned_text)
                model_result = FinancialEntities.model_validate(parsed_payload)
                extracted = model_result.model_dump(by_alias=True)
                value = extracted.get(alias)
                if not _is_missing_value(value):
                    extracted_values[alias] = value
                    break
            except Exception as exc:  # pragma: no cover - defensive runtime handling
                logger.warning("Notes fallback for field %s attempt %d failed: %s", alias, attempt, exc)
                if attempt == max_retries:
                    break

    return extracted_values


def _process_section(
    section_name: str,
    chunk_items: List[Dict[str, Any]],
    client: Any,
    max_retries: int,
) -> Dict[str, Optional[str]]:
    """Process a grouped set of chunks for a specific report section."""
    relevant_chunks = _select_relevant_chunks(chunk_items, section_name)
    if not relevant_chunks:
        logger.info("No relevant chunks for section: %s", section_name)
        return {}

    logger.info("Section %s using %d relevant chunks", section_name, len(relevant_chunks))
    section_text = "\n\n".join(relevant_chunks)
    prompt = get_extraction_prompt(
        context=section_text,
        section_name=section_name,
        relevant_fields=SECTION_FIELDS.get(section_name, []),
    )

    section_result = _build_empty_result_payload()

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Sending prompt to LLM for section %s (attempt %d/%d)",
                section_name,
                attempt,
                max_retries,
            )
            response = client.invoke(prompt)
            response_text = _response_to_text(response)
            cleaned_text = _clean_json_payload(response_text)
            parsed_payload = json.loads(cleaned_text)
            model_result = FinancialEntities.model_validate(parsed_payload)
            section_result = model_result.model_dump(by_alias=True)
            logger.info("Processed section %s successfully", section_name)
            break
        except Exception as exc:  # pragma: no cover - defensive runtime handling
            logger.warning("Section %s attempt %d failed: %s", section_name, attempt, exc)
            if attempt == max_retries:
                logger.error("Section %s failed after %d attempts", section_name, max_retries)
                section_result = {
                    (field.alias or field_name): None
                    for field_name, field in FinancialEntities.model_fields.items()
                }

    return section_result


def extract_financial_entities(
    chunks: List[str],
    llm_client: Optional[Any] = None,
    output_path: Optional[Path] = None,
    max_retries: int = 3,
    config: Optional[AppConfig] = None,
) -> Dict[str, Optional[str]]:
    """Extract financial entities from text chunks, merge results, and save them to disk.

    Args:
        chunks: The text chunks to process.
        llm_client: Optional preconfigured LLM client.
        output_path: Destination JSON file for the merged output.
        max_retries: Number of retries for malformed or invalid responses.
        config: Optional app configuration override.

    Returns:
        A merged dictionary of extracted financial fields using the schema keys.
    """
    if not isinstance(chunks, list):
        raise TypeError("chunks must be provided as a list of strings")

    if not chunks:
        raise ValueError("chunks must not be empty")

    app_config = config or get_config()
    client = _build_llm_client(app_config, llm_client=llm_client)

    merged = _build_empty_result_payload()

    normalized_chunks: List[Dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, str) or not chunk.strip():
            logger.warning("Skipping empty chunk at position %d", index)
            continue
        section_name = _classify_chunk(chunk)
        normalized_chunks.append({"text": chunk, "section": section_name})
        logger.debug("Chunk %d classified as %s", index, section_name)

    for section_name in ["Balance Sheet", "Profit & Loss", "Cash Flow", "Other Financial Information"]:
        section_result = _process_section(section_name, normalized_chunks, client, max_retries)
        if section_name in {"Balance Sheet", "Profit & Loss", "Cash Flow"}:
            note_chunks = _get_note_chunks(normalized_chunks)
            if note_chunks:
                note_fallback = _extract_missing_fields_from_notes(
                    section_name,
                    section_result,
                    note_chunks,
                    client,
                    max_retries,
                )
                for key, value in note_fallback.items():
                    if _is_missing_value(section_result.get(key)):
                        section_result[key] = value
        merged = _merge_results(merged, section_result)

    target_path = output_path or (app_config.output_folder / "entities.json")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    logger.info("Saved merged extraction output to %s", target_path)
    return merged
