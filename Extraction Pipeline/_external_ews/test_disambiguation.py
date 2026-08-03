"""Quick test of _find_table_entity standalone/consolidated disambiguation."""
import sys, os, json, ast
sys.path.insert(0, os.getcwd())

from canonicalizer.persistence import load_canonical_document
from contracts import CustomExtractionFieldSpec, FieldExtractionMode, FieldValueType
from extractors.custom_spec.direct_mapping import resolve_direct_mapping

# Load the actual canonical document
doc = load_canonical_document("canonical_document.v0.json")
print(f"Loaded: {doc.document_id}, sections={len(doc.sections)}, tables={len(doc.tables)}")

# Test standalone balance sheet
spec_standalone = CustomExtractionFieldSpec(
    field_id="standalone_balance_sheet",
    category="Financial Data",
    subcategory="Balance Sheet",
    entity_name="Standalone Balance Sheet Statement",
    entity_type="table",
    description="Standalone primary balance sheet",
    extraction_mode=FieldExtractionMode.DIRECT_MAPPING,
    synonyms=["standalone balance sheet", "standalone statement of financial position"],
    expected_section_types=["balance_sheet", "financial_statements"],
    expected_value_type=FieldValueType.TABLE,
)

# Test consolidated balance sheet
spec_consolidated = CustomExtractionFieldSpec(
    field_id="consolidated_balance_sheet",
    category="Financial Data",
    subcategory="Balance Sheet",
    entity_name="Consolidated Balance Sheet Statement",
    entity_type="table",
    description="Consolidated primary balance sheet",
    extraction_mode=FieldExtractionMode.DIRECT_MAPPING,
    synonyms=["consolidated balance sheet", "consolidated statement of financial position"],
    expected_section_types=["balance_sheet", "financial_statements"],
    expected_value_type=FieldValueType.TABLE,
)

print("\n--- STANDALONE BALANCE SHEET ---")
r_s = resolve_direct_mapping(doc, spec_standalone)
print(f"Status: {r_s.status}")
print(f"Confidence: {r_s.confidence}")
print(f"value_raw: {r_s.value_raw}")
print(f"Explanation: {r_s.explanation[:150]}")
if r_s.value_normalized and isinstance(r_s.value_normalized, list) and len(r_s.value_normalized) > 0:
    print(f"Grid rows: {len(r_s.value_normalized)}")
    print(f"First row: {r_s.value_normalized[0]}")
    print(f"Sample data row: {r_s.value_normalized[1] if len(r_s.value_normalized) > 1 else 'N/A'}")
print(f"other_candidates: {len(r_s.other_candidates or [])}")

print("\n--- CONSOLIDATED BALANCE SHEET ---")
r_c = resolve_direct_mapping(doc, spec_consolidated)
print(f"Status: {r_c.status}")
print(f"Confidence: {r_c.confidence}")
print(f"value_raw: {r_c.value_raw}")
print(f"Explanation: {r_c.explanation[:150]}")
if r_c.value_normalized and isinstance(r_c.value_normalized, list):
    print(f"Grid rows: {len(r_c.value_normalized)}")
    print(f"First row: {r_c.value_normalized[0]}")
print(f"other_candidates: {len(r_c.other_candidates or [])}")

print("\n--- SAME TABLE? ---")
s_tbl = r_s.provenance[0].table_id if r_s.provenance else "N/A"
c_tbl = r_c.provenance[0].table_id if r_c.provenance else "N/A"
print(f"Standalone table_id: {s_tbl}")
print(f"Consolidated table_id: {c_tbl}")
print(f"Are they DIFFERENT? {s_tbl != c_tbl}")
