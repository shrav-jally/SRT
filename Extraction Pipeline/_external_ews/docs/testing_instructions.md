# Testing Instructions for Company Laptop Testing

This document provides step-by-step instructions to pull, run, validate, and benchmark the **Enterprise Two-Layer Custom Extraction Engine** on your company laptop with the on-premise Qwen VLM connected.

---

## 1. Prerequisites & Environment Setup

On your company laptop, open your terminal (PowerShell or Bash) and navigate to the project directory.

### Step 1.1: Git Pull Latest Changes
Ensure you are on the `qwen-onprem` branch and have pulled the latest committed architecture code:

```bash
git checkout qwen-onprem
git pull origin qwen-onprem
```

### Step 1.2: Virtual Environment & Dependencies
Make sure your Python virtual environment is activated and dependencies are up to date:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Install / update dependencies if needed
pip install -r requirements.txt
```

---

## 2. Fast Verification (Contract & Unit Tests)

Run the fast contract and engine unit tests to verify your Python environment and imports:

```bash
# 1. Run versioned contract tests
python tests/contract/test_contracts.py

# 2. Run custom spec engine unit tests
python tests/contract/test_custom_spec.py

# 3. Run legacy pipeline sprint 2 tests
python test_sprint2.py
```

**Expected Outcome**: All three test runs should print `PASSED!` with zero errors.

---

## 3. Running the Full Extraction Demo

Run the main Two-Layer Custom Extraction Demo against your target PDF file (e.g. `cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf` or any annual report PDF on your company laptop):

```bash
python -m demo.run_custom_extraction --pdf cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf --spec sample_custom_spec.json
```

*Note: Replace `cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf` with your actual annual report PDF path if testing another report.*

---

## 4. What to Look For & How to Validate

Once the command finishes, check the console output summary table and the generated artifacts under `output/<document_id>/`:

### 4.1 Check Generated Artifacts
Navigate to `output/<document_id>/` and inspect these three files:

1. **`canonical_document.v0.json`** (Product 1 Output):
   - Check file size (should be 500KB - 5MB depending on PDF length).
   - Check `pages` count, `sections` list, and `tables` array.
   - Verify `document_metadata` (company name, FY, currency, unit denomination).

2. **`custom_extraction_result.json`** (Product 2 JSON Output):
   - Inspect the 10 requested fields from `sample_custom_spec.json`.
   - Verify every `FOUND` field contains full `provenance` (`page_number`, `section_id`, `table_id`, `raw_text`).
   - Check `status` counts (`FOUND`, `NOT_FOUND`, `AMBIGUOUS`, `FAILED_VALIDATION`).

3. **`custom_extraction_result.xlsx`** (Excel Presentation Output):
   - Open in Excel / LibreOffice.
   - Check the **Status** column (Green = `FOUND`, Orange/Red = `NOT_FOUND` / `FAILED_VALIDATION`).
   - Verify that column headers and formatting are clean and readable.

### 4.2 Key Extraction Fields to Validate (from `sample_custom_spec.json`)

| Field ID | Expected Source Section | Expected Extraction Mode | Validation Criteria |
|---|---|---|---|
| `company_name` | Corporate Overview / Cover | `DIRECT_MAPPING` | Legal company name |
| `board_of_directors` | Board of Directors | `DIRECT_MAPPING` | Director names / DINs |
| `employee_count` | Workforce / BRSR / HR | `DIRECT_MAPPING` | Headcount number |
| `balance_sheet` | Balance Sheet | `DIRECT_MAPPING` | Statement table match |
| `profit_and_loss` | Statement of P&L | `DIRECT_MAPPING` | Statement table match |
| `cash_flow` | Cash Flow Statement | `DIRECT_MAPPING` | Statement table match |
| `share_capital` | Shareholding / Directors Report | `DIRECT_MAPPING` | Equity capital figure |
| `dividend_info` | Directors Report | `DIRECT_MAPPING` | Dividend per share / amount |
| `auditor_report` | Independent Auditor's Report | `DIRECT_MAPPING` | Auditor name & opinion |
| `business_outlook` | MD&A / Strategy | `INFERENCE_BASED` | Strategic summary via LLM |

---

## 5. What to Report Back Here

After running the demo test on your company laptop, reply back with the following details:

```markdown
### 1. Test Suite Results
- `test_contracts.py`: [PASSED / FAILED]
- `test_custom_spec.py`: [PASSED / FAILED]
- `test_sprint2.py`: [PASSED / FAILED]

### 2. Demo Execution Summary
- **PDF Tested**: [File Name / Page Count]
- **Elapsed Time**: [X seconds / minutes]
- **Completion Stats**:
  - Total Fields Requested: 10
  - Fields FOUND: [X]
  - Fields NOT FOUND: [Y]
  - Completion Rate: [Z%]

### 3. Field Results Break-down
- `company_name`: [FOUND / NOT_FOUND] (Value: ...)
- `board_of_directors`: [FOUND / NOT_FOUND]
- `employee_count`: [FOUND / NOT_FOUND]
- `balance_sheet`: [FOUND / NOT_FOUND]
- `profit_and_loss`: [FOUND / NOT_FOUND]
- `cash_flow`: [FOUND / NOT_FOUND]
- `share_capital`: [FOUND / NOT_FOUND]
- `dividend_info`: [FOUND / NOT_FOUND]
- `auditor_report`: [FOUND / NOT_FOUND]
- `business_outlook`: [FOUND / NOT_FOUND] (Explanation: ...)

### 4. Issues or Connection Errors
- Any VLM / LLM API errors, timeout warnings, or missing section issues.
```
