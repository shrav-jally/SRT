from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .config import AppConfig, get_config

logger = logging.getLogger(__name__)

_NUMERIC_KEYWORDS = (
    "revenue",
    "income",
    "expense",
    "expenses",
    "assets",
    "liabilities",
    "equity",
    "cash",
    "borrow",
    "receivable",
    "payable",
    "inventory",
    "investment",
    "loan",
    "flow",
    "capital",
    "tax",
    "maturity",
    "dividend",
    "employee",
    "shares",
    "market",
    "remuneration",
)

_DATE_KEYWORDS = ("year", "date")

_CURRENCY_PATTERN = re.compile(
    r"^\s*(?:[₹$€£]|USD|EUR|GBP|INR|JPY|CAD|AUD)?\s*[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*$",
    re.IGNORECASE,
)

_YEAR_PATTERN = re.compile(r"^(?:FY)?\d{4}(?:[-/]\d{2,4})?$", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}$")


def _normalize_string(value: Any) -> Optional[str]:
    """Convert values to trimmed strings or return None for missing values."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return str(value).strip() or None


def _looks_like_currency(value: str, key: str) -> bool:
    """Return True when a value appears to be a currency-style financial number."""
    lowered_key = key.lower()
    if any(keyword in lowered_key for keyword in _NUMERIC_KEYWORDS):
        return True
    return bool(_CURRENCY_PATTERN.match(value))


def _looks_like_number(value: str, key: str) -> bool:
    """Return True when a value appears to be a numeric field."""
    lowered_key = key.lower()
    if any(keyword in lowered_key for keyword in _NUMERIC_KEYWORDS):
        return True
    return bool(re.fullmatch(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", value))


def _looks_like_date(value: str, key: str) -> bool:
    """Return True when a value appears to be a date or year-like field."""
    lowered_key = key.lower()
    if any(keyword in lowered_key for keyword in _DATE_KEYWORDS):
        return bool(_YEAR_PATTERN.match(value) or _DATE_PATTERN.match(value))
    return False


def parse_numeric_value(value: Any) -> Dict[str, Any]:
    """Parse common financial numeric formats into structured components."""
    raw_value = _normalize_string(value)
    if raw_value is None:
        return {
            "raw_value": None,
            "numeric_value": None,
            "display_value": None,
            "currency": None,
            "unit": None,
        }

    normalized = raw_value.strip()
    currency = None
    unit = None
    sign = 1
    if normalized.startswith("(") and normalized.endswith(")"):
        sign = -1
        normalized = normalized[1:-1].strip()

    currency_symbol_match = re.match(r"^([₹$€£])\s*(.+)$", normalized)
    if currency_symbol_match:
        currency = currency_symbol_match.group(1)
        normalized = currency_symbol_match.group(2).strip()

    if re.search(r"\b(million|billion|trillion)\b", normalized, flags=re.IGNORECASE):
        unit_match = re.search(r"\b(million|billion|trillion)\b", normalized, flags=re.IGNORECASE)
        unit = unit_match.group(1).lower()
        normalized = re.sub(r"\b(million|billion|trillion)\b", "", normalized, flags=re.IGNORECASE).strip()

    cleaned = normalized.replace(",", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    try:
        numeric_value = float(cleaned) * sign
    except ValueError:
        numeric_value = None

    if unit in {"million", "billion", "trillion"} and numeric_value is not None:
        multiplier = {"million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}[unit]
        numeric_value *= multiplier

    if numeric_value is None:
        return {
            "raw_value": raw_value,
            "numeric_value": None,
            "display_value": raw_value,
            "currency": currency,
            "unit": unit,
        }

    display_value = raw_value

    if currency is not None:
        display_value = f"{currency}{numeric_value:,.2f}"
    elif unit is not None:
        display_value = raw_value
    else:
        display_value = f"{numeric_value:,.2f}"
        if display_value.endswith(".00"):
            display_value = display_value[:-3]

    return {
        "raw_value": raw_value,
        "numeric_value": numeric_value,
        "display_value": display_value,
        "currency": currency,
        "unit": unit,
    }


def _extract_multi_year_value(value: Any, key: str) -> tuple[Optional[str], Optional[Dict[str, str]]]:
    """Extract the latest-year value from multi-year disclosures while preserving history."""
    normalized = _normalize_string(value)
    if normalized is None:
        return None, None

    if not isinstance(value, str):
        return normalized, None

    current_match = re.search(r"current\s+year\s*[:\-]?\s*([₹$€£A-Za-z0-9,\.\-]+)", normalized, flags=re.IGNORECASE)
    previous_match = re.search(r"previous\s+year\s*[:\-]?\s*([₹$€£A-Za-z0-9,\.\-]+)", normalized, flags=re.IGNORECASE)
    if current_match and previous_match:
        latest_value = current_match.group(1).strip()
        previous_value = previous_match.group(1).strip()
        if _looks_like_currency(latest_value, key) or _looks_like_number(latest_value, key):
            return latest_value, {"current_year": latest_value, "previous_year": previous_value}

    return normalized, None


def _validate_value(key: str, value: Any) -> Optional[str]:
    """Validate a single field value and return a cleaned value or None."""
    normalized = _normalize_string(value)
    if normalized is None:
        return None

    if normalized.lower() in {"n/a", "na", "none", "null", "not available", "not disclosed"}:
        return None

    if _looks_like_date(normalized, key):
        return normalized

    if _looks_like_currency(normalized, key):
        return normalized

    if _looks_like_number(normalized, key):
        return normalized

    if any(keyword in key.lower() for keyword in _NUMERIC_KEYWORDS):
        return None

    return normalized


def _parse_numeric_value_for_key(value: Any) -> Optional[float]:
    """Parse a field value into a float when possible."""
    parsed = parse_numeric_value(value)
    return parsed.get("numeric_value")


def _add_validation_warning(warnings: list[str], message: str) -> None:
    """Append a warning only once."""
    if message not in warnings:
        warnings.append(message)


def _validate_accounting_relationships(payload: Dict[str, Optional[str]]) -> list[str]:
    """Check core accounting relationships and return warnings for mismatches."""
    warnings: list[str] = []

    def _coerce(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            parsed = parse_numeric_value(value)
            return parsed.get("numeric_value")
        return None

    total_assets = _coerce(payload.get("Total Assets"))
    total_equity = _coerce(payload.get("Total Equity"))
    total_liabilities = _coerce(payload.get("Total Liabilities"))
    if all(value is not None for value in (total_assets, total_equity, total_liabilities)):
        if abs(total_assets - (total_equity + total_liabilities)) > 0.01:
            _add_validation_warning(warnings, "Assets = Equity + Liabilities mismatch")

    current_assets = _coerce(payload.get("Current Assets"))
    non_current_assets = _coerce(payload.get("Non Current Assets"))
    if all(value is not None for value in (current_assets, non_current_assets, total_assets)):
        if abs(total_assets - (current_assets + non_current_assets)) > 0.01:
            _add_validation_warning(warnings, "Current Assets + Non Current Assets mismatch")

    current_liabilities = _coerce(payload.get("Current Liabilities"))
    non_current_liabilities = _coerce(payload.get("Non Current Liabilities"))
    if all(value is not None for value in (current_liabilities, non_current_liabilities, total_liabilities)):
        if abs(total_liabilities - (current_liabilities + non_current_liabilities)) > 0.01:
            _add_validation_warning(warnings, "Current Liabilities + Non Current Liabilities mismatch")

    total_expenses = _coerce(payload.get("Total expenses"))
    cost_materials = _coerce(payload.get("Cost of materials consumed"))
    purchases_stock = _coerce(payload.get("Purchases of Stock-in-Trade"))
    changes_inventories = _coerce(payload.get("Changes in inventories"))
    employee_benefits = _coerce(payload.get("Employee benefits expense"))
    finance_costs = _coerce(payload.get("Finance costs"))
    depreciation = _coerce(payload.get("Depreciation and amortisation expense"))
    other_expenses = _coerce(payload.get("Other expenses"))
    if all(value is not None for value in (total_expenses, cost_materials, purchases_stock, changes_inventories, employee_benefits, finance_costs, depreciation, other_expenses)):
        expected_total_expenses = cost_materials + purchases_stock + changes_inventories + employee_benefits + finance_costs + depreciation + other_expenses
        if abs(total_expenses - expected_total_expenses) > 0.01:
            _add_validation_warning(warnings, "Total Expenses calculation mismatch")

    profit_before_tax = _coerce(payload.get("Profit before tax"))
    profit_after_tax = _coerce(payload.get("Profit after tax"))
    current_tax = _coerce(payload.get("Current tax"))
    deferred_tax = _coerce(payload.get("Deferred tax"))
    if all(value is not None for value in (profit_before_tax, profit_after_tax, current_tax, deferred_tax)):
        if abs(profit_after_tax - (profit_before_tax - current_tax - deferred_tax)) > 0.01:
            _add_validation_warning(warnings, "Profit After Tax mismatch")

    operating_cash_flow = _coerce(payload.get("Operating Cash Flow"))
    investing_cash_flow = _coerce(payload.get("Investing Cash Flow"))
    financing_cash_flow = _coerce(payload.get("Financing Cash Flow"))
    net_increase = _coerce(payload.get("Net Increase in Cash"))
    if all(value is not None for value in (operating_cash_flow, investing_cash_flow, financing_cash_flow, net_increase)):
        if abs(net_increase - (operating_cash_flow + investing_cash_flow + financing_cash_flow)) > 0.01:
            _add_validation_warning(warnings, "Cash Flow consistency mismatch")

    return warnings


def _remove_duplicates(payload: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Null out duplicate values encountered across different fields."""
    seen: set[str] = set()
    cleaned: Dict[str, Optional[str]] = {}

    for key, value in payload.items():
        if value is None:
            cleaned[key] = None
            continue

        normalized_value = value.strip().lower()
        if normalized_value in seen:
            cleaned[key] = None
            logger.warning("Duplicate value detected for field %s; setting to null", key)
        else:
            seen.add(normalized_value)
            cleaned[key] = value

    return cleaned


def validate_entities(
    entities_path: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    config: Optional[AppConfig] = None,
) -> Dict[str, Optional[str]]:
    """Validate, clean, and persist financial entity extraction results.

    Args:
        entities_path: Path to the input JSON file containing extracted entities.
        output_path: Path to write the cleaned validated JSON file.
        config: Optional application configuration override.

    Returns:
        A cleaned dictionary of financial entities with invalid values replaced by None.
    """
    app_config = config or get_config()

    input_path = Path(entities_path) if entities_path else app_config.output_folder / "entities.json"
    target_path = Path(output_path) if output_path else app_config.output_folder / "validated_entities.json"

    if not input_path.exists():
        raise FileNotFoundError(f"Input entities file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Input entities payload must be a JSON object")

    cleaned_payload: Dict[str, Optional[str]] = {}
    for key, value in payload.items():
        cleaned_value = _validate_value(key, value)
        cleaned_payload[key] = cleaned_value

        parsed = parse_numeric_value(value)
        if parsed["numeric_value"] is not None:
            cleaned_payload[f"{key}__parsed"] = json.dumps(parsed)

    for key, value in list(cleaned_payload.items()):
        latest_value, history = _extract_multi_year_value(value, key)
        if latest_value is not None:
            cleaned_payload[key] = latest_value
            if history is not None:
                cleaned_payload[f"{key}__history"] = json.dumps(history)

    cleaned_payload = _remove_duplicates(cleaned_payload)

    validation_warnings = _validate_accounting_relationships(cleaned_payload)
    if validation_warnings:
        cleaned_payload["validation_warnings"] = json.dumps(validation_warnings)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(cleaned_payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    logger.info("Validated entities written to %s", target_path)
    return cleaned_payload
