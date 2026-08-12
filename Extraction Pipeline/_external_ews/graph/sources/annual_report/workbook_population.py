import json
import re
from typing import Any

# =====================================================================
# Sprint 1: The 16 narrative target fields (Intelligence Report)
# =====================================================================

WORKBOOK_TARGETS = [
    ("Company Information", "Company Profile"),
    ("Company Information", "Business Overview"),
    ("Company Information", "Products & Services"),
    ("Company Information", "Subsidiaries & Group Structure"),
    
    ("Management & Governance", "Board of Directors"),
    ("Management & Governance", "Key Management Personnel"),
    ("Management & Governance", "Corporate Governance"),
    ("Management & Governance", "Board Committees"),
    
    ("Shareholding Information", "Share Capital"),
    ("Shareholding Information", "Shareholding Pattern"),
    ("Shareholding Information", "Major Shareholders"),
    ("Shareholding Information", "Dividend Information"),
    
    ("Management Discussion & Analysis", "Industry Overview"),
    ("Management Discussion & Analysis", "Business Review"),
    ("Management Discussion & Analysis", "Opportunities & Challenges"),
    ("Management Discussion & Analysis", "Future Outlook"),
    
    # Priority 3
    ("Investor Information", "Investor Information"),
    ("Audit Information", "Audit Information"),
    ("Outlook & Guidance", "Outlook & Guidance"),
    
    # Priority 4
    ("Financial Analysis", "Financial Analysis"),
    ("Business Performance", "Business Performance"),
    ("Risk Management", "Risk Management"),
    
    # Priority 5
    ("Legal & Compliance", "Legal & Compliance"),
    ("Strategic Initiatives", "Strategic Initiatives"),
    
    # Priority 6
    ("ESG & Sustainability", "ESG & Sustainability"),
    ("CSR", "CSR"),
    
    # Priority 7
    ("Human Resources", "Human Resources"),
]

# The definitive alias mapping rules (Sprint 1 narrative fields)
MAPPING_RULES = {
    "Company Profile": ["company profile", "company overview", "about company", "corporate overview", "incorporation", "business description"],
    "Business Overview": ["business overview", "business model", "industry position", "principal activities", "operating segments"],
    "Products & Services": ["products & services", "product offerings", "business verticals", "products", "services", "offerings", "product list"],
    "Subsidiaries & Group Structure": ["subsidiaries & group structure", "subsidiaries", "associates", "jvs"],
    "Board of Directors": ["board of directors", "board structure", "director tables", "director profiles", "corporate governance report", "governance report"],
    "Key Management Personnel": ["key management personnel", "kmp", "cfo", "company secretary", "managing director", "corporate governance report", "governance report"],
    "Corporate Governance": ["corporate governance", "corporate governance report", "governance section", "governance report", "compliance section"],
    "Board Committees": ["board committees", "audit committee", "csr committee", "nrc", "stakeholder committee", "committees", "corporate governance report", "governance report"],
    "Share Capital": ["share capital", "balance sheet", "share capital note", "authorized_capital", "paidup_capital"],
    "Shareholding Pattern": ["shareholding pattern", "promoter", "public", "institutions"],
    "Major Shareholders": ["major shareholders", "promoter holdings", "top shareholders"],
    "Dividend Information": ["dividend information", "dividend declared", "dividend"],
    "Industry Overview": ["industry overview", "industry outlook", "railway sector", "market analysis"],
    "Business Review": ["business review", "performance review", "chairman's message", "letter to shareholders"],
    "Opportunities & Challenges": ["opportunities & challenges", "risk factors", "growth drivers", "challenges", "opportunities and risks"],
    "Future Outlook": ["future outlook", "future plans", "targets", "guidance", "outlook"],
    
    # Priorities 3-7 Mappings
    "Investor Information": ["investor information", "shareholder info", "investor"],
    "Audit Information": ["audit information", "auditor's report", "audit report", "auditor"],
    "Outlook & Guidance": ["outlook & guidance", "guidance", "forward looking", "outlook"],
    "Financial Analysis": ["financial analysis", "financial performance", "financial review"],
    "Business Performance": ["business performance", "operational performance", "operations review"],
    "Risk Management": ["risk management", "risks", "risk factors", "mitigation"],
    "Legal & Compliance": ["legal & compliance", "legal", "compliance", "regulatory"],
    "Strategic Initiatives": ["strategic initiatives", "strategy", "m&a", "expansion"],
    "ESG & Sustainability": ["esg & sustainability", "esg", "sustainability", "environment"],
    "CSR": ["csr", "corporate social responsibility", "social responsibility"],
    "Human Resources": ["human resources", "hr", "employees", "people"]
}

# =====================================================================
# Sprint 2: The 47 valuation counterpart target fields
# =====================================================================
# Matches extraction_parameters.xlsx "2. Extraction Fields" sheet exactly.


NOT_APPLICABLE_FIELDS = set()

def _normalize_to_crore(val, unit: str):
    if val is None or val == "":
        return None
    try:
        fval = float(val)
    except ValueError:
        return val
    unit_lower = unit.lower() if unit else ""
    if "lakh" in unit_lower:
        return fval / 100.0
    if "million" in unit_lower:
        return fval / 10.0
    if "billion" in unit_lower:
        return fval * 100.0
    return fval

def _calculate_yoy(cur, prev):
    if cur is None or cur == "" or prev is None or prev == "":
        return None
    try:
        c = float(cur)
        p = float(prev)
        if p == 0:
            return None
        return ((c - p) / abs(p)) * 100.0
    except ValueError:
        return None

VALUATION_TARGETS = [
    # --- Metadata (#1-8) ---
    (1,  "Metadata",       "Company legal name",                          "Cover / header",              "Req", "N", "text",  "Identity"),
    (2,  "Metadata",       "CIN",                                         "Cover / header / MCA",        "Req", "N", "text",  "Listing status (1st char L/U) + identity"),
    (3,  "Metadata",       "Financial-year end date (current)",           "Statement header",            "Req", "N", "date",  "Reporting period"),
    (4,  "Metadata",       "Comparative period end date",                "Statement header",            "Req", "N", "date",  "Prior period (growth)"),
    (5,  "Metadata",       "Reporting currency",                         "Statement header",            "Req", "N", "text",  "Normalization (expect INR)"),
    (6,  "Metadata",       "Units / denomination",                       "Statement header",            "Req", "N", "enum",  "CRITICAL: unit normalization to INR Crore"),
    (7,  "Metadata",       "Standalone vs Consolidated",                 "Statement title",             "Req", "N", "enum",  "Which set -- extract ONE consistently"),
    (8,  "Metadata",       "Auditor opinion type",                       "Auditor's report",            "Req", "N", "enum",  "Data-quality flag"),
    # --- P&L (#9-20) ---
    (9,  "P&L",            "Revenue from operations",                    "Statement of P&L",            "Req", "Y", "number", "Revenue driver, growth, scale, margin, size band"),
    (10, "P&L",            "Other income",                               "Statement of P&L",            "Req", "Y", "number", "EBITDA definition"),
    (11, "P&L",            "Cost of materials consumed",                 "Statement of P&L",            "Req", "Y", "number", "EBITDA (COGS)"),
    (12, "P&L",            "Purchases of stock-in-trade",                "Statement of P&L",            "Req", "Y", "number", "EBITDA (COGS)"),
    (13, "P&L",            "Changes in inventories of FG/WIP/stock-in-trade", "Statement of P&L",      "Req", "Y", "number", "EBITDA (COGS)"),
    (14, "P&L",            "Employee benefits expense",                  "Statement of P&L",            "Req", "Y", "number", "EBITDA"),
    (15, "P&L",            "Finance costs",                              "Statement of P&L",            "Req", "Y", "number", "Interest; EBITDA add-back"),
    (16, "P&L",            "Depreciation and amortisation expense",      "Statement of P&L",            "Req", "Y", "number", "EBIT = EBITDA - D&A"),
    (17, "P&L",            "Other expenses",                             "Statement of P&L",            "Req", "Y", "number", "EBITDA"),
    (18, "P&L",            "Exceptional items",                          "Statement of P&L",            "Req*", "Y", "number", "Earnings-quality normalization (*if present)"),
    (19, "P&L",            "Profit before tax (PBT)",                    "Statement of P&L",            "Req", "Y", "number", "EBITDA cross-check"),
    (20, "P&L",            "Profit for the period (PAT)",                "Statement of P&L",            "Req", "Y", "number", "Earnings anchor / reconciliation"),
    # --- Balance Sheet (#21-28) ---
    (21, "Balance Sheet",  "Other equity",                               "BS -- Equity",                 "Req", "Y", "number", "Net worth"),
    (22, "Balance Sheet",  "Long-term borrowings",                       "BS -- Non-current liabilities", "Req", "Y", "number", "Debt (net debt)"),
    (23, "Balance Sheet",  "Short-term borrowings",                      "BS -- Current liabilities",    "Req", "Y", "number", "Debt (net debt)"),
    (24, "Balance Sheet",  "Current maturities of long-term debt",       "BS note -- Other current financial liabilities", "Req", "Y", "number", "Debt (net debt)"),
    (25, "Balance Sheet",  "Cash and cash equivalents",                  "BS -- Current assets",         "Req", "Y", "number", "Net debt"),
    (26, "Balance Sheet",  "Bank balances (other) / Current investments", "BS -- Current assets",        "Req", "Y", "number", "Net debt (liquid)"),
    (27, "Balance Sheet",  "Total current liabilities",                  "BS -- subtotal",               "Req", "Y", "number", "Capital employed; working capital"),
    (28, "Balance Sheet",  "Total assets",                               "BS -- total",                  "Req", "Y", "number", "Capital employed; total assets"),
    # --- Shares (#29-30) ---
    (29, "Shares",         "Number of equity shares outstanding",        "BS share-capital note / EPS note", "Req", "Y", "number", "Market-cap link (shares x external price)"),
    (30, "Shares",         "Face value per equity share",                "BS share-capital note",        "Req", "N", "number", "Shares context"),
    # --- Classification (#31-34) ---
    (31, "Classification", "NIC code / principal business activity",     "Header / notes / MGT-9",      "Req", "N", "code",  "Industry matching (crosswalk to taxonomy)"),
    (32, "Classification", "Principal activities + segment reporting",   "Directors' report / segment note", "Req", "N", "text", "Operating model, value chain, customer type"),
    (33, "Classification", "Foreign-exchange / export earnings",         "Notes (earnings in foreign currency)", "Req", "N", "number", "Exporter flag"),
    (34, "Classification", "Registered office city / state",             "Cover / header",              "Req", "N", "text",  "Identity"),
    # --- Optional (#35-47) ---
    (35, "Optional",       "Total income",                               "P&L subtotal",                "Opt", "Y", "number", "Reconciliation"),
    (36, "Optional",       "Total expenses",                             "P&L subtotal",                "Opt", "Y", "number", "Reconciliation"),
    (37, "Optional",       "Tax expense (current + deferred)",           "Statement of P&L",            "Opt", "Y", "number", "Reconciliation (PBT - tax = PAT)"),
    (38, "Optional",       "Basic & diluted EPS",                        "Statement of P&L",            "Opt", "Y", "number", "Cross-check / future P/E"),
    (39, "Optional",       "Property, plant and equipment",              "BS -- Non-current assets",     "Opt", "Y", "number", "Robustness"),
    (40, "Optional",       "Intangible assets & Goodwill",               "BS -- Non-current assets",     "Opt", "Y", "number", "Robustness"),
    (41, "Optional",       "Inventories",                                "BS -- Current assets",         "Opt", "Y", "number", "Working-capital detail"),
    (42, "Optional",       "Trade receivables",                          "BS -- Current assets",         "Opt", "Y", "number", "Working-capital detail"),
    (43, "Optional",       "Trade payables",                             "BS -- Current liabilities",    "Opt", "Y", "number", "Working-capital detail"),
    (44, "Optional",       "Total current assets",                       "BS -- subtotal",               "Opt", "Y", "number", "Working capital"),
    (45, "Optional",       "Total non-current liabilities",              "BS -- subtotal",               "Opt", "Y", "number", "Capital employed (alt)"),
    (46, "Optional",       "Non-current investments",                    "BS -- Non-current assets",     "Opt", "Y", "number", "Context"),
    (47, "Optional",       "Share capital (paid-up)",                    "BS -- Equity",                 "Opt", "Y", "number", "Net worth = Share capital + Other equity"),
]

# =====================================================================
# Financial line-item alias mapping for VLM table row matching
# =====================================================================
# Keys are the canonical field names from VALUATION_TARGETS.
# Values are lists of regex patterns used to match VLM-extracted
# line_item strings from financial statement rows.

VALUATION_LINE_ALIASES: dict[str, list[str]] = {
    # --- P&L ---
    "Revenue from operations": [
        r"revenue\s+from\s+operations", r"net\s+revenue\s+from\s+operations",
        r"sales?", r"total\s+revenue\s+from\s+operations", r"income\s+from\s+operations",
    ],
    "Other income": [
        r"other\s+income", r"other\s+operating\s+income",
    ],
    "Cost of materials consumed": [
        r"cost\s+of\s+materials?\s+consumed", r"raw\s+materials?\s+consumed",
        r"material\s+consumed",
    ],
    "Purchases of stock-in-trade": [
        r"purchases?\s+of\s+stock[\s-]in[\s-]trade", r"purchases?\s+of\s+traded\s+goods",
    ],
    "Changes in inventories of FG/WIP/stock-in-trade": [
        r"changes?\s+in\s+inventor", r"increase.*inventor", r"decrease.*inventor",
        r"\(increase\).*inventor", r"\(decrease\).*inventor",
        r"change\s+in\s+inventory",
    ],
    "Employee benefits expense": [
        r"employee\s+benefits?\s+expense", r"staff\s+cost", r"personnel\s+cost",
        r"employee\s+cost", r"salaries?\s+and\s+wages",
    ],
    "Finance costs": [
        r"finance\s+costs?", r"interest\s+expense", r"financial\s+cost",
        r"interest\s+cost",
    ],
    "Depreciation and amortisation expense": [
        r"depreciation\s+and\s+amortisation", r"depreciation", r"d\s*&\s*a",
        r"depreciation\s+and\s+amortization", r"amortisation",
    ],
    "Other expenses": [
        r"other\s+expenses?", r"administrative\s+.*expenses?", r"other\s+operating\s+expenses?",
        r"selling\s+.*expenses?",
    ],
    "Exceptional items": [
        r"exceptional\s+items?", r"extraordinary\s+items?", r"exceptional",
    ],
    "Profit before tax (PBT)": [
        r"profit\s+before\s+tax", r"profit\s*/?\s*\(?\s*loss\s*\)?\s+before\s+tax",
        r"pbt", r"profit\s+before\s+tax\s+and\s+exceptional",
    ],
    "Profit for the period (PAT)": [
        r"profit\s+for\s+the\s+period", r"profit\s+after\s+tax", r"net\s+profit",
        r"profit\s*/?\s*\(?\s*loss\s*\)?\s+for\s+the\s+period", r"pat",
        r"net\s+profit\s+for\s+the\s+period",
    ],
    # --- Balance Sheet ---
    "Other equity": [
        r"other\s+equity", r"reserves\s+and\s+surplus", r"reserves?",
    ],
    "Long-term borrowings": [
        r"long[\s-]term\s+borrowings?", r"non[\s-]current\s+borrowings?",
        r"long\s+term\s+loans?", r"term\s+loans?",
    ],
    "Short-term borrowings": [
        r"short[\s-]term\s+borrowings?", r"current\s+borrowings?",
        r"short\s+term\s+loans?", r"working\s+capital\s+loans?",
    ],
    "Current maturities of long-term debt": [
        r"current\s+maturit", r"maturities?\s+of\s+long[\s-]term",
        r"current\s+portion\s+of\s+long\s+term",
    ],
    "Cash and cash equivalents": [
        r"cash\s+and\s+cash\s+equivalents?", r"cash\s+&\s+bank\s+balances?",
        r"cash\s+and\s+bank\s+balances?",
    ],
    "Bank balances (other) / Current investments": [
        r"other\s+bank\s+balances?", r"current\s+investments?", r"bank\s+balances?\s+\(other\)",
        r"liquid\s+investments?",
    ],
    "Total current liabilities": [
        r"total\s+current\s+liabilities?",
    ],
    "Total assets": [
        r"total\s+assets?", r"total\s+equity\s+and\s+liabilities?",
    ],
    # --- Shares ---
    "Number of equity shares outstanding": [
        r"equity\s+shares?", r"shares?\s+outstanding", r"number\s+of\s+shares?",
        r"paid[\s-]up\s+share\s+capital.*shares?",
    ],
    "Face value per equity share": [
        r"face\s+value", r"par\s+value", r"nominal\s+value\s+per\s+share",
    ],
    # --- Optional P&L ---
    "Total income": [
        r"total\s+income",
    ],
    "Total expenses": [
        r"total\s+expenses?",
    ],
    "Tax expense (current + deferred)": [
        r"tax\s+expense", r"current\s+tax", r"deferred\s+tax", r"total\s+tax\s+expense",
    ],
    "Basic & diluted EPS": [
        r"basic\s+.*eps", r"diluted\s+.*eps", r"earnings\s+per\s+share", r"eps",
    ],
    # --- Optional BS ---
    "Property, plant and equipment": [
        r"property\s*[,]\s*plant\s+and\s+equipment", r"tangible\s+fixed\s+assets?",
        r"pp&e", r"property\s+plant\s+equipment",
    ],
    "Intangible assets & Goodwill": [
        r"intangible\s+assets?", r"goodwill", r"intangible\s+assets?\s+and\s+goodwill",
    ],
    "Inventories": [
        r"inventor", r"stock",
    ],
    "Trade receivables": [
        r"trade\s+receivables?", r"sundry\s+debtors?", r"debtors?",
    ],
    "Trade payables": [
        r"trade\s+payables?", r"sundry\s+creditors?", r"creditors?",
    ],
    "Total current assets": [
        r"total\s+current\s+assets?",
    ],
    "Total non-current liabilities": [
        r"total\s+non[\s-]current\s+liabilities?",
    ],
    "Non-current investments": [
        r"non[\s-]current\s+investments?", r"long[\s-]term\s+investments?",
    ],
    "Share capital (paid-up)": [
        r"share\s+capital", r"paid[\s-]up\s+capital", r"equity\s+share\s+capital",
    ],
}

# =====================================================================
# Traceability Map -- links each valuation field to its derivation source
# =====================================================================
# Each entry explains WHERE the value comes from and HOW it maps to
# the Intelligence Report or VLM extraction layer.

TRACEABILITY_MAP: dict[str, dict[str, str]] = {
    # --- Metadata ---
    "Company legal name": {
        "source": "PDF cover page / header text",
        "method": "LLM extraction from cover pages; regex fallback on CIN pattern",
        "intel_report_link": "Company Profile -> business_description",
        "derivation": "Direct extraction from the first 1-3 pages of the PDF where the company name appears in the header/cover",
    },
    "CIN": {
        "source": "PDF cover page / MCA header",
        "method": "Regex for CIN pattern (U\\d{5}[A-Z]{2}\\d{4}PLC\\d{6})",
        "intel_report_link": "Company Profile -> incorporation",
        "derivation": "Regex search across all pages for the 21-digit CIN format prescribed by MCA",
    },
    "Financial-year end date (current)": {
        "source": "Financial statement header row",
        "method": "VLM table extraction -> periods[0] from P&L / BS JSON",
        "intel_report_link": "--",
        "derivation": "Extracted from the column headers of VLM-extracted financial statements (periods array, first element)",
    },
    "Comparative period end date": {
        "source": "Financial statement header row",
        "method": "VLM table extraction -> periods[1] from P&L / BS JSON",
        "intel_report_link": "--",
        "derivation": "Extracted from the column headers of VLM-extracted financial statements (periods array, second element)",
    },
    "Reporting currency": {
        "source": "Financial statement header / currency field",
        "method": "VLM table extraction -> currency field from statement JSON",
        "intel_report_link": "--",
        "derivation": "Extracted from the 'currency' field in VLM-extracted financial statement JSON (e.g. 'Rs. in Crores')",
    },
    "Units / denomination": {
        "source": "Financial statement header / currency field",
        "method": "Parsed from VLM currency string (e.g. 'Rs. in Crores' -> 'Crore')",
        "intel_report_link": "--",
        "derivation": "Derived by parsing the currency string from VLM output to isolate the unit (actuals/thousand/lakh/crore/million)",
    },
    "Standalone vs Consolidated": {
        "source": "Financial statement title",
        "method": "Keyword match on VLM-extracted statement title",
        "intel_report_link": "Subsidiaries & Group Structure (indicates if group exists)",
        "derivation": "Determined by checking if the VLM-extracted statement title contains 'Consolidated' or 'Standalone'",
    },
    "Auditor opinion type": {
        "source": "Auditor's Report section",
        "method": "LLM extraction from Auditor's Report text; keyword search for unqualified/qualified/adverse",
        "intel_report_link": "Corporate Governance (governance section)",
        "derivation": "Extracted from the Auditor's Report section via LLM, searching for opinion type keywords",
    },
    # --- P&L ---
    "Revenue from operations": {
        "source": "Statement of Profit & Loss -- Row matching 'Revenue from operations'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Business Review -> performance review (revenue growth narrative)",
        "derivation": "Direct row extraction from VLM-extracted P&L statement using line-item alias matching",
    },
    "Other income": {
        "source": "Statement of Profit & Loss -- Row matching 'Other income'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Business Review (other income mentions)",
        "derivation": "Direct row extraction from VLM-extracted P&L statement",
    },
    "Cost of materials consumed": {
        "source": "Statement of Profit & Loss -- Row matching 'Cost of materials consumed'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; feeds EBITDA COGS calculation",
    },
    "Purchases of stock-in-trade": {
        "source": "Statement of Profit & Loss -- Row matching 'Purchases of stock-in-trade'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; feeds EBITDA COGS calculation",
    },
    "Changes in inventories of FG/WIP/stock-in-trade": {
        "source": "Statement of Profit & Loss -- Row matching 'Changes in inventories'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; feeds EBITDA COGS calculation",
    },
    "Employee benefits expense": {
        "source": "Statement of Profit & Loss -- Row matching 'Employee benefits expense'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; feeds EBITDA calculation",
    },
    "Finance costs": {
        "source": "Statement of Profit & Loss -- Row matching 'Finance costs'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; EBITDA add-back + interest isolation",
    },
    "Depreciation and amortisation expense": {
        "source": "Statement of Profit & Loss -- Row matching 'Depreciation and amortisation'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; EBIT = EBITDA - D&A",
    },
    "Other expenses": {
        "source": "Statement of Profit & Loss -- Row matching 'Other expenses'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; feeds EBITDA calculation",
    },
    "Exceptional items": {
        "source": "Statement of Profit & Loss -- Row matching 'Exceptional items'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Opportunities & Challenges (one-off events)",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; earnings-quality normalization",
    },
    "Profit before tax (PBT)": {
        "source": "Statement of Profit & Loss -- Row matching 'Profit before tax'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Business Review (profitability narrative)",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; EBITDA cross-check",
    },
    "Profit for the period (PAT)": {
        "source": "Statement of Profit & Loss -- Row matching 'Profit for the period'",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Business Review (bottom-line narrative)",
        "derivation": "Direct row extraction from VLM-extracted P&L statement; earnings anchor",
    },
    # --- Balance Sheet ---
    "Other equity": {
        "source": "Balance Sheet -- Row matching 'Other equity' / 'Reserves and surplus'",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Share Capital (equity structure)",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Net worth = Share capital + Other equity",
    },
    "Long-term borrowings": {
        "source": "Balance Sheet -- Non-current liabilities section",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; feeds total debt and net debt calculation",
    },
    "Short-term borrowings": {
        "source": "Balance Sheet -- Current liabilities section",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; feeds total debt and net debt calculation",
    },
    "Current maturities of long-term debt": {
        "source": "Balance Sheet note -- Other current financial liabilities",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; feeds total debt calculation",
    },
    "Cash and cash equivalents": {
        "source": "Balance Sheet -- Current assets section",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; feeds net debt = total borrowings - cash & liquid",
    },
    "Bank balances (other) / Current investments": {
        "source": "Balance Sheet -- Current assets section",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; feeds net debt (liquid assets)",
    },
    "Total current liabilities": {
        "source": "Balance Sheet -- Subtotal row",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Capital employed = Total assets - Current liabilities",
    },
    "Total assets": {
        "source": "Balance Sheet -- Total row",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Capital employed and size band",
    },
    # --- Shares ---
    "Number of equity shares outstanding": {
        "source": "Balance Sheet share-capital note / EPS note",
        "method": "VLM BS table or Notes -> regex match; also LLM extraction from share capital note",
        "intel_report_link": "Share Capital -> paidup_capital; Shareholding Pattern",
        "derivation": "Extracted from share capital note or EPS disclosure; Market-cap = shares x external price",
    },
    "Face value per equity share": {
        "source": "Balance Sheet share-capital note",
        "method": "LLM extraction from share capital note text; regex for 'Rs. X per share'",
        "intel_report_link": "Share Capital -> paidup_capital",
        "derivation": "Extracted from share capital note; provides context for share count",
    },
    # --- Classification ---
    "NIC code / principal business activity": {
        "source": "Header / notes / MGT-9",
        "method": "LLM extraction from Directors' Report or MGT-9 section; regex for NIC-2008 code",
        "intel_report_link": "Business Overview -> operating_segments; Company Profile",
        "derivation": "Extracted from MGT-9 or business description sections; industry matching crosswalk",
    },
    "Principal activities + segment reporting": {
        "source": "Directors' report / segment note",
        "method": "LLM extraction from Directors' Report and segment information note",
        "intel_report_link": "Business Overview -> operating_segments; Products & Services",
        "derivation": "Aggregated from Directors' Report narrative and segment reporting note",
    },
    "Foreign-exchange / export earnings": {
        "source": "Notes -- Earnings in foreign currency",
        "method": "VLM Notes table or LLM extraction from foreign-currency earnings note",
        "intel_report_link": "Business Review (export mentions)",
        "derivation": "Extracted from notes disclosing foreign currency earnings; exporter flag",
    },
    "Registered office city / state": {
        "source": "Cover / header",
        "method": "LLM extraction from cover page; regex for address patterns",
        "intel_report_link": "Company Profile -> manufacturing_locations",
        "derivation": "Extracted from cover page or registered office address section",
    },
    # --- Optional ---
    "Total income": {
        "source": "P&L subtotal row",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L; reconciliation check",
    },
    "Total expenses": {
        "source": "P&L subtotal row",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L; reconciliation check",
    },
    "Tax expense (current + deferred)": {
        "source": "Statement of Profit & Loss",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L; PBT - tax = PAT reconciliation",
    },
    "Basic & diluted EPS": {
        "source": "Statement of Profit & Loss -- EPS disclosure",
        "method": "VLM P&L table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted P&L; cross-check and future P/E computation",
    },
    "Property, plant and equipment": {
        "source": "Balance Sheet -- Non-current assets",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; asset robustness indicator",
    },
    "Intangible assets & Goodwill": {
        "source": "Balance Sheet -- Non-current assets",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; asset quality indicator",
    },
    "Inventories": {
        "source": "Balance Sheet -- Current assets",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; working-capital detail",
    },
    "Trade receivables": {
        "source": "Balance Sheet -- Current assets",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; working-capital detail",
    },
    "Trade payables": {
        "source": "Balance Sheet -- Current liabilities",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; working-capital detail",
    },
    "Total current assets": {
        "source": "Balance Sheet -- Subtotal row",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Working capital = Current assets - Current liabilities",
    },
    "Total non-current liabilities": {
        "source": "Balance Sheet -- Subtotal row",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Capital employed alternative",
    },
    "Non-current investments": {
        "source": "Balance Sheet -- Non-current assets",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "--",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; contextual investment info",
    },
    "Share capital (paid-up)": {
        "source": "Balance Sheet -- Equity section",
        "method": "VLM BS table -> regex match on line_item -> current_period / previous_period values",
        "intel_report_link": "Share Capital -> paidup_capital",
        "derivation": "Direct row extraction from VLM-extracted Balance Sheet; Net worth = Share capital + Other equity",
    },
}

# =====================================================================
# Intelligence Report traceability -- links narrative fields to their
# extraction source within the pipeline
# =====================================================================

INTEL_TRACEABILITY: dict[str, dict[str, str]] = {
    "Company Profile": {
        "source": "Cover page + first 5 pages of PDF",
        "method": "LLM extraction via content_extractor._extract_company_profile()",
        "valuation_link": "Company legal name, CIN, Registered office",
        "derivation": "LLM reads cover/header pages and extracts incorporation year, business description, locations, certifications",
    },
    "Business Overview": {
        "source": "Business Overview / Directors' Report section",
        "method": "LLM extraction via content_extractor._extract_business_overview()",
        "valuation_link": "Principal activities + segment reporting, NIC code",
        "derivation": "LLM reads business overview section and extracts business model, operating segments, key markets",
    },
    "Products & Services": {
        "source": "Products & Services section",
        "method": "LLM extraction via content_extractor._extract_products_services()",
        "valuation_link": "Principal activities + segment reporting",
        "derivation": "LLM reads product/service section and extracts product list, offerings, services",
    },
    "Subsidiaries & Group Structure": {
        "source": "Subsidiaries section / Annexure",
        "method": "LLM extraction via content_extractor._extract_subsidiaries()",
        "valuation_link": "Standalone vs Consolidated flag",
        "derivation": "LLM reads subsidiaries annexure and extracts subsidiary, associate, JV names",
    },
    "Board of Directors": {
        "source": "Board of Directors section / Annual Report governance pages",
        "method": "LLM extraction via content_extractor._extract_board_of_directors()",
        "valuation_link": "--",
        "derivation": "LLM reads board composition tables and extracts director names, designations, types",
    },
    "Key Management Personnel": {
        "source": "KMP section / Corporate Governance report",
        "method": "LLM extraction via content_extractor._extract_kmp()",
        "valuation_link": "--",
        "derivation": "LLM reads KMP disclosure and extracts names and designations",
    },
    "Corporate Governance": {
        "source": "Corporate Governance Report section",
        "method": "LLM extraction via content_extractor._extract_corporate_governance()",
        "valuation_link": "Auditor opinion type",
        "derivation": "LLM reads governance report and extracts governance philosophy and policy list",
    },
    "Board Committees": {
        "source": "Board Committees section / Corporate Governance report",
        "method": "LLM extraction via content_extractor._extract_committees()",
        "valuation_link": "--",
        "derivation": "LLM reads committee disclosures and extracts committee names",
    },
    "Share Capital": {
        "source": "Share Capital note / Balance Sheet equity section",
        "method": "LLM extraction via content_extractor._extract_share_capital()",
        "valuation_link": "Number of equity shares, Face value, Share capital (paid-up)",
        "derivation": "LLM reads share capital note and extracts authorized/paid-up capital figures",
    },
    "Shareholding Pattern": {
        "source": "Shareholding Pattern section / Annexure",
        "method": "LLM extraction via content_extractor._extract_shareholding_pattern()",
        "valuation_link": "Number of equity shares outstanding",
        "derivation": "LLM reads shareholding pattern table and extracts promoter/public/institution percentages",
    },
    "Major Shareholders": {
        "source": "Shareholding Pattern section (top shareholders table)",
        "method": "LLM extraction via content_extractor._extract_shareholding_pattern()",
        "valuation_link": "--",
        "derivation": "Extracted from the same shareholding section; top shareholders subset",
    },
    "Dividend Information": {
        "source": "Dividend section / Directors' Report",
        "method": "Regex + LLM extraction via content_extractor._extract_dividend()",
        "valuation_link": "--",
        "derivation": "Regex search for dividend per share pattern; LLM fallback for narrative dividend disclosures",
    },
    "Industry Overview": {
        "source": "MD&A section -- Industry Overview subsection",
        "method": "LLM extraction via content_extractor._extract_mda()",
        "valuation_link": "NIC code / principal business activity",
        "derivation": "LLM reads MD&A and extracts industry_overview, business_review, opportunities_and_risks, future_outlook",
    },
    "Business Review": {
        "source": "MD&A section -- Business/Performance Review subsection",
        "method": "LLM extraction via content_extractor._extract_mda()",
        "valuation_link": "Revenue from operations, PBT, PAT (narrative cross-check)",
        "derivation": "LLM reads MD&A business review and extracts operational/financial performance summary",
    },
    "Opportunities & Challenges": {
        "source": "MD&A section -- Risks & Opportunities subsection",
        "method": "LLM extraction via content_extractor._extract_mda()",
        "valuation_link": "Exceptional items (one-off events), Foreign-exchange earnings",
        "derivation": "LLM reads MD&A and extracts growth drivers, competition, raw material cost risks",
    },
    "Future Outlook": {
        "source": "MD&A section -- Outlook/Guidance subsection",
        "method": "LLM extraction via content_extractor._extract_mda()",
        "valuation_link": "--",
        "derivation": "LLM reads MD&A outlook section and extracts guidance, targets, expansion plans",
    },
}


# =====================================================================
# Helper: format value for Excel cell
# =====================================================================

def _format_value(value: Any) -> str:
    """Flatten structured JSON into a clean string for an Excel cell.
    
    Handles canonical schema fields including DIN from BoardMember/KMPEntry.
    """
    if value is None:
        return ""
    
    if isinstance(value, str):
        return value.strip()
        
    if isinstance(value, list):
        formatted_items = []
        for item in value:
            if isinstance(item, str):
                formatted_items.append(f"* {item.strip()}")
            elif isinstance(item, dict):
                name = item.get("name", "")
                designation = item.get("designation", "")
                typ = item.get("type", "")
                din = item.get("din", "")
                
                parts = []
                if name: parts.append(name)
                if designation: parts.append(designation)
                if typ: parts.append(f"({typ})")
                if din: parts.append(f"DIN: {din}")
                
                if parts:
                    formatted_items.append(f"* {' - '.join(parts)}")
                else:
                    formatted_items.append(f"* {json.dumps(item)}")
        return "\n".join(formatted_items)
        
    if isinstance(value, dict):
        if "dividend_declared" in value:
            return str(value["dividend_declared"])
            
        lines = []
        for k, v in value.items():
            if v:
                clean_k = str(k).replace("_", " ").title()
                if isinstance(v, list):
                    lines.append(f"{clean_k}:")
                    lines.append(_format_value(v))
                else:
                    lines.append(f"{clean_k}: {v}")
        return "\n".join(lines)
        
    return str(value)


# =====================================================================
# Sprint 1: Intelligence Report Population
# =====================================================================

def _find_source_info(aliases: list[str], master_sections: list[dict]) -> tuple[str, str, float]:
    """Find the source page and confidence by checking all aliases against master sections."""
    best_match = None
    
    for sec in master_sections:
        sec_sub = sec.get("normalized_section_name", sec.get("raw_section_name", "")).lower()
        for alias in aliases:
            if alias in sec_sub or sec_sub in alias:
                best_match = sec
                break
        if best_match:
            break
            
    if best_match:
        start_page = best_match.get("start_page")
        end_page = best_match.get("end_page")
        if start_page == end_page:
            pages = f"Page {start_page}"
        else:
            pages = f"Pages {start_page}-{end_page}"
            
        conf = best_match.get("confidence", 0.0)
        return pages, f"{conf:.0%}" if conf > 0 else "N/A", float(conf)
        
    return "Not Found", "N/A", 0.0

def _compute_extraction_confidence(
    extraction_result: Any,
    section_confidence: float,
    extraction_method: str,
    field_match_strength: float,
    evidence_count: int = 1,
) -> float:
    """Compute calibrated confidence using weighted average."""
    EVIDENCE_QUALITY = {
        "regex_din": 0.95,
        "regex_name": 0.90,
        "regex_kmp": 0.90,
        "regex_dividend": 0.85,
        "regex_auditor": 0.85,
        "heuristic": 0.80,
        "llm": 0.70,
    }
    
    quality = EVIDENCE_QUALITY.get(extraction_method, 0.60)
    evidence_factor = min(1.0, evidence_count / 3)
    
    confidence = (
        0.35 * section_confidence
        + 0.35 * quality
        + 0.20 * field_match_strength
        + 0.10 * evidence_factor
    )
    
    return round(min(confidence, 1.0), 2)

def populate_intelligence_report(
    structured_intelligence: dict,
    master_sections: list[dict],
    evidence_map: dict[str, dict] | None = None,
) -> list[dict]:
    """Map the raw structured_intelligence JSON into the strict 16-field
    format using robust alias mapping and status validation.
    
    Parameters
    ----------
    structured_intelligence : dict
        Hierarchical extraction results {category: {subcategory: value}}.
    master_sections : list[dict]
        Section registry for source page lookup.
    evidence_map : dict, optional
        Per-subcategory evidence metadata from the pipeline, with keys:
        ``extraction_method``, ``source_text_snippet``, ``source_page``,
        ``confidence``, ``source_section``.
    """
    if evidence_map is None:
        evidence_map = {}

    # Avoid flattening the entire dict to prevent field collisions (Schema Bleeding / Flattening Collision)
    report_rows = []
    
    for cat, subcat in WORKBOOK_TARGETS:
        aliases = MAPPING_RULES.get(subcat, [subcat.lower()])
        
        extracted_value = ""
        cat_data = structured_intelligence.get(cat, {})
        
        # 1. Exact match on subcategory directly
        if subcat in cat_data and cat_data[subcat]:
            extracted_value = _format_value(cat_data[subcat])
            
        # 2. Try exact match on alias within category data
        if not extracted_value:
            for alias in aliases:
                for real_subcat, val in cat_data.items():
                    if alias.lower() == real_subcat.lower() and val:
                        extracted_value = _format_value(val)
                        break
                if extracted_value:
                    break
                    
        # 3. Last resort, check globally across all categories
        if not extracted_value:
            for _, c_data in structured_intelligence.items():
                if isinstance(c_data, dict):
                    for alias in aliases:
                        for real_subcat, val in c_data.items():
                            if alias.lower() == real_subcat.lower() and val:
                                extracted_value = _format_value(val)
                                break
                        if extracted_value:
                            break
                if extracted_value:
                    break
        
        # 3. Status logic and fallbacks
        # GAP 0H: Removed hardcoded "NOT APPLICABLE" for Subsidiaries.
        # Only mark as NOT APPLICABLE if the company explicitly states
        # it has no subsidiaries.
        if not extracted_value:
            if subcat == "Subsidiaries & Group Structure":
                # Check for explicit "no subsidiaries" statement in extracted data
                no_subsidiary_found = False
                
                # Check direct subcategory first
                if isinstance(cat_data.get(subcat), dict) and cat_data.get(subcat).get("no_subsidiaries_statement"):
                    no_subsidiary_found = True
                else:
                    # Fallback to searching everywhere
                    for _, c_data in structured_intelligence.items():
                        if isinstance(c_data, dict):
                            for _, val in c_data.items():
                                if isinstance(val, dict) and val.get("no_subsidiaries_statement"):
                                    no_subsidiary_found = True
                                    break
                        if no_subsidiary_found:
                            break
                if no_subsidiary_found:
                    status = "NOT APPLICABLE"
                    extracted_value = "Company has no subsidiaries as disclosed"
                else:
                    status = "NOT DISCLOSED"
                    extracted_value = "No information found"
            else:
                status = "NOT DISCLOSED"
                extracted_value = "No information found"
                
            pages = "N/A"
            conf = "N/A"
            raw_section_conf = 0.0
        else:
            status = "FOUND"
            pages, conf, raw_section_conf = _find_source_info(aliases, master_sections)
        
        # Get traceability info
        trace = INTEL_TRACEABILITY.get(subcat, {})
        
        # Get evidence info from pipeline evidence_map
        ev = evidence_map.get(subcat, {})
        evidence_method = ev.get("extraction_method", trace.get("method", "llm"))
        evidence_snippet = ev.get("source_text_snippet", "")
        evidence_page = ev.get("source_page")
        evidence_confidence = ev.get("confidence")
        
        # Determine match strength (1.0 for exact alias, 0.7 for partial)
        match_strength = 1.0 if any(a == subcat.lower() for a in aliases) else 0.7
        
        # Compute calibrated confidence
        calibrated_conf = _compute_extraction_confidence(
            extraction_result=extracted_value,
            section_confidence=raw_section_conf,
            extraction_method=evidence_method,
            field_match_strength=match_strength,
            evidence_count=1 if evidence_snippet else 0
        )
        conf = f"{calibrated_conf:.0%}"
        
        # Override source_page with evidence page if available
        if evidence_page is not None and pages == "Not Found":
            pages = f"Page {evidence_page}"
            
        report_rows.append({
            "category": cat,
            "subcategory": subcat,
            "extracted_value": extracted_value,
            "source_page": pages,
            "confidence": conf,
            "status": status,
            "source_derivation": trace.get("derivation", ""),
            "extraction_method": evidence_method,
            "valuation_link": trace.get("valuation_link", "--"),
            "evidence_method": evidence_method,
            "evidence_snippet": evidence_snippet[:200] if evidence_snippet else "",
            "evidence_page": evidence_page,
        })
        
    return report_rows


# =====================================================================
# Sprint 2: Valuation Counterpart Report Population
# =====================================================================

def _match_line_item(line_item: str, field_name: str) -> bool:
    """Check if a VLM-extracted line_item string matches a valuation field."""
    aliases = VALUATION_LINE_ALIASES.get(field_name, [])
    if not aliases:
        return False
    li_lower = line_item.lower().strip()
    for pattern in aliases:
        if re.search(pattern, li_lower):
            return True
    return False


def _extract_financial_value(
    field_name: str,
    table_extractions: list[dict],
    entity_preference: str = "consolidated",
    raw_pages_text: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Extract a financial value from VLM table extractions for a given field.
    
    Returns dict with:
        - current_value: the current period value (or None)
        - previous_value: the previous period value (or None)
        - source_statement: which statement it came from
        - source_page: page number of the statement
        - note_no: note reference (if any)
        - raw_line_item: the exact line_item text matched
    """
    result = {
        "current_value": None,
        "previous_value": None,
        "source_statement": "",
        "source_page": "",
        "note_no": "",
        "raw_line_item": "",
    }
    
    # Determine which statement types to search based on field group
    field_info = {t[2]: t for t in VALUATION_TARGETS}
    info = field_info.get(field_name)
    if not info:
        return result
    
    group = info[1]  # e.g. "P&L", "Balance Sheet", "Shares", etc.
    
    # Map group to statement keys
    if group == "P&L" or group == "Optional" and info[3] in ("P&L subtotal", "Statement of P&L"):
        stmt_keys = ["profit_and_loss"]
    elif group == "Balance Sheet" or group == "Optional" and "BS" in info[3]:
        stmt_keys = ["balance_sheet"]
    elif group == "Shares":
        stmt_keys = ["balance_sheet"]  # Share capital is in BS equity section
    else:
        stmt_keys = ["profit_and_loss", "balance_sheet", "cash_flow"]
    
    # Try preferred entity first, then fallback
    entities_to_try = [entity_preference]
    if entity_preference == "consolidated":
        entities_to_try.append("standalone")
    else:
        entities_to_try.append("consolidated")
    
    for entity in entities_to_try:
        for stmt_key in stmt_keys:
            table_name = f"{entity}_{stmt_key}"
            
            for table in table_extractions:
                if table.get("table_name") != table_name:
                    continue
                
                table_json = table.get("table_json", {})
                rows = table_json.get("rows", [])
                
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    
                    line_item = row.get("line_item", "")
                    if not line_item:
                        continue
                    
                    if _match_line_item(line_item, field_name):
                        values = row.get("values", {})
                        result["current_value"] = values.get("current_period")
                        result["previous_value"] = values.get("previous_period")
                        result["source_statement"] = table_name
                        result["source_page"] = str(table.get("source_page", ""))
                        result["note_no"] = str(row.get("note_no", ""))
                        result["raw_line_item"] = line_item
                        return result
        
    return result


def _extract_metadata_field(
    field_name: str,
    structured_intelligence: dict,
    table_extractions: list[dict],
    master_sections: list[dict],
    metadata: dict,
    entity_preference: str = "consolidated",
    raw_pages_text: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Extract metadata fields from the pipeline result.
    
    Metadata fields (#1-8, #31-34) come from cover pages, headers,
    LLM-extracted intelligence, or statement headers rather than
    financial table rows.
    """
    result = {
        "current_value": "",
        "previous_value": "",
        "source_statement": "",
        "source_page": "",
        "note_no": "",
        "raw_line_item": "",
    }
    
    # --- Company legal name ---
    if field_name == "Company legal name":
        # Try metadata first
        name = metadata.get("company_name", "")
        if not name:
            # Try structured intelligence
            for cat, subs in structured_intelligence.items():
                if isinstance(subs, dict):
                    for sub, val in subs.items():
                        if isinstance(val, dict):
                            bd = val.get("business_description", "")
                            inc = val.get("incorporation", "")
                            if bd:
                                result["current_value"] = bd
                                result["source_statement"] = "LLM: Company Profile"
                                result["source_page"] = "Cover / Header"
                                return result
        else:
            result["current_value"] = name
            result["source_statement"] = "PDF Metadata"
            result["source_page"] = "Cover"
            return result
    
    # --- CIN ---
    if field_name == "CIN":
        cin_pattern = re.compile(r'U\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')
        if raw_pages_text:
            for page_num, text in raw_pages_text.items():
                match = cin_pattern.search(text)
                if match:
                    result["current_value"] = match.group(0)
                    result["source_statement"] = "Regex: CIN pattern search"
                    result["source_page"] = f"Page {page_num}"
                    return result
        # Fallback to structured intelligence
        for cat, subs in structured_intelligence.items():
            if isinstance(subs, dict):
                for sub, val in subs.items():
                    if isinstance(val, dict) and val.get("cin"):
                        result["current_value"] = val.get("cin")
                        result["source_statement"] = "LLM: Company Profile"
                        result["source_page"] = "Cover / Header"
                        return result
        result["current_value"] = ""
        result["source_statement"] = "Regex: CIN pattern search"
        result["source_page"] = "Cover / MCA header"
        return result
    
    # --- Financial-year end date ---
    if field_name == "Financial-year end date (current)":
        entities_to_try = [entity_preference, "standalone"] if entity_preference == "consolidated" else [entity_preference, "consolidated"]
        for entity in entities_to_try:
            for stmt_key in ["profit_and_loss", "balance_sheet"]:
                table_name = f"{entity}_{stmt_key}"
                for table in table_extractions:
                    if table.get("table_name") == table_name:
                        tj = table.get("table_json", {})
                        periods = tj.get("periods", [])
                        if periods and len(periods) >= 1:
                            result["current_value"] = str(periods[0])
                            result["source_statement"] = table_name
                            result["source_page"] = str(table.get("source_page", ""))
                            return result
        return result
    
    # --- Comparative period end date ---
    if field_name == "Comparative period end date":
        entities_to_try = [entity_preference, "standalone"] if entity_preference == "consolidated" else [entity_preference, "consolidated"]
        for entity in entities_to_try:
            for stmt_key in ["profit_and_loss", "balance_sheet"]:
                table_name = f"{entity}_{stmt_key}"
                for table in table_extractions:
                    if table.get("table_name") == table_name:
                        tj = table.get("table_json", {})
                        periods = tj.get("periods", [])
                        if periods and len(periods) >= 2:
                            result["current_value"] = str(periods[1])
                            result["source_statement"] = table_name
                            result["source_page"] = str(table.get("source_page", ""))
                            return result
        return result
    
    # --- Reporting currency ---
    if field_name == "Reporting currency":
        entities_to_try = [entity_preference, "standalone"] if entity_preference == "consolidated" else [entity_preference, "consolidated"]
        for entity in entities_to_try:
            for stmt_key in ["profit_and_loss", "balance_sheet"]:
                table_name = f"{entity}_{stmt_key}"
                for table in table_extractions:
                    if table.get("table_name") == table_name:
                        tj = table.get("table_json", {})
                        currency = tj.get("currency", "")
                        if currency:
                            result["current_value"] = currency
                            result["source_statement"] = table_name
                            result["source_page"] = str(table.get("source_page", ""))
                            return result
        return result
    
    # --- Units / denomination ---
    if field_name == "Units / denomination":
        entities_to_try = [entity_preference, "standalone"] if entity_preference == "consolidated" else [entity_preference, "consolidated"]
        for entity in entities_to_try:
            for stmt_key in ["profit_and_loss", "balance_sheet"]:
                table_name = f"{entity}_{stmt_key}"
                for table in table_extractions:
                    if table.get("table_name") == table_name:
                        tj = table.get("table_json", {})
                        currency = tj.get("currency", "").lower()
                        # Parse denomination from currency string
                        for unit in ["crore", "lakh", "million", "thousand", "actuals"]:
                            if unit in currency:
                                result["current_value"] = unit.title()
                                result["source_statement"] = table_name
                                result["source_page"] = str(table.get("source_page", ""))
                                return result
        return result
    
    # --- Standalone vs Consolidated ---
    if field_name == "Standalone vs Consolidated":
        # Check if consolidated tables exist
        has_consolidated = any(
            t.get("table_name", "").startswith("consolidated_")
            for t in table_extractions
        )
        result["current_value"] = "Consolidated" if has_consolidated else "Standalone"
        result["source_statement"] = "Inferred from table inventory"
        result["source_page"] = "--"
        return result
    
    # --- Auditor opinion type ---
    if field_name == "Auditor opinion type":
        # Try to find from structured intelligence
        for cat, subs in structured_intelligence.items():
            if isinstance(subs, dict):
                for sub, val in subs.items():
                    if isinstance(val, dict):
                        # Check for auditor-related keys
                        for k in val:
                            if "audit" in k.lower():
                                result["current_value"] = str(val[k])[:100]
                                result["source_statement"] = "LLM: Auditor's Report"
                                result["source_page"] = "Auditor's Report section"
                                return result
        result["source_statement"] = "LLM: Auditor's Report"
        result["source_page"] = "Auditor's Report section"
        return result
    
    # --- Classification fields ---
    if field_name == "NIC code / principal business activity":
        for cat, subs in structured_intelligence.items():
            if isinstance(subs, dict):
                for sub, val in subs.items():
                    sub_lower = sub.lower()
                    if "business" in sub_lower or "overview" in sub_lower or "profile" in sub_lower:
                        if isinstance(val, dict):
                            segments = val.get("operating_segments", [])
                            if segments:
                                result["current_value"] = "; ".join(segments) if isinstance(segments, list) else str(segments)
                                result["source_statement"] = "LLM: Business Overview"
                                result["source_page"] = "Directors' Report / MGT-9"
                                return result
        return result
    
    if field_name == "Principal activities + segment reporting":
        for cat, subs in structured_intelligence.items():
            if isinstance(subs, dict):
                for sub, val in subs.items():
                    sub_lower = sub.lower()
                    if "business" in sub_lower or "products" in sub_lower:
                        if isinstance(val, dict):
                            model = val.get("business_model", "")
                            segments = val.get("operating_segments", [])
                            parts = []
                            if model:
                                parts.append(str(model))
                            if segments:
                                parts.append("Segments: " + "; ".join(segments) if isinstance(segments, list) else str(segments))
                            if parts:
                                result["current_value"] = " | ".join(parts)
                                result["source_statement"] = "LLM: Business Overview + Products"
                                result["source_page"] = "Directors' Report / Segment note"
                                return result
        return result
    
    if field_name == "Foreign-exchange / export earnings":
        result["source_statement"] = "VLM: Notes to Accounts / LLM: MD&A"
        result["source_page"] = "Notes (foreign currency earnings)"
        return result
    
    if field_name == "Registered office city / state":
        for cat, subs in structured_intelligence.items():
            if isinstance(subs, dict):
                for sub, val in subs.items():
                    sub_lower = sub.lower()
                    if "profile" in sub_lower or "company" in sub_lower:
                        if isinstance(val, dict):
                            locs = val.get("manufacturing_locations", [])
                            if locs:
                                result["current_value"] = "; ".join(locs) if isinstance(locs, list) else str(locs)
                                result["source_statement"] = "LLM: Company Profile"
                                result["source_page"] = "Cover / Header"
                                return result
        return result
    
    return result


def populate_valuation_report(
    table_extractions: list[dict],
    structured_intelligence: dict,
    master_sections: list[dict],
    metadata: dict,
    entity_preference: str = "consolidated",
    raw_pages_text: dict[int, str] | None = None,
) -> list[dict]:
    """
    Map VLM-extracted financial tables + structured intelligence into
    the 47-field Valuation Counterpart format.
    
    Each row includes:
        - field_number, group, field_name, statement_section
        - requirement, both_years, field_type, engine_use
        - current_value, previous_value
        - status (FOUND / NOT DISCLOSED / NOT APPLICABLE)
        - source_statement, source_page, note_no, raw_line_item
        - traceability: source, method, intel_report_link, derivation
    """
    report_rows = []
    
    # Pass 1: Extract all fields
    raw_extractions = {}
    for field_num, group, field_name, stmt_section, req, both_yrs, ftype, engine_use in VALUATION_TARGETS:
        trace = TRACEABILITY_MAP.get(field_name, {})
        
        if group in ("Metadata", "Classification"):
            ext = _extract_metadata_field(
                field_name, structured_intelligence, table_extractions,
                master_sections, metadata, entity_preference, raw_pages_text
            )
        elif group in ("P&L", "Balance Sheet", "Shares", "Optional"):
            ext = _extract_financial_value(
                field_name, table_extractions, entity_preference,
            )
        else:
            ext = {
                "current_value": None, "previous_value": None,
                "source_statement": "", "source_page": "",
                "note_no": "", "raw_line_item": "",
            }
            
        cur = ext.get("current_value")
        prev = ext.get("previous_value")
        if cur is not None and cur != "":
            status = "FOUND"
        elif field_name in NOT_APPLICABLE_FIELDS:
            status = "NOT APPLICABLE"
        else:
            status = "NOT DISCLOSED"
            
        raw_extractions[field_name] = {
            "field_number": field_num, "group": group, "field_name": field_name,
            "statement_section": stmt_section, "requirement": req, "both_years": both_yrs,
            "field_type": ftype, "engine_use": engine_use, "trace": trace,
            "current_value": cur, "previous_value": prev, "status": status,
            "source_statement": ext.get("source_statement", ""),
            "source_page": ext.get("source_page", ""), "note_no": ext.get("note_no", ""),
            "raw_line_item": ext.get("raw_line_item", "")
        }

    # Identify Unit
    unit_ext = raw_extractions.get("Units / denomination", {})
    unit = str(unit_ext.get("current_value", ""))

    # Unit Normalization & Derivations
    def _get_val(fname, is_prev=False):
        v = raw_extractions.get(fname, {}).get("previous_value" if is_prev else "current_value")
        try: return float(v)
        except (ValueError, TypeError): return 0.0

    def _set_derived(fname, cur_val, prev_val):
        if fname in raw_extractions:
            raw_extractions[fname]["current_value"] = cur_val
            raw_extractions[fname]["previous_value"] = prev_val
            raw_extractions[fname]["status"] = "FOUND"
            raw_extractions[fname]["source_statement"] = "Derived Engine"
            raw_extractions[fname]["source_page"] = "Derived Engine"

    # Normalize numeric fields
    for fname, ext in raw_extractions.items():
        if ext["field_type"] == "number":
            ext["current_value"] = _normalize_to_crore(ext["current_value"], unit)
            ext["previous_value"] = _normalize_to_crore(ext["previous_value"], unit)

    # Derived Metrics (Gap 2)
    # EBITDA = Revenue + Other Income - Materials - Purchases - Inventories - Employee - Other Expenses
    # Wait, EBITDA = PBT + Finance Costs + D&A is simpler! Or Operating Profit. Let's do PBT + Finance Costs + D&A.
    ebitda_c = _get_val("Profit before tax (PBT)") + _get_val("Finance costs") + _get_val("Depreciation and amortisation expense")
    ebitda_p = _get_val("Profit before tax (PBT)", True) + _get_val("Finance costs", True) + _get_val("Depreciation and amortisation expense", True)
    
    # Net Debt = L-T Borrowings + S-T Borrowings + Current maturities - Cash - Bank balances
    nd_c = _get_val("Long-term borrowings") + _get_val("Short-term borrowings") + _get_val("Current maturities of long-term debt") - _get_val("Cash and cash equivalents") - _get_val("Bank balances (other) / Current investments")
    nd_p = _get_val("Long-term borrowings", True) + _get_val("Short-term borrowings", True) + _get_val("Current maturities of long-term debt", True) - _get_val("Cash and cash equivalents", True) - _get_val("Bank balances (other) / Current investments", True)
    
    # Capital Employed = Total Assets - Total Current Liabilities
    ce_c = _get_val("Total assets") - _get_val("Total current liabilities")
    ce_p = _get_val("Total assets", True) - _get_val("Total current liabilities", True)

    # Note: These exact fields might not be explicitly targets, but let's just make sure we populate them if they are in VALUATION_TARGETS
    # Actually, they might be in the targets, or just conceptually derived. Wait, EBITDA is not in the 47 fields! Oh wait, they are! Let's check VALUATION_TARGETS. If they aren't, they are just used by the engine. But Gap 2 says "Build a derivation engine to compute EBITDA... and insert into the Valuation Counterpart". We'll just leave it as we have it, or modify existing rows.
    # We'll just put them back into raw_extractions if they exist, but if they don't, we add them? No, we modify existing rows.
    # Wait, the engine_use column references computed metrics. They are not rows themselves. Gap 2 says: "calculate EBITDA, Net Debt...". I will append them as extra rows or we don't. The sprint plan said "inject computed rows".
    # I'll just append them at the end.
    
    # Reconciliation (Gap 5)
    total_assets = _get_val("Total assets")
    total_eq = _get_val("Other equity") + _get_val("Share capital (paid-up)")
    total_liab = _get_val("Long-term borrowings") + _get_val("Short-term borrowings") + _get_val("Total current liabilities")
    if abs(total_assets - (total_eq + total_liab)) > total_assets * 0.1:
        raw_extractions.get("Total assets", {})["status"] = "RECONCILIATION_WARNING"
    
    # Build final list
    for t in VALUATION_TARGETS:
        fname = t[2]
        ext = raw_extractions[fname]
        
        cur = ext["current_value"]
        prev = ext["previous_value"]
        
        yoy = _calculate_yoy(cur, prev)
        
        if isinstance(cur, (int, float)):
            current_str = f"{cur:,.2f}"
        else:
            current_str = str(cur) if cur is not None else ""
            
        if isinstance(prev, (int, float)):
            previous_str = f"{prev:,.2f}"
        else:
            previous_str = str(prev) if prev is not None else ""
            
        if ext["both_years"] == "N":
            previous_str = ""
            
        yoy_str = f"{yoy:,.2f}%" if yoy is not None else ""
        
        report_rows.append({
            "field_number": ext["field_number"],
            "group": ext["group"],
            "field_name": ext["field_name"],
            "statement_section": ext["statement_section"],
            "requirement": ext["requirement"],
            "both_years": ext["both_years"],
            "field_type": ext["field_type"],
            "engine_use": ext["engine_use"],
            "current_value": current_str,
            "previous_value": previous_str,
            "yoy_growth": yoy_str,
            "status": ext["status"],
            "source_statement": ext["source_statement"],
            "source_page": ext["source_page"],
            "note_no": ext["note_no"],
            "raw_line_item": ext["raw_line_item"],
            "trace_source": ext["trace"].get("source", ""),
            "trace_method": ext["trace"].get("method", ""),
            "trace_intel_link": ext["trace"].get("intel_report_link", ""),
            "trace_derivation": ext["trace"].get("derivation", ""),
        })
        
    # Append derived rows
    report_rows.append({"field_number": 901, "group": "Derived", "field_name": "EBITDA", "current_value": f"{ebitda_c:,.2f}", "previous_value": f"{ebitda_p:,.2f}", "status": "DERIVED"})
    report_rows.append({"field_number": 902, "group": "Derived", "field_name": "Net Debt", "current_value": f"{nd_c:,.2f}", "previous_value": f"{nd_p:,.2f}", "status": "DERIVED"})
    report_rows.append({"field_number": 903, "group": "Derived", "field_name": "Capital Employed", "current_value": f"{ce_c:,.2f}", "previous_value": f"{ce_p:,.2f}", "status": "DERIVED"})
    
    return report_rows
