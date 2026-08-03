import json
import uuid

# 1. Financial Metrics Spec
msme_fields = [
    ("company_name", "string", ["company name", "name of the company", "legal name"]),
    ("cin", "string", ["cin", "corporate identity number"]),
    ("financial_year_end", "string", ["financial year end", "year ended"]),
    ("reporting_currency", "string", ["reporting currency", "currency"]),
    ("revenue_from_operations", "number", ["revenue from operations", "sale of products", "revenue"]),
    ("other_income", "number", ["other income"]),
    ("cost_of_materials_consumed", "number", ["cost of materials consumed", "raw materials consumed"]),
    ("employee_benefits_expense", "number", ["employee benefits expense", "employee cost"]),
    ("finance_costs", "number", ["finance costs", "interest expense"]),
    ("depreciation_and_amortisation", "number", ["depreciation and amortisation", "depreciation"]),
    ("other_expenses", "number", ["other expenses"]),
    ("profit_before_tax", "number", ["profit before tax", "pbt"]),
    ("profit_for_the_period", "number", ["profit for the period", "pat", "profit after tax"]),
    ("equity_share_capital", "number", ["equity share capital", "share capital"]),
    ("other_equity", "number", ["other equity", "reserves and surplus"]),
    ("long_term_borrowings", "number", ["long term borrowings", "long-term borrowings", "non-current borrowings"]),
    ("short_term_borrowings", "number", ["short term borrowings", "short-term borrowings", "current borrowings"]),
    ("cash_and_cash_equivalents", "number", ["cash and cash equivalents", "cash & bank balances"]),
    ("total_current_liabilities", "number", ["total current liabilities", "current liabilities"]),
    ("total_non_current_liabilities", "number", ["total non-current liabilities", "non-current liabilities"]),
    ("total_current_assets", "number", ["total current assets", "current assets"]),
    ("property_plant_and_equipment", "number", ["property, plant and equipment", "tangible assets"]),
    ("inventories", "number", ["inventories", "inventory"]),
    ("trade_receivables", "number", ["trade receivables", "debtors"]),
    ("trade_payables", "number", ["trade payables", "creditors"]),
    ("total_assets", "number", ["total assets"]),
    ("basic_and_diluted_eps", "number", ["earnings per share", "eps", "basic eps"]),
]

msme_spec = {
    "spec_id": "msme_financial_metrics_v1",
    "name": "Detailed Financial Metrics (MSME)",
    "description": "Extracts highly granular financial line items from the Balance Sheet and P&L.",
    "version": "1.0",
    "fields": []
}

for field_id, expected_type, synonyms in msme_fields:
    msme_spec["fields"].append({
        "field_id": field_id,
        "category": "Financial Statements",
        "subcategory": "Line Items",
        "entity_name": synonyms[0].title(),
        "entity_type": "Metric",
        "description": f"Extracts {synonyms[0].title()}",
        "extraction_mode": "DIRECT_MAPPING",
        "expected_value_type": expected_type,
        "synonyms": synonyms,
        "is_required": False
    })


# 2. Comprehensive Sections Spec
sections_fields = [
    ("company_profile", "Company Information", ["company profile", "about us"]),
    ("board_of_directors", "Management & Governance", ["board of directors", "directors"]),
    ("corporate_governance", "Management & Governance", ["corporate governance"]),
    ("shareholding_pattern", "Shareholding Information", ["shareholding pattern"]),
    ("industry_overview", "Management Discussion & Analysis", ["industry overview"]),
    ("future_outlook", "Management Discussion & Analysis", ["future outlook", "outlook"]),
    ("accounting_policies", "Notes to Accounts", ["accounting policies", "significant accounting policies"]),
    ("related_party_transactions", "Notes to Accounts", ["related party transactions"]),
    ("business_risks", "Risk Management", ["business risks", "risk management"]),
    ("esg_initiatives", "ESG & Sustainability", ["esg", "sustainability", "environmental"]),
    ("csr_projects", "CSR", ["csr", "corporate social responsibility"]),
    ("litigations", "Legal & Compliance", ["litigations", "legal proceedings", "contingent liabilities"]),
    ("auditor_report", "Audit Information", ["auditor's report", "independent auditor"]),
]

sections_spec = {
    "spec_id": "comprehensive_sections_v1",
    "name": "Comprehensive Narrative Sections",
    "description": "Extracts broad narrative sections like CSR, ESG, Outlook, and Governance.",
    "version": "1.0",
    "fields": []
}

for field_id, category, synonyms in sections_fields:
    sections_spec["fields"].append({
        "field_id": field_id,
        "category": category,
        "subcategory": synonyms[0].title(),
        "entity_name": synonyms[0].title(),
        "entity_type": "Narrative",
        "description": f"Extracts {synonyms[0].title()}",
        "extraction_mode": "INFERENCE_BASE",  # Ask LLM to summarize/extract the section
        "expected_value_type": "string",
        "synonyms": synonyms,
        "is_required": False
    })


with open("msme_financial_metrics_spec.json", "w") as f:
    json.dump(msme_spec, f, indent=2)

with open("comprehensive_sections_spec.json", "w") as f:
    json.dump(sections_spec, f, indent=2)

print("Generated msme_financial_metrics_spec.json and comprehensive_sections_spec.json")
