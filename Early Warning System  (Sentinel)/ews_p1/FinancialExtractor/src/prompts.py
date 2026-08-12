from __future__ import annotations

from typing import List, Optional


def get_extraction_prompt(
    context: str,
    section_name: Optional[str] = None,
    relevant_fields: Optional[List[str]] = None,
) -> str:
    """Build a strict extraction prompt for financial entity extraction.

    Args:
        context: The source text or document content to analyze.
        section_name: Optional section label such as Balance Sheet or Profit & Loss.
        relevant_fields: Optional list of schema fields to focus on for this section.

    Returns:
        A production-quality prompt instructing the model to extract financial
        fields into valid JSON matching the FinancialEntities schema.
    """
    if relevant_fields:
        field_list = ", ".join(relevant_fields)
    else:
        field_list = (
            "Company Name, Financial Year, Revenue from operations, Other income, Total Income, "
            "Cost of materials consumed, Purchases of Stock-in-Trade, Changes in inventories, "
            "Employee benefits expense, Finance costs, Depreciation and amortisation expense, "
            "Other expenses, Total expenses, Profit before tax, Current tax, Deferred tax, "
            "Profit after tax, EBIT, EBITDA, Total Assets, Total Liabilities, Total Equity, "
            "Cash and cash equivalents, Borrowings, Trade receivables, Trade payables, "
            "Inventories, Property Plant Equipment, Capital work in progress, Investment Property, "
            "Goodwill, Other Intangible Assets, Investments, Loans, Deferred Tax Assets, "
            "Deferred Tax Liabilities, Current Assets, Non Current Assets, Current Liabilities, "
            "Non Current Liabilities, Operating Cash Flow, Investing Cash Flow, Financing Cash Flow, "
            "Contingent Liabilities, Creditors Outstanding More Than One Year, Debtors Outstanding More Than One Year, "
            "Inventory Outstanding More Than 180 Days, Disputed Trade Receivables, Advance From Customers, "
            "Auditors Remuneration, Power and fuel expenses, Significant Impairment, One-time Revenue, "
            "Provision for doubtful debts, Bad Debts, Related Party Investments, Related Party Expenses, "
            "Related Party Revenues, Related Party Loans and Advances, Related Party Bad Debts, "
            "Related Party Loan Liability, Current maturities of borrowings, Risk Factors, Business Segments, "
            "Currency, Country, CEO, Employees, Auditor, Dividend, Shares Outstanding, Market Capitalization, Notes"
        )

    section_instruction = ""
    if section_name:
        section_instruction = f"\nYou are extracting from the {section_name} section of the annual report."

    return f"""You are a precise financial information extraction assistant.{section_instruction}

Task:
Extract the requested financial fields from the provided annual report context and populate the output JSON exactly according to the FinancialEntities schema.

Instructions:
- Extract only information explicitly supported by the provided context.
- Never invent, infer, or hallucinate missing values.
- If a field is not available in the context, return null for that field.
- Focus on numerical values, monetary amounts, and exact labels from the source text.
- Preserve numeric precision and currency wording where present.
- If the source shows both Current Year and Previous Year values for a field, prefer the Current Year value for the main output.
- If both years are present, preserve both values internally in a structured way rather than mixing them together.
- Do not confuse adjacent columns or years; extract the value that belongs to the requested label and year.
- Return ONLY valid JSON.
- Do not wrap the response in markdown code blocks.
- Do not include explanations, comments, notes, or any extra text.
- Ensure the output is valid JSON with double-quoted keys and string values.
- Use null for missing values.
- For balance sheet extraction, prioritize exact label matching from the source text.
- For profit and loss extraction, preserve the exact sign, decimal precision, and units from the source text.
- For cash flow extraction, prefer the consolidated cash flow statement when multiple statements are present.
- For other financial information, search both financial statements and notes, and return null when a value is unavailable.
- If the source contains a line item but no value, return null for that field.
- For financial tables, capture the numeric amount associated with the label.

Relevant fields to populate:
{field_list}

Context:
{context}
"""
