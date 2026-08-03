# Subcategory Content Extraction Engine (Layer 6.5)

The Annual Report Knowledge Engine is now live. We have bridged the gap between **Section Boundaries** (knowing where things are) and **Structured Intelligence** (extracting exactly what the Excel workbook needs).

## What Was Built

### 1. The `content_extractor.py` Router
A new module was introduced to handle parsing non-financial text. It routes raw text blocks from the PDF into specific extractor functions based on the taxonomy category and subcategory.

> [!TIP]
> The LLM text-extraction retry limit is hardcapped to **2 attempts** to balance accuracy with rate-limit safety.

### 2. LLM Subcategory Handlers
The engine now intercepts targeted sections and prompts the LLM to output structured JSON:
- **Board of Directors**: Extracts a JSON array of `[{"name", "designation", "type"}]`.
- **Key Management Personnel**: Extracts KMP names and designations.
- **Board Committees**: Extracts a list of committee names (Audit, CSR, Risk, etc).
- **Company Profile / Products & Services**: Extracts business descriptions, operating segments, and product offerings into dicts.
- **Management Discussion & Analysis (MD&A)**: Uses a financial analyst prompt to extract nuanced summaries for `industry_overview`, `business_review`, `opportunities_and_risks`, and `future_outlook`.

### 3. Heuristic Handlers
For simpler numeric targets, it uses rapid fallback heuristics:
- **Share Capital**: Pulls Authorized and Paid-up capital numbers.
- **Shareholding Pattern**: Extracts promoter vs. public vs. institutional split.
- **Dividend Information**: Scans for dividend declaration rates (e.g. "Rs 1.80/share").

### 4. API Integration
The `extraction_pipeline.py` was updated with a new **Layer 6.5** that executes just before the Financial Statement Engine. The extracted JSON payloads are accumulated into a `structured_intelligence` dictionary and exposed directly on the root of the API response:

```json
{
  "document_registry": {
    "structured_intelligence": {
      "Governance": {
        "Board Of Directors": [
          {"name": "...", "designation": "Executive"}
        ]
      },
      "Management Discussion & Analysis": {
        "industry_overview": "...",
        "opportunities_and_risks": ["..."]
      }
    }
  }
}
```

## Next Steps
The backend extraction engine is functionally complete for both Tabular/Financial and Text/Intelligence data. You can now execute a full extraction and test the JSON output!
