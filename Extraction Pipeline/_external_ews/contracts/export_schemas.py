"""JSON Schema exporter for versioned contract models."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from contracts.canonical_document_v0 import CanonicalDocument
from contracts.financial_statements_v0 import FinancialStatementsDocument
from contracts.msme_valuation_v0 import MSMEValuationDocument
from contracts.taxonomy_output_v0 import TaxonomyDocument
from contracts.custom_extraction_spec_v0 import CustomExtractionSpecDocument, CustomExtractionResultDocument

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


def export_json_schemas(output_dir: Path | None = None) -> dict[str, Path]:
    """Export Pydantic JSON schemas for all contract models.

    Parameters
    ----------
    output_dir : Path, optional
        Target directory to write JSON schema files. Defaults to contracts/schemas.

    Returns
    -------
    dict[str, Path]
        Dictionary mapping model names to output file paths.
    """
    target_dir = output_dir or SCHEMAS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    models = {
        "canonical_document_v0": CanonicalDocument,
        "financial_statements_v0": FinancialStatementsDocument,
        "msme_valuation_v0": MSMEValuationDocument,
        "taxonomy_output_v0": TaxonomyDocument,
        "custom_extraction_spec_v0": CustomExtractionSpecDocument,
        "custom_extraction_result_v0": CustomExtractionResultDocument,
    }

    exported_files = {}
    for name, model_cls in models.items():
        schema = model_cls.model_json_schema()
        out_path = target_dir / f"{name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
        exported_files[name] = out_path

    return exported_files


if __name__ == "__main__":
    paths = export_json_schemas()
    print(f"Exported {len(paths)} JSON schemas to: {SCHEMAS_DIR}")
    for name, path in paths.items():
        print(f"  - {name}: {path.name}")
