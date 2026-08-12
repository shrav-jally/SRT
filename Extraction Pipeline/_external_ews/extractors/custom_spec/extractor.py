"""Custom Spec Extractor — Product 2 Main Entry Point.

Executes a user-defined CustomExtractionSpecDocument strictly against a CanonicalDocument v0.
"""

from __future__ import annotations

import logging
from contracts import (
    CanonicalDocument,
    CustomExtractionResult,
    CustomExtractionResultDocument,
    CustomExtractionSpecDocument,
    ExtractionStatus,
    FieldExtractionMode,
)
from .direct_mapping import resolve_direct_mapping
from .inference_mapping import resolve_inference_mapping

logger = logging.getLogger(__name__)


def extract_from_custom_spec(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionSpecDocument,
) -> CustomExtractionResultDocument:
    """Execute a custom extraction specification against a CanonicalDocument v0.

    Parameters
    ----------
    canonical_doc : CanonicalDocument
        Input canonical document JSON from Product 1.
    spec : CustomExtractionSpecDocument
        User-defined extraction specification.

    Returns
    -------
    CustomExtractionResultDocument
        Structured extraction results for all requested fields with provenance.
    """
    logger.info(f"Executing Custom Spec Engine on document '{canonical_doc.document_id}' with spec '{spec.spec_id}' ({len(spec.fields)} fields)...")

    results: list[CustomExtractionResult] = []

    for field_spec in spec.fields:
        mode = field_spec.extraction_mode

        if mode == FieldExtractionMode.DIRECT_MAPPING:
            res = resolve_direct_mapping(canonical_doc, field_spec)
        elif mode == FieldExtractionMode.INFERENCE_BASED:
            res = resolve_inference_mapping(canonical_doc, field_spec)
        elif mode == FieldExtractionMode.DERIVED:
            # Derived mode placeholder for v0
            res = CustomExtractionResult(
                field_id=field_spec.field_id,
                category=field_spec.category,
                subcategory=field_spec.subcategory,
                entity_name=field_spec.entity_name,
                entity_type=field_spec.entity_type,
                extraction_mode=mode,
                status=ExtractionStatus.NOT_FOUND,
                explanation="Derived calculation mode placeholder — missing upstream dependent fields.",
            )
        else:
            res = resolve_direct_mapping(canonical_doc, field_spec)

        results.append(res)

    # Compute summary stats
    total_fields = len(results)
    found_count = sum(1 for r in results if r.status == ExtractionStatus.FOUND)
    not_found_count = sum(1 for r in results if r.status == ExtractionStatus.NOT_FOUND)
    found_rate = (found_count / total_fields) if total_fields > 0 else 0.0

    summary = {
        "total_fields_requested": total_fields,
        "fields_found": found_count,
        "fields_not_found": not_found_count,
        "completion_rate_pct": round(found_rate * 100, 1),
    }

    logger.info(f"Custom Spec Extraction complete: {found_count}/{total_fields} fields FOUND ({found_rate * 100:.1f}%)")

    return CustomExtractionResultDocument(
        document_id=canonical_doc.document_id,
        spec_id=spec.spec_id,
        results=results,
        summary=summary,
    )
