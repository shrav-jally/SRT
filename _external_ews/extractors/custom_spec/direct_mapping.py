"""Direct Mapping Resolver — resolves DIRECT_MAPPING fields using canonical sections, tables, blocks, and evidence."""

from __future__ import annotations

import logging
import re
from pathlib import Path
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


def resolve_direct_mapping(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> CustomExtractionResult:
    """Resolve a single DIRECT_MAPPING field against CanonicalDocument.

    Parameters
    ----------
    canonical_doc : CanonicalDocument
        Canonical document JSON structure.
    spec : CustomExtractionFieldSpec
        Field specification.

    Returns
    -------
    CustomExtractionResult
        Result containing value, provenance, status, and explanation.
    """
    field_id = spec.field_id
    category = spec.category
    subcategory = spec.subcategory
    entity_name = spec.entity_name
    entity_type = spec.entity_type

    # -------------------------------------------------------------------------
    # 1. Check Document Metadata (Company Name, Auditor, Currency, FY End, etc.)
    # -------------------------------------------------------------------------
    meta_res = _find_in_document_metadata(canonical_doc, spec)
    if meta_res:
        return meta_res

    # -------------------------------------------------------------------------
    # 2. Table-type entity lookup (Balance Sheet, P&L, Cash Flow)
    # -------------------------------------------------------------------------
    if spec.expected_value_type.value == "table" or entity_type == "table":
        table_res = _find_table_entity(canonical_doc, spec)
        if table_res:
            return table_res

    # -------------------------------------------------------------------------
    # 3. Check canonical table cell labels (Highest Priority for Financials)
    # -------------------------------------------------------------------------
    table_match, tbl_cell, tbl_prov = _find_in_canonical_tables(canonical_doc, entity_name, spec.synonyms)
    if table_match:
        norm_val, unit, currency = normalize_field_value(table_match.get("raw_text"), spec.expected_value_type.value)
        return CustomExtractionResult(
            field_id=field_id,
            category=category,
            subcategory=subcategory,
            entity_name=entity_name,
            entity_type=entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.FOUND,
            value_raw=table_match.get("raw_text"),
            value_normalized=norm_val,
            unit=unit,
            currency=currency,
            confidence=0.88,
            explanation=f"Matched canonical table row '{entity_name}' on page {tbl_prov.page_number}.",
            provenance=[tbl_prov],
            validation_status=ValidationStatus.VALIDATED,
        )

    # -------------------------------------------------------------------------
    # 4. Look for pre-extracted structured intelligence in processing_metadata
    # -------------------------------------------------------------------------
    proc_meta = canonical_doc.processing_metadata or {}
    raw_intel = proc_meta.get("raw_extractions", {})
    evidence_map = proc_meta.get("raw_evidence_map", {})

    match_val, match_evidence = _find_in_structured_intelligence(
        raw_intel, evidence_map, category, subcategory, entity_name, spec.synonyms
    )

    if match_val is not None:
        # Prevent severe VLM hallucinations (e.g., lists/dicts for numeric fields)
        expected = spec.expected_value_type.value
        if expected in ("currency_amount", "number", "count", "percentage"):
            if isinstance(match_val, (list, dict)):
                match_val = None
                
    if match_val is not None:
        norm_val, unit, currency = normalize_field_value(match_val, spec.expected_value_type.value)
        page_num = (match_evidence.get("source_page") or 1) if match_evidence else 1
        section_name = match_evidence.get("source_section") if match_evidence else subcategory
        sec_id = _find_section_id(canonical_doc.sections, section_name, page_num)

        return CustomExtractionResult(
            field_id=field_id,
            category=category,
            subcategory=subcategory,
            entity_name=entity_name,
            entity_type=entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.FOUND,
            value_raw=str(match_val),
            value_normalized=norm_val,
            unit=unit,
            currency=currency,
            confidence=match_evidence.get("confidence", 0.92) if match_evidence else 0.88,
            explanation=f"Matched direct label '{entity_name}' from section '{section_name}' on page {page_num}.",
            provenance=[
                SourceReference(
                    document_id=canonical_doc.document_id,
                    page_number=page_num,
                    section_id=sec_id,
                    raw_text=str(match_evidence.get("source_text_snippet", match_val))[:200] if match_evidence else str(match_val)[:200],
                )
            ],
            validation_status=ValidationStatus.VALIDATED,
        )

    # -------------------------------------------------------------------------
    # 5. Check canonical section matching expected_section_types or synonyms
    # -------------------------------------------------------------------------
    sec_res = _find_section_by_type_or_synonym(canonical_doc, spec)
    if sec_res:
        return sec_res

    # -------------------------------------------------------------------------
    # 6. Regex text pattern matching (Employee Count, Ratios, Numbers)
    # -------------------------------------------------------------------------
    regex_match, reg_prov = _find_by_regex_patterns(canonical_doc, spec)
    if regex_match:
        norm_val, unit, currency = normalize_field_value(regex_match, spec.expected_value_type.value)
        return CustomExtractionResult(
            field_id=field_id,
            category=category,
            subcategory=subcategory,
            entity_name=entity_name,
            entity_type=entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.FOUND,
            value_raw=regex_match,
            value_normalized=norm_val,
            unit=unit or "count",
            currency=currency,
            confidence=0.82,
            explanation=f"Matched pattern for '{entity_name}' in section '{reg_prov.section_id}' on page {reg_prov.page_number}.",
            provenance=[reg_prov],
            validation_status=ValidationStatus.VALIDATED,
        )

    # -------------------------------------------------------------------------
    # 7. Search text blocks directly
    # -------------------------------------------------------------------------
    text_match, sec_prov = _find_in_canonical_sections(canonical_doc, entity_name, spec.synonyms)
    if text_match:
        norm_val, unit, currency = normalize_field_value(text_match, spec.expected_value_type.value)
        return CustomExtractionResult(
            field_id=field_id,
            category=category,
            subcategory=subcategory,
            entity_name=entity_name,
            entity_type=entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.FOUND,
            value_raw=text_match,
            value_normalized=norm_val,
            unit=unit,
            currency=currency,
            confidence=0.85,
            explanation=f"Found direct label text match for '{entity_name}' in section '{sec_prov.section_id}'.",
            provenance=[sec_prov],
            validation_status=ValidationStatus.VALIDATED,
        )

    # 8. Field not found
    return CustomExtractionResult(
        field_id=field_id,
        category=category,
        subcategory=subcategory,
        entity_name=entity_name,
        entity_type=entity_type,
        extraction_mode=spec.extraction_mode,
        status=ExtractionStatus.NOT_FOUND,
        confidence=0.0,
        explanation=f"No matching label or section found for '{entity_name}' in CanonicalDocument.",
        validation_status=ValidationStatus.NOT_RUN,
    )


# =============================================================================
# Helper Resolvers
# =============================================================================

def _find_in_document_metadata(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> CustomExtractionResult | None:
    """Check DocumentMetadata for standard metadata fields like Company Name, Auditor, etc."""
    meta = canonical_doc.document_metadata
    e_name = spec.entity_name.lower()
    f_id = spec.field_id.lower()
    syns = [s.lower() for s in spec.synonyms]

    val = None
    exp = ""

    if ("company" in e_name or "company_name" in f_id or "company legal name" in e_name):
        if meta.company_name and meta.company_name != "Unknown Company":
            val = meta.company_name
            exp = "Extracted company legal name from document metadata."
        else:
            # Fallback to source PDF filename clean title
            raw_fn = Path(canonical_doc.source_metadata.file_name).stem
            clean_name = re.sub(r"[\-_]", " ", raw_fn).strip()
            val = clean_name
            exp = "Extracted company name from source PDF document title."
    elif ("auditor" in e_name or "auditor_report" in f_id) and (meta.auditor_name or meta.auditor_opinion):
        val = f"Auditor: {meta.auditor_name or 'N/A'} | Opinion: {meta.auditor_opinion or 'Clean/Unqualified'}"
        exp = "Extracted independent auditor report metadata."
    elif "fy_end" in f_id or "financial_year" in f_id:
        val = meta.fy_end
        exp = "Extracted reporting financial year."

    if val:
        norm_val, unit, currency = normalize_field_value(val, spec.expected_value_type.value)
        return CustomExtractionResult(
            field_id=spec.field_id,
            category=spec.category,
            subcategory=spec.subcategory,
            entity_name=spec.entity_name,
            entity_type=spec.entity_type,
            extraction_mode=spec.extraction_mode,
            status=ExtractionStatus.FOUND,
            value_raw=str(val),
            value_normalized=norm_val,
            unit=unit,
            currency=currency or meta.currency,
            confidence=0.95,
            explanation=exp,
            provenance=[
                SourceReference(
                    document_id=canonical_doc.document_id,
                    page_number=1,
                    raw_text=str(val),
                )
            ],
            validation_status=ValidationStatus.VALIDATED,
        )
    return None


def _find_table_entity(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> CustomExtractionResult | None:
    """Match table entities against canonical tables and sections using candidate scoring and LLM disambiguation.
    
    Handles:
    - column_index = None on row-label cells (treated as col 0)
    - raw_text stored as dict string {'current_period': X, 'previous_period': Y}
    - section.table_ids not populated → page-range-based section title matching
    - standalone vs consolidated disambiguation via section page ranges
    """
    import ast

    is_consolidated = "consolidated" in spec.entity_name.lower() or any("consolidated" in s for s in spec.synonyms)
    is_standalone = "standalone" in spec.entity_name.lower() or any("standalone" in s for s in spec.synonyms)

    # Core terms for matching table content
    if any(k in spec.entity_name.lower() or k in spec.subcategory.lower() for k in ["balance sheet", "financial position"]):
        core_terms = ["balance sheet", "financial position", "assets", "liabilities", "equity and liabilities",
                      "non-current assets", "share capital", "total assets", "particulars"]
    elif any(k in spec.entity_name.lower() or k in spec.subcategory.lower() for k in ["profit", "loss", "income"]):
        core_terms = ["profit and loss", "profit & loss", "income statement", "revenue", "total income",
                      "expenses", "revenue from operations"]
    elif any(k in spec.entity_name.lower() or k in spec.subcategory.lower() for k in ["cash flow"]):
        core_terms = ["cash flow", "operating activities", "investing activities", "financing activities"]
    else:
        core_terms = ["balance sheet", "profit and loss", "cash flow", "statement"]

    # Build page -> section title index (since table_ids are not populated in canonical doc)
    page_to_section_titles: dict[int, list[str]] = {}
    for sec in canonical_doc.sections:
        start_p = sec.start_page or 1
        end_p = sec.end_page or start_p
        t = (sec.title_raw or sec.title_normalized or "").lower()
        if not t:
            continue
        for p in range(start_p, min(end_p + 1, start_p + 10)):  # cap range to avoid huge loops
            page_to_section_titles.setdefault(p, []).append(t)

    def _cell_text(cell) -> str:
        """Extract display text from a cell whose raw_text may be a dict-string or plain str."""
        raw = cell.raw_text
        if not raw:
            return ""
        raw_str = str(raw).strip()
        # Check if it looks like a dict: {'current_period': X, 'previous_period': Y}
        if raw_str.startswith("{") and "current_period" in raw_str:
            try:
                d = ast.literal_eval(raw_str)
                if isinstance(d, dict):
                    cp = d.get("current_period")
                    pp = d.get("previous_period")
                    parts = []
                    if cp is not None:
                        parts.append(str(cp))
                    if pp is not None:
                        parts.append(str(pp))
                    return " | ".join(parts) if parts else ""
            except Exception:
                pass
        return raw_str.replace("\n", " ").strip()

    def _cell_col(cell) -> int:
        """Return column_index, defaulting None → 0."""
        col = cell.column_index
        return int(col) if col is not None else 0

    def _build_grid(tbl_obj) -> list[list[str]]:
        """Build a 2D string grid from table cells."""
        if not tbl_obj.cells:
            return []
        max_row = max(c.row_index for c in tbl_obj.cells) + 1
        max_col = max(_cell_col(c) for c in tbl_obj.cells) + 1
        grid = [["" for _ in range(max_col)] for _ in range(max_row)]
        for cell in tbl_obj.cells:
            r = cell.row_index
            c = _cell_col(cell)
            if 0 <= r < max_row and 0 <= c < max_col:
                grid[r][c] = _cell_text(cell)
        return grid

    def _build_structured_grid(tbl_obj) -> list[list[str]]:
        """Build a structured 3-column grid [Particulars, Current Year, Previous Year] from dict-valued cells."""
        if not tbl_obj.cells:
            return []
        # Check if cells use dict-valued raw_text
        sample_cells = [c for c in tbl_obj.cells if c.raw_text and "current_period" in str(c.raw_text)]
        if not sample_cells:
            return _build_grid(tbl_obj)

        # Group by row — col0 = label, col2 = dict with current/previous
        rows_data: dict[int, dict] = {}
        for cell in tbl_obj.cells:
            r = cell.row_index
            col = _cell_col(cell)
            if r not in rows_data:
                rows_data[r] = {"label": "", "current": "", "previous": ""}
            raw_str = str(cell.raw_text or "").strip()
            if raw_str.startswith("{") and "current_period" in raw_str:
                try:
                    d = ast.literal_eval(raw_str)
                    if isinstance(d, dict):
                        cp = d.get("current_period")
                        pp = d.get("previous_period")
                        if cp is not None:
                            rows_data[r]["current"] = str(cp)
                        if pp is not None:
                            rows_data[r]["previous"] = str(pp)
                except Exception:
                    pass
            elif col == 0 and raw_str:
                rows_data[r]["label"] = raw_str.replace("\n", " ").strip()

        # Build clean 3-col grid
        result = [["Particulars", "Current Period", "Previous Period"]]
        for row_idx in sorted(rows_data.keys()):
            rd = rows_data[row_idx]
            if rd["label"] or rd["current"] or rd["previous"]:
                result.append([rd["label"], rd["current"], rd["previous"]])
        return result

    candidates = []

    for tbl in canonical_doc.tables:
        if not tbl.cells:
            continue

        tbl_pages = tbl.page_numbers or []
        tbl_page = tbl_pages[0] if tbl_pages else 0

        # Collect section titles for pages this table is on
        sec_titles_for_tbl = []
        for p in tbl_pages[:3]:
            sec_titles_for_tbl.extend(page_to_section_titles.get(p, []))
        sec_combined = " ".join(sec_titles_for_tbl)

        # Build header text from first 40 cells (label column only)
        label_cells = sorted(
            [c for c in tbl.cells if _cell_col(c) == 0],
            key=lambda c: c.row_index
        )[:20]
        header_text = " ".join(_cell_text(c) for c in label_cells).lower()

        combined_text = (header_text + " " + sec_combined).strip()

        score = 0
        if any(ct in combined_text for ct in core_terms):
            score += 10

        if score > 0:
            # Standalone / Consolidated disambiguation using section title context
            has_consolidated_ctx = "consolidated" in sec_combined
            has_standalone_ctx = "standalone" in sec_combined

            if is_consolidated:
                if has_consolidated_ctx:
                    score += 20  # strong boost
                elif has_standalone_ctx and not has_consolidated_ctx:
                    score -= 15  # penalize standalone sections
                # Also boost if table is on a later page (consolidated typically comes after standalone)
                if tbl_page > 100:
                    score += 5
            if is_standalone:
                if has_standalone_ctx and not has_consolidated_ctx:
                    score += 20  # strong boost
                elif has_consolidated_ctx and not has_standalone_ctx:
                    score -= 15
                # Standalone typically on earlier pages
                if tbl_page < 100:
                    score += 5

        if score > 0:
            # Find best section (by page proximity)
            best_sec = None
            for sec in canonical_doc.sections:
                sp = sec.start_page or 1
                ep = sec.end_page or sp
                if any(sp <= p <= ep for p in tbl_pages[:2]):
                    best_sec = sec
                    break

            candidates.append({
                "table": tbl,
                "section": best_sec,
                "score": score,
                "header_snippet": combined_text[:300],
                "tbl_page": tbl_page,
                "sec_titles": sec_combined[:200]
            })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    # LLM disambiguation only when scores are too close
    if len(candidates) > 1 and candidates[1]["score"] > 5 and (best["score"] - candidates[1]["score"]) < 8:
        try:
            from sources.annual_report.llm_config import get_llm
            from sources.annual_report.llm_utils import llm_call_with_retry, extract_json_from_response

            llm = get_llm()
            cand_descriptions = []
            for i, c in enumerate(candidates[:3]):
                pg = c["tbl_page"]
                cand_descriptions.append(
                    f"Option {i}: Table on Page {pg}, section context: '{c['sec_titles'][:150]}'"
                )
            prompt = (
                f"You are an expert financial audit assistant.\n"
                f"We are looking for the table: '{spec.entity_name}'.\n\n"
                f"Candidates:\n" + "\n\n".join(cand_descriptions) + "\n\n"
                f"Return JSON with 'selected_option_index' (0, 1, or 2). Output JSON ONLY:"
            )
            llm_res = llm_call_with_retry(llm, prompt)
            parsed = extract_json_from_response(llm_res) if llm_res else None
            if parsed and isinstance(parsed, dict) and "selected_option_index" in parsed:
                idx = int(parsed["selected_option_index"])
                if 0 <= idx < len(candidates[:3]):
                    best = candidates[idx]
        except Exception as e:
            logger.warning(f"LLM table selection failed, using top scored candidate: {e}")

    if best["score"] <= 0:
        return None

    tbl_obj = best["table"]
    linked_sec = best["section"]
    page_no = best["tbl_page"] or 1

    # Build structured grid
    grid = _build_structured_grid(tbl_obj)

    title_parts = []
    if linked_sec:
        title_parts.append(linked_sec.title_raw or "")
    title_parts.append(f"Table {tbl_obj.table_id} (Page {page_no})")
    title = " | ".join(t for t in title_parts if t) or f"Table {tbl_obj.table_id}"
    val_summary = f"Table '{tbl_obj.table_id}' [Page: {page_no}]"

    prov = SourceReference(
        document_id=canonical_doc.document_id,
        page_number=page_no,
        section_id=linked_sec.section_id if linked_sec else None,
        table_id=tbl_obj.table_id,
        raw_text=title[:200],
    )

    logger.info(
        f"[_find_table_entity] '{spec.field_id}' → Table {tbl_obj.table_id} "
        f"(page={page_no}, score={best['score']}, sec='{best['sec_titles'][:80]}')"
    )

    # Build other_candidates
    other_cands = []
    for c in candidates[1:4]:
        c_tbl = c["table"]
        c_sec = c["section"]
        c_page = c["tbl_page"] or 1
        c_title = c_sec.title_raw if c_sec else f"Table {c_tbl.table_id}"
        c_grid = _build_structured_grid(c_tbl)
        other_cands.append({
            "title": c_title or f"Table {c_tbl.table_id}",
            "page_number": c_page,
            "score": c["score"],
            "sec_context": c["sec_titles"][:120],
            "grid": c_grid,
            "table_id": c_tbl.table_id
        })

    return CustomExtractionResult(
        field_id=spec.field_id,
        category=spec.category,
        subcategory=spec.subcategory,
        entity_name=spec.entity_name,
        entity_type=spec.entity_type,
        extraction_mode=spec.extraction_mode,
        status=ExtractionStatus.FOUND,
        value_raw=val_summary,
        value_normalized=grid,
        unit=canonical_doc.document_metadata.unit_denomination,
        currency=canonical_doc.document_metadata.currency,
        confidence=0.95 if best["score"] >= 25 else 0.85,
        explanation=f"Extracted '{spec.entity_name}' from table {tbl_obj.table_id} (Page {page_no}). Section context: {best['sec_titles'][:120]}",
        provenance=[prov],
        validation_status=ValidationStatus.VALIDATED,
        other_candidates=other_cands,
    )


def _find_section_by_type_or_synonym(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> CustomExtractionResult | None:
    """Find a section matching expected_section_types or synonyms and extract its narrative summary."""
    search_types = [t.lower() for t in spec.expected_section_types]
    search_syns = [s.lower() for s in spec.synonyms] + [spec.subcategory.lower()]

    for sec in canonical_doc.sections:
        s_type = (sec.section_type or "").lower()
        sub_cat = (sec.subcategory or "").lower()
        t_raw = (sec.title_raw or "").lower()

        if any(st in s_type or st in sub_cat or st in t_raw for st in search_types + search_syns):
            # Gather text from first block of section
            block_tokens = []
            for b_id in sec.block_ids[:3]:
                blk = next((b for b in canonical_doc.blocks if b.block_id == b_id), None)
                if blk:
                    t_texts = [canonical_doc.token_registry[t].text for t in blk.token_ids if t in canonical_doc.token_registry]
                    if t_texts:
                        block_tokens.append(" ".join(t_texts))

            sec_text = " ".join(block_tokens)[:300] if block_tokens else sec.title_raw
            norm_val, unit, currency = normalize_field_value(sec_text, spec.expected_value_type.value)

            prov = SourceReference(
                document_id=canonical_doc.document_id,
                page_number=sec.start_page or 1,
                section_id=sec.section_id,
                raw_text=sec_text[:200],
            )

            return CustomExtractionResult(
                field_id=spec.field_id,
                category=spec.category,
                subcategory=spec.subcategory,
                entity_name=spec.entity_name,
                entity_type=spec.entity_type,
                extraction_mode=spec.extraction_mode,
                status=ExtractionStatus.FOUND,
                value_raw=sec_text,
                value_normalized=norm_val,
                unit=unit,
                currency=currency,
                confidence=0.88,
                explanation=f"Matched canonical section '{sec.title_raw}' (Type: {sec.section_type}) on page {sec.start_page}.",
                provenance=[prov],
                validation_status=ValidationStatus.VALIDATED,
            )
    return None


def _find_by_regex_patterns(
    canonical_doc: CanonicalDocument,
    spec: CustomExtractionFieldSpec,
) -> tuple[str | None, SourceReference | None]:
    """Search text blocks for numeric/regex patterns like Employee Count."""
    f_id = spec.field_id.lower()
    e_name = spec.entity_name.lower()

    regex_patterns = []
    
    # 1. Employee Count specific patterns
    if "employee" in f_id or "employee" in e_name or "workforce" in f_id or "headcount" in f_id:
        regex_patterns.extend([
            r"(?:total|permanent|regular|active|number of)?\s*(?:employees|workforce|people|headcount|manpower|personnel|staff)\s*(?:count|strength|as on|as at|in employment)?\s*[:\-=]?\s*([\d,]{2,})",
            r"([\d,]{2,})\s*(?:permanent|regular|active|full-time)?\s*(?:employees|workforce|people|personnel|staff)",
            r"(?:employees|workforce|headcount)\s*[:\-=]?\s*([\d,]+)",
        ])

    # 2. Universal Numeric Fallback (Aggressive table scraping from raw text)
    if spec.expected_value_type.value in ("currency_amount", "number"):
        terms = [re.escape(t.strip()) for t in [spec.entity_name] + spec.synonyms if len(t.strip()) > 2]
        if terms:
            terms_joined = "|".join(terms)
            # Matches: Label -> Optional Note Number/Letter -> Numeric Value
            # e.g. "Profit for the period A 12,938.22" -> captures "12,938.22"
            pattern = rf"(?i)(?:{terms_joined})\s*(?:[A-Za-z0-9\-\.]+\s*)?([\d\,\.\(\)]{{2,}})"
            regex_patterns.append(pattern)

    if not regex_patterns:
        return None, None

    # Search universally across all blocks to catch orphans missed by canonicalizer sections
    for blk in canonical_doc.blocks:
        b_tokens = [canonical_doc.token_registry[t].text for t in blk.token_ids if t in canonical_doc.token_registry]
        if not b_tokens:
            continue
            
        b_text = " ".join(b_tokens)
        for pat in regex_patterns:
            match = re.search(pat, b_text, re.IGNORECASE)
            if match:
                matched_val = match.group(1) if match.groups() else match.group(0)
                prov = SourceReference(
                    document_id=canonical_doc.document_id,
                    page_number=blk.page_number,
                    block_id=blk.block_id,
                    token_ids=blk.token_ids,
                    raw_text=b_text[:200],
                )
                return matched_val, prov
                
    return None, None


def _find_in_structured_intelligence(
    raw_intel: dict[str, Any],
    evidence_map: dict[str, Any],
    category: str,
    subcategory: str,
    entity_name: str,
    synonyms: list[str],
) -> tuple[Any, dict[str, Any] | None]:
    """Search for matching value in pre-extracted structured intelligence dict."""
    candidates = [entity_name.lower(), subcategory.lower()] + [s.lower() for s in synonyms]

    for cat_key, sub_dict in raw_intel.items():
        if isinstance(sub_dict, dict):
            for sub_key, val in sub_dict.items():
                sub_lower = sub_key.lower()
                for cand in candidates:
                    if cand in sub_lower or sub_lower in cand:
                        ev = evidence_map.get(sub_key) or evidence_map.get(entity_name)
                        return val, ev

    return None, None


def _find_section_id(sections: list[CanonicalSection], section_name: str | None, page_num: int | None) -> str | None:
    s_lower = section_name.lower() if section_name else ""
    for sec in sections:
        start_p = sec.start_page or 1
        end_p = sec.end_page or start_p
        if page_num is not None and start_p <= page_num <= end_p:
            return sec.section_id
        if s_lower and (s_lower in sec.title_normalized or s_lower in sec.title_raw.lower()):
            return sec.section_id
    return sections[0].section_id if sections else None



def _find_in_canonical_tables(
    doc: CanonicalDocument,
    entity_name: str,
    synonyms: list[str],
) -> tuple[dict[str, Any] | None, Any, SourceReference | None]:
    """Search canonical tables for matching row labels."""
    query_terms = [entity_name.lower()] + [s.lower() for s in synonyms]

    for tbl in doc.tables:
        for cell in tbl.cells:
            if cell.raw_text:
                c_text = cell.raw_text.lower()
                for q in query_terms:
                    if len(q) > 2:
                        import re
                        if re.search(rf'\b{re.escape(q)}\b', c_text):
                            for adj_cell in tbl.cells:
                                if adj_cell.row_index == cell.row_index and adj_cell.column_index > cell.column_index:
                                    if adj_cell.parsed_numeric is not None or any(char.isdigit() for char in adj_cell.raw_text):
                                        prov = SourceReference(
                                            document_id=doc.document_id,
                                            page_number=tbl.page_numbers[0] if tbl.page_numbers else 1,
                                            section_id=tbl.table_id,
                                            table_id=tbl.table_id,
                                            table_index=tbl.table_id,
                                            raw_text=f"{cell.raw_text} -> {adj_cell.raw_text}",
                                        )
                                        val_to_use = str(adj_cell.parsed_numeric) if adj_cell.parsed_numeric is not None else adj_cell.raw_text
                                        return {"raw_text": val_to_use}, adj_cell, prov
    return None, None, None


def _find_in_canonical_sections(
    doc: CanonicalDocument,
    entity_name: str,
    synonyms: list[str],
) -> tuple[str | None, SourceReference | None]:
    """Search text blocks in canonical sections for matching key-value text lines."""
    query_terms = [entity_name.lower()] + [s.lower() for s in synonyms]

    for sec in doc.sections:
        for blk_id in sec.block_ids:
            blk = next((b for b in doc.blocks if b.block_id == blk_id), None)
            if blk:
                block_tokens = [doc.token_registry[t_id].text for t_id in blk.token_ids if t_id in doc.token_registry]
                block_text = " ".join(block_tokens)
                b_lower = block_text.lower()

                for q in query_terms:
                    if q in b_lower:
                        prov = SourceReference(
                            document_id=doc.document_id,
                            page_number=blk.page_number,
                            section_id=sec.section_id,
                            block_id=blk.block_id,
                            token_ids=blk.token_ids,
                            raw_text=block_text[:200],
                        )
                        return block_text, prov
    return None, None
