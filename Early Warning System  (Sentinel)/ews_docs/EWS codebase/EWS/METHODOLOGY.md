# EWS Annual Report Extraction Agent — Methodology (SmartExtractionAgent Architecture)

## 1. Problem Statement

Given an annual report PDF (e.g., Godrej Properties, Sobha Limited) and an Excel template with three worksheets (Balance Sheet, P&L, Cash Flow), extract financial data from the PDF and populate the template for a specified financial year.

### Key Constraints

- **Deterministic extraction first**: Table extraction from PDF is deterministic (pdfplumber text parsing, like Excel's "Get Data from PDF") — this is not probabilistic and should not be made so.
- **LLM as primary mapper**: The on-prem LLM (Qwen2.5-7B-Instruct) is the **primary** mapping method after keyword aliases. LLM understands semantic equivalence, section context, abbreviations, and CID-fragmented text far better than fuzzy matching. Fuzzy matching is the **fallback** when LLM is unavailable or returns no results.
- **Keyword aliases → LLM → Fuzzy (fallback)**: Three-tier mapping priority: (1) keyword aliases for deterministic exact matches, (2) LLM for semantic understanding of remaining items, (3) fuzzy matching as fallback only. This ensures higher accuracy because LLM captures context that fuzzy string similarity misses.
- **Standardized naming**: Indian annual reports follow Schedule III of the Companies Act 2013, so financial statement terminology is largely standardized — keyword aliases handle the most common variations, and LLM handles the rest.
- **Handle PDF encoding issues**: Many Indian annual report PDFs use CID fonts without ToUnicode CMaps. These are handled by stripping CID placeholders before matching.
- **Fully automatic**: No manual page input required — the agent auto-detects which pages contain BS/P&L/CF statements.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Annual Report PDF                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Step 1:    │  ★ LLM page identification (PRIMARY)
                    │  Find       │  Quick deterministic check (cost opt)
                    │  Pages      │  Deterministic validation (SECONDARY)
                    │  + Type     │  Notes detection (deterministic)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 2:    │  5 filename patterns + page text
                    │  Detect     │  ★ LLM verification for low-confidence
                    │  Year       │  target_year threaded to mapper
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 2b:   │  Use statement_type from Step 1
                    │  Prefer     │  (LLM-detected or deterministic)
                    │  Standalone │  Filter to standalone when both exist
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 3:    │  pdfplumber extract_text()
                    │  Extract    │  Line-by-line parsing
                    │  BS/P&L/CF  │  Section tracking
                    │  Tables     │  No grid lines needed
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 3b:   │  Find notes section after
                    │  Extract    │  financial statements
                    │  Notes      │  Parse ALL lines (no start
                    │  Tables     │  pattern needed)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4:    │  Keyword alias pre-pass
                    │  Map        │  ★ LLM mapping (primary)
                    │  BS/P&L/CF  │  + Fuzzy matching (fallback)
                    │  to Template│  + Section-aware scoring
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4b:   │  4-phase notes mapping:
                    │  Map Notes  │  1. Keyword alias
                    │  to OFI     │  2. Context-aware total
                    │  + Merge    │  3. ★ LLM mapping (primary)
                    │             │  4. Fuzzy fallback
                    │             │  Smart override: notes > default_zero
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4c:   │  Default 0 for absent items
                    │  Default    │  (Goodwill, Biological Assets,
                    │  Zeros      │   Discontinued ops, etc.)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4d:   │  Compute residual items
                    │  Compute    │  "Other NC liabilities" = total - known
                    │  Derived    │  "Others (CA)" = total - known
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 4.5b: │  ★ CA Validation & Inference
                    │  CA         │  1. Cross-statement validation
                    │  Validator  │  2. Inferential mapping (EBITDA, EBIT, etc.)
                    │             │  3. Note cross-reference tracking
                    │             │  4. Ind AS / Schedule III compliance
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 5:    │  Write to column C
                    │  Write      │  Apply Excel formulas
                    │  Excel      │  + Meta Data sheet
                    │             │  + Raw extracted table sheets
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 6:    │  BS/P&L/CF completeness %
                    │  Compute    │  Based on leaf items filled
                    │  Completeness│ vs total leaf items
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Step 7:    │  Write Meta Data sheet
                    │  Write      │  (unit, statement type,
                    │  Meta Data  │   pages, stats, completeness)
                    └─────────────┘

★ = LLM used as PRIMARY method (Steps 1, 4) or verification (Step 2)
```

---

## 3. Step-by-Step Methodology

### Step 1: Find Financial Statement Pages (★ LLM-First with Deterministic Validation)

**Module**: [`table_finder.py`](ews_agent/table_finder.py)

**Goal**: Auto-detect which PDF pages contain the Balance Sheet, P&L, and Cash Flow statements, AND detect the statement type (Standalone vs Consolidated).

**Design principle**: LLM-first with deterministic validation. The LLM is the PRIMARY page finder because it understands context, non-standard titles, abbreviations, and CID-fragmented text. Deterministic methods validate LLM results and add any missed pages. For highly standard cases (exact Schedule III titles), a quick deterministic check skips the LLM call entirely (cost optimization).

**LLM-First Strategy** (4 steps):

| Step | Method | Role | When Used |
|------|--------|------|-----------|
| 1 | Quick deterministic check | Cost optimization | Always (fast, no LLM cost) |
| 2 | ★ LLM page identification | **PRIMARY** | When quick check is incomplete |
| 3 | Deterministic validation | **SECONDARY** (validation) | Always after LLM (merges + expands) |
| 4 | Notes page detection | Deterministic | Always (regex-based) |

**Step 1a — Quick Deterministic Check** ([`_quick_deterministic_check()`](ews_agent/table_finder.py:736)):

Cost optimization — if the PDF uses standard Schedule III titles (e.g., "Standalone Balance Sheet as at March 31, 2024"), all 3 statements can be found without an LLM call. This saves time and money for ~70% of Indian annual reports.

- Only runs Pass 1 title-area scan (first 10 lines, strict patterns)
- Does NOT do full-page scan or content-based detection
- If all 3 statements found with `confidence >= 1.0` → skip LLM, return immediately
- Also detects statement type from found pages (Standalone/Consolidated)
- `detection_method = "quick_deterministic"`

**Step 1b — ★ LLM Page Identification** ([`find_pages_by_llm()`](ews_agent/table_finder.py:837)) — **PRIMARY method**:

When the quick check is incomplete (missing one or more statements), the LLM identifies pages:

- Samples pages: every 2nd page in the financial section (15%-95%), plus first 5 pages, plus hint pages and their neighbors
- Sends 400-char snippets from each sampled page to LLM
- LLM receives deterministic hints (pages found by quick check) as guidance
- LLM returns JSON: `{balance_sheet: [pages], profit_and_loss: [pages], cash_flow: [pages], changes_in_equity: [pages], statement_type: "Standalone"|"Consolidated", confidence: "high"|"medium"|"low"}`
- Statement type is detected in the **same LLM call** (no extra cost)
- `detection_method = "llm_primary"`

**Why LLM-first for page finding?**
- LLM understands non-standard titles that regex patterns miss
- LLM handles abbreviations (e.g., "P&L" = "Profit and Loss")
- LLM can distinguish a title from a reference (e.g., "Balance Sheet" title vs "Refer to Balance Sheet")
- LLM detects statement type in the same call (no separate detection needed)
- LLM handles CID-fragmented text that breaks regex patterns

**Step 1c — Deterministic Validation** ([`_validate_with_deterministic()`](ews_agent/table_finder.py:1006)) — **SECONDARY**:

After LLM identifies pages, deterministic methods validate and supplement:

1. **Merge** (union, not intersection): LLM pages + deterministic pages — deterministic can add pages LLM missed
2. **Expand continuation pages**: Look up to 4 pages ahead for "(continued)" markers, matching content type, or strong content score (≥ 0.5)
3. **Cross-validate statement type**: If LLM said "Standalone" but deterministic found only consolidated pages, correct it
4. `detection_method = "llm_primary_validated"`

**Key rule**: Deterministic validation CANNOT remove pages found by LLM (LLM may see content that regex patterns miss), but it CAN add pages that LLM missed.

**Step 1d — Notes Pages Detection** (always deterministic):
- `find_notes_pages()`: Searches after the last financial statement page
- Looks for "Notes to Financial Statements" or similar titles (13+ patterns)
- Includes pages until hitting end patterns (Auditor's Report, Director's Report, etc.)
- Broad search: 60 pages forward, 50 pages backward, full PDF scan as last resort
- Notes pages are used for "Other Financial Information" extraction

**Fallback**: If LLM is unavailable (`llm=None` or `use_llm=False`), falls back to full deterministic scan: title scan → full-page scan → content-based detection (the old multi-pass approach). `detection_method = "deterministic_fallback"`.

**Line-by-line title validation** ([`_line_contains_title()`](ews_agent/table_finder.py:246)):

A pattern match is only considered a TITLE (not a reference) if:
1. The match starts within the first 5 characters of the line, OR
2. The line is short (≤ 70 chars — titles are usually short), OR
3. The match starts within the first 40% of the line (allows company name prefix)

This prevents false positives from lines like:
- ❌ "Refer to the Balance Sheet on page 47" (match too far into line)
- ❌ "As per the Cash Flow Statement, the company..." (match too far)
While allowing true titles like:
- ✅ "Balance Sheet" (short line, match at start)
- ✅ "Godrej Properties Limited Balance Sheet" (match within first 40%)
- ✅ "Standalone Statement of Profit and Loss" (match at start)

**Output**: `FinancialStatementPages` dataclass with `balance_sheet`, `profit_and_loss`, `cash_flow`, `changes_in_equity`, `notes_pages` page lists, `statement_type` ("Standalone"/"Consolidated"), `detection_method`, and `confidence`.

### Step 2: Auto-Detect Year (Deterministic + ★ LLM Verification for Low-Confidence)

**Module**: [`smart_agent.py`](ews_agent/smart_agent.py) — `_detect_year_from_pdf()`, `_detect_year_from_page_text()`, `_verify_year_with_llm()`

**Indian Financial Year convention**: FY "2017-18" means year ending March 31, 2018. We always return the **ending year** (2018, not 2017).

**Strategy** — 5 ordered filename patterns, then page text, then LLM verification:

| Priority | Pattern | Example Filename | Result | Detection Method | Confidence |
|----------|---------|-----------------|--------|-----------------|------------|
| 1 | Full 4-digit range | `Annual-Report-2022-2023.pdf` | 2023 | `filename_full_range` | High |
| 2 | 4-digit + 2-digit suffix | `AnnualReport2017-18.pdf` | 2018 | `filename_2digit_suffix` | High |
| 3 | 6-digit compact YYYY+YY | `RajeshExportsAR202021.pdf` | 2021 | `filename_compact6` | High |
| 4 | FY prefix | `Report_FY2024.pdf` | 2024 | `filename_fy_prefix` | Medium |
| 5 | Single 4-digit year | `2023_Annual_Report.pdf` | 2023 | `filename_single_year` | Low* |
| 6 | Page text scan | Any PDF | — | `page_text` | High |
| 7 | Default | — | current year | `default_current` | Low |

*Pattern 5 tries page text first before falling back to the single filename year.

**Validation**: Patterns 1-3 verify `ending_year == year1 + 1` to prevent false matches (e.g., `"2020-15"` fails validation).

**Page text detection** ([`_detect_year_from_page_text()`](ews_agent/smart_agent.py:375)):
- Scans financial statement pages for `(March|April) \d{1,2},? (20\d{2})` patterns
- Returns the latest year found across all scanned pages
- Used as primary detection when filename has no year pattern, or as higher-confidence override when filename only has a single 4-digit year

**★ LLM Verification** ([`_verify_year_with_llm()`](ews_agent/smart_agent.py:418)):
- Only triggers for low-confidence detection methods: `filename_single_year`, `filename_fy_prefix`, `default_current`
- Sends first 1500 chars of the first financial statement page to LLM
- LLM returns JSON: `{"year": int, "confidence": "high"|"medium"|"low", "reasoning": str}`
- Can correct the detected year if LLM disagrees
- If LLM corrects the year, `year_detection_method` is set to `"llm_verified"`

**target_year threading**: The detected year is passed as `target_year` through the entire mapping pipeline:
- `map_balance_sheet(headers, rows, target_year=year)`
- `map_profit_and_loss(headers, rows, target_year=year)`
- `map_cash_flow(headers, rows, target_year=year)`
- `map_notes_to_other_financial_info(headers, rows, cf_mappings, year, target_year=year)`

This ensures [`_detect_year_column()`](ews_agent/data_mapper.py:986) selects the column matching the detected financial year, preventing wrong-year data extraction when headers contain multiple years.

**ExtractionResult** includes `year_detection_method` field (written to Meta Data sheet) for traceability.

### Step 2b: Standalone-Only Policy (Uses LLM-Detected Statement Type)

**Module**: [`smart_agent.py`](ews_agent/smart_agent.py) — `_prefer_standalone()`

**Policy**: This app extracts **ONLY standalone financial statements**. Per Schedule III of the Companies Act, 2013, standalone financial statements represent the company's own financials. Consolidated statements include subsidiaries and are not comparable on a like-for-like basis. If only consolidated pages are found, extraction is **aborted entirely**.

**Statement type**: Detected by the LLM/deterministic page finder in Step 1 (`FinancialStatementPages.statement_type`). The agent uses this directly instead of re-detecting. Falls back to `_detect_statement_type()` only if the page finder returned "Not specified".

**Filtering logic** ([`_prefer_standalone()`](ews_agent/smart_agent.py:1250)):
1. Check each page's title area (first 10 lines) for "Standalone" or "Consolidated"
2. If standalone pages found → use only those (skip consolidated)
3. If no clear indicator → keep the page (assume standalone per Schedule III default)
4. If ONLY consolidated pages found → return **empty list** (skip extraction for that statement)

**Standalone-only gate** (Step 2c in pipeline):
- After filtering, if ALL three statements (BS, P&L, CF) have no standalone pages → **abort extraction** with error: `"STANDALONE-ONLY POLICY: No standalone financial statement pages found"`
- If some statements have standalone pages but others don't → continue with available standalone statements, log warnings for skipped consolidated-only statements
- `result.statement_type` is set to `"Consolidated (rejected)"` when extraction is aborted

### Step 3: Extract Financial Statement Tables (Deterministic — No LLM)

**Module**: [`text_table_extractor.py`](ews_agent/text_table_extractor.py)

**Primary Method**: pdfplumber `extract_text()` + line-by-line parsing

Indian annual reports typically have **gridless tables** — no visible borders. `pdfplumber.extract_tables()` returns empty, but `extract_text()` works perfectly. This is identical to Excel's "Get Data from PDF" text import approach.

**Parsing Process**:
1. Extract text from each page using `pdfplumber.extract_text()`
2. Find the statement start line using two-tier pattern matching
3. Parse each line after the start:
   - `_parse_line()`: Scans right-to-left for numeric values
   - Detects note references like "(1)", "(2)" after the label
   - Handles parenthesized negative values like `(1,234.56)`
   - Tracks indent level for hierarchy detection
4. Section tracking: When a section header like "Non-current assets" is detected, all subsequent rows are assigned to that section until a new section header appears
5. Post-processing: Remove duplicate rows, fix continuation lines, detect unit patterns

**Unit Detection**: Scans page text for 30+ patterns:
- `₹ in Lakhs`, `₹ in Crores`, `Amounts in millions`, `Rs. in thousands`, etc.
- Stored in `ExtractedTable.unit` for Meta Data sheet

**Output**: `ExtractedTable` dataclass with:
- `rows: list[ExtractedRow]` — Each row has `label`, `note_ref`, `values`, `indent_level`, `is_total`, `is_section_header`
- `year_headers` — Column headers like "As at March 31, 2024"
- `page_numbers` — Which pages were extracted from
- `unit` — Detected value unit

### Step 3b: Extract Notes to Accounts Tables (Deterministic — No LLM)

**Module**: [`text_table_extractor.py`](ews_agent/text_table_extractor.py) — `extract_notes_from_pages()`

**Difference from Step 3**: Notes pages don't have a single "statement start" — they contain multiple notes, each with its own structure. So we parse ALL lines on every notes page.

**Parsing Process**:
1. For each notes page, extract text and parse every line
2. No statement start pattern needed — all lines are data
3. Same `_parse_line()` logic for value extraction
4. Section tracking uses note titles as section headers

**Output**: `ExtractedTable` with `statement_type="notes"`

### Step 4: Map Extracted Data to Template (Alias → ★ LLM → Fuzzy Fallback)

**Module**: [`data_mapper.py`](ews_agent/data_mapper.py)

**Goal**: Map PDF row labels to template line items using a three-tier strategy: keyword aliases (deterministic) → LLM (semantic, primary) → fuzzy matching (fallback).

**Why LLM-first?** Fuzzy string similarity (rapidfuzz `token_sort_ratio`) measures character-level similarity but cannot understand:
- **Semantic equivalence**: "Right of use assets" ≈ "Others (to be specified)" in Non-current assets — fuzzy score is 0, but LLM understands the accounting context
- **Section context**: "Other liabilities" in Non-current vs Current section — same label, different template item. LLM uses section information to disambiguate
- **Abbreviations**: "CWIP" = "Capital work-in-progress", "PPE" = "Property, Plant and Equipment" — fuzzy misses these
- **CID-fragmented text**: "operat ing activi ties" — fuzzy may match, but LLM handles it more reliably with surrounding context

#### 4a. Balance Sheet Mapping

**Function**: `map_balance_sheet(headers, rows, year_column=None, target_year=None, llm=None)`

**Three-tier approach** (ordered by priority):

| Tier | Method | Purpose | Confidence |
|------|--------|---------|------------|
| 1. Keyword alias | `BS_KEYWORD_ALIASES` (30+ aliases) | Deterministic exact matches for common variations | 0.95 |
| 2. ★ LLM mapping | `map_by_llm()` | Semantic understanding of remaining unmapped items | ≤ 0.90 |
| 3. Fuzzy fallback | `map_table_to_template()` | Character-level similarity for anything LLM missed | varies |

**Keyword Aliases** handle cases like:
- `"right of use assets"` → `"(iv) Others (to be specified)"` in Non-current assets
- `"lease liabilities"` → `"(iii) Other financial liabilities"` in Non-current liabilities
- `"tangible assets"` → `"(a) Property, Plant and Equipment"` (PPE sub-component)
- `"cwip"` → `"(b) Capital work-in-progress"`

**★ LLM Mapping** ([`map_by_llm()`](ews_agent/data_mapper.py:1085)):
- Receives: unmapped template items (with sections), all PDF rows (with values and sections), already-mapped items, exclude row indices
- Builds structured prompt asking LLM to match each unmapped template item to the best PDF row
- LLM returns JSON: `{"mappings": [{"template_item": "...", "row_number": N, "value": "...", "confidence": 0.9}]}`
- Uses `llm_call_with_retry()` with exponential backoff
- Filters out formula items and already-mapped items
- Returns `(list[MappingResult], set[int])` — both mappings AND matched row indices (so fuzzy pass can skip them)
- Method = `"llm"`, confidence capped at 0.90

**Fuzzy Matching** (`map_table_to_template()`) — **fallback only**:
- Only runs on rows NOT already matched by alias or LLM
- **Pass 1**: Collect ALL (pdf_row, template_item, score) candidates
- **Pass 2**: Assign optimally by processing in descending score order (greedy)
- **Section-aware scoring**: Same-section matches get +15 bonus; cross-section matches get -20 penalty
- **Formula item exclusion**: Template items in `FORMULA_TEMPLATE_ITEMS` are never matched
- **Total row exclusion**: Rows matching `TOTAL_ROW_PATTERNS` are skipped

**3-Way Merge** ([`_merge_alias_llm_and_fuzzy()`](ews_agent/data_mapper.py)):
When multiple methods map to the same template item, priority is: **alias > LLM > fuzzy**.
- Parent-child deduplication across all three sources (child value preferred over parent)
- Complementary values from different methods are kept (different template items)
- When `llm=None`, falls back to `_merge_alias_and_fuzzy()` (backward compatible)

#### 4b. P&L Mapping

**Function**: `map_profit_and_loss(headers, rows, year_column=None, target_year=None, llm=None)`

Same three-tier approach as BS, using `PL_KEYWORD_ALIASES`:
- `"land purchase cost"` → `"Purchases of Stock-in-Trade"` (real estate specific)
- `"deferred tax charge"` → `"(2) Deferred tax"` (common P&L label variation)

LLM maps remaining items after alias pass, fuzzy is fallback.

#### 4c. Cash Flow Mapping

**Function**: `map_cash_flow(headers, rows, year_column=None, target_year=None, llm=None)`

**Four-phase approach** (ordered by reliability):

| Phase | Method | Target Items |
|-------|--------|-------------|
| 0. Structural | Find "Net cash" rows, assign in order | 3 summary items (Ops/Invest/Finance) |
| 1. Alias | `CF_PHRASE_ALIASES` + `CF_ANCHOR_ALIASES` | 3 summary items (fallback) |
| 2. ★ LLM | `map_by_llm()` for OFI items | "Other Financial Information" items |
| 3. Fuzzy | `map_table_to_template()` | Remaining OFI items (fallback) |

**Structural matching** (`_structural_cf_match()`):
- Finds rows containing "net ca" (CID-tolerant form of "net cash")
- Assigns in order: Operations → Investing → Financing
- Most reliable for CID-fragmented text

**LLM for OFI**: After structural + alias phases handle the 3 summary CF items, LLM maps the "Other Financial Information" sub-template items (contingent liabilities, current maturities, etc.) that appear in the CF template but are sourced from notes.

### Step 4b: Map Notes to "Other Financial Information" + Smart Merge

**Module**: [`data_mapper.py`](ews_agent/data_mapper.py) — `map_notes_to_other_financial_info(notes_headers, notes_rows, existing_cf_mappings, year, target_year=None, llm=None)`

**Goal**: Extract CF template's "Other Financial Information" items (19 items) from Notes to Accounts.

These items are NOT in the Cash Flow statement itself — they come from specific notes:
- Contingent Liabilities → Note "Contingent liabilities and commitments"
- Current maturities → Note "Borrowings"
- Power and fuel → Note "Other expenses"
- Bad debts → Note "Other expenses"
- Auditors Remuneration → Note "Auditors' Remuneration"
- RP items → Note "Related party disclosures"

**Four-phase mapping** (alias → context → ★ LLM → fuzzy):

| Phase | Method | Details |
|-------|--------|---------|
| 1. Keyword alias | `NOTES_KEYWORD_ALIASES` (50+ aliases) | Deterministic exact substring matching |
| 2. Context-aware total | `_CONTEXT_TOTAL_ITEMS` | Find "Total" rows within specific note contexts |
| 3. ★ LLM mapping | `map_by_llm()` | **Primary** — semantic understanding of remaining OFI items |
| 4. Fuzzy fallback | `token_sort_ratio >= 65` | For any still-unmatched items after LLM |

**LLM as primary notes mapper**: The LLM receives the OFI sub-template `{"Other Financial Information": {...}}` with only the unmapped items, plus all notes rows excluding those already matched by alias/context phases. This focuses the LLM on exactly the items that need semantic matching.

**Critical: Default-zero exclusion**: The `already_mapped` set excludes items with `method="default_zero"`. This allows notes (and LLM) to find real values for items that were initially defaulted to 0. Without this exclusion, notes could never override default zeros.

**Smart Merge** (in `smart_agent.py`):
When notes mappings are merged into CF mappings:
1. New items (not in CF) → added directly
2. Items already in CF with `method="default_zero"` → replaced with notes value (smart override)
3. Items already in CF with real values → kept as-is (CF statement value is more reliable)

### Step 4c: Default Zeros (Deterministic — No LLM)

**Module**: [`data_mapper.py`](ews_agent/data_mapper.py) — `apply_default_zeros()`

**Goal**: Add value=0 for commonly absent template items.

| Sheet | Default Zero Items | Count |
|-------|-------------------|-------|
| BS | Goodwill, Biological Assets, Deferred tax liabilities (NC), Other NC liabilities, Current Tax Assets, Current Investments, Others (CA), Other financial liabilities (NC) | 8 |
| P&L | Discontinued operations, Exceptional items | 4 |
| CF | Creditors >1yr, Debtors >1yr, Inventory >180d, Impairment, Doubtful debts provision, Bad debts, RP items | 11 |

**Important**: Default-zero items can be overridden by notes extraction (see Step 4b smart merge).

### Step 4d: Derived Items Computation (Deterministic — No LLM)

**Module**: [`data_mapper.py`](ews_agent/data_mapper.py) — `compute_derived_items()`

**Goal**: Compute catch-all/residual template items that aren't directly in the PDF.

**Residual computation**: `parent_total - sum(known_leaf_sub_items)`

Examples:
- `"(d) Other non-current liabilities"` = Total NC Liabilities - Borrowings - Trade Payables - Other fin liab - Provisions - Deferred tax
- `"(vi) Others (to be specified)"` (Current Assets) = Total Current Assets - Inventories - Financial Assets - Current Tax - Other current assets

**Configuration**: `DERIVED_ITEMS` dict defines rules per item with `subtract_items` (LEAF items only, to prevent double-counting).

### Step 4.5b: CA Validation & Inference (Chartered Accountant-Level Reasoning)

**Module**: [`ca_validator.py`](ews_agent/ca_validator.py)

**Goal**: Go beyond direct 1:1 label matching by applying CA-level reasoning to validate, cross-check, and infer financial data. A Chartered Accountant doesn't just copy numbers — they **verify** them, **cross-check** across statements, **infer** missing values from accounting logic, and **flag** compliance gaps.

**Four validation categories**:

| Category | Purpose | Key Checks |
|----------|---------|------------|
| 1. Cross-statement validation | Internal consistency of BS, P&L, CF | BS equation (Assets = Equity + Liabilities), P&L equation (Income - Expenses = PBT), PAT consistency (P&L PAT ≈ BS Profit for the year) |
| 2. Inferential mapping | Derive values not directly in PDF | EBITDA = PBT + Depreciation + Finance costs, EBIT = PBT + Finance costs, BS Profit from P&L PAT, Total Debt, residual NC liabilities |
| 3. Note cross-reference tracking | Link BS/P&L items to their notes | Extract note numbers from row labels (e.g., "PPE (3)" → Note 3), flag items missing required references per Schedule III |
| 4. Accounting standard compliance | Ind AS / Schedule III disclosure checks | Ind AS 16 (PPE + Depreciation), Ind AS 116 (Leases + Finance costs), Ind AS 12 (Deferred tax), Ind AS 19 (Employee benefits), MSMED Act |

**Entry point**: [`run_ca_validation(bs_mappings, pl_mappings, cf_mappings)`](ews_agent/ca_validator.py) returns a `ValidationReport` with:
- `flags: list[ValidationFlag]` — Errors, warnings, and info messages
- `inferred_mappings: list[InferredMapping]` — CA-derived values to add to output
- `note_references: dict[str, list[str]]` — Template items → note numbers
- `is_balanced: bool` — Whether the BS equation holds

**Inferred mapping types**:

| Inference | Formula | Method | Confidence |
|-----------|---------|--------|------------|
| EBITDA | PBT + Depreciation + Finance costs | `ca_calculated` | 0.85 |
| EBIT | PBT + Finance costs | `ca_calculated` | 0.80 |
| BS Profit for the year | P&L PAT (per Schedule III, must match) | `ca_cross_statement` | 0.80 |
| Total Debt | NC Borrowings + Current Borrowings | `ca_calculated` | 0.80 |
| Other NC liabilities | Total NC Liab - known sub-items (residual) | `ca_inferred` | 0.70 |

**Integration in pipeline** (Step 4.5b in `smart_agent.py`):
1. Run `run_ca_validation()` after all mapping + derived items are computed
2. Apply inferred mappings — only for items NOT already mapped (no overrides)
3. Convert `InferredMapping` → `MappingResult` and add to the appropriate mapping list (BS/P&L/CF)
4. Store CA stats in `ExtractionResult` (ca_flags_count, ca_errors, ca_warnings, ca_inferred, ca_balanced)
5. Write CA validation data to Meta Data sheet in Excel output

**Flag severity levels**:
- **Error**: BS doesn't balance, fundamental equation violated → indicates mapping error or missing item
- **Warning**: Sub-total mismatch, cross-statement inconsistency → possible issue, needs review
- **Info**: Inferred value applied, note reference found, compliance note → informational, no action needed

**Regulatory basis**:
- Schedule III of the Companies Act, 2013 — prescribes BS/P&L/CF format
- Ind AS 16 — Property, Plant and Equipment (depreciation must be charged)
- Ind AS 116 — Leases (ROU assets and lease liabilities must be on BS)
- Ind AS 12 — Income Taxes (deferred tax assets/liabilities must be recognized)
- Ind AS 19 — Employee Benefits (defined benefit obligations as provisions)
- MSMED Act, 2006 — Micro/Small enterprise dues must be disclosed separately

### Step 5: Write to Excel (Deterministic — No LLM)

**Module**: [`excel_writer.py`](ews_agent/excel_writer.py)

**Output Excel Sheets** (7 sheets):

| Sheet | Content |
|-------|---------|
| Meta Data | Extraction metadata (unit, statement type, pages, stats, completeness) |
| Balance Sheet | Template with extracted values + formulas |
| P&L | Template with extracted values + formulas |
| Cash Flow | Template with extracted values + formulas |
| Raw BS | Raw extracted table data (as-is from PDF) |
| Raw P&L | Raw extracted table data |
| Raw CF | Raw extracted table data |

**Writing Process**:
1. For each mapping result, find the corresponding row in the template
2. Write the numeric value to column C with `#,##0.00` format
3. Apply Excel formulas for calculated fields (totals, subtotals)
4. Write raw extracted tables as additional sheets (for verification)
5. Write Meta Data sheet with styled sections

**Meta Data Sheet** includes:
- PDF filename, year, unit, statement type
- Page numbers used for each statement
- Extraction stats (rows extracted, items mapped, values written)
- Completeness percentages per sheet and overall
- CA Validation & Inference section:
  - BS Equation Balanced (YES/NO)
  - CA errors, warnings, inferred mappings count
  - Items with note cross-references
  - Detailed flag list (sorted: errors → warnings → info)
  - Inferred mapping details with reasoning
- Extraction timestamp

### Step 6: Compute Completeness (Deterministic — No LLM)

**Module**: [`smart_agent.py`](ews_agent/smart_agent.py)

**Method**: Count leaf items (non-formula, non-section-header) in each template, compare with items that received values.

```
completeness = items_written / leaf_items_count
```

**Overall completeness**: Average of BS, P&L, CF completeness scores.

### Step 7: Write Meta Data Sheet (Deterministic — No LLM)

**Module**: [`excel_writer.py`](ews_agent/excel_writer.py) — `write_metadata_sheet()`

Writes the Meta Data sheet to the already-created output Excel file. This is done after completeness computation so that completeness percentages can be included.

---

## 4. LLM Usage Policy (LLM-First Architecture)

| Scenario | LLM Role | Deterministic Role | When LLM Unavailable |
|----------|----------|-------------------|---------------------|
| Page identification | **★ PRIMARY** | Quick check (cost opt) + validation (secondary) | Full deterministic scan (title → full-page → content) |
| Statement type detection | **★ PRIMARY** (with page ID) | Cross-validation (secondary) | Keyword counting from page titles |
| Year detection | **Verification only** | 5 filename patterns + page text (primary) | Pattern+text detection (no verification) |
| Table extraction | **Never** | pdfplumber text parsing | N/A — always deterministic |
| BS/P&L data mapping | **★ Primary** (after alias) | Keyword alias → ★ LLM → Fuzzy (fallback) | Alias + fuzzy only (backward compatible) |
| CF data mapping | **★ Primary** (for OFI items) | Structural + alias → ★ LLM → Fuzzy (fallback) | Structural + alias + fuzzy only |
| Notes → OFI mapping | **★ Primary** (after alias+context) | Alias + context → ★ LLM → Fuzzy (fallback) | Alias + context + fuzzy only |
| Mapping verification | **Optional** | N/A | Skipped (no verification) |
| CA validation | **Never** (deterministic) | Cross-statement checks, inference, compliance | N/A — always deterministic |
| Derived computation | **Never** | Residual math | N/A — always deterministic |
| Default zeros | **Never** | Config-based | N/A — always deterministic |
| Excel writing | **Never** | openpyxl | N/A — always deterministic |

**LLM Configuration**: On-prem Qwen2.5-7B-Instruct via OpenAI-compatible API. Configured in [`llm_utils.py`](ews_agent/llm_utils.py).

**When LLM is used**:

1. **★ Page identification (primary)**: `find_pages_by_llm()` is the PRIMARY page finder. It receives page snippets and deterministic hints, then identifies BS/P&L/CF pages AND statement type in a single LLM call. Deterministic validation (`_validate_with_deterministic()`) merges LLM results with deterministic scan results (union), expands continuation pages, and cross-validates statement type. Cost optimization: if the quick deterministic check finds all 3 statements with standard titles, the LLM call is skipped.

2. **★ Data mapping (primary)**: After keyword alias pre-pass, `map_by_llm()` is called for each statement type (BS, P&L, CF) and for notes → OFI mapping. The LLM receives unmapped template items (with section context) and all PDF rows (with values and sections), then returns structured JSON mappings. This is the **primary** mapping method — fuzzy matching only runs as fallback for items the LLM didn't map. Enabled by default (`verify_with_llm=True`).

3. **Year verification**: When the year is detected from a low-confidence source (single filename year, FY prefix, or default current year), the LLM reads the first financial statement page to verify or correct the year. Only triggers when `use_llm=True` and LLM is available.

4. **Optional mapping verification**: When `verify_with_llm=True`, the LLM reviews low-confidence mappings (< 0.7 confidence) after the primary mapping pass.

**Backward compatibility**: When `llm=None` is passed, the system falls back to deterministic-only behavior for both page finding and mapping. This ensures the system works even without an LLM server.

---

## 5. Module Reference

### Active Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| [`smart_agent.py`](ews_agent/smart_agent.py) | Main orchestrator (8-step pipeline) | `SmartExtractionAgent.run()`, `_convert_extracted_table_to_tabular()`, `_prefer_standalone()`, `_detect_year_from_pdf()`, `_detect_year_from_page_text()`, `_verify_year_with_llm()`, `_detect_statement_type()`, `_count_leaf_items()` |
| [`table_finder.py`](ews_agent/table_finder.py) | Page identification (LLM-first) | `find_financial_statements()`, `find_pages_by_llm()`, `_quick_deterministic_check()`, `_validate_with_deterministic()`, `find_notes_pages()`, `FinancialStatementPages` |
| [`text_table_extractor.py`](ews_agent/text_table_extractor.py) | Deterministic text parsing | `extract_table_from_pages()`, `extract_notes_from_pages()`, `extract_financial_statement()`, `ExtractedTable`, `ExtractedRow` |
| [`data_mapper.py`](ews_agent/data_mapper.py) | Mapping engine | `map_balance_sheet()`, `map_profit_and_loss()`, `map_cash_flow()`, `map_notes_to_other_financial_info()`, `map_by_llm()`, `_merge_alias_llm_and_fuzzy()`, `_detect_year_column()`, `compute_derived_items()`, `apply_default_zeros()`, `extract_equity_roll_forward()` |
| [`ca_validator.py`](ews_agent/ca_validator.py) | CA validation & inference | `run_ca_validation()`, `validate_balance_sheet_equation()`, `validate_profit_and_loss_equation()`, `validate_cross_statement_consistency()`, `infer_missing_values()`, `extract_note_references()`, `check_accounting_compliance()`, `ValidationReport`, `ValidationFlag`, `InferredMapping` |
| [`excel_writer.py`](ews_agent/excel_writer.py) | Excel output | `write_all_sheets()`, `write_metadata_sheet()`, `write_raw_table_sheet()` |
| [`llm_utils.py`](ews_agent/llm_utils.py) | LLM utility | `llm_call_with_retry()`, `extract_json_from_response()` |
| [`llm_config.py`](ews_agent/llm_config.py) | LLM configuration | `get_llm()` — on-prem Qwen2.5-7B-Instruct via Deloitte endpoint |
| [`app.py`](app.py) | FastAPI application | REST API endpoints, background task processing |
| [`static/index.html`](static/index.html) | Web UI | Drag-and-drop upload, real-time progress, results dashboard |

### Data Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `ExtractionResult` | `smart_agent.py` | Full pipeline result with stats, completeness, and CA validation stats |
| `FinancialStatementPages` | `table_finder.py` | Page numbers for each statement type + notes |
| `ExtractedTable` | `text_table_extractor.py` | Extracted table data with rows, headers, unit |
| `ExtractedRow` | `text_table_extractor.py` | Single extracted row with label, values, section info |
| `MappingResult` | `data_mapper.py` | Mapping of PDF row to template item with confidence |
| `ValidationReport` | `ca_validator.py` | CA validation results with flags, inferred mappings, note refs |
| `ValidationFlag` | `ca_validator.py` | Single validation finding (error/warning/info) |
| `InferredMapping` | `ca_validator.py` | CA-derived mapping with reasoning and source items |

---

## 6. Handling PDF Variations

### 6.1 Gridless Tables (Most Indian Annual Reports)

**Problem**: pdfplumber `extract_tables()` returns empty — no visible borders/lines to detect.

**Solution**: Text-based extraction using `extract_text()` + line-by-line parsing:
1. Extract page text as a string
2. Split into lines
3. For each line, scan right-to-left for numeric values
4. Everything before the first numeric value is the label
5. Section tracking assigns rows to correct template sections

### 6.2 CID-Font PDFs (e.g., Godrej Properties)

**Problem**: Text appears as `(cid:NN)` — font-internal character IDs with no Unicode mapping.

**Solution** (deterministic, no LLM):
1. CID placeholders are stripped by `_normalize_text()` before matching
2. Pattern `[CID:NN]` is replaced with space
3. Fuzzy matching with `token_sort_ratio` handles fragmented text (e.g., "operat ing" still matches "operating")
4. Anchor aliases (single keywords like "operating", "investing") with fuzzy word-level matching handle CID-fragmented words

### 6.3 Company-Name-Prefixed Titles

**Problem**: Some reports prefix the company name before the statement title (e.g., "Godrej Properties Limited Balance Sheet" instead of just "Balance Sheet").

**Solution**: Line-by-line position validation in [`_line_contains_title()`](ews_agent/table_finder.py:223):
- If the match starts within the first 40% of the line, it's considered a title
- Short lines (≤ 70 chars) containing a match are always considered titles
- This allows "Godrej Properties Limited Balance Sheet" (match at ~60%) while rejecting "Refer to the Balance Sheet on page 47" (match at ~60% in a long line)

### 6.4 Multi-Page Financial Statements

**Problem**: A Balance Sheet may span pages 45-46.

**Solution**: `extract_table_from_pages()` accepts a list of page numbers and concatenates rows from all pages. Section tracking persists across pages.

### 6.5 Standalone vs Consolidated (Standalone-Only Policy)

**Problem**: Many reports contain both standalone and consolidated statements. Consolidated statements include subsidiary data and are not comparable to standalone statements.

**Solution**: This app enforces a **standalone-only policy**. Statement type is detected by the LLM during page identification (Step 1) — `FinancialStatementPages.statement_type`. The LLM identifies whether pages are "Standalone" or "Consolidated" in the same call that identifies page numbers. Deterministic validation cross-checks this by counting standalone/consolidated keywords in page titles. `_prefer_standalone()` then:

1. **Filters to standalone pages** when both types are present (consolidated pages are skipped)
2. **Returns empty list** when only consolidated pages are found (extraction skipped for that statement)
3. **Aborts extraction entirely** when ALL statements are consolidated-only (no standalone pages found for BS, P&L, or CF)

This ensures the output Excel always contains standalone financial data per Schedule III of the Companies Act, 2013.

### 6.6 Title on Different Page Than Data

**Problem**: Some reports have the statement title on one page and the data table starts on the next page.

**Solution**: The text extractor looks for the statement start pattern across all specified pages. If the title is on page N and data starts on page N+1, both pages are included in the extraction.

---

## 7. Running the System

### FastAPI Web Application

```bash
# Start the server
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080

# Access the web UI
# Open browser: http://localhost:8080
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web UI (static HTML) |
| `/upload` | POST | Upload PDF(s) for extraction |
| `/status/{job_id}` | GET | Check extraction progress |
| `/download/{job_id}` | GET | Download completed Excel |
| `/health` | GET | Health check |

### Upload Request

```bash
curl -X POST http://localhost:8080/upload \
  -F "files=@Annual_Report.pdf"
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

### Output

- Excel file with 7 sheets: Meta Data, Balance Sheet, P&L, Cash Flow, Raw BS, Raw P&L, Raw CF
- Meta Data sheet includes: unit, statement type, pages used, extraction stats, completeness percentages
- Raw sheets contain the original extracted table data for verification

---

## 8. Known Limitations & Future Improvements

### Current Limitations

1. **Notes OFI mapping effectiveness**: The notes keyword aliases cover common terms but may miss company-specific wording. The 4-phase approach (alias → context → LLM → fuzzy) significantly improves coverage, but some highly unusual note titles may still not match.
2. **Year column detection**: Now uses `target_year` from the detected financial year to prefer the matching column. Falls back to latest year column if `target_year` not found in headers (with warning). Non-standard headers without any year pattern may still fail.
3. **Title on separate page**: If the statement title is on a completely different page (not included in detected pages), extraction may start from the wrong position.
4. **Formula accuracy**: BS/P&L formulas assume standard template row layout; non-standard templates need adjustment.
5. **Equity roll-forward**: `extract_equity_roll_forward()` exists but is not integrated into the main pipeline — equity items (Profit for the year, Change in FCTR, NCI share) may not be extracted.
6. **CA validation is deterministic**: The CA validator uses hardcoded accounting rules and does not use LLM for inference. This means it can only check known patterns (e.g., standard EBITDA formula) and may miss company-specific adjustments.
7. **No gap analysis**: The old Gap Analysis Agent was removed. No diagnostic report on missing items.

### Future Improvements

1. **Expand notes aliases**: Add more company-specific aliases based on testing with diverse annual reports.
2. **Integrate equity roll-forward**: Add Step 4e to extract equity items from the "Other Equity" note.
3. **LLM-powered CA validation**: Use LLM to perform deeper cross-statement analysis (e.g., "Why doesn't the BS balance? Which item is likely mis-mapped?") instead of just flagging the error.
4. **Multi-year extraction**: Process both current and previous year columns from the same PDF.
5. **Batch processing**: Process multiple PDFs in sequence via the web UI.
6. **Confidence scoring**: Add per-field confidence scores to output Excel (via cell comments or a summary sheet).
7. **Template-agnostic formulas**: Read formula row positions from template highlighting instead of hardcoding.
8. **Consolidated support**: Currently standalone-only policy. Future: add optional consolidated mode with consolidated-specific template rows (NCI, goodwill on consolidation, etc.).
9. **Note content extraction**: Currently note references are tracked but note content is not fetched. Future: follow note references to extract detailed schedules (PPE schedule, borrowing schedule, etc.).
