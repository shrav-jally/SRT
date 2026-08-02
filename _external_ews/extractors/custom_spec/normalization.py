"""Value Normalization Helper — parses and formats raw strings into typed numbers, units, and currencies."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


def normalize_field_value(
    raw_val: Any,
    expected_type: str = "string",
) -> tuple[Any, str | None, str | None]:
    """Normalize raw extracted value into typed value, unit, and currency.

    Returns
    -------
    tuple[Any, str | None, str | None]
        (normalized_val, unit, currency)
    """
    if raw_val is None:
        return None, None, None

    if isinstance(raw_val, (dict, list)):
        return raw_val, None, None

    val_str = str(raw_val).strip()
    if not val_str:
        return None, None, None

    unit = None
    currency = None

    # Detect Currency
    if "rs." in val_str.lower() or "inr" in val_str.lower() or "₹" in val_str:
        currency = "INR"

    # Detect Units
    val_lower = val_str.lower()
    if "crore" in val_lower or "cr" in val_lower:
        unit = "Crore"
    elif "lakh" in val_lower or "lac" in val_lower:
        unit = "Lakh"
    elif "million" in val_lower:
        unit = "Million"
    elif "thousand" in val_lower:
        unit = "Thousand"
    elif "employee" in val_lower or "people" in val_lower:
        unit = "employees"

    if expected_type in ("number", "currency_amount", "count", "integer"):
        # Extract digits, decimals, commas
        digits_match = re.search(r"[-+]?\d[\d,]*\.?\d*", val_str)
        if digits_match:
            clean_digits = digits_match.group(0).replace(",", "")
            try:
                num = float(clean_digits)
                if expected_type in ("count", "integer"):
                    return int(num), unit, currency
                return num, unit, currency
            except ValueError:
                pass

    return val_str, unit, currency
