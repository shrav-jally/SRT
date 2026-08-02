# INVESTIGATION REPORT: Sheet 2 (Intelligence Report) Data Loss Analysis

**Date:** 2025-07-15  
**Scope:** End-to-end trace of where Sheet 2 data is being lost, overwritten, skipped, or incorrectly routed  
**Method:** Static code analysis of the 9-layer extraction pipeline  
**Status:** Investigation-only — NO code changes  

---

## Executive Summary

The Intelligence Report (Sheet 2) is designed to populate 16 narrative fields from Indian company annual reports. Investigation reveals **5 confirmed bugs** and **7 architectural weaknesses** that cause data loss across the pipeline. The most critical finding is a **format-string KeyError in [`_classify_via_llm()`](graph/sources/annual_report/taxonomy.py:441)** that silently kills ALL LLM taxonomy classification, forcing every section into keyword/regex fallback — which produces lower-confidence, often-wrong category assignments that cascade downstream into wrong routing, wrong extraction, and missing fields.

| # | Finding | Severity | Root Cause File | Impact |
|---|---------|----------|-----------------|--------|
| 1 | LLM taxonomy classification always fails | **P0 CRITICAL** | [`taxonomy.py:445`](graph/sources/annual_report/taxonomy.py:445) | All sections classified by keyword/regex only → wrong categories → wrong routing |
| 2 | Phase 1→Phase 2 dedup uses source name not target name | **P0** | [`extraction_pipeline.py:339`](graph/sources/annual_report/extraction_pipeline.py:339) | Already-extracted fields re-processed in Phase 2, overwriting good data |
| 3 | TOC-anchored count always reports 0 | **P1** | [`section_consolidator.py:46`](graph/sources/annual_report/section_consolidator.py:46) | Pipeline log misleading; `source` field never set to "toc" |
| 4 | Phase 2 stores taxonomy subcategory names, not target field names | **P0** | [`extraction_pipeline.py:364-367`](graph/sources/annual_report/extraction_pipeline.py:364) | `structured_intelligence` keys don't match WORKBOOK_TARGETS aliases |
| 5 | Corporate Governance router swallows KMP/Committees/Board | **P0** | [`content_extractor.py:589`](graph/sources/annual_report/content_extractor.py:589) | KMP data lost when section classified as "Corporate Governance" |
| 6 | `select_best_source()` substring matching too loose | **P1** | [`source_routing.py:164`](graph/sources/annual_report/source_routing.py:164) | "directors" in "Independent Directors" false-positive match |
| 7 | Flat-intel key collision in populate_intelligence_report | **P2** | [`workbook_population.py:767`](graph/sources/annual_report/workbook_population.py:767) | Nested dict keys overwrite subcategory keys |

---

## SECTION 1: Source Priority Routing (P0)

### 1.1 Symptom

Pipeline log reports: **"4 fields extracted via source priority"** when 12 of 16 fields have priority definitions in [`FIELD_SOURCE_PRIORITY`](graph/sources/annual_report/source_routing.py:34).

### 1.2 Execution Trace

Phase 1 in [`extraction_pipeline.py:318-342`](graph/sources/annual_report/extraction_pipeline.py:318) iterates over all 16 WORKBOOK_TARGETS fields and calls [`select_best_source(subcat, text_extractions)`](graph/sources/annual_report/source_routing.py:132) for each:

```
for subcat, cat in priority_fields.items():       # 16 iterations
    best_source = select_best_source(subcat, text_extractions)
    if best_source:                                # Only 4-6 match
        ...
        priority_extracted_subcats.add(src_sub)    # BUG: adds SOURCE name
```

### 1.3 Root Causes

**Cause A — `text_extractions` subcategory names don't match priority aliases**

The [`text_extractions`](graph/sources/annual_report/extraction_pipeline.py:265) list is built from `master_sections`, where `subcategory` comes from taxonomy classification. If taxonomy classified a section as `"Directors Report"` but the priority alias is `"directors report"` (lowercase), the match works because [`select_best_source()`](graph/sources/annual_report/source_routing.py:160) lowercases both sides.

However, if taxonomy classified the section as `"Business Review"` (from keyword/regex fallback) but the priority alias for "Business Review" is `["business review", "performance review", "management discussion", "directors report"]`, the match works. The problem is when taxonomy produces **non-standard names** like `"Directors' Report"` or `"Report of the Directors"` — the substring match `priority_alias in sub` handles these, but can also produce **false positives**.

**Cause B — Substring matching is too loose**

At [`source_routing.py:164`](graph/sources/annual_report/source_routing.py:164):
```python
if priority_alias in sub or priority_alias in cat:
```

The alias `"directors"` would match a section named `"Independent Directors"` even though that section is about board composition, not the Directors' Report. Similarly, `"notice"` (in Dividend priorities) would match `"Notice of AGM"` which is correct, but also `"Notice of EVM"` which is not.

**Cause C — Financial section filter is too aggressive**

At [`extraction_pipeline.py:327-328`](graph/sources/annual_report/extraction_pipeline.py:327):
```python
if "financial" in src_cat.lower() or "notes to accounts" in src_cat.lower():
    continue
```

This skips any section whose category contains "financial" — but "Financial Analysis" and "Financial Ratios" are narrative sections that should NOT be skipped for fields like "Business Review".

### 1.4 Data Flow Diagram

```
WORKBOOK_TARGETS (16 fields)
    │
    ├─ select_best_source() ──→ MATCH (4-6 fields) ──→ extract_subcategory_content()
    │                                                    │
    │                                                    └─→ _store_result(save_cat, subcat, result)
    │                                                         priority_extracted_subcats.add(src_sub) ← BUG
    │
    └─ select_best_source() ──→ NO MATCH (10-12 fields) ──→ Falls to Phase 2
```

### 1.5 Recommended Fix

1. **Fix substring matching** to use word-boundary regex instead of `in` operator
2. **Relax financial filter** to only skip `category == "Financial Statements"` exactly, not substring
3. **Fix dedup bug** (see Section 2) — add target subcat name, not source name

---

## SECTION 2: Structured Intelligence Storage (P0)

### 2.1 Symptom

Only 5 categories populated in `structured_intelligence` when 16 fields were targeted.

### 2.2 Root Cause: Phase 1 vs Phase 2 Key Mismatch

**Phase 1** (lines [318-342](graph/sources/annual_report/extraction_pipeline.py:318)) stores results correctly:
```python
save_cat = cat if cat and cat != "Unclassified" else "Extracted Intelligence"
# cat comes from WORKBOOK_TARGETS: "Company Information", "Management & Governance", etc.
_store_result(save_cat, subcat, extracted)
# subcat is the TARGET field name: "Board of Directors", "KMP", etc.
```

**Phase 2** (lines [346-367](graph/sources/annual_report/extraction_pipeline.py:346)) stores results with TAXONOMY names:
```python
category = extraction.get("category", "")      # From taxonomy: "Management & Governance"
subcategory = extraction.get("subcategory", "") # From taxonomy: "Corporate Governance Report"
save_cat = category if category and category != "Unclassified" else "Extracted Intelligence"
_store_result(save_cat, subcategory, extracted)
# subcategory is the SOURCE section name, NOT the target field name!
```

This means Phase 2 stores data under keys like `"Corporate Governance Report"` instead of `"Corporate Governance"`, or `"Directors Report"` instead of `"Business Review"`.

### 2.3 Dedup Bug: `priority_extracted_subcats.add(src_sub)`

At [line 339](graph/sources/annual_report/extraction_pipeline.py:339):
```python
priority_extracted_subcats.add(src_sub)  # src_sub = source section name
```

But Phase 2 checks at [line 353](graph/sources/annual_report/extraction_pipeline.py:353):
```python
if subcategory in priority_extracted_subcats:  # subcategory = current extraction's name
    continue
```

**Example of data corruption:**
1. Phase 1: Field "Dividend Information" → source section "Directors Report" → extracted successfully
2. `priority_extracted_subcats.add("Directors Report")`
3. Phase 2: Iterates over text_extractions, encounters "Directors Report" section
4. `"Directors Report" in priority_extracted_subcats` → TRUE → SKIPPED ✓
5. BUT: Phase 2 also encounters "Corporate Governance Report" section
6. `"Corporate Governance Report" in priority_extracted_subcats` → FALSE → NOT SKIPPED
7. This section also contains dividend info → **overwrites** the good Phase 1 result with lower-quality Phase 2 data

**Conversely:**
1. Phase 1: Field "Business Review" → source section "MD&A" → extracted
2. `priority_extracted_subcats.add("MD&A")`
3. Phase 2: Encounters "Directors Report" section (which also contains business review)
4. `"Directors Report" in priority_extracted_subcats` → FALSE → NOT SKIPPED
5. Directors Report extraction runs, potentially overwriting the MD&A result with different data

### 2.4 Category Count Mismatch

`structured_intelligence` is keyed by `save_cat`. The 4 WORKBOOK_TARGETS categories are:
- `"Company Information"` (4 fields)
- `"Management & Governance"` (4 fields)
- `"Shareholding Information"` (4 fields)
- `"Management Discussion & Analysis"` (4 fields)

But taxonomy may produce categories like `"Audit Information"`, `"Legal & Compliance"`, `"ESG & Sustainability"` that don't match any WORKBOOK_TARGETS category. These go into `structured_intelligence` under their taxonomy category name, where [`populate_intelligence_report()`](graph/sources/annual_report/workbook_population.py:738) may never find them.

### 2.5 Recommended Fix

1. Phase 1: Add `priority_extracted_subcats.add(subcat)` (target name) IN ADDITION to `src_sub`
2. Phase 2: After extraction, map the result to the correct WORKBOOK_TARGETS field name using `MAPPING_RULES` reverse lookup
3. Add a normalization pass that re-keys `structured_intelligence` to match WORKBOOK_TARGETS categories

---

## SECTION 3: Deterministic Extractor Execution (P0)

### 3.1 Symptom

Question: Are regex pre-extractors actually running in production, or are sections being misrouted before they reach the extractors?

### 3.2 Execution Trace

The regex pre-extractors are called from within the main extractors:

```python
# content_extractor.py:634-644
def _extract_board_of_directors(text, llm, source_page, source_section):
    pre_result = _pre_extract_board_members(text, source_page, source_section)
    if pre_result and isinstance(pre_result.value, list) and len(pre_result.value) >= 2:
        return pre_result  # Regex succeeded, skip LLM
    # Fall back to LLM...
```

The regex pre-extractors **ARE implemented and functional**. The question is whether the router ever reaches them.

### 3.3 Router Reachability Analysis

The router [`extract_subcategory_content()`](graph/sources/annual_report/content_extractor.py:541) uses a chain of `if/elif` conditions. For a regex pre-extractor to run, the router must first match the section to the correct extractor function.

**Matching logic** (lines [571-578](graph/sources/annual_report/content_extractor.py:571)):
```python
def matches_target(target_name: str) -> bool:
    aliases = MAPPING_RULES.get(target_name, [target_name.lower()])
    clean_sub = _clean_str(subcategory)
    for alias in aliases:
        clean_alias = _clean_str(alias)
        if clean_alias and (clean_alias in clean_sub or clean_sub in clean_alias):
            return True
    return False
```

The `_clean_str()` function removes stop words ("the", "and", "of", "in", "to") and all non-alphanumeric characters. This is good for fuzzy matching but can produce false matches.

**Critical routing collision** at [line 589](graph/sources/annual_report/content_extractor.py:589):
```python
elif matches_target("Corporate Governance") or category == "Management & Governance" or "corporate governance" in text_head:
    return _extract_corporate_governance(truncated_text, llm, source_page, source_section)
```

The condition `category == "Management & Governance"` means **ANY section classified as "Management & Governance"** will be routed to `_extract_corporate_governance()`, even if the section is specifically about Board of Directors, KMP, or Board Committees. This is because the `elif` chain means the first matching condition wins, and `category == "Management & Governance"` is checked at the Corporate Governance branch.

Wait — let me re-examine. The Board/KMP/Committees checks come BEFORE Corporate Governance in the elif chain:
```python
if matches_target("Board of Directors") or ...:     # Line 583
    return _extract_board_of_directors(...)
elif matches_target("Key Management Personnel") or ...:  # Line 585
    return _extract_kmp(...)
elif matches_target("Board Committees") or ...:      # Line 587
    return _extract_committees(...)
elif matches_target("Corporate Governance") or category == "Management & Governance" or ...:  # Line 589
    return _extract_corporate_governance(...)
```

So if the section name matches "Board of Directors" aliases, it routes correctly. The problem is when the section name is something like `"Report on Corporate Governance"` which contains the board/KMP data but the name matches "Corporate Governance" first.

**The real issue**: If a section is classified as category `"Management & Governance"` with subcategory `"Corporate Governance Report"` (a common taxonomy output), the `matches_target("Board of Directors")` check uses the subcategory name `"Corporate Governance Report"`. After cleaning: `"corporategovernancereport"`. The Board alias `"board of directors"` cleans to `"boarddirectors"`. Neither is a substring of the other → **Board routing fails** → falls through to Corporate Governance.

### 3.4 Regex Pre-Extractor Reachability Matrix

| Pre-Extractor | Router Condition | Reachable? | Blockers |
|---------------|-----------------|------------|----------|
| `_pre_extract_board_members` | `matches_target("Board of Directors")` or category+keyword | **Partial** | Section named "Corporate Governance Report" won't match Board aliases |
| `_pre_extract_kmp` | `matches_target("Key Management Personnel")` or category+keyword | **Partial** | Same — KMP data often inside "Corporate Governance Report" |
| `_pre_extract_committees` | `matches_target("Board Committees")` or category+keyword | **Partial** | Committee data inside "Corporate Governance Report" |
| `_pre_extract_subsidiaries` | `matches_target("Subsidiaries & Group Structure")` or category+keyword | **Yes** | Subsidiaries usually a standalone section |
| `_pre_extract_dividend` | `matches_target("Dividend Information")` or category+keyword | **Yes** | Dividend usually in Directors Report |
| `_pre_extract_auditor` | `"auditor" in sub_lower` | **Yes** | Auditor section usually standalone |

### 3.5 Recommended Fix

1. When routing `"Corporate Governance Report"` sections, run ALL governance extractors (Board, KMP, Committees, Corp Gov) and merge results
2. Add a "multi-extract" mode for sections that contain multiple target fields
3. Consider extracting the full Corporate Governance section and then running sub-extractors on the extracted text

---

## SECTION 4: Board Extraction Trace (P0)

### 4.1 Complete End-to-End Trace

```
Layer 1: PDF Ingestion
  └─ pdf_ingestion.ingest_pdf() → pages_data[{page_number, raw_text, detected_heading, ...}]

Layer 2: Master Data
  └─ MasterDataStore.load_pages() → SQLite pages table

Layer 3: Section Registry
  ├─ toc_parser.parse_toc_for_page_hints() → toc_hints.raw_entries
  │   └─ Looks for "Board of Directors" in TOC → may or may not find it
  ├─ section_consolidator.build_section_registry()
  │   ├─ Pass 1: TOC anchors → _map_boundary_description("Board of Directors")
  │   │   └─ Matches: r"\bboard\s+of\s+directors\b" → ("Management & Governance", "Board of Directors") ✓
  │   ├─ Pass 2: Heading anchors → checks detected_heading on each page
  │   │   └─ If a page has heading "Board of Directors" → creates anchor ✓
  │   └─ Pass 3: Boundary resolution → assigns end_page

Layer 3.5: Taxonomy Classification
  ├─ _classify_via_llm() → FAILS (KeyError bug, see Section 7)
  └─ _classify_via_keywords()
      ├─ Heading match: r"\bboard\s+of\s+directors\b" → confidence 0.95 ✓
      └─ Body match: lower confidence 0.75

Layer 5/6: Text Extraction
  └─ For each master_section, gather text from start_page to end_page
     └─ text_extractions.append({category, subcategory, extracted_text, source_pages, ...})

Layer 6.5: Subcategory Content Extraction
  ├─ Phase 1: Priority routing
  │   ├─ select_best_source("Board of Directors", text_extractions)
  │   │   └─ Searches for aliases: ["board of directors", "board structure", ...]
  │   │       in text_extractions subcategory/category
  │   ├─ If match found:
  │   │   └─ extract_subcategory_content("Management & Governance", "Board of Directors", text, llm)
  │   │       └─ Router: matches_target("Board of Directors") → TRUE
  │   │           └─ _extract_board_of_directors(text, llm, ...)
  │   │               ├─ _pre_extract_board_members(text, ...)  ← REGEX FIRST
  │   │               │   ├─ Pattern 1: DIN-based → very high confidence (0.95)
  │   │               │   └─ Pattern 2: Shri/Smt prefix → high confidence (0.85)
  │   │               └─ If regex finds >= 2 members → return EvidenceBackedResult
  │   │                   └─ Else: LLM fallback → confidence 0.70
  │   └─ _store_result("Management & Governance", "Board of Directors", result)
  │       └─ structured_intelligence["Management & Governance"]["Board of Directors"] = result.value
  │
  └─ Phase 2: Fallback
      └─ For remaining text_extractions not in priority_extracted_subcats
          └─ If section contains "board" in subcategory → routes to _extract_board_of_directors
              └─ May OVERWRITE Phase 1 result (see Section 2)

Layer 8: Workbook Population
  └─ populate_intelligence_report(structured_intelligence, master_sections, evidence_map)
      ├─ Flatten: flat_intel["board of directors"] = value
      ├─ Alias search: MAPPING_RULES["Board of Directors"] = ["board of directors", ...]
      ├─ Exact match: "board of directors" in flat_intel → FOUND ✓
      └─ _format_value(value) → formatted string with DIN

Layer 8.5: Excel Builder
  └─ _build_intelligence_sheet(wb, report_rows)
      └─ 12 columns including Evidence Method, Evidence Snippet, Evidence Page
```

### 4.2 Data Loss Points

| Step | Loss Point | Probability | Impact |
|------|-----------|-------------|--------|
| Layer 3 | No TOC entry for "Board of Directors" | Medium | Section may not be anchored → gap-fill creates "Unclassified" block |
| Layer 3.5 | LLM taxonomy fails → keyword fallback may misclassify | High | Board section classified as "Corporate Governance" |
| Layer 6.5 Phase 1 | `select_best_source()` returns None | Medium | Board field not extracted in Phase 1 |
| Layer 6.5 Phase 2 | `subcategory in priority_extracted_subcats` dedup fails | High | Re-extraction overwrites good data |
| Router | `matches_target("Board of Directors")` fails for "Corp Gov Report" | High | Board extractor never runs |
| Regex | DIN pattern doesn't match non-tabular format | Medium | Falls to LLM which may fail |
| LLM | LLM unavailable or returns bad JSON | Medium | Returns None → field empty |

### 4.3 Recommended Fix

1. Add "corporate governance report" as a Board of Directors alias in `MAPPING_RULES`
2. When routing Corporate Governance sections, always try Board/KMP/Committees sub-extractors
3. Fix the dedup bug to prevent Phase 2 overwrites

---

## SECTION 5: KMP Extraction Trace (P1)

### 5.1 Complete End-to-End Trace

The KMP trace follows the same path as Board (Section 4) but with critical differences:

**KMP is almost never a standalone section in Indian annual reports.** It is typically embedded within the "Corporate Governance Report" section, often as a subsection titled "Key Management Personnel" or within a table.

```
Layer 3: Section Registry
  └─ TOC may have "Corporate Governance Report" but NOT "Key Management Personnel"
  └─ Heading detection may find "Key Management Personnel" on a specific page
      └─ But if that page is within the "Corporate Governance Report" page range,
         the consolidator may NOT create a separate section (it only creates
         anchors for pages NOT already covered by TOC anchors — see line 250-251:
         "if pg_num in toc_pages: continue")

Layer 3.5: Taxonomy
  └─ The "Corporate Governance Report" section is classified as:
      category="Management & Governance", subcategory="Corporate Governance"

Layer 6.5: Router
  └─ extract_subcategory_content("Management & Governance", "Corporate Governance", text, llm)
      └─ matches_target("Board of Directors")? → "corporategovernance" vs "boarddirectors" → NO
      └─ matches_target("Key Management Personnel")? → "corporategovernance" vs "keymanagementpersonnel" → NO
      └─ matches_target("Board Committees")? → "corporategovernance" vs "boardcommittees" → NO
      └─ matches_target("Corporate Governance")? → "corporategovernance" vs "corporategovernance" → YES
          └─ _extract_corporate_governance() runs → extracts governance philosophy
          └─ KMP data is IN THE TEXT but the KMP extractor NEVER RUNS
          └─ **KMP DATA LOST**
```

### 5.2 The Corporate Governance Black Hole

The [`_extract_corporate_governance()`](graph/sources/annual_report/content_extractor.py:766) function extracts:
- Governance philosophy
- Number of board meetings
- Compliance status

It does NOT extract:
- Board members (handled by `_extract_board_of_directors`)
- KMP (handled by `_extract_kmp`)
- Committee details (handled by `_extract_committees`)

But when the section is named "Corporate Governance" or "Corporate Governance Report", the router sends the entire text to `_extract_corporate_governance()`, and the other three extractors never see it.

### 5.3 Quantified Impact

For a typical 200-page Indian annual report:
- "Corporate Governance Report" section: ~30-40 pages
- Contains: Board composition table, KMP disclosure, Committee details, Governance policies
- Current extraction: Only governance philosophy extracted
- **Lost: Board members, KMP names, Committee names** — 3 of 16 fields

### 5.4 Recommended Fix

1. **Split the Corporate Governance section**: When `_extract_corporate_governance()` is called, also call `_pre_extract_board_members()`, `_pre_extract_kmp()`, and `_pre_extract_committees()` on the same text
2. **Return merged results**: The Corporate Governance extractor should return a dict containing all four sub-results
3. **Alternative**: Add a "governance multi-extract" mode in the router that runs all governance extractors when category is "Management & Governance"

---

## SECTION 6: Section Detection Noise (P1)

### 6.1 Symptom

Notice bullets and other non-section content becomes section headers in the Section Registry, creating spurious "Unclassified" sections that dilute the extraction pipeline.

### 6.2 Root Cause Analysis

**Source 1: TOC entries that are notice items**

The TOC parser ([`toc_parser.py`](graph/sources/annual_report/toc_parser.py:1)) extracts ALL entries from the Table of Contents, including:
```
Notice of the 25th Annual General Meeting
  Item 1: Adoption of Financial Statements
  Item 2: Declaration of Dividend
  Item 3: Re-appointment of Director
  Item 4: Appointment of Auditor
```

Each of these becomes a `TocEntry` in `toc_hints.raw_entries`. The consolidator at [`build_section_registry()`](graph/sources/annual_report/section_consolidator.py:188) Pass 1 processes each entry:

```python
for entry in toc_hints.raw_entries:
    desc = getattr(entry, "description", "")
    sec_type, sec_subtype = _map_boundary_description(desc)
    if not sec_type:
        sec_type, sec_subtype = "Unclassified", desc  # ← Notice items become "Unclassified"
```

Since `_map_boundary_description()` at [line 176](graph/sources/annual_report/section_consolidator.py:176) checks against `_BOUNDARY_PATTERNS`, and notice items like "Item 3: Re-appointment of Director" don't match any pattern, they become `"Unclassified"` sections.

**Source 2: Heading detection false positives**

The consolidator's Pass 2 at [line 248-269](graph/sources/annual_report/section_consolidator.py:248) checks every page's `detected_heading`. If a page has a bold line like `"We hereby give notice..."`, it may be detected as a heading and create a section anchor.

**Source 3: Page-level noise from pdfplumber**

The PDF ingestion layer extracts text per page. If a page starts with a bold header that's actually a sub-item within a larger section (e.g., `"3.1 Risk Management"` within the Directors' Report), it creates a heading that the consolidator treats as a new section boundary.

### 6.3 Impact on Sheet 2

Spurious "Unclassified" sections cause two problems:

1. **Text dilution**: The real content is split across multiple small "Unclassified" sections instead of being concentrated in the correct taxonomy section. When Phase 2 processes these, the text is too short for meaningful extraction.

2. **Priority routing miss**: `select_best_source()` searches `text_extractions` for matching subcategory names. If the Directors' Report is split into 5 "Unclassified" sub-sections, none of them match the priority aliases for "Business Review", "Dividend Information", etc.

### 6.4 Recommended Fix

1. **Filter TOC entries**: Skip entries that start with "Item", are numbered sub-items, or are clearly notice agenda items
2. **Minimum section size**: Require at least 500 characters of text before creating a section
3. **Merge adjacent Unclassified sections**: Combine all contiguous "Unclassified" sections into one block
4. **Heading confidence threshold**: Only create heading anchors for headings with confidence > 0.7

---

## SECTION 7: Taxonomy Classification (P2)

### 7.1 Symptom

Pipeline log reports: **"0 blocks via LLM, N blocks via keyword/regex"** — LLM classification never succeeds.

### 7.2 CRITICAL BUG: Format-String KeyError

At [`_classify_via_llm()`](graph/sources/annual_report/taxonomy.py:420), line 441-447:

```python
prompt = _LLM_CLASSIFY_PROMPT.format(
    taxonomy_list=taxonomy_str,
    start_page=start_page,
    end_page=end_page,
    section_name=raw_section_name,    # ← keyword arg is "section_name"
    section_text=block_text,
)
```

But the prompt template at [line 244](graph/sources/annual_report/taxonomy.py:244) uses:
```
SECTION TEXT (pages {start_page} to {end_page}, title: "{raw_section_name}"):
```

The placeholder is `{raw_section_name}` but the keyword argument is `section_name=raw_section_name`. Python's `str.format()` requires the keyword to match the placeholder exactly. This raises a **KeyError: 'raw_section_name'** every time.

The exception is caught at [line 481-483](graph/sources/annual_report/taxonomy.py:481):
```python
except Exception as exc:
    logger.debug(f"LLM call failed for block {section_name}: {exc}")
    return []
```

The error is logged at DEBUG level (invisible in normal operation) and the function returns `[]`, causing the caller to fall through to keyword/regex classification.

### 7.3 Impact Cascade

```
LLM classification fails (KeyError)
  → All sections classified by keyword/regex only
  → Keyword/regex has lower confidence and less nuance
  → Sections like "Directors' Report" may be classified as:
      - "Management & Governance" / "Corporate Governance" (wrong — should be "Company Information" / "Business Review")
      - "Management Discussion & Analysis" / "Business Review" (if "business" keyword found in body)
  → Wrong category → wrong priority routing → wrong extractor → wrong/missing data
```

### 7.4 Additional LLM Classification Issues

Even if the KeyError were fixed:

1. **Text truncation at 3000 chars** ([line 327](graph/sources/annual_report/taxonomy.py:327)): For a 30-page Directors' Report, only the first 3000 characters are sent to the LLM. This may not contain the most distinctive keywords.

2. **Confidence threshold too high** ([line 469](graph/sources/annual_report/taxonomy.py:469)): `if confidence < 0.5: continue` — LLM may return 0.4-0.49 for ambiguous sections, which are discarded.

3. **Category validation** ([line 467](graph/sources/annual_report/taxonomy.py:467)): `if section_type not in TAXONOMY: continue` — If the LLM returns a slightly different category name (e.g., "Management and Governance" instead of "Management & Governance"), the result is discarded.

### 7.5 Recommended Fix

1. **IMMEDIATE**: Change `section_name=raw_section_name` to `raw_section_name=raw_section_name` in the format call (but the parameter is named `section_name`, so use `raw_section_name=section_name`)
2. Increase text truncation limit to 5000 chars
3. Add fuzzy category name matching (normalize "&" vs "and")
4. Lower confidence threshold to 0.4

---

## SECTION 8: TOC Anchoring Quality (P2)

### 8.1 Symptom

Pipeline log reports: **"TOC-anchored: 0"** even when TOC parsing succeeds and returns entries.

### 8.2 Root Cause: `source` Field Never Set to "toc"

The [`ConsolidatedSection`](graph/sources/annual_report/section_consolidator.py:29) dataclass has:
```python
source: str = "taxonomy"  # Line 46 — DEFAULT is "taxonomy"
```

When TOC anchors are created at [lines 230-242](graph/sources/annual_report/section_consolidator.py:230):
```python
anchors.append(ConsolidatedSection(
    section_id=_make_section_id(sec_type, sec_subtype),
    raw_section_name=desc,
    ...
    boundary_source="toc",    # ← This IS set correctly
    toc_entry=desc,
    # source is NOT set → defaults to "taxonomy"
))
```

The `source` field is never explicitly set to `"toc"`. It always defaults to `"taxonomy"`.

The pipeline log at [line 516](graph/sources/annual_report/extraction_pipeline.py:516) checks:
```python
toc_anchor_count = sum(1 for s in master_sections if s.get("source") == "toc")
```

Since `source` is always `"taxonomy"`, this count is always 0.

Note: `boundary_source` IS set correctly to `"toc"`, but the pipeline log doesn't check `boundary_source`.

### 8.3 Impact

This is primarily a **reporting bug**, not a data loss bug. The TOC anchors ARE created and DO contribute to section boundaries. The issue is that the pipeline log misreports the TOC anchoring quality, making it appear that TOC parsing is failing when it may actually be working.

However, there IS a downstream impact: if any future code relies on `s.get("source") == "toc"` for logic decisions (e.g., giving TOC-anchored sections higher priority), it will incorrectly treat them as taxonomy-derived sections.

### 8.4 Additional TOC Quality Issues

1. **Page offset detection**: The TOC parser at [`toc_parser.py`](graph/sources/annual_report/toc_parser.py:1) attempts to detect the offset between printed page numbers and PDF page indices. If this fails, TOC entries point to wrong pages.

2. **Duplicate page suppression**: At [line 229](graph/sources/annual_report/section_consolidator.py:229), `if not any(a.start_page == pdf_page for a in anchors)` prevents two anchors on the same page. But if a TOC entry and a heading both point to the same page, the heading is silently dropped.

3. **CID-encoded page numbers**: Some PDFs use custom font encoding (CID) that makes page numbers unreadable. The TOC parser has LLM fallback for this, but it may fail.

### 8.5 Recommended Fix

1. **IMMEDIATE**: Set `source="toc"` when creating TOC anchors in `build_section_registry()`
2. Update pipeline log to check `boundary_source` instead of `source`
3. Add TOC quality metrics: number of entries parsed, number mapped to taxonomy, number with valid page offsets

---

## SECTION 9: Sheet 2 Coverage Accounting (P0)

### 9.1 Complete Field-by-Field Accounting

For each of the 16 Intelligence Report fields, the following table traces the expected data path and identifies where data is lost.

| # | Field | Category | Priority Aliases | Phase 1 Match? | Router Match? | Extractor | Typical Outcome |
|---|-------|----------|-----------------|----------------|---------------|-----------|-----------------|
| 1 | Company Profile | Company Information | company profile, company overview, about the company, directors report | **Yes** if "Company Profile" section exists | `matches_target("Company Profile")` ✓ | `_extract_company_profile()` | **FOUND** — regex for CIN, incorporation year |
| 2 | Business Overview | Company Information | business overview, business review, directors report, management discussion | **Yes** if "Business Overview" or "Directors Report" section | `matches_target("Business Overview")` or `matches_target("Business Review")` ✓ | `_extract_business_overview()` | **FOUND** if section detected |
| 3 | Products & Services | Company Information | products and services, business overview, directors report | **Maybe** — "Products & Services" rarely a standalone section | `matches_target("Products & Services")` ✓ | `_extract_products_services()` | **OFTEN MISSING** — section rarely exists |
| 4 | Subsidiaries & Group Structure | Company Information | subsidiaries, group structure, subsidiary, directors report, annexure | **Yes** if "Subsidiaries" section exists | `matches_target("Subsidiaries & Group Structure")` ✓ | `_extract_subsidiaries()` | **FOUND** if section detected |
| 5 | Board of Directors | Management & Governance | board of directors, board structure, directors profile, corporate governance | **Yes** if "Board of Directors" section exists | `matches_target("Board of Directors")` ✓ | `_extract_board_of_directors()` | **FOUND** if standalone; **LOST** if inside Corp Gov |
| 6 | Key Management Personnel | Management & Governance | key management personnel, kmp, corporate governance, management discussion | **Maybe** — KMP rarely a standalone section | `matches_target("Key Management Personnel")` ✓ | `_extract_kmp()` | **OFTEN LOST** — inside Corp Gov Report |
| 7 | Corporate Governance | Management & Governance | corporate governance, governance report, governance section | **Yes** — always a section | `matches_target("Corporate Governance")` ✓ | `_extract_corporate_governance()` | **FOUND** but only extracts philosophy |
| 8 | Board Committees | Management & Governance | board committees, audit committee, csr committee, nrc | **Maybe** — Committees rarely standalone | `matches_target("Board Committees")` ✓ | `_extract_committees()` | **OFTEN LOST** — inside Corp Gov Report |
| 9 | Share Capital | Shareholding Information | share capital, balance sheet, share capital note | **Maybe** — often in Notes, not standalone | `matches_target("Share Capital")` ✓ | `_extract_share_capital()` | **OFTEN MISSING** — in financial sections (skipped!) |
| 10 | Shareholding Pattern | Shareholding Information | shareholding pattern, shareholding, corporate governance | **Yes** if section exists | `matches_target("Shareholding Pattern")` ✓ | `_extract_shareholding_pattern()` | **FOUND** if section detected |
| 11 | Major Shareholders | Shareholding Information | shareholding pattern, shareholding, corporate governance | **Yes** (same source as Shareholding Pattern) | `matches_target("Major Shareholders")` ✓ | `_extract_shareholding_pattern()` | **FOUND** (same extraction as #10) |
| 12 | Dividend Information | Shareholding Information | directors report, dividend, financial statements, notice, agm | **Yes** — Directors Report usually contains dividend | `matches_target("Dividend Information")` ✓ | `_extract_dividend()` | **FOUND** — regex for dividend per share |
| 13 | Industry Overview | Management Discussion & Analysis | industry overview, management discussion, directors report | **Yes** if MD&A section exists | `matches_target("Industry Overview")` ✓ | `_extract_mda()` | **FOUND** if MD&A detected |
| 14 | Business Review | Management Discussion & Analysis | business review, performance review, management discussion, directors report | **Yes** if MD&A or Directors Report exists | `matches_target("Business Review")` ✓ | `_extract_mda()` | **FOUND** if MD&A detected |
| 15 | Opportunities & Challenges | Management Discussion & Analysis | opportunities, risk factors, management discussion, directors report | **Yes** if MD&A exists | `matches_target("Opportunities & Challenges")` ✓ | `_extract_mda()` | **FOUND** if MD&A detected |
| 16 | Future Outlook | Management Discussion & Analysis | future outlook, outlook, management discussion, directors report | **Yes** if MD&A exists | `matches_target("Future Outlook")` ✓ | `_extract_mda()` | **FOUND** if MD&A detected |

### 9.2 Expected Coverage: 10-12/16 fields

In a typical Indian annual report with working LLM taxonomy:
- **Reliably found (8-9):** Company Profile, Business Overview, Corporate Governance, Shareholding Pattern, Major Shareholders, Dividend Information, Industry Overview, Business Review, Future Outlook
- **Conditionally found (2-3):** Board of Directors, Subsidiaries, Opportunities & Challenges
- **Frequently missing (4-5):** Products & Services, Key Management Personnel, Board Committees, Share Capital

### 9.3 Actual Coverage with Current Bugs

With the LLM taxonomy KeyError bug (Section 7), taxonomy classification degrades significantly. Sections that would be correctly classified by LLM are instead classified by keyword/regex, which:
- Misclassifies "Directors' Report" as "Corporate Governance" instead of containing Business Review, Dividend, etc.
- Fails to identify "Products & Services" sections
- Misclassifies "Share Capital Note" as "Financial Statements" → skipped by financial filter

**Estimated actual coverage: 5-7/16 fields**

### 9.4 The `flat_intel` Key Collision Bug

At [`workbook_population.py:761-768`](graph/sources/annual_report/workbook_population.py:761):
```python
flat_intel = {}
for cat, sub_dict in structured_intelligence.items():
    if isinstance(sub_dict, dict):
        for sub, val in sub_dict.items():
            if isinstance(val, dict):
                for k, v in val.items():
                    flat_intel[k.replace("_", " ").lower()] = v  # ← Nested keys
            flat_intel[sub.lower()] = val                         # ← Subcategory keys
```

If `_extract_board_of_directors()` returns:
```python
{"members": [...], "committees_count": 5, "meetings_held": 12}
```

Then `flat_intel` gets keys: `"members"`, `"committees count"`, `"meetings held"`, AND `"board of directors"`.

The alias search at [line 777](graph/sources/annual_report/workbook_population.py:777) checks:
```python
for alias in aliases:
    if alias in flat_intel and flat_intel[alias]:
        extracted_value = _format_value(flat_intel[alias])
        break
```

For "Board of Directors", aliases are `["board of directors", "board structure", ...]`. The key `"board of directors"` exists in `flat_intel` → match found ✓.

But for "Board Committees", aliases are `["board committees", "audit committee", ...]`. If the Board extraction returned a nested key `"committees_count"`, the flattened key `"committees count"` does NOT match any alias → **Board Committees field shows "NOT DISCLOSED"** even though committee data exists in the Board extraction result.

### 9.5 Recommended Fix

1. Fix LLM taxonomy KeyError (Section 7) — single biggest coverage improvement
2. Add Corporate Governance multi-extract (Section 5) — recovers 3 fields
3. Fix Phase 2 key naming (Section 2) — prevents data going to wrong buckets
4. Relax financial section filter for Share Capital
5. Add Products & Services extraction from Directors Report text

---

## SECTION 10: Performance Analysis (P2)

### 10.1 Current Timing Infrastructure

The pipeline only tracks **total elapsed time** at [`extraction_pipeline.py:84,507`](graph/sources/annual_report/extraction_pipeline.py:84):
```python
t0 = time.time()
# ... all 9 layers ...
elapsed = time.time() - t0
```

There is **no per-layer timing** and **no per-field timing** for Layer 6.5.

### 10.2 Estimated Time Breakdown

Based on code analysis, the expected time distribution for a 200-page PDF:

| Layer | Operation | Estimated Time | Bottleneck? |
|-------|-----------|---------------|-------------|
| 1 | PDF Ingestion (pdfplumber) | 5-15s | No |
| 2 | Master Data (SQLite) | <1s | No |
| 3 | Section Registry (TOC + Headings) | 2-5s | No |
| 3.5 | Taxonomy Classification | 10-60s | **Yes** — LLM calls per section |
| 3.6 | Section Hierarchy | <1s | No |
| 4 | Table Inventory | 2-5s | No |
| 4.5 | VLM Target Generation | <1s | No |
| 5/6 | Text Extraction | 1-3s | No |
| 6.5 | Subcategory Content Extraction | 30-120s | **Yes** — LLM calls per field |
| 7 | Financial Statement Engine (VLM) | 60-300s | **Yes** — VLM image rendering + API |
| 8 | Validation | 1-3s | No |
| 9 | Quality Report | <1s | No |
| **Total** | | **110-500s** | |

### 10.3 Layer 6.5 Performance Detail

Phase 1 iterates over 16 fields. For each field:
1. `select_best_source()`: O(N) where N = number of text_extractions (~20-50) — fast
2. `extract_subcategory_content()`: 
   - Regex pre-extractor: ~1-5ms per field — **negligible**
   - LLM fallback: ~2-10s per call (if LLM is available)
   - With 16 fields and ~50% needing LLM fallback: ~16-80s

Phase 2 iterates over all text_extractions not in priority_extracted_subcats. For each:
1. `extract_subcategory_content()`: same cost as above
2. With ~10-30 sections and ~30% matching: ~6-90s

**Total Layer 6.5: 22-170s** (highly dependent on LLM availability and number of fallback calls)

### 10.4 Optimization Opportunities

1. **Parallel LLM calls**: Phase 1 fields are independent — could be extracted in parallel (4-8x speedup)
2. **Skip Phase 2 for fully-covered fields**: If all 16 fields are extracted in Phase 1, skip Phase 2 entirely
3. **Cache regex results**: If the same text is processed by multiple extractors (e.g., Corporate Governance text for Board + KMP + Committees), cache the regex pre-extraction results
4. **Early termination**: If regex pre-extractor succeeds with high confidence, skip LLM immediately (already implemented)
5. **Batch LLM calls**: Combine multiple extraction prompts into a single LLM call for the same section text

### 10.5 Recommended Fix

1. Add per-layer timing using `time.time()` checkpoints
2. Add per-field timing in Layer 6.5 (both Phase 1 and Phase 2)
3. Log timing breakdown in the pipeline result dict
4. Implement parallel Phase 1 extraction using `concurrent.futures.ThreadPoolExecutor`

---

## Appendix A: Bug Severity Matrix

| Bug ID | Description | File:Line | Severity | Fix Complexity | Coverage Impact |
|--------|-------------|-----------|----------|---------------|-----------------|
| BUG-1 | LLM taxonomy KeyError | `taxonomy.py:445` | P0 CRITICAL | 1 line | +5-7 fields |
| BUG-2 | Phase 1 dedup uses source name | `extraction_pipeline.py:339` | P0 | 1 line | Prevents overwrite |
| BUG-3 | TOC source field never set | `section_consolidator.py:46` | P1 | 1 line | Reporting only |
| BUG-4 | Phase 2 stores taxonomy names | `extraction_pipeline.py:364-367` | P0 | 10 lines | +2-3 fields |
| BUG-5 | Corp Gov swallows KMP/Board/Committees | `content_extractor.py:589` | P0 | 30 lines | +3 fields |
| BUG-6 | Loose substring matching in routing | `source_routing.py:164` | P1 | 5 lines | Better routing |
| BUG-7 | flat_intel key collision | `workbook_population.py:767` | P2 | 10 lines | Better lookup |

## Appendix B: Fix Priority Order

1. **BUG-1** (taxonomy KeyError) — Single line fix, recovers LLM classification, biggest impact
2. **BUG-5** (Corp Gov multi-extract) — Medium complexity, recovers 3 fields
3. **BUG-2** (dedup bug) — Single line fix, prevents data corruption
4. **BUG-4** (Phase 2 key naming) — Medium complexity, improves coverage
5. **BUG-6** (substring matching) — Small fix, improves routing accuracy
6. **BUG-3** (TOC source field) — Single line fix, reporting only
7. **BUG-7** (flat_intel collision) — Medium complexity, edge case

## Appendix C: File Change Map

| File | Changes Required | Phase |
|------|-----------------|-------|
| [`taxonomy.py`](graph/sources/annual_report/taxonomy.py:445) | Fix format-string KeyError | B |
| [`extraction_pipeline.py`](graph/sources/annual_report/extraction_pipeline.py:339) | Fix dedup, fix Phase 2 key naming | B |
| [`content_extractor.py`](graph/sources/annual_report/content_extractor.py:589) | Add Corp Gov multi-extract | B |
| [`source_routing.py`](graph/sources/annual_report/source_routing.py:164) | Word-boundary matching | B |
| [`section_consolidator.py`](graph/sources/annual_report/section_consolidator.py:46) | Set source="toc" | B |
| [`workbook_population.py`](graph/sources/annual_report/workbook_population.py:767) | Fix flat_intel collision | B |

---

*End of Investigation Report. No code changes were made. All findings are based on static code analysis of the current codebase as of 2025-07-15.*
