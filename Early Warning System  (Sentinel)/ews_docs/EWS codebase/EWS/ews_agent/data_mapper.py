"""
Data Mapper Module

Maps extracted financial table data to the Excel template line items.

Strategy (LLM-first for accuracy):
    1. KEYWORD ALIASES: Deterministic pre-pass for known label variations
    2. LLM MAPPING: Primary method — LLM understands context, sections,
       and semantic equivalence (e.g., "PPE" = "Property, Plant and Equipment")
    3. FUZZY MATCHING: Fallback for items LLM couldn't map (deterministic, fast)

The LLM-first approach ensures higher accuracy because:
    - LLM understands semantic equivalence (e.g., "PPE" = "Property, Plant and Equipment")
    - LLM uses section context to disambiguate (NC vs Current "Borrowings")
    - LLM handles abbreviations, CID-fragmented text, and non-standard labels
    - Fuzzy matching only handles typographical similarity, not semantic equivalence

If LLM is unavailable (llm=None), falls back to fuzzy-only mode (legacy behavior).

For example:
    Template: "Property, Plant and Equipment"
    PDF:      "Property, plant and equipment"  (minor case difference — fuzzy OK)
    PDF:      "Property Plant and Equipment"   (missing comma — fuzzy OK)
    PDF:      "PPE"                            (abbreviation — LLM needed)
    PDF:      "Tangible Assets"                (semantic alias — keyword alias or LLM)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


# ============================================================================
# TEMPLATE DEFINITIONS
# ============================================================================

# Balance Sheet template line items (from the Excel)
BALANCE_SHEET_TEMPLATE = {
    # ASSETS - Non-current
    "Non-current assets": {
        "(a) Property, Plant and Equipment": None,
        "(b) Capital work-in-progress": None,
        "(c) Investment Property": None,
        "(d) Goodwill": None,
        "(e) Other Intangible assets": None,
        "(f) Intangible assets under development": None,
        "(g) Biological Assets other than bearer plants": None,
        "(h) Financial Assets": None,
        "(i) Investments": None,
        "(ii) Trade receivables": None,
        "(iii) Loans": None,
        "(iv) Others (to be specified)": None,
        "(i) Deferred tax assets (net)": None,
        "(j) Other non-current assets": None,
    },
    "Total Non Current Assets": None,
    "Total Fixed assets": None,
    # ASSETS - Current
    "Current assets": {
        "(a) Inventories": None,
        "(b) Financial Assets": None,
        "(i) Investments": None,
        "(ii) Trade receivables": None,
        "(iii) Cash and cash equivalents": None,
        "(iv) Bank balances other than (iii) above": None,
        "(v) Loans": None,
        "(vi) Others (to be specified)": None,
        "(c) Current Tax Assets (Net)": None,
        "(d) Other current assets": None,
    },
    "Total Current Assets": None,
    "Total Assets": None,
    # EQUITY
    "Equity Share Capital": None,
    "Other Equity": None,
    "Total Equity": None,
    "Profit for the year": None,
    "Change in FCTR": None,
    "NCI share of loss": None,
    # LIABILITIES - Non-current
    "Non-current liabilities": {
        "(a) Financial Liabilities": None,
        "(i) Borrowings": None,
        "(ii) Trade Payables": None,
        "(A) total outstanding dues of micro enterprises and small enterprises; and": None,
        "(B) total outstanding dues of creditors other than micro enterprises and small enterprises.": None,
        "(iii) Other financial liabilities": None,
        "(b) Provisions": None,
        "(c) Deferred tax liabilities (Net)": None,
        "(d) Other non-current liabilities": None,
    },
    "Total Non-current Liabilities": None,
    # LIABILITIES - Current
    "Current liabilities": {
        "(a) Financial Liabilities": None,
        "(i) Borrowings": None,
        "(ii) Trade payables": None,
        "(iii) Other financial liabilities": None,
        "(b) Other current liabilities": None,
        "(c) Provisions": None,
        "(d) Current Tax Liabilities (Net)": None,
    },
    "Total Current Liabilities": None,
    "Total Liabilities": None,
    "Total Equity and Liabilities": None,
    "Total debt": None,
}

# P&L template line items
PL_TEMPLATE = {
    "Income": {
        "I. Revenue from operations": None,
        "II. Other income": None,
        "III. Total Income (I + II)": None,
    },
    "IV. Expenses": {
        "Cost of materials consumed": None,
        "Purchases of Stock-in-Trade": None,
        "Changes in inventories of finished goods, work-in-progress and Stock-in-Trade": None,
        "Employee benefits expense": None,
        "Finance costs": None,
        "Depreciation and amortisation expense": None,
        "Other expenses": None,
        "Total expenses": None,
        "V. Profit/(loss) before exceptional items and tax (III - IV)": None,
        "VI. Exceptional items": None,
        "VII. Profit/(loss) before tax (V-VI)": None,
    },
    "Taxes": {
        "(1) Current tax": None,
        "(2) Deferred tax": None,
        "VIII. Tax expense": None,
    },
    "Profit/Loss": {
        "IX. Profit/(Loss) for the period from continuing operations (VII-VIII)": None,
        "X. Profit/(loss) from discontinued operations": None,
        "XI. Tax expense of discontinued operations": None,
        "XII. Profit/(loss) from Discontinuing operations (after tax) (X-XI)": None,
        "XIII. Profit/(Loss) after taxes (IX + XII)": None,
    },
    "EBITDA": None,
    "EBIT": None,
}

# Cash Flow template line items
CASH_FLOW_TEMPLATE = {
    "Cash Flow": {
        "Cash Flows From Operations": None,
        "Cash Flows From Investing": None,
        "Cash Flows From Financing": None,
    },
    "Other Financial Information": {
        "Contingent Liabilities": None,
        "Creditors outstanding for more than 1 year": None,
        "Debtors outstanding for more than 1 year": None,
        "Inventory outstanding for more than 180 days": None,
        "Disputed Trade Receivable": None,
        "Advance from Customers": None,
        "Power and fuel/electricity Expenses": None,
        "Significant impairment of assets/ write-offs": None,
        "Auditors Remunerations": None,
        "One-time revenue (revaluation of assets, etc.)": None,
        "Provision for doubtful debts expense": None,
        "Bad Debts expenses": None,
        "RP Investments": None,
        "RP Expenses": None,
        "RP Revenues": None,
        "RP Loan and Advances*": None,
        "RP Bad debts": None,
        "RP Loan (Liab)": None,
        "Current maturities of borrowings/debts, including interest": None,
    },
}

# Alias mappings for Cash Flow: map detailed CF line items to the 3 summary items.
# These are common phrases found in Indian annual report CF statements.
# The key is a lowercase substring to search for (after CID placeholder stripping),
# and the value is the template item name it maps to.
#
# ANCHOR ALIASES (short, resilient to CID fragmentation):
# These are single-keyword anchors that survive CID placeholder stripping well.
# They are checked with fuzzy matching (token_sort_ratio >= 70) so fragmented
# text like "operat[CID:74]ing" still matches.
CF_ANCHOR_ALIASES = {
    # Cash Flows From Operations
    "operating": "Cash Flows From Operations",
    # Cash Flows From Investing
    "investing": "Cash Flows From Investing",
    # Cash Flows From Financing
    "financing": "Cash Flows From Financing",
}

# PHRASE ALIASES (longer phrases, checked with both exact substring and fuzzy):
CF_PHRASE_ALIASES = {
    # Cash Flows From Operations
    "cash flows from operating": "Cash Flows From Operations",
    "cash flow from operating": "Cash Flows From Operations",
    "net cash from operating": "Cash Flows From Operations",
    "net cash flow from operating": "Cash Flows From Operations",
    "net cash flow generated from operating": "Cash Flows From Operations",
    "net cash used in operating": "Cash Flows From Operations",
    "cash generated from operations": "Cash Flows From Operations",
    "cash from operations": "Cash Flows From Operations",
    "operating activities": "Cash Flows From Operations",
    "net increase in cash from operating": "Cash Flows From Operations",
    "net decrease in cash from operating": "Cash Flows From Operations",
    
    # Cash Flows From Investing
    "cash flows from investing": "Cash Flows From Investing",
    "cash flow from investing": "Cash Flows From Investing",
    "net cash from investing": "Cash Flows From Investing",
    "net cash flow from investing": "Cash Flows From Investing",
    "net cash flow used in investing": "Cash Flows From Investing",
    "net cash used in investing": "Cash Flows From Investing",
    "investing activities": "Cash Flows From Investing",
    "net increase in cash from investing": "Cash Flows From Investing",
    "net decrease in cash from investing": "Cash Flows From Investing",
    
    # Cash Flows From Financing
    "cash flows from financing": "Cash Flows From Financing",
    "cash flow from financing": "Cash Flows From Financing",
    "net cash from financing": "Cash Flows From Financing",
    "net cash flow from financing": "Cash Flows From Financing",
    "net cash flow used in financing": "Cash Flows From Financing",
    "net cash used in financing": "Cash Flows From Financing",
    "financing activities": "Cash Flows From Financing",
    "net increase in cash from financing": "Cash Flows From Financing",
    "net decrease in cash from financing": "Cash Flows From Financing",
}

# Backward-compatible combined alias dict (used elsewhere if needed)
CF_ALIASES = {**CF_PHRASE_ALIASES, **CF_ANCHOR_ALIASES}


# ============================================================================
# BALANCE SHEET & P&L KEYWORD ALIASES
# ============================================================================

# Explicit mappings for PDF row labels that don't fuzzy-match well to template
# items. These are checked BEFORE fuzzy matching as a pre-processing step.
# Format: {normalized_pdf_substring: (template_item, template_section)}
#
# These handle company-specific or industry-specific terminology that has
# low fuzzy similarity to the standard Schedule III template items.

BS_KEYWORD_ALIASES = {
    # Non-current assets
    "right of use assets": ("(iv) Others (to be specified)", "Non-current assets"),
    "income tax assets": ("(iv) Others (to be specified)", "Non-current assets"),
    "right-of-use assets": ("(iv) Others (to be specified)", "Non-current assets"),
    # Capital work-in-progress — common alternative names in real estate/construction
    "capital work-in-progress": ("(b) Capital work-in-progress", "Non-current assets"),
    "capital work in progress": ("(b) Capital work-in-progress", "Non-current assets"),
    "capital work-in- progress": ("(b) Capital work-in-progress", "Non-current assets"),
    "cwip": ("(b) Capital work-in-progress", "Non-current assets"),
    "investment property under development": ("(b) Capital work-in-progress", "Non-current assets"),
    "assets under development": ("(b) Capital work-in-progress", "Non-current assets"),
    "under development": ("(b) Capital work-in-progress", "Non-current assets"),
    # PPE sub-components — when PDF breaks PPE into sub-items.
    # In many Indian annual reports, "Property, plant & equipment" is a parent
    # header with sub-items: Tangible Assets, Intangible Assets, CWIP.
    # In the template, these map to DIFFERENT rows:
    #   Tangible Assets → "(a) Property, Plant and Equipment" (row 3)
    #   Intangible Assets → "(e) Other Intangible assets" (row 7)
    #   CWIP → "(b) Capital work-in-progress" (row 4)
    # More specific aliases MUST come before less specific ones to prevent
    # substring mismatches (e.g., "intangible assets under development" before
    # "intangible assets").
    "intangible assets under development": ("(f) Intangible assets under development", "Non-current assets"),
    "tangible assets": ("(a) Property, Plant and Equipment", "Non-current assets"),
    "tangible fixed assets": ("(a) Property, Plant and Equipment", "Non-current assets"),
    "intangible assets": ("(e) Other Intangible assets", "Non-current assets"),
    # Non-current Financial Assets sub-items
    # NOTE: "(h) Financial Assets" is a FORMULA row (parent of i-iv). Map to leaf items.
    "other financial assets": ("(iv) Others (to be specified)", "Non-current assets"),
    # Non-current liabilities — lease liabilities
    # NOTE: "(a) Financial Liabilities" is a FORMULA row (parent of i-iii).
    # Lease liabilities are NOT borrowings and NOT trade payables,
    # so they map to "(iii) Other financial liabilities" (leaf item).
    "lease liabilities": ("(iii) Other financial liabilities", "Non-current liabilities"),
    # Current liabilities — lease liabilities
    # NOTE: "(a) Financial Liabilities" (Current) is also a FORMULA row (parent of i-iii).
    # Current lease liabilities map to "(iii) Other financial liabilities" (leaf item).
    "current lease liabilities": ("(iii) Other financial liabilities", "Current liabilities"),
    # Current liabilities - trade payables (leaf item, not a parent)
    "total outstanding dues of micro enterprises": ("(ii) Trade payables", "Current liabilities"),
    "total outstanding dues of creditors other than micro": ("(ii) Trade payables", "Current liabilities"),
    # NC Trade Payables sub-items (A)/(B) — often found in current section but
    # template places them under NC. Map from both sections.
    # NOTE: "(ii) Trade Payables" (NC) is a FORMULA row (parent of A+B).
    # The (A) and (B) sub-items are leaf items.
    "outstanding dues of micro enterprises and small enterprises": (
        "(A) total outstanding dues of micro enterprises and small enterprises; and",
        "Non-current liabilities"
    ),
    "outstanding dues of creditors other than micro enterprises and small enterprises": (
        "(B) total outstanding dues of creditors other than micro enterprises and small enterprises.",
        "Non-current liabilities"
    ),
    # Deferred tax liabilities
    "deferred tax liabilities": ("(c) Deferred tax liabilities (Net)", "Non-current liabilities"),
    "deferred tax liab": ("(c) Deferred tax liabilities (Net)", "Non-current liabilities"),
    # Other non-current liabilities
    "other non current liabilities": ("(d) Other non-current liabilities", "Non-current liabilities"),
    "other non-current liabilities": ("(d) Other non-current liabilities", "Non-current liabilities"),
    # Other financial liabilities (NC) — leaf item under (a) Financial Liabilities
    "other financial liabilities": ("(iii) Other financial liabilities", "Non-current liabilities"),
    # Current Tax Assets
    "current tax assets": ("(c) Current Tax Assets (Net)", "Current assets"),
    "income tax assets (net)": ("(c) Current Tax Assets (Net)", "Current assets"),
    # Current Investments — leaf item under (b) Financial Assets
    "current investments": ("(i) Investments", "Current assets"),
    # === NEW ALIASES — common Indian report terminology ===
    # Current liabilities — Provisions (short-term)
    "short-term provisions": ("(c) Provisions", "Current liabilities"),
    "short term provisions": ("(c) Provisions", "Current liabilities"),
    "short term provision": ("(c) Provisions", "Current liabilities"),
    # NC Provisions (long-term)
    "long-term provisions": ("(b) Provisions", "Non-current liabilities"),
    "long term provisions": ("(b) Provisions", "Non-current liabilities"),
    "long term provision": ("(b) Provisions", "Non-current liabilities"),
    # Current Tax Liabilities
    "current tax liabilities": ("(d) Current Tax Liabilities (Net)", "Current liabilities"),
    "current tax liab": ("(d) Current Tax Liabilities (Net)", "Current liabilities"),
    "income tax liabilities": ("(d) Current Tax Liabilities (Net)", "Current liabilities"),
    # Other current liabilities
    "other current liabilities": ("(b) Other current liabilities", "Current liabilities"),
    # NC Borrowings (leaf item)
    "long-term borrowings": ("(i) Borrowings", "Non-current liabilities"),
    "long term borrowings": ("(i) Borrowings", "Non-current liabilities"),
    "non-current borrowings": ("(i) Borrowings", "Non-current liabilities"),
    # Current Borrowings (leaf item)
    "short-term borrowings": ("(i) Borrowings", "Current liabilities"),
    "short term borrowings": ("(i) Borrowings", "Current liabilities"),
    "current borrowings": ("(i) Borrowings", "Current liabilities"),
    # NC Trade Payables
    "non-current trade payables": ("(ii) Trade Payables", "Non-current liabilities"),
    "long-term trade payables": ("(ii) Trade Payables", "Non-current liabilities"),
    # Current Trade Payables (leaf item)
    "trade payables": ("(ii) Trade payables", "Current liabilities"),
    "trade payable": ("(ii) Trade payables", "Current liabilities"),
    # NC Other financial liabilities
    "non-current other financial liabilities": ("(iii) Other financial liabilities", "Non-current liabilities"),
    # Current Other financial liabilities
    "current other financial liabilities": ("(iii) Other financial liabilities", "Current liabilities"),
    # Deferred tax assets
    "deferred tax assets": ("(i) Deferred tax assets (net)", "Non-current assets"),
    "deferred tax": ("(i) Deferred tax assets (net)", "Non-current assets"),
    # Other non-current assets
    "other non-current assets": ("(j) Other non-current assets", "Non-current assets"),
    "other non current assets": ("(j) Other non-current assets", "Non-current assets"),
    # Other current assets
    "other current assets": ("(d) Other current assets", "Current assets"),
    # Bank balances
    "bank balances other than cash and cash equivalents": ("(iv) Bank balances other than (iii) above", "Current assets"),
    # Cash and cash equivalents
    "cash and cash equivalents": ("(iii) Cash and cash equivalents", "Current assets"),
    "cash & cash equivalents": ("(iii) Cash and cash equivalents", "Current assets"),
    # Loans (current)
    "loans and advances": ("(v) Loans", "Current assets"),
    # NC Investments
    "non-current investments": ("(i) Investments", "Non-current assets"),
    "long term investments": ("(i) Investments", "Non-current assets"),
    # Investment Property
    "investment property": ("(c) Investment Property", "Non-current assets"),
    # Goodwill
    "goodwill": ("(d) Goodwill", "Non-current assets"),
    # Biological Assets
    "biological assets": ("(g) Biological Assets other than bearer plants", "Non-current assets"),
    # Equity Share Capital
    "equity share capital": ("Equity Share Capital", ""),
    # Other Equity
    "other equity": ("Other Equity", ""),
    "reserves and surplus": ("Other Equity", ""),
    # Inventories
    "inventories": ("(a) Inventories", "Current assets"),
    "inventory": ("(a) Inventories", "Current assets"),
}

PL_KEYWORD_ALIASES = {
    # Real estate / construction specific expenses
    "land purchase cost": ("Purchases of Stock-in-Trade", "IV. Expenses"),
    "purchase of project materials": ("Purchases of Stock-in-Trade", "IV. Expenses"),
    "sub-contractor cost": ("Other expenses", "IV. Expenses"),
    "subcontractor cost": ("Other expenses", "IV. Expenses"),
    "sub contractor cost": ("Other expenses", "IV. Expenses"),
    "construction cost": ("Purchases of Stock-in-Trade", "IV. Expenses"),
    # Deferred tax — common P&L label variations
    "deferred tax charge": ("(2) Deferred tax", "Taxes"),
    "deferred tax": ("(2) Deferred tax", "Taxes"),
}


# ============================================================================
# NOTES KEYWORD ALIASES FOR "OTHER FINANCIAL INFORMATION"
# ============================================================================

# Explicit mappings from Notes to Accounts terms to the CF template's
# "Other Financial Information" section items.
#
# These items are NOT found in the Cash Flow statement itself — they come
# from specific notes in the Notes to Accounts section:
#   - Contingent Liabilities → Note "Contingent liabilities and commitments"
#   - Current maturities → Note "Borrowings"
#   - Power and fuel → Note "Other expenses"
#   - Bad debts → Note "Other expenses"
#   - Auditors Remuneration → Note "Auditors' Remuneration"
#   - RP items → Note "Related party disclosures"
#   etc.
#
# Format: {normalized_substring: (template_item, section)}
# More specific aliases should come FIRST to prevent substring mismatches.
# The alias key is checked as a substring of the _normalize_text()'d row label.

NOTES_KEYWORD_ALIASES = {
    # --- Contingent Liabilities ---
    # Found in the "Contingent liabilities and commitments" note.
    # The total row may just say "Total" — handled separately in Phase 2
    # of map_notes_to_other_financial_info().
    "aggregate of contingent": ("Contingent Liabilities", "Other Financial Information"),
    "total contingent liab": ("Contingent Liabilities", "Other Financial Information"),
    "contingent liab": ("Contingent Liabilities", "Other Financial Information"),
    "contingencies and commitments": ("Contingent Liabilities", "Other Financial Information"),

    # --- Current maturities of borrowings/debts ---
    # Found in the "Borrowings" note under current liabilities section.
    "current maturities of long term borrowings": ("Current maturities of borrowings/debts, including interest", "Other Financial Information"),
    "current maturities of long term debt": ("Current maturities of borrowings/debts, including interest", "Other Financial Information"),
    "current maturities of borrowings": ("Current maturities of borrowings/debts, including interest", "Other Financial Information"),
    "current maturities of debentures": ("Current maturities of borrowings/debts, including interest", "Other Financial Information"),
    "maturities of long term borrowings": ("Current maturities of borrowings/debts, including interest", "Other Financial Information"),

    # --- Power and fuel/electricity Expenses ---
    # Found in the "Other expenses" note.
    "power and fuel": ("Power and fuel/electricity Expenses", "Other Financial Information"),
    "fuel and power": ("Power and fuel/electricity Expenses", "Other Financial Information"),
    "electricity expenses": ("Power and fuel/electricity Expenses", "Other Financial Information"),
    "power and electricity": ("Power and fuel/electricity Expenses", "Other Financial Information"),
    "fuel and electricity": ("Power and fuel/electricity Expenses", "Other Financial Information"),
    "power fuel": ("Power and fuel/electricity Expenses", "Other Financial Information"),

    # --- Bad Debts expenses ---
    # Found in the "Other expenses" note. More specific alias first.
    "bad debts written off": ("Bad Debts expenses", "Other Financial Information"),
    "bad debt written off": ("Bad Debts expenses", "Other Financial Information"),

    # --- Provision for doubtful debts expense ---
    # Found in "Trade receivables" or "Provisions" note.
    "provision for doubtful debts": ("Provision for doubtful debts expense", "Other Financial Information"),
    "provision for doubtful trade receivable": ("Provision for doubtful debts expense", "Other Financial Information"),
    "provision for bad and doubtful": ("Provision for doubtful debts expense", "Other Financial Information"),
    "doubtful debts provision": ("Provision for doubtful debts expense", "Other Financial Information"),

    # --- Auditors Remunerations ---
    # Found in the "Auditors' Remuneration" note.
    "auditor remuneration": ("Auditors Remunerations", "Other Financial Information"),
    "auditors remuneration": ("Auditors Remunerations", "Other Financial Information"),
    "audit remuneration": ("Auditors Remunerations", "Other Financial Information"),
    "audit fees": ("Auditors Remunerations", "Other Financial Information"),
    "auditor fees": ("Auditors Remunerations", "Other Financial Information"),
    "auditors fees": ("Auditors Remunerations", "Other Financial Information"),

    # --- Disputed Trade Receivable ---
    # Found in "Trade receivables" note.
    "disputed trade receivable": ("Disputed Trade Receivable", "Other Financial Information"),
    "disputed receivables": ("Disputed Trade Receivable", "Other Financial Information"),
    "disputed debts": ("Disputed Trade Receivable", "Other Financial Information"),
    "disputed dues": ("Disputed Trade Receivable", "Other Financial Information"),

    # --- Advance from Customers ---
    # Found in "Other current liabilities" or "Current liabilities" note.
    "advance from customers": ("Advance from Customers", "Other Financial Information"),
    "advances from customers": ("Advance from Customers", "Other Financial Information"),
    "customer advances": ("Advance from Customers", "Other Financial Information"),
    "advance received from customers": ("Advance from Customers", "Other Financial Information"),
    "advances received from customers": ("Advance from Customers", "Other Financial Information"),

    # --- Creditors outstanding for more than 1 year ---
    "creditors outstanding for more than": ("Creditors outstanding for more than 1 year", "Other Financial Information"),
    "trade payables outstanding for more than": ("Creditors outstanding for more than 1 year", "Other Financial Information"),
    "payables outstanding for more than": ("Creditors outstanding for more than 1 year", "Other Financial Information"),

    # --- Debtors outstanding for more than 1 year ---
    "debtors outstanding for more than": ("Debtors outstanding for more than 1 year", "Other Financial Information"),
    "trade receivables outstanding for more than": ("Debtors outstanding for more than 1 year", "Other Financial Information"),
    "receivables outstanding for more than": ("Debtors outstanding for more than 1 year", "Other Financial Information"),

    # --- Inventory outstanding for more than 180 days ---
    "inventory outstanding for more than": ("Inventory outstanding for more than 180 days", "Other Financial Information"),
    "inventories outstanding for more than": ("Inventory outstanding for more than 180 days", "Other Financial Information"),

    # --- Significant impairment of assets/ write-offs ---
    "impairment of assets": ("Significant impairment of assets/ write-offs", "Other Financial Information"),
    "significant impairment": ("Significant impairment of assets/ write-offs", "Other Financial Information"),
    "write off of assets": ("Significant impairment of assets/ write-offs", "Other Financial Information"),
    "write-off of assets": ("Significant impairment of assets/ write-offs", "Other Financial Information"),
    "impairment loss": ("Significant impairment of assets/ write-offs", "Other Financial Information"),

    # --- One-time revenue ---
    "revaluation of assets": ("One-time revenue (revaluation of assets, etc.)", "Other Financial Information"),
    "revaluation surplus": ("One-time revenue (revaluation of assets, etc.)", "Other Financial Information"),
    "one-time revenue": ("One-time revenue (revaluation of assets, etc.)", "Other Financial Information"),

    # --- RP (Related Party) items ---
    # Found in "Related party disclosures" note.
    # Note: RP row labels may not always contain "related party" — the context
    # comes from the note title. These aliases handle cases where the row label
    # does include "related party".
    "related party investment": ("RP Investments", "Other Financial Information"),
    "related party investments": ("RP Investments", "Other Financial Information"),
    "related party expense": ("RP Expenses", "Other Financial Information"),
    "related party expenses": ("RP Expenses", "Other Financial Information"),
    "related party purchase": ("RP Expenses", "Other Financial Information"),
    "related party purchases": ("RP Expenses", "Other Financial Information"),
    "related party revenue": ("RP Revenues", "Other Financial Information"),
    "related party revenues": ("RP Revenues", "Other Financial Information"),
    "related party sale": ("RP Revenues", "Other Financial Information"),
    "related party sales": ("RP Revenues", "Other Financial Information"),
    "related party loan and advance": ("RP Loan and Advances*", "Other Financial Information"),
    "related party loans and advances": ("RP Loan and Advances*", "Other Financial Information"),
    "related party lending": ("RP Loan and Advances*", "Other Financial Information"),
    "related party bad debt": ("RP Bad debts", "Other Financial Information"),
    "related party bad debts": ("RP Bad debts", "Other Financial Information"),
    "related party borrowing": ("RP Loan (Liab)", "Other Financial Information"),
    "related party borrowings": ("RP Loan (Liab)", "Other Financial Information"),
    "related party loan liab": ("RP Loan (Liab)", "Other Financial Information"),
    "related party debt": ("RP Loan (Liab)", "Other Financial Information"),
}


# ============================================================================
# FLATTEN TEMPLATES FOR MATCHING
# ============================================================================

def _flatten_template(template: dict) -> list[str]:
    """
    Flatten a nested template dict into a list of all line item names.
    """
    items = []
    for key, value in template.items():
        if isinstance(value, dict) and value is not None:
            items.append(key)  # Section header
            items.extend(value.keys())  # Sub-items
        else:
            items.append(key)
    return items


def _flatten_template_with_sections(template: dict) -> list[tuple[str, str]]:
    """
    Flatten template into list of (section, line_item) tuples.
    Section is the top-level key, line_item is the specific item.
    """
    items = []
    for key, value in template.items():
        if isinstance(value, dict) and value is not None:
            for sub_key in value.keys():
                items.append((key, sub_key))
        else:
            items.append(("", key))
    return items


# ============================================================================
# FUZZY MATCHING
# ============================================================================


# Regex to match CID placeholders like [CID:74] or [CID:193]
_CID_PLACEHOLDER_RE = re.compile(r'\[CID:\d+\]')


def _normalize_text(s: str) -> str:
    """
    Normalize text for better fuzzy matching.
    - Strip CID font placeholders like [CID:74]
    - Lowercase
    - Remove extra whitespace
    - Remove common prefixes like roman numerals, item numbers
    - Remove punctuation that varies across reports
    """
    s = s.lower().strip()
    # Strip CID placeholders FIRST (before other processing)
    s = _CID_PLACEHOLDER_RE.sub(' ', s)
    # Remove note references like "(1)", "(2)", "[1]"
    s = re.sub(r'[\(\[]?\d+[\)\]]?', '', s)
    # Remove roman numeral prefixes like "I.", "II.", "IV."
    s = re.sub(r'^[ivx]+\.\s*', '', s)
    # Remove item letter prefixes like "(a)", "(b)", "(i)", "(ii)"
    s = re.sub(r'^\(?[a-z]+[\).]\s*', '', s)
    # Remove slashes, parentheses, commas for matching
    s = re.sub(r'[/(),\-]', ' ', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


@dataclass
class MappingResult:
    """Result of mapping a PDF row to a template item."""
    template_item: str
    section: str
    pdf_row_label: str
    value: str
    confidence: float  # 0.0 to 1.0
    method: str  # "fuzzy" or "llm" or "exact"


# Labels from PDF rows that are totals/subtotals — these should NOT be mapped
# to template items because they'll be computed by Excel formulas.
# Matching these would waste template slots and cause formula cells to get
# overwritten with extracted values instead of formulas.
TOTAL_ROW_PATTERNS = re.compile(
    r'^(total\s+)?(assets|liabilities|equity|income|expenses|'
    r'non\s*[- ]?current\s+assets|current\s+assets|'
    r'non\s*[- ]?current\s+liabilities|current\s+liabilities|'
    r'fixed\s+assets|debt|equity\s+and\s+liabilities|'
    r'profit\s+before\s+tax|profit\s+before\s+exceptional|'
    r'tax\s+expense|profit\s+after\s+tax|'
    r'profit\s+from\s+continuing|ebitda|ebit)$',
    re.IGNORECASE
)

# Template items that are FORMULA rows — these should NEVER be matched by
# the mapper because they'll be computed by Excel formulas in the writer.
# If a PDF row matches one of these, it's a total/subtotal that should be
# skipped (the formula will compute it from component values).
FORMULA_TEMPLATE_ITEMS = {
    # Balance Sheet formula rows (top-level totals)
    "Total Non Current Assets", "Total Fixed assets", "Total Current Assets",
    "Total Assets", "Total Equity", "Total Non-current Liabilities",
    "Total Current Liabilities", "Total Liabilities",
    "Total Equity and Liabilities", "Total debt",
    # Balance Sheet section headers (parent rows whose value = sum of sub-items)
    # These MUST NOT be mapped from PDF because the Excel SUM formulas for
    # top-level totals include these rows. If we write a value here AND to
    # the sub-items, the SUM double-counts.
    #
    # NC Assets: "(h) Financial Assets" = sum of (i)+(ii)+(iii)+(iv)
    "(h) Financial Assets",
    # Current Assets: "(b) Financial Assets" = sum of (i) through (vi)
    "(b) Financial Assets",
    # NC Liabilities: "(a) Financial Liabilities" = sum of (i)+(ii)+(iii)
    # (same name appears in Current liabilities — both are parents)
    "(a) Financial Liabilities",
    # NC Liabilities: "(ii) Trade Payables" = sum of (A)+(B)
    # Note: Current "(ii) Trade payables" (lowercase p) is a LEAF item, NOT a parent
    "(ii) Trade Payables",
    # P&L formula rows
    "III. Total Income (I + II)", "VIII. Tax expense",
    "Total expenses", "V. Profit/(loss) before exceptional items and tax (III - IV)",
    "VII. Profit/(loss) before tax (V-VI)",
    "IX. Profit/(Loss) for the period from continuing operations (VII-VIII)",
    "XIII. Profit/(Loss) after taxes (IX + XII)",
    "EBITDA", "EBIT",
}


# ============================================================================
# PARENT ROW PATTERNS (for parent-child deduplication)
# ============================================================================

# Normalized substrings that identify "parent" rows in the PDF balance sheet.
# A parent row's value is the SUM of its children sub-items.
# When both a parent and a child map to the same template item via different
# methods (alias vs fuzzy), the child's value is more specific and should
# be preferred to avoid double-counting.
#
# Example: PDF has "Property, plant & equipment  6,714.71" as a parent total,
# and "(i) Tangible Assets  6,527.97" as a child. Both map to template row 3
# "(a) Property, Plant and Equipment". The parent value (6,714.71) already
# includes the child value (6,527.97), so summing them would double-count.
# Solution: detect the parent, keep the child's value, discard the parent's.

_PARENT_ROW_PATTERNS = {
    # "Property, plant & equipment" is a parent of: Tangible Assets, Intangible Assets, CWIP
    "property plant and equipment",
    "property plant & equipment",
    "total property plant and equipment",
    # "Investment Property" can be a parent in some reports
    "total investment property",
    # "Other Intangible assets" can be a parent of Intangible Assets + Under Development
    "total intangible assets",
    "total other intangible assets",
}


# ============================================================================
# DEFAULT ZERO ITEMS — REMOVED
# ============================================================================
# Previously, these sets defined template items that would default to 0 when
# not found in the PDF. This has been REMOVED per policy:
#   "Only write 0 if the PDF explicitly says 0/Nil/blank/— for that item.
#    If the item is simply NOT in the PDF, leave the Excel cell blank."
#
# The old sets are kept as empty sets for backward compatibility (imports
# still reference them), but they will produce no default-zero mappings.

BS_DEFAULT_ZERO_ITEMS = set()       # Removed — no auto-zero for absent items
PL_DEFAULT_ZERO_ITEMS_SET = set()   # Removed — no auto-zero for absent items
CF_DEFAULT_ZERO_ITEMS = set()       # Removed — no auto-zero for absent items


# ============================================================================
# DERIVED / CALCULATED ITEMS
# ============================================================================

# Template items that are NOT directly present in the PDF but can be
# CALCULATED from other mapped values. These are "catch-all" categories
# that represent the residual after known sub-items are accounted for.
#
# Format: {template_item: (section, derivation_rule)}
# derivation_rule types:
#   "residual" — computed as: parent_total - sum(known_sub_items)
#   "from_notes" — must be extracted from notes (equity roll-forward, etc.)

DERIVED_ITEMS = {
    # Balance Sheet
    "(d) Other non-current liabilities": {
        "section": "Non-current liabilities",
        "rule": "residual",
        "description": "Total NC liabilities minus known NC liability leaf items",
        "parent_total": "Total Non-current Liabilities",
        "subtract_items": [
            # Leaf items only — NOT section headers like "(a) Financial Liabilities"
            # which are sums of their sub-items and would cause double-counting
            "(i) Borrowings",
            "(ii) Trade Payables",
            "(A) total outstanding dues of micro enterprises and small enterprises; and",
            "(B) total outstanding dues of creditors other than micro enterprises and small enterprises.",
            "(iii) Other financial liabilities",
            "(b) Provisions",
            "(c) Deferred tax liabilities (Net)",
        ],
    },
    "(vi) Others (to be specified)": {
        "section": "Current assets",
        "rule": "residual",
        "description": "Total Current Assets minus known current asset leaf items",
        "parent_total": "Total Current Assets",
        "subtract_items": [
            # Leaf items only — NOT section headers like "(b) Financial Assets"
            "(a) Inventories",
            "(i) Investments",
            "(ii) Trade receivables",
            "(iii) Cash and cash equivalents",
            "(iv) Bank balances other than (iii) above",
            "(v) Loans",
            "(c) Current Tax Assets (Net)",
            "(d) Other current assets",
        ],
    },
    # Equity roll-forward items — from "Other Equity" note
    "Profit for the year": {
        "section": "",
        "rule": "from_notes",
        "description": "Profit for the year from Other Equity note / Statement of Changes in Equity",
        "note_keywords": ["other equity", "statement of changes in equity", "reserves and surplus"],
        "search_patterns": [
            "profit for the year",
            "profit/(loss) for the year",
            "net profit for the year",
            "total comprehensive income for the year",
        ],
    },
    "Change in FCTR": {
        "section": "",
        "rule": "from_notes",
        "description": "Foreign Currency Translation Reserve change from Other Equity note",
        "note_keywords": ["other equity", "reserves and surplus", "foreign currency"],
        "search_patterns": [
            "foreign currency translation reserve",
            "translation reserve",
            "fctr",
            "change in foreign currency",
        ],
    },
    "NCI share of loss": {
        "section": "",
        "rule": "from_notes",
        "description": "Non-controlling interest share from equity note or consolidated BS",
        "note_keywords": ["other equity", "non-controlling interest", "minority interest"],
        "search_patterns": [
            "non-controlling interest",
            "minority interest",
            "nci share",
            "share of loss attributable to non-controlling",
        ],
    },
}


def _is_total_row(label: str) -> bool:
    """
    Check if a PDF row label is a total/subtotal row that should be skipped.
    
    These rows will be computed by Excel formulas in the template, so we
    should not map extracted values to them.
    """
    label_clean = label.strip().lower()
    # Remove common prefixes like roman numerals, item numbers
    label_clean = re.sub(r'^[ivx]+\.\s*', '', label_clean)
    label_clean = re.sub(r'^\(?[a-z]+[\).]\s*', '', label_clean)
    label_clean = re.sub(r'[/(),\-]', ' ', label_clean)
    label_clean = re.sub(r'\s+', ' ', label_clean).strip()
    
    return bool(TOTAL_ROW_PATTERNS.match(label_clean))


def _get_row_section(row: list[str], table_headers: list[str]) -> str:
    """
    Extract the section name from a table row.
    
    If the table has a "Section" column (from text-based extraction with
    section tracking), return its value. Otherwise return empty string.
    """
    # Check if there's a "Section" column
    section_col = None
    for i, h in enumerate(table_headers):
        if str(h).strip().lower() == 'section':
            section_col = i
            break
    
    if section_col is not None and section_col < len(row):
        return str(row[section_col]).strip()
    
    return ""


def map_table_to_template(
    table_headers: list[str],
    table_rows: list[list[str]],
    template: dict,
    min_confidence: float = 0.6,
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
) -> list[MappingResult]:
    """
    Map extracted table rows to template line items using fuzzy matching.

    Uses a TWO-PASS approach to avoid greedy first-come-first-served mismatches:
    
    Pass 1: Collect ALL (pdf_row, template_item, score) candidates with
            section-aware scoring (same-section matches get a bonus).
    Pass 2: Assign optimally by processing candidates in descending score
            order, so the best match always wins.

    Section-aware matching: When a PDF row has a known section (from the
    text-based parser's section tracking), same-section matches are preferred.
    Cross-section matches are only considered if no same-section match exists
    AND the score is significantly higher.

    Total/subtotal rows are skipped — they'll be computed by Excel formulas.

    Args:
        table_headers: Column headers from the extracted table.
        table_rows: Data rows from the extracted table.
        template: The template dict (BALANCE_SHEET_TEMPLATE, etc.)
        min_confidence: Minimum fuzzy match score to accept (0-100 scale from rapidfuzz,
                        but we normalize to 0-1).
        year_column: Which column index contains the values for the target year.
                     If None, auto-detects from headers.

    Returns:
        List of MappingResult objects.
    """
    # Flatten template for matching
    template_items = _flatten_template_with_sections(template)
    template_labels = [item[1] for item in template_items]
    normalized_template = [_normalize_text(label) for label in template_labels]

    # Auto-detect year column if not specified
    if year_column is None:
        year_column = _detect_year_column(table_headers, target_year=target_year)

    # Build section -> template indices mapping for section-aware matching
    section_to_indices: dict[str, list[int]] = {}
    for i, (section, label) in enumerate(template_items):
        if section:
            section_to_indices.setdefault(section, []).append(i)

    # === PASS 1: Collect all candidates ===
    # Each candidate is (adjusted_score, row_idx, template_idx, method, raw_score)
    # adjusted_score incorporates section bonus for same-section matches
    SECTION_BONUS = 15  # Bonus points (out of 100) for same-section match
    CROSS_SECTION_PENALTY = 20  # Penalty for cross-section match (strong to prevent mismatches)
    
    candidates = []  # List of (adjusted_score, row_idx, template_idx, method)
    row_data = {}  # row_idx -> (row_label, value, pdf_section)
    
    for row_idx, row in enumerate(table_rows):
        if not row:
            continue

        # First column is typically the label
        row_label = str(row[0]).strip()
        if not row_label:
            continue

        # Skip total/subtotal rows — they'll be computed by Excel formulas
        if _is_total_row(row_label):
            logger.debug(f"Skipping total row: '{row_label}'")
            continue

        # Get value from the year column
        value = ""
        if year_column is not None and year_column < len(row):
            value = str(row[year_column]).strip()
        elif len(row) > 1:
            # Fallback: take the last numeric column
            for cell in reversed(row[1:]):
                cell_str = str(cell).strip()
                if cell_str and _is_numeric_value(cell_str):
                    value = cell_str
                    break

        if not value:
            continue

        # Get the PDF row's section (from section tracking in text parser)
        pdf_section = _get_row_section(row, table_headers)
        row_data[row_idx] = (row_label, value, pdf_section)

        # Normalize the row label for matching
        normalized_row = _normalize_text(row_label)

        # Score against ALL template items (EXCEPT formula items)
        for tmpl_idx, norm_tmpl in enumerate(normalized_template):
            # Skip template items that are formula rows — they'll be
            # computed by Excel formulas, not filled from extracted data
            tmpl_label = template_items[tmpl_idx][1]
            if tmpl_label in FORMULA_TEMPLATE_ITEMS:
                continue
            
            # Exact match
            if normalized_row == norm_tmpl:
                # Exact matches get very high score + section bonus
                tmpl_section = template_items[tmpl_idx][0]
                if pdf_section and tmpl_section and pdf_section == tmpl_section:
                    adjusted = 100.0 + SECTION_BONUS
                else:
                    adjusted = 100.0
                candidates.append((adjusted, row_idx, tmpl_idx, "exact"))
                continue
            
            # Fuzzy match
            raw_score = fuzz.token_sort_ratio(normalized_row, norm_tmpl)
            if raw_score < 55:  # Skip very low scores early
                continue
            
            # Apply section bonus/penalty
            tmpl_section = template_items[tmpl_idx][0]
            if pdf_section and tmpl_section:
                if pdf_section == tmpl_section:
                    adjusted = raw_score + SECTION_BONUS
                else:
                    # Cross-section: only allow if score is high enough
                    # to overcome the penalty
                    adjusted = raw_score - CROSS_SECTION_PENALTY
            else:
                adjusted = raw_score  # No section info, use raw score
            
            if adjusted >= 60:  # Minimum adjusted threshold
                candidates.append((adjusted, row_idx, tmpl_idx, "fuzzy"))

    # === PASS 2: Assign optimally (greedy by highest adjusted score) ===
    # Sort candidates by adjusted score descending
    candidates.sort(key=lambda c: c[0], reverse=True)
    
    matched_template_indices: set[int] = set()
    matched_row_indices: set[int] = set()
    results: list[MappingResult] = []
    
    for adjusted_score, row_idx, tmpl_idx, method in candidates:
        # Skip if either the row or template item is already matched
        if row_idx in matched_row_indices or tmpl_idx in matched_template_indices:
            continue
        
        # Compute the confidence from the raw fuzzy score (before adjustment)
        # For exact matches, raw score is 100
        if method == "exact":
            confidence = 1.0
        else:
            # Back out the raw score from adjusted
            tmpl_section = template_items[tmpl_idx][0]
            row_label, value, pdf_section = row_data[row_idx]
            if pdf_section and tmpl_section and pdf_section == tmpl_section:
                raw = adjusted_score - SECTION_BONUS
            elif pdf_section and tmpl_section:
                raw = adjusted_score + CROSS_SECTION_PENALTY
            else:
                raw = adjusted_score
            confidence = raw / 100.0
        
        if confidence < min_confidence:
            continue
        
        section, template_label = template_items[tmpl_idx]
        row_label, value, pdf_section = row_data[row_idx]
        
        matched_template_indices.add(tmpl_idx)
        matched_row_indices.add(row_idx)
        
        results.append(MappingResult(
            template_item=template_label,
            section=section,
            pdf_row_label=row_label,
            value=value,
            confidence=confidence,
            method=method,
        ))

        logger.debug(
            f"Mapped '{row_label}' -> '{template_label}' "
            f"(adj_score={adjusted_score:.1f}, confidence={confidence:.2f}, method={method}, "
            f"pdf_section='{pdf_section}', template_section='{section}')"
        )

    # Log unmatched template items
    for i, (section, label) in enumerate(template_items):
        if i not in matched_template_indices:
            logger.debug(f"Unmatched template item: [{section}] {label}")

    return results

def _detect_year_column(headers: list[str], target_year: Optional[int] = None) -> Optional[int]:
    """
    Auto-detect which column contains the current year's data.

    For Indian annual reports, headers typically look like:
    - ["Particulars", "Note", "As at March 31, 2024", "As at March 31, 2023"]
    - ["", "Current Year", "Previous Year"]

    We want the "current year" or the latest year column.

    If target_year is provided, we prefer the column whose header contains
    that exact year. This prevents selecting the wrong column when the
    detected financial year differs from the latest header year (rare but
    possible in comparative statements spanning 3+ years).

    Args:
        headers: Column header strings.
        target_year: The detected financial year (ending year). If provided,
            prefer the column matching this year.

    Returns:
        Column index for the target year's data, or None.
    """
    if not headers:
        return None

    # Look for year patterns in headers
    year_pattern = re.compile(r'(20\d{2})')
    years_found: list[tuple[int, int]] = []  # (column_index, year)

    for i, header in enumerate(headers):
        header_str = str(header)
        match = year_pattern.search(header_str)
        if match:
            years_found.append((i, int(match.group(1))))

    if years_found:
        # If target_year is provided, prefer the column matching it
        if target_year is not None:
            for col_idx, year_val in years_found:
                if year_val == target_year:
                    logger.debug(
                        f"Year column: selected column {col_idx} "
                        f"(header='{headers[col_idx]}', matches target_year={target_year})"
                    )
                    return col_idx
            # target_year not found in headers — fall through to latest year

        # Return the column with the latest year
        years_found.sort(key=lambda x: x[1], reverse=True)
        col_idx = years_found[0][0]
        if target_year is not None and years_found[0][1] != target_year:
            logger.warning(
                f"Year column: target_year={target_year} not found in headers, "
                f"using latest year column {col_idx} "
                f"(header='{headers[col_idx]}', year={years_found[0][1]})"
            )
        return col_idx

    # Look for "current year" / "current period" keywords
    current_keywords = ["current year", "current period", "year ended"]
    for i, header in enumerate(headers):
        header_lower = str(header).lower()
        if any(kw in header_lower for kw in current_keywords):
            return i

    # Default: second column (index 1) - first column is usually labels
    if len(headers) > 1:
        return 1

    return None


def _is_numeric_value(s: str) -> bool:
    """Check if a string represents a numeric value."""
    s = s.strip().replace(",", "").replace("(", "").replace(")", "")
    s = s.replace("-", "").replace(" ", "")
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


# ============================================================================
# LLM-BASED MAPPING (PRIMARY — after keyword aliases, before fuzzy)
# ============================================================================


def _fuzzy_match_template_item(
    llm_item: str,
    unmapped_lookup: dict[str, str],
) -> Optional[str]:
    """
    Fuzzy-match an LLM-returned template item name against the unmapped items.

    LLMs often:
    - Drop the (a), (b), (i), (ii) prefixes from template item names.
      E.g., "Property, Plant and Equipment" instead of "(a) Property, Plant and Equipment"
    - Prepend the section name in brackets.
      E.g., "[Non-current assets] (j) Other non-current assets" instead of "(j) Other non-current assets"
    - Prepend the section name without brackets.
      E.g., "Income I. Revenue from operations" instead of "I. Revenue from operations"

    This function handles all three cases by:
    1. Exact match (fast path)
    2. Strip [Section] prefixes and section-name prefixes from LLM item
    3. Strip (a)/(b)/(i)/(ii) prefixes from both LLM item and lookup keys, compare
    4. Fuzzy match with token_sort_ratio >= 80

    Args:
        llm_item: Template item name returned by the LLM.
        unmapped_lookup: Dict mapping valid template item names to their sections.

    Returns:
        The matched key from unmapped_lookup, or None if no match found.
    """
    if not llm_item:
        return None

    # 0. Strip [Section] prefix that LLM sometimes adds
    # E.g., "[Non-current assets] (j) Other non-current assets" -> "(j) Other non-current assets"
    # E.g., "[Other Financial Information] Advance from Customers" -> "Advance from Customers"
    section_prefix_pattern = re.compile(r'^\[.*?\]\s*')
    llm_item_cleaned = section_prefix_pattern.sub('', llm_item).strip()
    
    # Also strip section-name prefixes without brackets
    # E.g., "Income I. Revenue from operations" -> "I. Revenue from operations"
    # E.g., "IV. Expenses Cost of materials consumed" -> "Cost of materials consumed"
    # E.g., "Profit/Loss X. Profit/(loss)..." -> "X. Profit/(loss)..."
    # We need to be careful: "I. Revenue from operations" has "I." which is a valid roman numeral prefix
    # Strategy: strip known section names that the LLM prepends
    known_section_prefixes = [
        "Non-current assets", "Current assets", "Non-current liabilities",
        "Current liabilities", "Income", "IV. Expenses", "Taxes",
        "Profit/Loss", "Cash Flow", "Other Financial Information",
        "Equity", "EBITDA", "EBIT",
    ]
    for sec_prefix in known_section_prefixes:
        if llm_item_cleaned.startswith(sec_prefix + " "):
            llm_item_cleaned = llm_item_cleaned[len(sec_prefix):].strip()
            break

    # 1. Exact match (fast path) — try both original and cleaned
    if llm_item in unmapped_lookup:
        return llm_item
    if llm_item_cleaned in unmapped_lookup:
        logger.info(
            f"LLM template fuzzy: matched '{llm_item}' -> '{llm_item_cleaned}' "
            f"(stripped section prefix)"
        )
        return llm_item_cleaned

    # 2. Strip common prefixes from lookup keys and compare
    # Prefixes like (a), (b), (i), (ii), (A), (B), I., II., IV., etc.
    prefix_pattern = re.compile(
        r'^\(?[a-zA-Z]+[\).]\s*'  # (a), (b), (i), (ii), (A), (B), etc.
        r'|^[IVXivx]+\.\s*'        # I., II., IV., etc.
    )

    llm_item_stripped = prefix_pattern.sub('', llm_item_cleaned).strip()

    for lookup_key in unmapped_lookup:
        lookup_key_stripped = prefix_pattern.sub('', lookup_key).strip()
        if llm_item_stripped.lower() == lookup_key_stripped.lower():
            logger.info(
                f"LLM template fuzzy: matched '{llm_item}' -> '{lookup_key}' "
                f"(prefix-stripped match)"
            )
            return lookup_key

    # 3. Fuzzy match — compare normalized versions (use cleaned item)
    llm_norm = _normalize_text(llm_item_cleaned)

    best_score = 0.0
    best_key = None

    for lookup_key in unmapped_lookup:
        lookup_norm = _normalize_text(lookup_key)
        score = fuzz.token_sort_ratio(llm_norm, lookup_norm)
        if score > best_score:
            best_score = score
            best_key = lookup_key

    if best_score >= 80 and best_key is not None:
        logger.info(
            f"LLM template fuzzy: matched '{llm_item}' -> '{best_key}' "
            f"(fuzzy score={best_score:.1f})"
        )
        return best_key

    logger.info(
        f"LLM template fuzzy: no match for '{llm_item}' "
        f"(best fuzzy score={best_score:.1f} < 80)"
    )
    return None

def map_by_llm(
    table_headers: list[str],
    table_rows: list[list[str]],
    template: dict,
    already_mapped_items: set[str],
    llm,
    statement_type: str = "balance_sheet",
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
    exclude_row_indices: Optional[set[int]] = None,
) -> tuple[list[MappingResult], set[int]]:
    """
    Use LLM to map PDF rows to template items (PRIMARY mapping method).

    Called AFTER keyword aliases but BEFORE fuzzy matching. The LLM
    understands semantic equivalence, section context, and abbreviations
    that fuzzy matching cannot handle.

    If LLM is unavailable (llm=None), returns empty results (caller should
    fall back to fuzzy-only mode).

    Args:
        table_headers: Column headers from the extracted table.
        table_rows: ALL data rows from the extracted table.
        template: The template dict (BALANCE_SHEET_TEMPLATE, etc.)
        already_mapped_items: Set of template item names already mapped
                              by keyword aliases.
        llm: LangChain ChatOpenAI instance.
        statement_type: Type of statement ("balance_sheet", "profit_and_loss",
                        "cash_flow", "notes").
        year_column: Which column index contains the values.
        target_year: The detected financial year.
        exclude_row_indices: Set of row indices already claimed by aliases.

    Returns:
        Tuple of (list of MappingResult objects, set of matched row indices
        into the original table_rows list).
    """
    from .llm_utils import llm_call_with_retry, extract_json_from_response

    if llm is None or not table_rows:
        return [], set()

    if exclude_row_indices is None:
        exclude_row_indices = set()

    # Auto-detect year column if not specified
    if year_column is None:
        year_column = _detect_year_column(table_headers, target_year=target_year)

    # Get unmapped template items (excluding formula items and already-mapped)
    template_items_with_sections = _flatten_template_with_sections(template)
    unmapped_items = []
    for section, label in template_items_with_sections:
        if label in FORMULA_TEMPLATE_ITEMS:
            continue
        if label in already_mapped_items:
            continue
        unmapped_items.append((section, label))

    if not unmapped_items:
        return [], set()

    # Build list of unmapped template items for the prompt
    template_str = "\n".join(
        f"  {i+1}. [{section}] {label}"
        for i, (section, label) in enumerate(unmapped_items)
    )

    # Build list of PDF rows with values and sections
    # Track mapping from prompt row number → original row index
    row_num_to_original_idx: dict[int, int] = {}
    rows_str = ""
    prompt_row_num = 0

    for orig_idx, row in enumerate(table_rows):
        if orig_idx in exclude_row_indices:
            continue
        if not row:
            continue

        label = str(row[0]).strip()
        if not label:
            continue

        # Skip total rows
        if _is_total_row(label):
            continue

        # Get value
        value = ""
        if year_column is not None and year_column < len(row):
            value = str(row[year_column]).strip()
        elif len(row) > 1:
            for cell in reversed(row[1:]):
                cell_str = str(cell).strip()
                if cell_str and _is_numeric_value(cell_str):
                    value = cell_str
                    break

        if not value:
            continue

        # Get section
        pdf_section = _get_row_section(row, table_headers)

        prompt_row_num += 1
        row_num_to_original_idx[prompt_row_num] = orig_idx
        section_str = f" [{pdf_section}]" if pdf_section else ""
        rows_str += f"  Row {prompt_row_num}: {label}{section_str} => {value}\n"

    if not rows_str:
        return [], set()

    # Statement type description for context
    statement_desc = {
        "balance_sheet": "Balance Sheet (Assets, Equity, and Liabilities)",
        "profit_and_loss": "Statement of Profit and Loss (Income and Expenses)",
        "cash_flow": "Cash Flow Statement",
        "notes": "Notes to Accounts - Other Financial Information",
    }.get(statement_type, statement_type)

    # Build section context for the prompt — helps LLM disambiguate
    section_context = ""
    if statement_type == "balance_sheet":
        section_context = """
CRITICAL SECTION RULES for Balance Sheet:
- "Borrowings" under [Non-current liabilities] → "(i) Borrowings" (NC section)
- "Borrowings" under [Current liabilities] → "(i) Borrowings" (Current section)
- "Trade payables" under [Current liabilities] → "(ii) Trade payables" (Current, lowercase p)
- "Trade Payables" under [Non-current liabilities] → "(ii) Trade Payables" (NC, uppercase P)
- "Financial Assets" under [Non-current assets] → map to sub-items (i)-(iv)
- "Financial Assets" under [Current assets] → map to sub-items (i)-(vi)
- "Provisions" under [Non-current liabilities] → "(b) Provisions"
- "Provisions" under [Current liabilities] → "(c) Provisions"
- "Other financial liabilities" under NC → "(iii) Other financial liabilities" (NC)
- "Other financial liabilities" under Current → "(iii) Other financial liabilities" (Current)
- "Investments" under [Non-current assets] → "(i) Investments" (NC)
- "Investments" under [Current assets] → "(i) Investments" (Current)
- "Loans" under [Non-current assets] → "(iii) Loans" (NC)
- "Loans" under [Current assets] → "(v) Loans" (Current)
"""
    elif statement_type == "cash_flow" or statement_type == "notes":
        section_context = """
CRITICAL for Cash Flow / Notes:
- Only map to items in the "Other Financial Information" section.
- Do NOT map P&L items like "Finance costs", "Depreciation", "Employee benefits" here.
- Do NOT map BS items like "Borrowings", "Trade payables" here.
- "Finance cost" in CF/Notes context → NOT a valid OFI item. Skip it.
- "Interest expense" → NOT a valid OFI item. Skip it.
- "Taxes paid" → NOT a valid OFI item. Skip it.
- Valid OFI items include: Contingent Liabilities, Current maturities, Power and fuel,
  Bad Debts, Auditors Remunerations, RP items, Advance from Customers, etc.
"""

    prompt = f"""You are a financial data mapping assistant for Indian company annual reports following Schedule III of the Companies Act, 2013.

Statement type: {statement_desc}

Map the PDF table rows to the UNMATCHED template line items below. These are items that keyword aliases could not match deterministically.

UNMATCHED template items (map ONLY to these — do NOT invent items):
{template_str}

PDF table rows:
{rows_str}

RULES:
1. Map each template item to the BEST matching PDF row by semantic equivalence.
2. Use SECTION context — e.g., "Borrowings" under "Non-current liabilities" is different from "Borrowings" under "Current liabilities".
3. Handle abbreviations: PPE = Property Plant and Equipment, CWIP = Capital work-in-progress, ROU = Right of Use, etc.
4. Handle Indian terminology: "Tangible Assets" maps to "(a) Property, Plant and Equipment", "Finance Cost" maps to "Finance costs", etc.
5. Only map items you are CONFIDENT about (confidence >= 0.5). Skip uncertain matches.
6. Do NOT map to formula/total rows — these are computed by Excel formulas.
7. Each PDF row maps to at most ONE template item.
8. CRITICAL: The "template_item" field MUST be an EXACT name from the UNMATCHED template items list above. Do NOT invent, modify, or guess template item names.
9. Do NOT map a PDF row to a template item if the row's section doesn't match the template item's section. For example, do NOT map a "Current liabilities" row to a "Non-current liabilities" template item.
10. If no PDF row clearly matches a template item, simply omit it from the response. It is better to leave an item unmapped than to force a wrong mapping.
{section_context}
Respond in JSON:
{{
    "mappings": [
        {{
            "template_item": "<EXACT template item name from the list above>",
            "row_number": <row number from PDF rows list>,
            "value": "<numeric value from the PDF row>",
            "confidence": <0.5 to 1.0>
        }}
    ]
}}"""

    try:
        response = llm_call_with_retry(llm, prompt, max_retries=2)
        if not response:
            logger.warning("LLM mapping: no response received")
            return [], set()

        # Log raw response for debugging (truncated to avoid log spam)
        logger.info(f"LLM mapping raw response ({len(response)} chars): {response[:500]}...")
        
        # Step 1: Strip markdown code fences FIRST (LLMs often wrap JSON in ```json...```)
        # This must happen BEFORE truncation check, otherwise the trailing backticks
        # cause the truncation detector to falsely trigger and corrupt the JSON.
        response_clean = response.strip()
        fence_patterns = [
            r'^```(?:json)?\s*\n?(.*?)\n?\s*```$',  # Entire response wrapped
            r'```(?:json)?\s*\n?(.*?)\n?\s*```',     # Fences somewhere in response
        ]
        for pattern in fence_patterns:
            import re as _re
            match = _re.search(pattern, response_clean, _re.DOTALL)
            if match:
                response_clean = match.group(1).strip()
                logger.debug(f"LLM mapping: stripped markdown code fences from response")
                break
        
        # Step 2: Check if the CLEANED response looks truncated (no closing brace/bracket)
        response_stripped = response_clean.rstrip()
        if response_stripped and response_stripped[-1] not in ('}', ']'):
            logger.warning(
                f"LLM mapping: response appears truncated (ends with '{response_stripped[-20:]}'), "
                f"attempting repair"
            )
            # Try to repair by finding the last complete mapping object
            # and closing the JSON structure
            last_mapping_end = response_stripped.rfind('}')
            if last_mapping_end > 0:
                # Truncate to last complete mapping and close the array+object
                repaired = response_stripped[:last_mapping_end + 1] + ']}'
                logger.info(f"LLM mapping: repaired truncated response (kept {last_mapping_end + 1} chars)")
                result = extract_json_from_response(repaired)
            else:
                result = None
        else:
            # Parse JSON response normally
            result = extract_json_from_response(response_clean)
        
        if not result:
            logger.warning(
                f"LLM mapping: could not parse JSON from response "
                f"(first 300 chars: {response[:300]})"
            )
            return [], set()

        # Extract mappings from response
        raw_mappings = []
        if isinstance(result, dict) and "mappings" in result:
            raw_mappings = result["mappings"]
        elif isinstance(result, list):
            raw_mappings = result

        logger.info(f"LLM mapping: parsed {len(raw_mappings)} raw mappings from LLM response")
        if not raw_mappings:
            logger.warning("LLM mapping: no mappings in response")
            return [], set()

        # Build MappingResult objects
        results: list[MappingResult] = []
        matched_row_indices: set[int] = set()

        # Build lookup for unmapped items
        unmapped_lookup = {label: section for section, label in unmapped_items}

        # Track which template items have been mapped (to avoid duplicates)
        mapped_template_items: set[str] = set()

        for m in raw_mappings:
            if not isinstance(m, dict):
                continue

            template_item = m.get("template_item", "")
            row_number = m.get("row_number", 0)
            value = str(m.get("value", ""))
            confidence = float(m.get("confidence", 0.75))

            # --- Confidence threshold filtering ---
            # Skip low-confidence mappings to reduce hallucinations
            if confidence < 0.5:
                logger.info(
                    f"LLM mapping: skipping low-confidence mapping "
                    f"'{template_item}' (confidence={confidence:.2f} < 0.5)"
                )
                continue

            # Validate template item (fuzzy match to handle LLM dropping prefixes)
            matched_key = _fuzzy_match_template_item(template_item, unmapped_lookup)
            if matched_key is None:
                logger.info(f"LLM mapping: skipping unresolvable template item '{template_item}'")
                continue
            # Use the matched key (exact template name) from now on
            template_item = matched_key

            # Skip if already mapped (duplicate in LLM response)
            if template_item in mapped_template_items:
                continue

            # Skip formula items (double-check)
            if template_item in FORMULA_TEMPLATE_ITEMS:
                continue

            # Map row number back to original index
            orig_idx = None
            if isinstance(row_number, int) and row_number in row_num_to_original_idx:
                orig_idx = row_num_to_original_idx[row_number]

            # --- Value cross-validation ---
            # Verify LLM's claimed value matches the actual extracted row value.
            # If mismatch, use the actual extracted value (more trustworthy).
            if orig_idx is not None and orig_idx < len(table_rows):
                actual_value = ""
                if year_column is not None and year_column < len(table_rows[orig_idx]):
                    actual_value = str(table_rows[orig_idx][year_column]).strip()
                if actual_value and value and actual_value != value:
                    # Normalize both for comparison (remove commas, spaces, parens)
                    norm_actual = actual_value.replace(",", "").replace(" ", "").strip()
                    norm_llm = value.replace(",", "").replace(" ", "").strip()
                    if norm_actual != norm_llm:
                        logger.info(
                            f"LLM mapping: value mismatch for '{template_item}': "
                            f"LLM says '{value}', actual row value is '{actual_value}' "
                            f"— using actual"
                        )
                        value = actual_value

            # Get PDF row label from original table
            pdf_row_label = ""
            if orig_idx is not None and orig_idx < len(table_rows):
                pdf_row_label = str(table_rows[orig_idx][0]).strip()
            elif value:
                # Fallback: try to find by value match
                for row in table_rows:
                    if row:
                        row_label = str(row[0]).strip()
                        row_value = ""
                        if year_column is not None and year_column < len(row):
                            row_value = str(row[year_column]).strip()
                        if row_value == value and row_label:
                            pdf_row_label = row_label
                            break

            section = unmapped_lookup[template_item]

            results.append(MappingResult(
                template_item=template_item,
                section=section,
                pdf_row_label=pdf_row_label,
                value=value,
                confidence=min(confidence, 0.90),  # Cap at 0.90 (alias is 0.85)
                method="llm",
            ))

            if orig_idx is not None:
                matched_row_indices.add(orig_idx)

            mapped_template_items.add(template_item)

            logger.info(
                f"LLM mapping: '{pdf_row_label}' -> '{template_item}' "
                f"(value={value}, confidence={confidence:.2f})"
            )

        logger.info(f"LLM mapping: {len(results)} items mapped via LLM")
        return results, matched_row_indices

    except Exception as e:
        logger.error(f"LLM mapping failed: {e}")
        return [], set()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def _apply_keyword_aliases(
    table_headers: list[str],
    table_rows: list[list[str]],
    keyword_aliases: dict,
    template: dict,
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
) -> list[MappingResult]:
    """
    Apply keyword alias matching as a pre-pass before fuzzy matching.
    
    Handles cases where multiple PDF rows map to the same template item
    by summing their numeric values.
    
    Args:
        table_headers: Column headers from the extracted table.
        table_rows: Data rows from the extracted table.
        keyword_aliases: Dict mapping normalized_substring -> (template_item, section).
        template: The template dict for looking up item names.
        year_column: Which column index contains the values.
    
    Returns:
        List of MappingResult objects for alias-matched items.
    """
    if year_column is None:
        year_column = _detect_year_column(table_headers, target_year=target_year)
    
    # Collect (template_item, section) -> list of (row_label, value)
    alias_matches: dict[tuple[str, str], list[tuple[str, str]]] = {}
    matched_row_indices: set[int] = set()
    
    for row_idx, row in enumerate(table_rows):
        if not row:
            continue
        
        row_label = str(row[0]).strip()
        if not row_label:
            continue
        
        # Skip total rows
        if _is_total_row(row_label):
            continue
        
        # Get value
        value = ""
        if year_column is not None and year_column < len(row):
            value = str(row[year_column]).strip()
        elif len(row) > 1:
            for cell in reversed(row[1:]):
                cell_str = str(cell).strip()
                if cell_str and _is_numeric_value(cell_str):
                    value = cell_str
                    break
        
        if not value:
            continue
        
        # Check keyword aliases
        label_lower = _normalize_text(row_label)
        for alias_key, (template_item, section) in keyword_aliases.items():
            if alias_key in label_lower:
                key = (template_item, section)
                alias_matches.setdefault(key, []).append((row_label, value))
                matched_row_indices.add(row_idx)
                logger.debug(
                    f"Keyword alias: '{row_label}' -> '{template_item}' "
                    f"(alias='{alias_key}', value={value})"
                )
                break
    
    # Build results, aggregating values for same template item
    results = []
    for (template_item, section), row_items in alias_matches.items():
        if len(row_items) == 1:
            # Single match — use value directly
            row_label, value = row_items[0]
            results.append(MappingResult(
                template_item=template_item,
                section=section,
                pdf_row_label=row_label,
                value=value,
                confidence=0.85,
                method="keyword_alias",
            ))
        else:
            # Multiple matches — sum the values
            total = 0.0
            labels = []
            for row_label, value_str in row_items:
                parsed = _parse_alias_value(value_str)
                total += parsed
                labels.append(row_label)
            
            results.append(MappingResult(
                template_item=template_item,
                section=section,
                pdf_row_label=" + ".join(labels),
                value=f"{total:,.2f}" if total != int(total) else f"{total:,.0f}",
                confidence=0.80,
                method="keyword_alias_aggregated",
            ))
            logger.info(
                f"Aggregated {len(row_items)} rows -> '{template_item}': "
                f"{', '.join(f'{l}={v}' for l, v in row_items)} = {total:,.2f}"
            )
    
    return results, matched_row_indices


def _parse_alias_value(value_str: str) -> float:
    """Parse a numeric value from an alias match."""
    s = value_str.strip()
    if s.lower() in ("nil", "na", "n.a.", "n/a", "-", "—", "–"):
        return 0.0
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-") or s.startswith("−") or s.startswith("–"):
        is_negative = True
        s = s[1:].strip()
    s = s.replace(",", "").replace(" ", "")
    try:
        val = float(s)
        return -val if is_negative else val
    except ValueError:
        return 0.0


def _merge_alias_and_fuzzy(
    alias_results: list[MappingResult],
    fuzzy_results: list[MappingResult],
) -> list[MappingResult]:
    """
    Merge alias and fuzzy results, with parent-child deduplication.
    
    When a keyword alias and a fuzzy match both map to the same template
    item, there are two possible scenarios:
    
    1. PARENT-CHILD: The fuzzy match is a "parent" row (e.g., "Property,
       plant & equipment" = 6,714.71) and the alias is a "child" (e.g.,
       "Tangible Assets" = 6,527.97). The parent's value already includes
       the child's value, so summing would double-count. Solution: keep
       the child's value (more specific), discard the parent's.
    
    2. COMPLEMENTARY: Both values are independent components that should
       be summed (e.g., "Sub-contractor cost" alias + "Other expenses"
       exact match both mapping to "Other expenses").
    
    Parent detection uses _PARENT_ROW_PATTERNS — normalized substrings
    that identify parent/section-header rows whose value equals the sum
    of their children.
    """
    # Build lookup: template_item -> alias result
    alias_by_item: dict[str, MappingResult] = {}
    for r in alias_results:
        alias_by_item[r.template_item] = r
    
    combined = list(alias_results)
    
    for r in fuzzy_results:
        if r.template_item in alias_by_item:
            existing = alias_by_item[r.template_item]
            
            # Check if this is a parent-child relationship
            fuzzy_label_norm = _normalize_text(r.pdf_row_label)
            alias_label_norm = _normalize_text(existing.pdf_row_label)
            
            fuzzy_is_parent = any(
                pat in fuzzy_label_norm for pat in _PARENT_ROW_PATTERNS
            )
            alias_is_parent = any(
                pat in alias_label_norm for pat in _PARENT_ROW_PATTERNS
            )
            
            if fuzzy_is_parent and not alias_is_parent:
                # Fuzzy match is a parent, alias is a child — prefer child
                # The parent's value already includes the child's value
                logger.info(
                    f"Parent-child dedup: keeping alias (child) value for "
                    f"'{r.template_item}': '{existing.pdf_row_label}'="
                    f"{existing.value}, discarding fuzzy (parent) "
                    f"'{r.pdf_row_label}'={r.value}"
                )
                # Keep existing alias result as-is (don't add fuzzy)
                
            elif alias_is_parent and not fuzzy_is_parent:
                # Alias is a parent, fuzzy is a child — prefer child (fuzzy)
                logger.info(
                    f"Parent-child dedup: keeping fuzzy (child) value for "
                    f"'{r.template_item}': '{r.pdf_row_label}'="
                    f"{r.value}, discarding alias (parent) "
                    f"'{existing.pdf_row_label}'={existing.value}"
                )
                # Replace alias result with fuzzy (child) result
                existing.value = r.value
                existing.pdf_row_label = r.pdf_row_label
                existing.confidence = r.confidence
                existing.method = "child_preferred_over_parent"
                
            else:
                # Not a parent-child case — aggregate (sum) values
                alias_val = _parse_alias_value(existing.value)
                fuzzy_val = _parse_alias_value(r.value)
                total = alias_val + fuzzy_val
                
                # Update the existing result with aggregated value
                existing.value = f"{total:,.2f}" if total != int(total) else f"{total:,.0f}"
                existing.pdf_row_label = f"{existing.pdf_row_label} + {r.pdf_row_label}"
                existing.method = "alias+fuzzy_aggregated"
                
                logger.info(
                    f"Aggregated alias+fuzzy for '{r.template_item}': "
                    f"alias={alias_val:,.2f} + fuzzy={fuzzy_val:,.2f} = {total:,.2f}"
                )
        else:
            # No conflict — add fuzzy result
            combined.append(r)
    
    return combined


def _merge_alias_llm_and_fuzzy(
    alias_results: list[MappingResult],
    llm_results: list[MappingResult],
    fuzzy_results: list[MappingResult],
) -> list[MappingResult]:
    """
    Merge alias, LLM, and fuzzy results with parent-child deduplication.
    
    LLM-first strategy: Priority order when multiple methods map the same
    template item is: alias > LLM > fuzzy.
    
    Rationale:
        - Keyword aliases are deterministic and highest confidence (0.85)
        - LLM understands semantics but may hallucinate (capped at 0.90)
        - Fuzzy matching is purely textual similarity (lowest reliability)
    
    Parent-child deduplication is applied across all three sources:
        - If alias and LLM conflict: prefer alias (deterministic)
        - If LLM and fuzzy conflict: prefer LLM (semantic understanding)
        - If alias and fuzzy conflict: apply existing parent-child logic
        - If all three conflict: prefer alias > LLM > fuzzy
    
    Complementary values (different PDF rows mapping to the same template
    item) are summed when there's no parent-child relationship.
    """
    # Build lookups: template_item -> result for each method
    alias_by_item: dict[str, MappingResult] = {}
    for r in alias_results:
        alias_by_item[r.template_item] = r
    
    llm_by_item: dict[str, MappingResult] = {}
    for r in llm_results:
        llm_by_item[r.template_item] = r
    
    # Start with alias results as the base
    combined = list(alias_results)
    
    # Helper: check if a result's PDF label is a "parent" row
    def _is_parent(result: MappingResult) -> bool:
        label_norm = _normalize_text(result.pdf_row_label)
        return any(pat in label_norm for pat in _PARENT_ROW_PATTERNS)
    
    # Merge LLM results
    for r in llm_results:
        if r.template_item in alias_by_item:
            # Conflict: alias and LLM both map this item
            existing = alias_by_item[r.template_item]
            
            alias_is_parent = _is_parent(existing)
            llm_is_parent = _is_parent(r)
            
            if alias_is_parent and not llm_is_parent:
                # Alias is parent, LLM is child — prefer LLM (child)
                logger.info(
                    f"3-way merge: alias is parent, LLM is child for "
                    f"'{r.template_item}' — preferring LLM child "
                    f"'{r.pdf_row_label}'={r.value} over alias parent "
                    f"'{existing.pdf_row_label}'={existing.value}"
                )
                existing.value = r.value
                existing.pdf_row_label = r.pdf_row_label
                existing.confidence = r.confidence
                existing.method = "child_preferred_over_parent"
            elif llm_is_parent and not alias_is_parent:
                # LLM is parent, alias is child — prefer alias (child, deterministic)
                logger.info(
                    f"3-way merge: LLM is parent, alias is child for "
                    f"'{r.template_item}' — keeping alias child "
                    f"'{existing.pdf_row_label}'={existing.value}"
                )
                # Keep alias as-is
            else:
                # No parent-child — prefer alias (deterministic) over LLM
                logger.info(
                    f"3-way merge: alias+LLM conflict on '{r.template_item}' "
                    f"— keeping alias (deterministic) "
                    f"'{existing.pdf_row_label}'={existing.value}, "
                    f"discarding LLM '{r.pdf_row_label}'={r.value}"
                )
                # Keep alias as-is
            
        else:
            # No alias conflict — add LLM result
            combined.append(r)
    
    # Merge fuzzy results
    # Build current lookup (alias + LLM combined)
    current_by_item: dict[str, MappingResult] = {}
    for r in combined:
        current_by_item[r.template_item] = r
    
    for r in fuzzy_results:
        if r.template_item in current_by_item:
            existing = current_by_item[r.template_item]
            
            existing_is_parent = _is_parent(existing)
            fuzzy_is_parent = _is_parent(r)
            
            if fuzzy_is_parent and not existing_is_parent:
                # Fuzzy is parent, existing is child — prefer child
                logger.info(
                    f"3-way merge: fuzzy is parent, existing ({existing.method}) is child "
                    f"for '{r.template_item}' — keeping existing child "
                    f"'{existing.pdf_row_label}'={existing.value}"
                )
                # Keep existing as-is
            elif existing_is_parent and not fuzzy_is_parent:
                # Existing is parent, fuzzy is child — prefer child (fuzzy)
                logger.info(
                    f"3-way merge: existing ({existing.method}) is parent, fuzzy is child "
                    f"for '{r.template_item}' — preferring fuzzy child "
                    f"'{r.pdf_row_label}'={r.value}"
                )
                existing.value = r.value
                existing.pdf_row_label = r.pdf_row_label
                existing.confidence = r.confidence
                existing.method = "child_preferred_over_parent"
            else:
                # No parent-child — existing (alias or LLM) takes priority over fuzzy
                logger.info(
                    f"3-way merge: fuzzy conflicts with {existing.method} on "
                    f"'{r.template_item}' — keeping {existing.method} "
                    f"'{existing.pdf_row_label}'={existing.value}, "
                    f"discarding fuzzy '{r.pdf_row_label}'={r.value}"
                )
                # Keep existing as-is
        else:
            # No conflict — add fuzzy result
            combined.append(r)
    
    return combined


def map_balance_sheet(
    table_headers: list[str],
    table_rows: list[list[str]],
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
    llm=None,
) -> list[MappingResult]:
    """
    Map extracted table data to Balance Sheet template.
    
    Strategy (LLM-first for accuracy):
        1. KEYWORD ALIASES: Deterministic pre-pass for known label variations
        2. LLM MAPPING: Primary method — understands semantics, sections, abbreviations
        3. FUZZY MATCHING: Fallback for items LLM couldn't map
    """
    # Step 1: Keyword alias matching (deterministic, fastest)
    alias_results, alias_row_indices = _apply_keyword_aliases(
        table_headers, table_rows, BS_KEYWORD_ALIASES,
        BALANCE_SHEET_TEMPLATE, year_column, target_year=target_year,
    )
    
    # Step 2: LLM mapping (PRIMARY — if LLM available)
    llm_results: list[MappingResult] = []
    llm_row_indices: set[int] = set()
    if llm is not None:
        already_mapped = {r.template_item for r in alias_results}
        llm_results, llm_row_indices = map_by_llm(
            table_headers, table_rows, BALANCE_SHEET_TEMPLATE,
            already_mapped, llm, "balance_sheet",
            year_column=year_column, target_year=target_year,
            exclude_row_indices=alias_row_indices,
        )
        if llm_results:
            logger.info(
                f"Balance Sheet LLM: mapped {len(llm_results)} items via LLM"
            )
    
    # Step 3: Fuzzy matching (FALLBACK — for items not mapped by alias or LLM)
    exclude_rows = alias_row_indices | llm_row_indices
    remaining_rows = [
        row for i, row in enumerate(table_rows)
        if i not in exclude_rows
    ]
    fuzzy_results = map_table_to_template(
        table_headers, remaining_rows, BALANCE_SHEET_TEMPLATE,
        min_confidence=0.6, year_column=year_column, target_year=target_year,
    )
    
    # Step 4: Merge all three (alias > LLM > fuzzy priority)
    if llm_results:
        return _merge_alias_llm_and_fuzzy(alias_results, llm_results, fuzzy_results)
    else:
        return _merge_alias_and_fuzzy(alias_results, fuzzy_results)


def map_profit_and_loss(
    table_headers: list[str],
    table_rows: list[list[str]],
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
    llm=None,
) -> list[MappingResult]:
    """
    Map extracted table data to P&L template.
    
    Strategy (LLM-first for accuracy):
        1. KEYWORD ALIASES: Deterministic pre-pass for known label variations
        2. LLM MAPPING: Primary method — understands semantics, sections, abbreviations
        3. FUZZY MATCHING: Fallback for items LLM couldn't map
    """
    # Step 1: Keyword alias matching (deterministic, fastest)
    alias_results, alias_row_indices = _apply_keyword_aliases(
        table_headers, table_rows, PL_KEYWORD_ALIASES,
        PL_TEMPLATE, year_column, target_year=target_year,
    )
    
    # Step 2: LLM mapping (PRIMARY — if LLM available)
    llm_results: list[MappingResult] = []
    llm_row_indices: set[int] = set()
    if llm is not None:
        already_mapped = {r.template_item for r in alias_results}
        llm_results, llm_row_indices = map_by_llm(
            table_headers, table_rows, PL_TEMPLATE,
            already_mapped, llm, "profit_and_loss",
            year_column=year_column, target_year=target_year,
            exclude_row_indices=alias_row_indices,
        )
        if llm_results:
            logger.info(
                f"P&L LLM: mapped {len(llm_results)} items via LLM"
            )
    
    # Step 3: Fuzzy matching (FALLBACK — for items not mapped by alias or LLM)
    exclude_rows = alias_row_indices | llm_row_indices
    remaining_rows = [
        row for i, row in enumerate(table_rows)
        if i not in exclude_rows
    ]
    fuzzy_results = map_table_to_template(
        table_headers, remaining_rows, PL_TEMPLATE,
        min_confidence=0.6, year_column=year_column, target_year=target_year,
    )
    
    # Step 4: Merge all three (alias > LLM > fuzzy priority)
    if llm_results:
        return _merge_alias_llm_and_fuzzy(alias_results, llm_results, fuzzy_results)
    else:
        return _merge_alias_and_fuzzy(alias_results, fuzzy_results)


def _structural_cf_match(
    table_rows: list[list[str]],
    year_column: Optional[int] = None,
) -> list[MappingResult]:
    """
    Use structural pattern matching to find CF summary rows.
    
    In Indian annual reports, the CF statement always has summary rows
    following the pattern:
        "Net cash flow generated from / (used in) operating activities"
        "Net cash flow (used in) investing activities"
        "Net cash flow (used in) financing activities"
    
    These are the ONLY rows that start with "Net cash". We find rows
    containing "net ca" (fuzzy-tolerant for CID-decoded "net cash")
    and assign them in order: Operations → Investing → Financing.
    
    This approach is more reliable than word-level fuzzy matching on
    CID-fragmented text where "investing" might become "infie ting".
    """
    CF_SUMMARY_ORDER = [
        "Cash Flows From Operations",
        "Cash Flows From Investing",
        "Cash Flows From Financing",
    ]
    
    # Find rows that look like CF summary rows
    # Key indicator: contains "net ca" (CID-tolerant form of "net cash")
    summary_rows = []
    
    for row in table_rows:
        if not row:
            continue
        
        row_label = str(row[0]).strip()
        if not row_label:
            continue
        
        # Strip CID placeholders and normalize
        label_clean = _CID_PLACEHOLDER_RE.sub(' ', row_label).lower()
        label_clean = re.sub(r'\s+', ' ', label_clean).strip()
        
        # Check if this row looks like a CF summary row
        # Must contain "net ca" (for "net cash") - the universal CF summary indicator
        is_net_cash_row = False
        
        # Exact substring: "net ca" survives most CID decodings
        if "net ca" in label_clean:
            is_net_cash_row = True
        # Fuzzy fallback: check if "net cash" fuzzy-matches start of label
        elif fuzz.token_sort_ratio(label_clean[:20], "net cash") >= 70:
            is_net_cash_row = True
        
        if not is_net_cash_row:
            continue
        
        # Get value
        value = ""
        if year_column is not None and year_column < len(row):
            value = str(row[year_column]).strip()
        elif len(row) > 1:
            for cell in reversed(row[1:]):
                cell_str = str(cell).strip()
                if cell_str and _is_numeric_value(cell_str):
                    value = cell_str
                    break
        
        if not value:
            continue
        
        summary_rows.append((row_label, value))
    
    # Assign summary rows in order: Operations, Investing, Financing
    results = []
    for i, (row_label, value) in enumerate(summary_rows):
        if i >= len(CF_SUMMARY_ORDER):
            break  # More summary rows than expected
        
        results.append(MappingResult(
            template_item=CF_SUMMARY_ORDER[i],
            section="Cash Flow",
            pdf_row_label=row_label,
            value=value,
            confidence=0.85,
            method="structural",
        ))
        logger.debug(
            f"CF Structural: '{row_label[:60]}' -> '{CF_SUMMARY_ORDER[i]}' "
            f"(value={value}, order={i+1})"
        )
    
    return results


def _fuzzy_alias_match(label_clean: str, alias_key: str, threshold: int = 70) -> bool:
    """
    Check if a cleaned label matches an alias key, using both exact substring
    and fuzzy matching. This handles CID-fragmented text where placeholders
    break words (e.g., "operat ing" matching "operating").
    
    Args:
        label_clean: Lowercase, CID-stripped, whitespace-collapsed label text.
        alias_key: Lowercase alias phrase to match against.
        threshold: Minimum fuzzy score (0-100) for token_sort_ratio.
    
    Returns:
        True if the label matches the alias.
    """
    # 1. Exact substring match (fast path)
    if alias_key in label_clean:
        return True
    
    # 2. Fuzzy match on the full label vs alias
    score = fuzz.token_sort_ratio(label_clean, alias_key)
    if score >= threshold:
        return True
    
    # 3. For short anchor aliases (single word like "operating", "investing",
    #    "financing"), check if any word in the label fuzzy-matches the anchor.
    #    This handles cases like "operat" matching "operating" when CID
    #    placeholders fragment the word.
    if ' ' not in alias_key:
        label_words = label_clean.split()
        for word in label_words:
            if len(word) < 3:
                continue
            word_score = fuzz.ratio(word, alias_key)
            if word_score >= 75:
                return True
    
    return False


def map_cash_flow(
    table_headers: list[str],
    table_rows: list[list[str]],
    year_column: Optional[int] = None,
    target_year: Optional[int] = None,
    llm=None,
) -> list[MappingResult]:
    """
    Map extracted table data to Cash Flow template.
    
    The CF template has only 3 summary items (Operations, Investing, Financing)
    plus "Other Financial Information" items. The PDF CF statement has detailed
    line items.
    
    Strategy (LLM-first for accuracy):
        0. STRUCTURAL: Find "Net cash" rows and assign in order (Ops→Invest→Finance).
           Most reliable for CID-fragmented text since it only needs "net ca" to match.
        1. ALIAS: Use CF_PHRASE_ALIASES and CF_ANCHOR_ALIASES with fuzzy matching.
           Good for non-CID text or well-decoded text.
        2. LLM: Primary method for "Other Financial Information" items — understands
           semantics and note context that fuzzy cannot.
        3. FUZZY: Fallback for items LLM couldn't map.
    """
    # Auto-detect year column if not specified
    if year_column is None:
        year_column = _detect_year_column(table_headers, target_year=target_year)
    
    results: list[MappingResult] = []
    matched_aliases: set[str] = set()  # Track which alias groups already matched
    
    # Phase 0: Structural matching — find "Net cash" summary rows in order
    structural_results = _structural_cf_match(table_rows, year_column)
    if structural_results:
        for r in structural_results:
            matched_aliases.add(r.template_item)
            results.append(r)
        logger.info(
            f"CF Structural: found {len(structural_results)} summary items "
            f"({', '.join(r.template_item for r in structural_results)})"
        )
    
    # Phase 1a: Use CF_PHRASE_ALIASES for any still-unmatched summary items
    if len(matched_aliases) < 3:
        sorted_phrases = sorted(CF_PHRASE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
        
        for row in table_rows:
            if not row:
                continue
            
            row_label = str(row[0]).strip()
            if not row_label:
                continue
            
            label_clean = _CID_PLACEHOLDER_RE.sub(' ', row_label).lower()
            label_clean = re.sub(r'\s+', ' ', label_clean).strip()
            
            value = ""
            if year_column is not None and year_column < len(row):
                value = str(row[year_column]).strip()
            elif len(row) > 1:
                for cell in reversed(row[1:]):
                    cell_str = str(cell).strip()
                    if cell_str and _is_numeric_value(cell_str):
                        value = cell_str
                        break
            
            if not value:
                continue
            
            for alias_key, template_item in sorted_phrases:
                if template_item in matched_aliases:
                    continue
                
                if _fuzzy_alias_match(label_clean, alias_key):
                    section = "Cash Flow"
                    matched_aliases.add(template_item)
                    results.append(MappingResult(
                        template_item=template_item,
                        section=section,
                        pdf_row_label=row_label,
                        value=value,
                        confidence=0.9,
                        method="alias",
                    ))
                    logger.debug(
                        f"CF Phrase Alias: '{row_label}' -> '{template_item}' "
                        f"(alias='{alias_key}', value={value})"
                    )
                    break
    
    # Phase 1b: Use CF_ANCHOR_ALIASES for any still-unmatched summary items
    if len(matched_aliases) < 3:
        for row in table_rows:
            if not row:
                continue
            
            row_label = str(row[0]).strip()
            if not row_label:
                continue
            
            label_clean = _CID_PLACEHOLDER_RE.sub(' ', row_label).lower()
            label_clean = re.sub(r'\s+', ' ', label_clean).strip()
            
            value = ""
            if year_column is not None and year_column < len(row):
                value = str(row[year_column]).strip()
            elif len(row) > 1:
                for cell in reversed(row[1:]):
                    cell_str = str(cell).strip()
                    if cell_str and _is_numeric_value(cell_str):
                        value = cell_str
                        break
            
            if not value:
                continue
            
            for anchor_key, template_item in CF_ANCHOR_ALIASES.items():
                if template_item in matched_aliases:
                    continue
                
                if _fuzzy_alias_match(label_clean, anchor_key, threshold=65):
                    section = "Cash Flow"
                    matched_aliases.add(template_item)
                    results.append(MappingResult(
                        template_item=template_item,
                        section=section,
                        pdf_row_label=row_label,
                        value=value,
                        confidence=0.75,
                        method="anchor_alias",
                    ))
                    logger.debug(
                        f"CF Anchor Alias: '{row_label}' -> '{template_item}' "
                        f"(anchor='{anchor_key}', value={value})"
                    )
                    break
    
    # Phase 2: LLM mapping for "Other Financial Information" items (PRIMARY)
    llm_results: list[MappingResult] = []
    llm_row_indices: set[int] = set()
    if llm is not None:
        # Only map OFI items — CF summary items are already handled above
        already_mapped_items = {r.template_item for r in results}
        llm_results, llm_row_indices = map_by_llm(
            table_headers, table_rows, CASH_FLOW_TEMPLATE,
            already_mapped_items, llm, "cash_flow",
            year_column=year_column, target_year=target_year,
        )
        if llm_results:
            logger.info(
                f"CF LLM: mapped {len(llm_results)} OFI items via LLM"
            )
    
    # Phase 3: Fuzzy matching (FALLBACK for items not mapped by structural/alias/LLM)
    fuzzy_results = map_table_to_template(
        table_headers, table_rows, CASH_FLOW_TEMPLATE,
        min_confidence=0.6, year_column=year_column, target_year=target_year,
    )
    
    # Merge: structural+alias results first, then LLM, then fuzzy
    # Structural and alias results are already in `results`
    existing_items = {r.template_item for r in results}
    
    # Add LLM results (skip duplicates)
    for r in llm_results:
        if r.template_item not in existing_items:
            results.append(r)
            existing_items.add(r.template_item)
    
    # Add fuzzy results (skip duplicates — lowest priority)
    for r in fuzzy_results:
        if r.template_item not in existing_items:
            results.append(r)
            existing_items.add(r.template_item)
    
    return results


# ============================================================================
# NOTES EXTRACTION FOR "OTHER FINANCIAL INFORMATION"
# ============================================================================


def _get_value_from_row(
    row: list[str],
    year_column: Optional[int] = None,
    table_headers: list[str] = None,
) -> str:
    """
    Extract a numeric value from a table row.
    
    Tries the year_column first, then falls back to the last numeric column.
    """
    if year_column is not None and year_column < len(row):
        value = str(row[year_column]).strip()
        if value and _is_numeric_value(value):
            return value
    
    # Fallback: last numeric column
    if len(row) > 1:
        for cell in reversed(row[1:]):
            cell_str = str(cell).strip()
            if cell_str and _is_numeric_value(cell_str):
                return cell_str
    
    return ""


def map_notes_to_other_financial_info(
    notes_headers: list[str],
    notes_rows: list[list[str]],
    existing_cf_mappings: list[MappingResult],
    year: Optional[int] = None,
    target_year: Optional[int] = None,
    llm=None,
) -> list[MappingResult]:
    """
    Extract "Other Financial Information" items from Notes to Accounts data.
    
    The CF template's "Other Financial Information" section (rows 7-25) contains
    items that are NOT found in the Cash Flow statement itself — they come from
    specific notes in the Notes to Accounts section of the annual report:
    
        - Contingent Liabilities → Note "Contingent liabilities and commitments"
        - Current maturities → Note "Borrowings"
        - Power and fuel → Note "Other expenses"
        - Bad debts → Note "Other expenses"
        - Auditors Remuneration → Note "Auditors' Remuneration"
        - RP items → Note "Related party disclosures"
        etc.
    
    Strategy (LLM-first for accuracy):
        Phase 1: KEYWORD ALIAS — Search all notes rows for NOTES_KEYWORD_ALIASES
                 matches. Deterministic and fastest.
        Phase 2: CONTEXT-AWARE TOTAL — For items like Contingent Liabilities
                 where the total row may just say "Total" within a contingent
                 liabilities note, detect the note context and find the total.
        Phase 3: LLM MAPPING — Primary method for remaining unmatched items.
                 LLM understands note context, abbreviations, and semantics.
        Phase 4: FUZZY FALLBACK — For any still-unmatched items, use fuzzy
                 matching against the "Other Financial Information" template items.
    
    Args:
        notes_headers: Column headers from the extracted notes table.
        notes_rows: Data rows from the extracted notes table (tabular format).
        existing_cf_mappings: Existing CF mapping results (to avoid duplicates).
        year: Financial year (for year column detection).
        target_year: The detected financial year.
        llm: LangChain ChatOpenAI instance for LLM mapping.
    
    Returns:
        List of MappingResult objects for "Other Financial Information" items.
    """
    if not notes_rows:
        return []
    
    # Auto-detect year column
    year_column = _detect_year_column(notes_headers, target_year=target_year or year)
    
    # Track which template items are already mapped by the CF statement.
    # Only consider items in the "Other Financial Information" section that
    # have real (non-formula) mappings. Notes extraction can override
    # placeholder values if needed.
    already_mapped = {
        r.template_item for r in existing_cf_mappings
        if r.section == "Other Financial Information"
    }
    
    results: list[MappingResult] = []
    mapped_items: set[str] = set(already_mapped)  # Start with already-mapped items
    
    # ========================================================================
    # Phase 1: Keyword alias matching across all notes rows
    # ========================================================================
    # Alias matches: (template_item, section) -> list of (row_label, value)
    alias_matches: dict[tuple[str, str], list[tuple[str, str]]] = {}
    matched_row_indices: set[int] = set()
    
    for row_idx, row in enumerate(notes_rows):
        if not row:
            continue
        
        row_label = str(row[0]).strip()
        if not row_label:
            continue
        
        label_lower = _normalize_text(row_label)
        
        # Get value
        value = _get_value_from_row(row, year_column, notes_headers)
        if not value:
            continue
        
        # Check NOTES_KEYWORD_ALIASES
        for alias_key, (template_item, section) in NOTES_KEYWORD_ALIASES.items():
            if template_item in mapped_items:
                continue
            
            if alias_key in label_lower:
                key = (template_item, section)
                alias_matches.setdefault(key, []).append((row_label, value))
                matched_row_indices.add(row_idx)
                logger.debug(
                    f"Notes alias: '{row_label}' -> '{template_item}' "
                    f"(alias='{alias_key}', value={value})"
                )
                break
    
    # Build results from alias matches, aggregating values for same template item
    for (template_item, section), row_items in alias_matches.items():
        if template_item in mapped_items:
            continue
        
        if len(row_items) == 1:
            row_label, value = row_items[0]
            results.append(MappingResult(
                template_item=template_item,
                section=section,
                pdf_row_label=row_label,
                value=value,
                confidence=0.85,
                method="notes_alias",
            ))
        else:
            # Multiple matches — sum the values
            total = 0.0
            labels = []
            for row_label, value_str in row_items:
                parsed = _parse_alias_value(value_str)
                total += parsed
                labels.append(row_label)
            
            results.append(MappingResult(
                template_item=template_item,
                section=section,
                pdf_row_label=" + ".join(labels),
                value=f"{total:,.2f}" if total != int(total) else f"{total:,.0f}",
                confidence=0.80,
                method="notes_alias_aggregated",
            ))
            logger.info(
                f"Notes aggregated {len(row_items)} rows -> '{template_item}': "
                f"{', '.join(f'{l}={v}' for l, v in row_items)} = {total:,.2f}"
            )
        
        mapped_items.add(template_item)
    
    # ========================================================================
    # Phase 2: Context-aware total extraction for specific notes
    # ========================================================================
    # Some notes have a "Total" row that represents the value we want, but the
    # label is just "Total" which doesn't match any alias. We need to know the
    # note context to assign the total correctly.
    #
    # Example: In the "Contingent liabilities and commitments" note, the last
    # "Total" row contains the aggregate contingent liability figure.
    #
    # Strategy: Scan backwards from each "Total" row to find if there's a
    # "contingent liab" keyword in the preceding rows (within 15 rows).
    
    _CONTEXT_TOTAL_ITEMS = {
        "Contingent Liabilities": [
            r'contingent\s+liab', r'contingencies\s+and\s+commitments',
        ],
    }
    
    for template_item, note_patterns in _CONTEXT_TOTAL_ITEMS.items():
        if template_item in mapped_items:
            continue  # Already found via alias
        
        # Search for "Total" rows that are preceded by a contingent liabilities note
        for row_idx, row in enumerate(notes_rows):
            if not row:
                continue
            
            row_label = str(row[0]).strip().lower()
            row_label_clean = re.sub(r'\s+', ' ', row_label).strip()
            
            # Check if this is a total row
            is_total = False
            if row_label_clean in ('total', 'aggregate', 'total (a)'):
                is_total = True
            elif re.match(r'^total\s*[\(\[]', row_label_clean):
                is_total = True
            elif re.match(r'^aggregate\s*(of|for)?\s*[\(\[]?', row_label_clean):
                is_total = True
            
            if not is_total:
                continue
            
            # Look backwards for context (within 15 rows)
            context_text = ""
            look_back = max(0, row_idx - 15)
            for prev_idx in range(look_back, row_idx):
                prev_row = notes_rows[prev_idx]
                if prev_row:
                    prev_label = str(prev_row[0]).strip().lower()
                    context_text += " " + prev_label
            
            is_relevant_note = any(
                re.search(pat, context_text) for pat in note_patterns
            )
            
            if not is_relevant_note:
                continue
            
            # Found a total row in a contingent liabilities context
            value = _get_value_from_row(row, year_column, notes_headers)
            if not value:
                continue
            
            results.append(MappingResult(
                template_item=template_item,
                section="Other Financial Information",
                pdf_row_label=str(row[0]).strip(),
                value=value,
                confidence=0.80,
                method="notes_context_total",
            ))
            mapped_items.add(template_item)
            logger.info(
                f"Notes context total: '{str(row[0]).strip()}' -> '{template_item}' "
                f"(value={value})"
            )
            break  # Found the total, stop searching
    
    # ========================================================================
    # Phase 3: LLM mapping for still-unmatched items (PRIMARY)
    # ========================================================================
    llm_results: list[MappingResult] = []
    llm_row_indices: set[int] = set()
    if llm is not None:
        # Build the OFI sub-template for LLM
        ofi_template = {
            "Other Financial Information": CASH_FLOW_TEMPLATE.get("Other Financial Information", {})
        }
        already_mapped_for_llm = mapped_items.copy()
        llm_results, llm_row_indices = map_by_llm(
            notes_headers, notes_rows, ofi_template,
            already_mapped_for_llm, llm, "notes",
            year_column=year_column, target_year=target_year or year,
            exclude_row_indices=matched_row_indices,
        )
        if llm_results:
            logger.info(
                f"Notes LLM: mapped {len(llm_results)} OFI items via LLM"
            )
            for r in llm_results:
                results.append(r)
                mapped_items.add(r.template_item)
    
    # ========================================================================
    # Phase 4: Fuzzy fallback for still-unmatched items
    # ========================================================================
    # Get the "Other Financial Information" template items that are still unmapped
    other_fin_info_items = CASH_FLOW_TEMPLATE.get("Other Financial Information", {})
    unmatched_items = [
        (label, _normalize_text(label))
        for label in other_fin_info_items.keys()
        if label not in mapped_items
    ]
    
    if unmatched_items:
        # Combine alias and LLM matched row indices for exclusion
        all_matched_row_indices = matched_row_indices | llm_row_indices
        
        # For each unmatched template item, try fuzzy matching against all notes rows
        for template_label, norm_template in unmatched_items:
            best_score = 0.0
            best_match = None
            
            for row_idx, row in enumerate(notes_rows):
                if row_idx in all_matched_row_indices:
                    continue  # Skip rows already matched by aliases or LLM
                
                row_label = str(row[0]).strip()
                if not row_label:
                    continue
                
                norm_row = _normalize_text(row_label)
                
                # Fuzzy match
                score = fuzz.token_sort_ratio(norm_row, norm_template)
                if score > best_score and score >= 65:
                    value = _get_value_from_row(row, year_column, notes_headers)
                    if value:
                        best_score = score
                        best_match = (row_label, value)
            
            if best_match:
                row_label, value = best_match
                confidence = best_score / 100.0
                results.append(MappingResult(
                    template_item=template_label,
                    section="Other Financial Information",
                    pdf_row_label=row_label,
                    value=value,
                    confidence=confidence,
                    method="notes_fuzzy",
                ))
                mapped_items.add(template_label)
                logger.info(
                    f"Notes fuzzy: '{row_label}' -> '{template_label}' "
                    f"(score={best_score:.1f}, value={value})"
                )
    
    # Log summary
    total_ofi_items = len(other_fin_info_items)
    found_count = len([r for r in results if r.section == "Other Financial Information"])
    logger.info(
        f"Notes extraction: found {found_count}/{total_ofi_items} "
        f"'Other Financial Information' items "
        f"(already had {len(already_mapped)} from CF statement)"
    )
    
    return results


# ============================================================================
# DERIVED ITEMS COMPUTATION
# ============================================================================


def compute_derived_items(
    mappings: list[MappingResult],
    template: dict,
) -> list[MappingResult]:
    """
    Compute derived/calculated items that are not directly present in the PDF
    but can be calculated from other mapped values.
    
    Handles two types of derived items:
    
    1. RESIDUAL items: Computed as parent_total - sum(known_sub_items).
       E.g., "Other non-current liabilities" = Total NC Liabilities - known NC liability items.
       This is needed because the PDF may not have a row for "Other non-current liabilities"
       but the template requires it — it's the residual that makes the total add up.
    
    2. FROM_NOTES items: Must be extracted from notes tables (equity roll-forward).
       These are handled separately by extract_equity_roll_forward().
    
    Args:
        mappings: Existing mapping results (from alias/fuzzy/LLM mapping).
        template: The template dict (BALANCE_SHEET_TEMPLATE, etc.)
    
    Returns:
        List of NEW MappingResult objects for derived items that were not
        already in the input mappings.
    """
    # Build a lookup of already-mapped items
    mapped_items = {r.template_item: r for r in mappings}
    
    results = []
    
    for item_name, item_config in DERIVED_ITEMS.items():
        # Skip if already mapped
        if item_name in mapped_items:
            continue
        
        if item_config["rule"] == "residual":
            # Compute: parent_total - sum(known_sub_items)
            parent_name = item_config["parent_total"]
            subtract_names = item_config["subtract_items"]
            
            # Get parent total value
            parent_result = mapped_items.get(parent_name)
            if parent_result is None:
                # Parent total might be a formula item — try to compute from mapped sub-items
                # For BS, the parent total is computed by Excel formula, so we need to
                # sum all items in that section instead
                logger.debug(
                    f"Derived item '{item_name}': parent '{parent_name}' not in mappings, "
                    f"skipping residual computation"
                )
                continue
            
            parent_val = _parse_alias_value(parent_result.value)
            
            # Sum known sub-items
            sub_total = 0.0
            sub_found = 0
            for sub_name in subtract_names:
                sub_result = mapped_items.get(sub_name)
                if sub_result is not None:
                    sub_total += _parse_alias_value(sub_result.value)
                    sub_found += 1
            
            if sub_found == 0:
                logger.debug(
                    f"Derived item '{item_name}': no sub-items found, skipping"
                )
                continue
            
            # Compute residual
            residual = parent_val - sub_total
            
            section = item_config["section"]
            results.append(MappingResult(
                template_item=item_name,
                section=section,
                pdf_row_label=f"[derived: {parent_name} - {sub_found} sub-items]",
                value=f"{residual:,.2f}" if residual != int(residual) else f"{residual:,.0f}",
                confidence=0.70,
                method="derived_residual",
            ))
            logger.info(
                f"Derived residual: '{item_name}' = {parent_name}({parent_val:,.2f}) "
                f"- {sub_found} sub-items({sub_total:,.2f}) = {residual:,.2f}"
            )
        
        elif item_config["rule"] == "from_notes":
            # These are handled by extract_equity_roll_forward()
            pass
    
    return results


def apply_default_zeros(
    mappings: list[MappingResult],
    default_zero_items: set,
    template: dict,
) -> list[MappingResult]:
    """
    Apply default zero values for template items that are not found in the PDF.

    DEPRECATED — This function is kept for backward compatibility but the
    default_zero_items sets are now EMPTY per policy:
        "Only write 0 if the PDF explicitly says 0/Nil/blank/— for that item.
         If the item is simply NOT in the PDF, leave the Excel cell blank."

    This function will always return an empty list since default_zero_items
    is always an empty set(). It is no longer called from smart_agent.py.

    Previously, some items were auto-zeroed (e.g., Goodwill, Biological Assets)
    on the assumption that absence implies zero. This was incorrect because:
        - 0 means "confirmed absent by the report" (explicit Nil/—/0 in PDF)
        - Blank/None means "not found" (could be missing data, not zero)
    Auto-zeroing conflated "not found" with "confirmed zero", which is
    misleading for financial analysis.

    Args:
        mappings: Existing mapping results.
        default_zero_items: Set of template item names that should default to 0.
                            Now always empty set().
        template: The template dict for section lookup.

    Returns:
        List of NEW MappingResult objects for default-zero items (always empty).
    """
    mapped_items = {r.template_item for r in mappings}
    
    # Build section lookup from template
    item_to_section = {}
    for section, item in _flatten_template_with_sections(template):
        item_to_section[item] = section
    
    results = []
    for item_name in default_zero_items:
        if item_name not in mapped_items:
            section = item_to_section.get(item_name, "")
            results.append(MappingResult(
                template_item=item_name,
                section=section,
                pdf_row_label="[default: not found in PDF]",
                value="0",
                confidence=0.50,
                method="default_zero",
            ))
            logger.debug(f"Default zero: '{item_name}' = 0")
    
    return results


# ============================================================================
# EQUITY ROLL-FORWARD EXTRACTION
# ============================================================================


def extract_equity_roll_forward(
    notes_tables: list['ExtractedTable'],
    existing_mappings: list[MappingResult],
    year: Optional[int] = None,
) -> list[MappingResult]:
    """
    Extract equity roll-forward items from Notes to Accounts.
    
    The Balance Sheet template has three items that come from the "Other Equity"
    note or "Statement of Changes in Equity":
        - Profit for the year
        - Change in FCTR (Foreign Currency Translation Reserve)
        - NCI share of loss (Non-Controlling Interest)
    
    These are NOT in the Balance Sheet itself — they're in the equity note
    which breaks down "Other Equity" into its components.
    
    Strategy:
        1. Search notes tables for equity-related notes
        2. Look for specific row labels matching DERIVED_ITEMS search_patterns
        3. Extract the values from matching rows
    
    Args:
        notes_tables: List of ExtractedTable objects from notes pages.
        existing_mappings: Existing BS mapping results (to avoid duplicates).
        year: Financial year.
    
    Returns:
        List of MappingResult objects for equity roll-forward items.
    """
    if not notes_tables:
        return []
    
    # Already mapped items
    already_mapped = {r.template_item for r in existing_mappings}
    
    # Get equity items that need extraction
    equity_items = {
        name: config
        for name, config in DERIVED_ITEMS.items()
        if config["rule"] == "from_notes" and name not in already_mapped
    }
    
    if not equity_items:
        return []
    
    results = []
    mapped_items = set(already_mapped)
    
    # Collect all notes rows
    all_rows = []
    for table in notes_tables:
        headers = table.headers if table.headers else []
        year_col = _detect_year_column(headers)
        
        # Detect note context
        context = ""
        for row in table.rows[:3]:
            row_text = " ".join(str(c) for c in row).strip().lower()
            if row_text and len(row_text) > 5:
                context = row_text[:100]
                break
        
        for row in table.rows:
            if not row:
                continue
            label = str(row[0]).strip()
            if not label:
                continue
            
            value = _get_value_from_row(row, year_col, headers)
            if value:
                all_rows.append((label, value, context, table.page_number))
    
    # For each equity item, search for matching rows
    for item_name, item_config in equity_items.items():
        search_patterns = item_config["search_patterns"]
        note_keywords = item_config["note_keywords"]
        
        best_match = None
        best_score = 0.0
        
        for label, value, context, page_num in all_rows:
            label_norm = _normalize_text(label)
            context_norm = context.lower()
            
            # Check if this row is in a relevant note
            in_relevant_note = any(
                kw in context_norm for kw in note_keywords
            )
            
            # Check search patterns
            for pattern in search_patterns:
                pattern_norm = _normalize_text(pattern)
                
                # Exact substring match
                if pattern_norm in label_norm:
                    score = 0.90 if in_relevant_note else 0.75
                    if score > best_score:
                        best_score = score
                        best_match = (label, value, page_num)
                    break
                
                # Fuzzy match
                fuzzy_score = fuzz.token_sort_ratio(label_norm, pattern_norm)
                if fuzzy_score >= 70:
                    score = (fuzzy_score / 100.0) * (0.95 if in_relevant_note else 0.80)
                    if score > best_score:
                        best_score = score
                        best_match = (label, value, page_num)
        
        if best_match:
            label, value, page_num = best_match
            results.append(MappingResult(
                template_item=item_name,
                section="",
                pdf_row_label=label,
                value=value,
                confidence=best_score,
                method="equity_roll_forward",
            ))
            mapped_items.add(item_name)
            logger.info(
                f"Equity roll-forward: '{label}' -> '{item_name}' "
                f"(value={value}, confidence={best_score:.2f}, page={page_num})"
            )
    
    return results
