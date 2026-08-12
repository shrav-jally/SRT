# EWS Annual Report Extraction Agent

An agent-based system that extracts financial data from Indian annual report PDFs and populates an Excel template with Balance Sheet, P&L, and Cash Flow data.

## Architecture

The agent follows an **LLM-first, deterministic-validation** approach for maximum accuracy:

```
┌──────────────────────────────────────────────────────────────┐
│                    Annual Report PDF                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Step 1:    │  ★ LLM page identification (PRIMARY)
                    │  Find       │  Quick deterministic check (cost opt)
                    │  Pages      │  Deterministic validation (SECONDARY)
                    │             │  + Statement type detection
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 2:    │  From filename or page text
                    │  Detect     │  "March 31, 2024" patterns
                    │  Year       │  LLM verification (low conf)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 2b:   │  ★ LLM-detected (with page ID)
                    │  Statement  │  Deterministic keyword scan
                    │  Type       │  Prefer standalone over consolidated
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 3:    │  pdfplumber extract_text()
                    │  Extract    │  Line-by-line parsing
                    │  BS/P&L/CF  │  Section tracking
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 3b:   │  Parse Notes to Accounts
                    │  Extract    │  for "Other Financial
                    │  Notes      │  Information" items
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4:    │  Keyword aliases (exact match)
                    │  Map to     │  ★ LLM mapping (PRIMARY)
                    │  Template   │  Fuzzy matching (FALLBACK)
                    │             │  3-way merge: alias > LLM > fuzzy
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 5:    │  Write values + formulas
                    │  Write      │  + Meta Data sheet
                    │  Excel      │  + Raw extracted tables
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Steps 6-7: │  Completeness % and
                    │  Meta Data  │  extraction metadata
                    └─────────────┘

★ = LLM used as PRIMARY method
```

### Why LLM-first?

1. **Semantic understanding**: LLM understands that "Right of use assets" maps to "Others (NC assets)" — fuzzy matching scores this as 0. LLM handles abbreviations (CWIP, PPE), CID-fragmented text, and section disambiguation.

2. **Non-standard titles**: LLM identifies a Balance Sheet even with non-standard titles, bilingual headers, or CID-fragmented text that deterministic regex patterns miss.

3. **Cost optimization**: A quick deterministic check skips the LLM for ~70% of standard PDFs that use exact Schedule III titles. LLM is only invoked when needed.

4. **Deterministic validation**: After LLM identifies pages, deterministic methods validate and add any missed continuation pages. This catches LLM hallucinations while preserving LLM's semantic advantages.

5. **Indian standards enable efficiency**: Schedule III of the Companies Act, 2013 prescribes exact format for BS/P&L/CF. This makes keyword alias matching highly effective for standard items, so LLM only needs to handle the non-standard variations.

### LLM Usage Summary

| Pipeline Stage | Primary | Secondary/Fallback |
|---|---|---|
| **Page Finding** | ★ `find_pages_by_llm()` | `_validate_with_deterministic()` |
| **Statement Type** | ★ LLM (same call as page ID) | Deterministic keyword scan |
| **Mapping** | ★ `map_by_llm()` (after aliases) | Fuzzy matching |
| **Year Detection** | Filename regex → page text | LLM verification (low conf only) |
| **Notes Pages** | Deterministic (regex) | — (no LLM needed) |

## Setup

### Option 1: Using setup.sh
```bash
chmod +x setup.sh
./setup.sh
```

### Option 2: Manual installation
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### FastAPI Web Application (Recommended)

```bash
# Start the server
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080

# Open browser: http://localhost:8080
# Drag-and-drop PDF(s) → real-time progress → download Excel
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web UI (drag-and-drop upload) |
| `/extract` | POST | Upload PDF(s) for extraction |
| `/status/{job_id}` | GET | Check extraction progress (real-time) |
| `/download/{job_id}` | GET | Download completed Excel |
| `/health` | GET | Health check |
| `/jobs` | GET | List all jobs |

### Upload via curl

```bash
# Single PDF (year auto-detected from filename)
curl -X POST http://localhost:8080/extract \
  -F "files=@Annual_Report_2022-2023.pdf"

# With explicit year
curl -X POST http://localhost:8080/extract \
  -F "files=@report.pdf" \
  -F "years=2023"

# Check status
curl http://localhost:8080/status/{job_id}

# Download result
curl -O http://localhost:8080/download/{job_id}
```

### Programmatic Usage

```python
from ews_agent.smart_agent import SmartExtractionAgent

agent = SmartExtractionAgent(llm=None, use_llm=True)
result = agent.run(
    pdf_path="Annual_Report.pdf",
    template_path="Entities for extraction.xlsx",
    output_path="output.xlsx",
    year=2024,  # Optional — auto-detected if not provided
)

print(f"BS: {result.bs_completeness:.1%}")
print(f"P&L: {result.pl_completeness:.1%}")
print(f"CF: {result.cf_completeness:.1%}")
print(f"Overall: {result.overall_completeness:.1%}")
```

## Project Structure

```
EWS/
├── app.py                        # FastAPI application (REST API + web UI)
├── setup.sh                      # Dependency installation script
├── requirements.txt              # Python dependencies
├── Entities for extraction.xlsx  # Excel template (3 sheets: BS, P&L, CF)
├── METHODOLOGY.md                # Detailed methodology documentation
├── FDD.html                      # Functional Design Document (visual)
├── FLOWCHART.html                # Master flowchart with WHY/HOW/STD annotations
├── AGENTIC_FLOW.html             # Agentic workflow diagram
├── ews_agent/                    # Agent package
│   ├── __init__.py
│   ├── smart_agent.py            # Main orchestrator (7-step pipeline)
│   ├── table_finder.py           # ★ LLM-first page identification + deterministic validation
│   ├── text_table_extractor.py   # Deterministic text parsing (pdfplumber)
│   ├── data_mapper.py            # ★ LLM-primary mapping + fuzzy fallback + 3-way merge
│   ├── excel_writer.py           # Excel output (openpyxl)
│   └── llm_utils.py             # LLM utility (on-prem Qwen, retry, JSON parse)
├── static/
│   └── index.html                # Web UI (drag-and-drop, real-time progress)
├── uploads/                      # Temporary PDF uploads (auto-cleaned)
└── api_output/                   # Generated Excel files
```

## Excel Template Structure

The template (`Entities for extraction.xlsx`) has 3 worksheets:

### 1. Balance Sheet
- **ASSETS**: Non-current assets (PPE, CWIP, intangibles, financial assets, etc.) + Current assets (inventories, receivables, cash, etc.)
- **EQUITY**: Share capital, other equity, profit for the year
- **LIABILITIES**: Non-current liabilities (borrowings, trade payables, provisions, etc.) + Current liabilities

### 2. P&L
- **Income**: Revenue from operations, other income, total income
- **Expenses**: Materials, purchases, employee benefits, finance costs, depreciation, other expenses
- **Taxes**: Current tax, deferred tax
- **Profit/Loss**: Before tax, after tax, from discontinued operations
- **EBITDA / EBIT**

### 3. Cash Flow
- **Cash Flow**: Operating, investing, financing activities
- **Other Financial Information**: Contingent liabilities, outstanding creditors/debtors, RP data, etc. (extracted from Notes to Accounts)

## Output Excel

The output Excel has **7 sheets**:

| Sheet | Content |
|-------|---------|
| Meta Data | Extraction metadata (unit, statement type, pages, stats, completeness) |
| Balance Sheet | Template with extracted values + formulas |
| P&L | Template with extracted values + formulas |
| Cash Flow | Template with extracted values + formulas |
| Raw BS | Raw extracted table data (as-is from PDF) |
| Raw P&L | Raw extracted table data |
| Raw CF | Raw extracted table data |

The **Raw sheets** contain ALL extracted rows from ALL detected pages for that statement type. These same rows are what the mapping step uses to populate the real BS/P&L/CF sheets. If wrong pages were included at detection, the Raw sheet would show irrelevant data and the mapping would struggle.

## LLM Configuration

The agent uses the on-prem Qwen2.5-7B-Instruct model via OpenAI-compatible API. Configuration is read from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `https://llm-qwen-7b-route-srt-innovation...` | On-prem LLM API URL |
| `LLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Model name |
| `LLM_API_KEY` | `not-needed` | API key |
| `LLM_MAX_TOKENS` | `2048` | Max generation tokens |
| `LLM_TEMPERATURE` | `0.0` | Temperature (0 = deterministic) |
| `LLM_VERIFY_SSL` | `false` | SSL verification (self-signed certs) |

## Known Limitations

1. **Notes OFI mapping effectiveness**: The notes keyword aliases cover common terms but may miss company-specific wording.
2. **Year column detection**: Relies on header patterns like "As at March 31, 2024" — non-standard headers may fail.
3. **Title on separate page**: If the statement title is on a completely different page than the data, extraction may fail.
4. **No cross-validation**: No inter-statement consistency checks (e.g., Total Assets = Total Equity + Liabilities).
5. **Equity roll-forward**: Not integrated into the main pipeline — equity items may not be fully extracted.

## Documentation

- [METHODOLOGY.md](METHODOLOGY.md) — Detailed 7-step pipeline documentation
- [FDD.html](FDD.html) — Functional Design Document with flowcharts and case tables
- [FLOWCHART.html](FLOWCHART.html) — Master flowchart with WHY/HOW/STANDARD annotations
- [AGENTIC_FLOW.html](AGENTIC_FLOW.html) — Agentic workflow diagram with data handoffs
