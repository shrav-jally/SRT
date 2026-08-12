"""
EWS Annual Report Extraction Agent

An agent-based system that extracts financial data from annual report PDFs
and populates an Excel template with Balance Sheet, P&L, and Cash Flow data.

Architecture (LLM-First + CA Validation):
    1. Table Finder (LLM-primary + deterministic validation) - identifies BS/P&L/CF pages
    2. Text Table Extractor (pdfplumber) - deterministic line-by-line parsing
    3. Data Mapper (LLM-primary + alias + fuzzy fallback) - maps extracted data to template items
    4. CA Validator (ca_validator.py) - Chartered Accountant-level validation & inference:
       a. Cross-statement validation (BS equation, P&L equation, PAT consistency)
       b. Inferential mapping (EBITDA, EBIT, BS Profit from P&L PAT, Total Debt)
       c. Note cross-reference tracking (link BS/P&L items to their notes)
       d. Ind AS / Schedule III compliance checks
    5. Excel Writer (openpyxl) - writes results + CA flags to the template Excel file

Sub-Agents:
    - CA Validation Agent (ca_validator.py): Post-mapping validation with
      4 categories: cross_statement, inferential, note_reference, compliance.
      Applies CA-level reasoning to infer missing values and flag inconsistencies.
    - LLM Config (llm_config.py): On-prem LLM configuration for Deloitte endpoint.
"""

__version__ = "0.3.0"
