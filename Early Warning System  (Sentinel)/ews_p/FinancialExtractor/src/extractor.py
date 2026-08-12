from __future__ import annotations

import json
from typing import List

from langchain.chat_models import ChatAnthropic
from langchain.schema import Document, HumanMessage, SystemMessage

from src.config import Config


class FinancialExtractor:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = ChatAnthropic(model=self.config.llm_model, anthropic_api_key=self.config.anthropic_api_key)

    def extract_entities(self, chunks: List[Document]) -> dict:
        context = '\n\n'.join([chunk.page_content for chunk in chunks])
        prompt = self._build_prompt(context)
        response = self.client([SystemMessage(content='You are a JSON extraction engine.'), HumanMessage(content=prompt)])
        raw_text = response.content.strip()
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise ValueError('LLM returned invalid JSON.') from error

    def _build_prompt(self, context: str) -> str:
        return (
            'Extract financial entities from the provided context. '
            'Return ONLY valid JSON. No markdown. No explanation. No extra keys beyond the schema. '
            'Respond with JSON only. Do not wrap output in code fences. '
            'If a value is not present, omit it or set null. '
            '\n\nContext:\n'
            f'{context}\n\n'
            'Required fields: Company Name, Financial Year, Revenue, Gross Profit, Operating Income, EBITDA, Net Income, EPS, Total Assets, Total Liabilities, Cash, Cash Flow, Operating Cash Flow, Investing Cash Flow, Financing Cash Flow, Capital Expenditure, Currency, Country, CEO, Employees, Auditor, Business Segments, Risk Factors, Dividend, Shares Outstanding, Market Capitalization, Notes. '
            'Also extract balance sheet, profit and loss, cashflows, and other financial sections in structured nested JSON where available.'
        )
