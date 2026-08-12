from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.config import Config
from src.utils import save_json


class FinancialEntityModel(BaseModel):
    Company_Name: str | None = Field(None, alias='Company Name')
    Financial_Year: str | None = Field(None, alias='Financial Year')
    Revenue: str | None = None
    Gross_Profit: str | None = Field(None, alias='Gross Profit')
    Operating_Income: str | None = Field(None, alias='Operating Income')
    EBITDA: str | None = None
    Net_Income: str | None = Field(None, alias='Net Income')
    EPS: str | None = None
    Total_Assets: str | None = Field(None, alias='Total Assets')
    Total_Liabilities: str | None = Field(None, alias='Total Liabilities')
    Cash: str | None = None
    Cash_Flow: str | None = Field(None, alias='Cash Flow')
    Operating_Cash_Flow: str | None = Field(None, alias='Operating Cash Flow')
    Investing_Cash_Flow: str | None = Field(None, alias='Investing Cash Flow')
    Financing_Cash_Flow: str | None = Field(None, alias='Financing Cash Flow')
    Capital_Expenditure: str | None = Field(None, alias='Capital Expenditure')
    Currency: str | None = None
    Country: str | None = None
    CEO: str | None = None
    Employees: str | None = None
    Auditor: str | None = None
    Business_Segments: str | None = Field(None, alias='Business Segments')
    Risk_Factors: str | None = Field(None, alias='Risk Factors')
    Dividend: str | None = None
    Shares_Outstanding: str | None = Field(None, alias='Shares Outstanding')
    Market_Capitalization: str | None = Field(None, alias='Market Capitalization')
    Notes: str | None = None


class JsonValidator:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            text = re.sub(r'[\u200b\u200c\u200d]', '', text)
            return text or None
        return value

    def validate(self, data: dict) -> dict:
        normalized = {k: self._normalize_value(v) for k, v in data.items()}
        try:
            validated = FinancialEntityModel.model_validate(normalized)
        except ValidationError as error:
            raise ValueError(f'Validation failed: {error}')

        result = validated.model_dump(by_alias=True, exclude_none=True)
        save_json(self.config.validated_json, result)
        return result
