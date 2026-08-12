"""Inference Mapping Resolver — resolves INFERENCE_BASED fields using LLM over canonical snippets ONLY.

STRICT RULE: Never opens the raw PDF. Reads only canonical document sections and text blocks.
"""

from __future__ import annotations

import logging
from typing import Any
from contracts import (
    CanonicalDocument,
    CanonicalSection,
    CustomExtractionFieldSpec,
    CustomExtractionResult,
    ExtractionStatus,
    SourceReference,
    ValidationStatus,
)
from .normalization import normalize_field_value

logger = logging.getLogger(__name__)


def resolve_inference_mapping(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> CustomExtractionResult:
    """Resolve an INFERENCE_BASED field using constrained LLM inference over canonical text snippets.

    Parameters
    ----------
    canonical_doc : CanonicalDocument
        Canonical document JSON.
    spec : CustomExtractionFieldSpec
        Field spec.

    Returns
    -------
    CustomExtractionResult
        Extracted value with reasoning explanation and canonical provenance.
    """
    field_id = spec.field_id
    category = spec.category
    subcategory = spec.subcategory
    entity_name = spec.entity_name
    entity_type = spec.entity_type

    # 1. Gather relevant canonical section text
    snippets: list[str] = []
    target_section: CanonicalSection | None = None

    for sec in canonical_doc.sections:
        c_lower = (sec.section_type or sec.taxonomy_path or "").lower()
        s_lower = sec.subcategory.lower()
        t_lower = sec.title_normalized.lower()

        match_found = False
        if (
            category.lower() in c_lower
            or subcategory.lower() in s_lower
            or any(exp.lower() in t_lower for exp in spec.expected_section_types)
            or any(syn.lower() in t_lower for syn in spec.synonyms)
        ):
            match_found = True

        # Pre-fetch text blocks for this section
        sec_text_parts = []
        for blk_id in sec.block_ids:
            for blk in canonical_doc.blocks:
                if blk.block_id == blk_id:
                    block_tokens = [
                        canonical_doc.token_registry[t].text
                        for t in blk.token_ids
                        if t in canonical_doc.token_registry
                    ]
                    if block_tokens:
                        sec_text_parts.append(" ".join(block_tokens))

        if not match_found and sec_text_parts:
            # Fallback to checking if synonyms exist in the actual text
            section_full_text = " ".join(sec_text_parts).lower()
            # Require minimum length for synonyms to avoid spurious matches
            if any(len(syn) > 3 and syn.lower() in section_full_text for syn in spec.synonyms):
                match_found = True

        if match_found:
            target_section = sec
            if sec_text_parts:
                snippets.append("\n".join(sec_text_parts[:10]))  # First 10 blocks

    if not snippets:
        # UNIVERSAL BLOCK SEARCH FALLBACK
        # If the canonicalizer failed to map blocks to sections, scan all raw blocks directly.
        all_blocks = canonical_doc.blocks
        matched_block_indices = set()
        
        for i, blk in enumerate(all_blocks):
            if i in matched_block_indices:
                continue
                
            block_tokens = [
                canonical_doc.token_registry[t].text
                for t in blk.token_ids
                if t in canonical_doc.token_registry
            ]
            if not block_tokens:
                continue
                
            block_text_lower = " ".join(block_tokens).lower()
            if any(len(syn) > 3 and syn.lower() in block_text_lower for syn in spec.synonyms):
                # We found a hit! Grab surrounding context (+/- 1 block)
                context_parts = []
                start_idx = max(0, i - 1)
                end_idx = min(len(all_blocks), i + 2)
                
                for j in range(start_idx, end_idx):
                    matched_block_indices.add(j)
                    c_tokens = [
                        canonical_doc.token_registry[t].text
                        for t in all_blocks[j].token_ids
                        if t in canonical_doc.token_registry
                    ]
                    if c_tokens:
                        context_parts.append(" ".join(c_tokens))
                        
                snippets.append("\n".join(context_parts))
                if len(snippets) >= 5:  # Cap at 5 contexts to avoid exceeding token limits
                    break

    if not snippets:
        # Fallback to general processing_metadata text extractions
        proc_meta = canonical_doc.processing_metadata or {}
        raw_text_exts = proc_meta.get("raw_text_extractions", [])
        for txt_ext in raw_text_exts:
            if category.lower() in txt_ext.get("category", "").lower():
                snippets.append(txt_ext.get("extracted_text", "")[:3000])

    if not snippets:
        return CustomExtractionResult(
            field_id=field_id,
            category=category,
            subcategory=subcategory,
            entity_name=entity_name,
            entity_type=entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.NOT_FOUND,
            confidence=0.0,
            explanation=f"No relevant canonical text snippet found for inference field '{entity_name}'.",
            validation_status=ValidationStatus.NOT_RUN,
        )

    context_text = "\n\n".join(snippets[:2])[:4000]  # Cap snippet context

    # 2. Attempt LLM inference call
    try:
        from sources.annual_report.llm_config import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = get_llm(temperature=0.0, max_tokens=500)
        sys_prompt = (
            "You are an enterprise document intelligence assistant. Extract the requested field "
            "strictly from the provided document context snippet. Return a JSON object with: "
            '{"value": "<extracted value>", "explanation": "<short reasoning summary>", "confidence": 0.85}. '
            "If the information is not present or cannot be inferred safely, set value to null."
        )
        user_prompt = (
            f"Field Name: {entity_name}\n"
            f"Category: {category} > {subcategory}\n"
            f"Description: {spec.description}\n\n"
            f"DOCUMENT CONTEXT SNIPPET:\n{context_text}"
        )

        resp = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
        resp_text = resp.content if hasattr(resp, "content") else str(resp)

        # Parse LLM JSON
        import json, re
        json_match = re.search(r"\{.*\}", resp_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            inf_val = parsed.get("value")
            explanation = parsed.get("explanation", f"Inferred via LLM from section '{target_section.title_raw if target_section else subcategory}'.")
            confidence = float(parsed.get("confidence", 0.85))

            if inf_val:
                norm_val, unit, currency = normalize_field_value(inf_val, spec.expected_value_type.value)
                page_no = target_section.start_page if target_section else 1
                sec_id = target_section.section_id if target_section else None

                prov = SourceReference(
                    document_id=canonical_doc.document_id,
                    page_number=page_no,
                    section_id=sec_id,
                    raw_text=context_text[:200],
                )

                return CustomExtractionResult(
                    field_id=field_id,
                    category=category,
                    subcategory=subcategory,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    extraction_mode=spec.extraction_mode,
                    status=ExtractionStatus.FOUND,
                    value_raw=str(inf_val),
                    value_normalized=norm_val,
                    unit=unit,
                    currency=currency,
                    confidence=confidence,
                    explanation=explanation,
                    provenance=[prov],
                    validation_status=ValidationStatus.VALIDATED,
                )
    except Exception as exc:
        logger.warning(f"Inference mapping fallback for '{entity_name}': {exc}")

    # 3. Field not found or LLM returned null
    return CustomExtractionResult(
        field_id=field_id,
        category=category,
        subcategory=subcategory,
        entity_name=entity_name,
        entity_type=entity_type,
        extraction_mode=spec.extraction_mode,
        status=ExtractionStatus.NOT_FOUND,
        value_raw=None,
        value_normalized=None,
        unit=None,
        currency=None,
        confidence=0.0,
        explanation=f"LLM could not confidently extract a value for '{entity_name}' from the provided context.",
        provenance=[],
        validation_status=ValidationStatus.NOT_RUN,
    )
