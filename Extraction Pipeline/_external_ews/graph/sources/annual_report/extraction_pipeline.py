"""Extraction Pipeline Orchestrator -- chains all 9 layers together.

This is the main entry point for the enterprise-grade Annual Report
Extraction Framework. It orchestrates:

  Layer 1: PDF Ingestion
  Layer 2: Master Data Layer (SQLite)
  Layer 3: Taxonomy Classification (Hybrid LLM + keyword/regex)
  Layer 4: Table Detection
  Layer 5/6: Extraction Strategy + VLM Workflow
  Layer 7: Financial Statement Engine
  Layer 8: Output Schema
  Layer 9: Validation

Flow::

    PDF -> Ingestion -> Master Data -> Taxonomy -> Table Detection
         -> Text Extraction (default) -> VLM Extraction (fallback)
         -> Financial Statement Engine -> Validation -> Output

Usage::

    from extraction_pipeline import run_full_extraction
    result = run_full_extraction("path/to/annual_report.pdf")
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from .schemas import (
    DocumentRegistry,
    FullExtractionResult,
    QualityReport,
    SectionRegistry,
    TableInventorySummary,
    TaxonomyMapping,
    TaxonomySummary,
    TextExtractionResult,
    TableExtractionResult,
    VLMTargetItem,
)

logger = logging.getLogger(__name__)


def run_full_extraction(
    pdf_path: str | Path,
    progress_callback=None,
    use_llm_taxonomy: bool = True,
    dpi: int = 150,
) -> dict[str, Any]:
    """Run the full 9-layer extraction pipeline.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the annual report PDF.
    progress_callback : callable, optional
        Called with progress message strings.
    use_llm_taxonomy : bool
        Whether to use LLM for taxonomy classification (default True).
    dpi : int
        Image resolution for VLM extraction (default 150).

    Returns
    -------
    dict
        Complete extraction result with taxonomy mappings, text
        extractions, table extractions, and validation report.
        Also includes legacy standalone/consolidated format for
        backward compatibility.
    """
    pdf_path = Path(pdf_path)

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    t0 = time.time()
    _log(f"[Pipeline] === Starting Full Extraction Pipeline ===")
    _log(f"[Pipeline] File: {pdf_path.name}")

    # ==================================================================
    # Layer 1: PDF Ingestion
    # ==================================================================
    _log("[Pipeline] -- Layer 1: PDF Ingestion --")
    from .pdf_ingestion import ingest_pdf, get_pdf_metadata

    metadata = get_pdf_metadata(pdf_path)
    metadata["extraction_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    metadata["extraction_method"] = "hybrid_framework"

    pages_data = ingest_pdf(pdf_path, progress_callback=progress_callback)
    _log(f"[Pipeline]    Ingested {len(pages_data)} pages")

    # ==================================================================
    # Layer 2: Master Data Layer (SQLite)
    # ==================================================================
    _log("[Pipeline] -- Layer 2: Master Data Layer (SQLite) --")
    from .master_data import MasterDataStore

    store = MasterDataStore()  # In-memory SQLite
    store.load_pages(pages_data)

    summary = store.get_summary()
    _log(f"[Pipeline]    SQLite loaded: {summary['total_pages']} pages, "
         f"{summary['pages_with_headings']} headings, "
         f"{summary['pages_with_tables']} pages with tables")
    _log(f"[Pipeline]    Unique sections: {summary['unique_sections']}")

    sections = store.get_unique_sections()
    for section in sections[:20]:  # Log first 20
        _log(f"[Pipeline]      * {section}")
    if len(sections) > 20:
        _log(f"[Pipeline]      ... and {len(sections) - 20} more")

    # ==================================================================
    # Layer 3: Section Registry (TOC & Headings)
    # ==================================================================
    _log("[Pipeline] -- Layer 3: Section Registry (TOC & Headings) --")
    
    all_pages = store.get_all_pages()

    # Parse TOC for section anchors
    toc_hints = None
    try:
        from .toc_parser import parse_toc_for_page_hints
        toc_hints = parse_toc_for_page_hints(
            pdf_path,
            pages=[{"page": p["page_number"], "text": p.get("raw_text", "")} for p in all_pages],
            progress_callback=progress_callback,
        )
        toc_entry_count = len(toc_hints.raw_entries) if toc_hints else 0
        _log(f"[Pipeline]    TOC parsed: {toc_entry_count} entries found")
    except Exception as exc:
        logger.warning(f"TOC parsing failed: {exc}")
        _log(f"[Pipeline]    TOC parsing failed: {exc}")

    from .section_consolidator import build_section_registry
    master_sections = build_section_registry(
        toc_hints=toc_hints,
        all_pages=all_pages,
        total_pages=len(pages_data),
        progress_callback=progress_callback,
    )

    # ==================================================================
    # Layer 3.5: Taxonomy Classification (on Section Blocks)
    # ==================================================================
    _log("[Pipeline] -- Layer 3.5: Taxonomy Classification --")
    from .taxonomy import classify_sections

    master_sections = classify_sections(
        sections=master_sections,
        all_pages=all_pages,
        progress_callback=progress_callback,
        use_llm=use_llm_taxonomy,
    )

    # Generate legacy taxonomy_mappings
    taxonomy_mappings = []
    for sec in master_sections:
        for pg in range(sec.get("start_page", 0), sec.get("end_page", 0) + 1):
            taxonomy_mappings.append({
                "page_number": pg,
                "section_type": sec.get("section_type", ""),
                "section_subtype": sec.get("section_subtype", ""),
                "category": sec.get("category", ""),
                "subcategory": sec.get("subcategory", ""),
                "confidence": sec.get("confidence", 0.0),
                "method": "section_registry",
            })

    # Store in SQLite
    store.save_taxonomy_mappings_bulk(taxonomy_mappings)
    store.save_master_sections(master_sections)
    _log(f"[Pipeline]    {len(master_sections)} sections and {len(taxonomy_mappings)} page mappings saved to SQLite")

    # Log consolidation stats
    toc_sections = sum(1 for s in master_sections if s.get("boundary_source") == "toc")
    heading_sections = sum(1 for s in master_sections if s.get("boundary_source") == "heading")
    inferred_sections = sum(1 for s in master_sections if s.get("boundary_source") == "classifier")
    _log(f"[Pipeline]    Sources: {toc_sections} TOC, {heading_sections} Heading, {inferred_sections} Inferred")

    # ==================================================================
    # Layer 3.6: Section Hierarchy
    # ==================================================================
    _log("[Pipeline] -- Layer 3.6: Section Hierarchy --")
    from .section_consolidator import build_section_hierarchy

    section_hierarchy = build_section_hierarchy(
        master_sections,
        progress_callback=progress_callback,
    )
    _log(f"[Pipeline]    {section_hierarchy['total_categories']} categories, "
         f"{section_hierarchy['total_sections']} sections in hierarchy")

    # ==================================================================
    # Layer 4: Table Inventory
    # ==================================================================
    _log("[Pipeline] -- Layer 4: Table Inventory --")
    from .table_detector import detect_tables

    detected_tables = detect_tables(
        all_pages,
        master_sections=master_sections,
        progress_callback=progress_callback,
    )

    # Store detected tables in SQLite
    store.save_table_inventory(detected_tables)
    _log(f"[Pipeline]    {len(detected_tables)} tables added to Table Inventory")

    # ==================================================================
    # Layer 4.5: VLM Target Generation
    # ==================================================================
    _log("[Pipeline] -- Layer 4.5: VLM Target Generation --")
    from .vlm_targets import generate_vlm_targets, vlm_target_summary

    vlm_targets = generate_vlm_targets(
        master_sections=master_sections,
        table_inventory=detected_tables,
        progress_callback=progress_callback,
    )
    
    vlm_summary = vlm_target_summary(vlm_targets)
    _log(f"[Pipeline]    {vlm_summary['total_targets']} VLM targets: "
         f"{vlm_summary['by_priority']['high']} HIGH, "
         f"{vlm_summary['by_priority']['medium']} MEDIUM, "
         f"{vlm_summary['by_priority']['low']} LOW")

    # ==================================================================
    # Layer 5/6: Extraction Strategy + VLM Workflow
    # ==================================================================
    _log("[Pipeline] -- Layer 5/6: Extraction + VLM Workflow --")

    text_extractions: list[dict[str, Any]] = []
    table_extractions: list[dict[str, Any]] = []

    # Extract text content for EVERY master section
    for section in master_sections:
        category = section.get("category", "")
        subcategory = section.get("normalized_section_name", section.get("raw_section_name", ""))
        start = section["start_page"]
        end = section["end_page"]
        
        # Gather text from start_page to end_page inclusive
        section_text_blocks = []
        for p in range(start, end + 1):
            page_data = store.get_page(p)
            if page_data and page_data.get("raw_text"):
                section_text_blocks.append(f"--- Page {p} ---\n{page_data['raw_text']}")
                
        if not section_text_blocks:
            continue
            
        combined_text = "\n\n".join(section_text_blocks)
        source_pages = list(range(start, end + 1))
        
        text_extractions.append({
            "category": category,
            "subcategory": subcategory,
            "extracted_text": combined_text[:50000],  # Cap at 50k chars
            "source_pages": source_pages,
            "extraction_method": section.get("extraction_strategy", "pdf_text"),
            "confidence": section.get("confidence", 0.0),
        })

    _log(f"[Pipeline]    {len(text_extractions)} sections extracted as text/content")

    # ==================================================================
    # Layer 6.5: Subcategory Content Extraction Engine
    # ==================================================================
    _log("[Pipeline] -- Layer 6.5: Subcategory Content Extraction Engine --")
    
    from .content_extractor import extract_subcategory_content, EvidenceBackedResult, extract_governance_multi
    from .llm_config import get_llm
    from .source_routing import select_best_source, get_all_field_names
    from .workbook_population import WORKBOOK_TARGETS, MAPPING_RULES
    
    structured_intelligence = {}
    evidence_map: dict[str, dict] = {}   # subcat → evidence metadata
    
    llm = None
    try:
        llm = get_llm()
    except Exception as exc:
        logger.warning(f"Failed to initialize LLM for structured extraction: {exc}")
    
    # Helper: unwrap EvidenceBackedResult and populate evidence_map
    def _store_result(save_cat: str, subcat: str, result):
        """Store extraction result, unwrapping EvidenceBackedResult if present."""
        if isinstance(result, EvidenceBackedResult):
            structured_intelligence[save_cat][subcat] = result.value
            evidence_map[subcat] = {
                "extraction_method": result.evidence.extraction_method,
                "source_text_snippet": result.evidence.source_text_snippet,
                "source_page": result.evidence.source_page,
                "confidence": result.evidence.confidence,
                "source_section": result.evidence.source_section,
            }
        else:
            # Backward compat: raw value (shouldn't happen with new code)
            structured_intelligence[save_cat][subcat] = result
    
    # Phase 1: Priority-driven extraction for known target fields.
    # For each Intelligence Report field, select the best source section
    # using FIELD_SOURCE_PRIORITY (e.g., Dividend from Directors Report,
    # not AGM Notice).  This prevents wrong-source extraction errors.
    priority_fields = {subcat: cat for cat, subcat in WORKBOOK_TARGETS}
    priority_extracted_targets: set[str] = set()   # target field names (e.g. "Board of Directors")
    priority_extracted_sources: set[str] = set()   # source section names (e.g. "Directors Report")

    # Helper: map a taxonomy subcategory name to a WORKBOOK_TARGETS field name
    def _resolve_target_field(sub_name: str) -> str | None:
        """Map a taxonomy subcategory name to a WORKBOOK_TARGETS field name using MAPPING_RULES."""
        sub_lower = sub_name.lower()
        for target_name, aliases in MAPPING_RULES.items():
            for alias in aliases:
                if alias in sub_lower or sub_lower in alias:
                    return target_name
        return None
    
    # FIX 4: Governance fields that benefit from multi-extract
    _GOVERNANCE_FIELDS = {"Board of Directors", "Key Management Personnel", "Board Committees", "Corporate Governance"}
    
    # Track which governance sources have already been multi-extracted
    _governance_multi_done: set[str] = set()   # source section names already processed

    for subcat, cat in priority_fields.items():
        best_source = select_best_source(subcat, text_extractions)
        if best_source:
            src_cat = best_source.get("category", "")
            src_sub = best_source.get("subcategory", "")
            text_content = best_source.get("extracted_text", "")
            src_page = best_source.get("start_page")
            
            # Removed financial sections skip filter (Gap 7)
            
            # FIX 4: If this is a governance field and the source is a governance section,
            # use multi-extract to get Board + KMP + Committees + Corp Gov all at once.
            src_lower = src_sub.lower()
            is_governance_source = (
                "corporate governance" in src_lower
                or "governance report" in src_lower
                or src_cat == "Management & Governance"
            )
            
            if subcat in _GOVERNANCE_FIELDS and is_governance_source and src_sub not in _governance_multi_done:
                _governance_multi_done.add(src_sub)
                gov_results = extract_governance_multi(
                    text_content, llm,
                    source_page=src_page, source_section=src_sub,
                )
                for gov_field, gov_result in gov_results.items():
                    gov_cat = priority_fields.get(gov_field, "Management & Governance")
                    save_cat = gov_cat if gov_cat and gov_cat != "Unclassified" else "Extracted Intelligence"
                    if save_cat not in structured_intelligence:
                        structured_intelligence[save_cat] = {}
                    _store_result(save_cat, gov_field, gov_result)
                    priority_extracted_targets.add(gov_field)
                    logger.info("[Priority] Extracted target=%s source=%s (via governance multi)", gov_field, src_sub)
                    _log(f"[Pipeline]    Governance multi: '{gov_field}' ← source '{src_sub}'")
                priority_extracted_sources.add(src_sub)
                continue
            
            # Skip if already extracted via governance multi
            if subcat in priority_extracted_targets:
                continue
            
            extracted = extract_subcategory_content(
                src_cat, src_sub, text_content, llm,
                source_page=src_page, source_section=src_sub,
            )
            if extracted:
                save_cat = cat if cat and cat != "Unclassified" else "Extracted Intelligence"
                if save_cat not in structured_intelligence:
                    structured_intelligence[save_cat] = {}
                _store_result(save_cat, subcat, extracted)
                priority_extracted_targets.add(subcat)   # FIX 2: track target name
                priority_extracted_sources.add(src_sub)   # FIX 2: track source name
                logger.info("[Priority] Extracted target=%s source=%s", subcat, src_sub)
                _log(f"[Pipeline]    Priority match: '{subcat}' ← source '{src_sub}'")
    
    _log(f"[Pipeline]    {len(priority_extracted_targets)} fields extracted via source priority")
    
    # Phase 2: Fallback — extract remaining sections not covered by priority routing.
    # This catches Unclassified sections and any fields not in WORKBOOK_TARGETS.
    # FIX 2: Skip sections whose source OR target was already processed in Phase 1.
    # FIX 3: Store results under WORKBOOK_TARGETS field names, not taxonomy names.
    # FIX 4: Use governance multi-extract for Corporate Governance sections.
    for extraction in text_extractions:
        category = extraction.get("category", "")
        subcategory = extraction.get("subcategory", "")
        text_content = extraction.get("extracted_text", "")
        src_page = extraction.get("start_page")
        
        # Skip sections already extracted in Phase 1 (by source name or target name)
        if subcategory in priority_extracted_sources or subcategory in priority_extracted_targets:
            logger.info("[Priority] Skipping already processed target=%s", subcategory)
            continue
        
        # Process all non-financial categories so we can catch Unclassified aliases
        if "financial" not in category.lower() and "notes to accounts" not in category.lower():
            # FIX 4: Governance multi-extract for Corporate Governance sections in Phase 2
            sub_lower = subcategory.lower()
            is_gov_section = (
                "corporate governance" in sub_lower
                or "governance report" in sub_lower
                or category == "Management & Governance"
            )
            if is_gov_section and subcategory not in _governance_multi_done:
                _governance_multi_done.add(subcategory)
                gov_results = extract_governance_multi(
                    text_content, llm,
                    source_page=src_page, source_section=subcategory,
                )
                for gov_field, gov_result in gov_results.items():
                    if gov_field in priority_extracted_targets:
                        continue   # Already extracted in Phase 1
                    gov_cat = priority_fields.get(gov_field, "Management & Governance")
                    save_cat = gov_cat if gov_cat and gov_cat != "Unclassified" else "Extracted Intelligence"
                    if save_cat not in structured_intelligence:
                        structured_intelligence[save_cat] = {}
                    _store_result(save_cat, gov_field, gov_result)
                    priority_extracted_targets.add(gov_field)
                    logger.info("[Storage] category=%s target=%s (via governance multi Phase 2)", save_cat, gov_field)
                continue
            
            extracted = extract_subcategory_content(
                category, subcategory, text_content, llm,
                source_page=src_page, source_section=subcategory,
            )
            if extracted:
                # FIX 3: Resolve taxonomy subcategory → WORKBOOK_TARGETS field name
                target_field = _resolve_target_field(subcategory)
                
                if target_field:
                    # Skip if this target was already successfully extracted in Phase 1
                    if target_field in priority_extracted_targets:
                        logger.info("[Priority] Skipping already processed target=%s", target_field)
                        continue
                    
                    # Store under the WORKBOOK_TARGETS category and field name
                    target_cat = priority_fields.get(target_field, category)
                    save_cat = target_cat if target_cat and target_cat != "Unclassified" else "Extracted Intelligence"
                    if save_cat not in structured_intelligence:
                        structured_intelligence[save_cat] = {}
                    _store_result(save_cat, target_field, extracted)
                    logger.info("[Storage] category=%s target=%s (from subcategory=%s)", save_cat, target_field, subcategory)
                else:
                    # No mapping found — store under taxonomy name as before
                    save_cat = category if category and category != "Unclassified" else "Extracted Intelligence"
                    if save_cat not in structured_intelligence:
                        structured_intelligence[save_cat] = {}
                    _store_result(save_cat, subcategory, extracted)
                    logger.info("[Storage] category=%s target=%s (unmapped)", save_cat, subcategory)

    _log(f"[Pipeline]    Structured Intelligence populated for {len(structured_intelligence)} categories")

    # ==================================================================
    # Layer 7: Financial Statement Engine (VLM for complex tables)
    # ==================================================================
    _log("[Pipeline] -- Layer 7: Financial Statement Engine --")

    # Use existing discovery + VLM pipeline for financial statements
    legacy_result: dict[str, Any] = {"standalone": {}, "consolidated": {}}

    try:
        from .vlm_extractor import vlm_extract_all

        # Run the existing VLM pipeline for financial tables
        vlm_result = vlm_extract_all(
            pdf_path=pdf_path,
            dpi=dpi,
            progress_callback=progress_callback,
        )

        legacy_result["standalone"] = vlm_result.get("standalone", {})
        legacy_result["consolidated"] = vlm_result.get("consolidated", {})

        # Convert VLM results to table extractions
        for entity in ("standalone", "consolidated"):
            entity_data = vlm_result.get(entity, {})
            for stmt_key in ("balance_sheet", "profit_and_loss", "cash_flow"):
                stmt = entity_data.get(stmt_key)
                if stmt and stmt.get("rows"):
                    table_extractions.append({
                        "table_name": f"{entity}_{stmt_key}",
                        "source_page": stmt.get("page", 0),
                        "extraction_method": stmt.get("extraction_method", "vlm"),
                        "table_json": {
                            "title": stmt.get("title", ""),
                            "currency": stmt.get("currency", ""),
                            "periods": stmt.get("periods", []),
                            "rows": stmt.get("rows", []),
                        },
                        "confidence": 0.85,
                    })

        _log(f"[Pipeline]    {len(table_extractions)} financial tables extracted via VLM")
        
        # -- VLM Target-Driven Router for Generic Tables --
        # Replaces the old hardcoded routing with VLM-target-based routing
        from .vlm_extractor import extract_generic_table
        from .vlm_targets import TableCategory as TC

        # Sections already handled by the legacy VLM pipeline above
        LEGACY_STATEMENTS = {
            "Standalone Balance Sheet", "Standalone Profit & Loss", "Standalone Cash Flow",
            "Consolidated Balance Sheet", "Consolidated Profit & Loss", "Consolidated Cash Flow",
            "Notes to Accounts"
        }

        generic_tables_extracted = 0
        for target in vlm_targets:
            # Only route HIGH and MEDIUM priority targets to VLM
            if target["priority"] not in ("high", "medium"):
                continue

            # Skip sections already handled by the legacy financial statement pipeline
            if target["section_name"] in LEGACY_STATEMENTS:
                continue

            # Skip financial_statement category -- already handled by vlm_extract_all
            if target["table_category"] == TC.FINANCIAL_STATEMENT:
                continue

            # Route to VLM generic table extractor
            _log(f"[Pipeline]    VLM routing: {target['section_name']} "
                 f"(priority={target['priority']}, category={target['table_category']}, "
                 f"pp. {target['page_range'][0]}-{target['page_range'][1]})")

            pages = list(range(target["page_range"][0], target["page_range"][1] + 1))

            generic_result = extract_generic_table(
                pdf_path=pdf_path,
                table_name=target["section_name"],
                page_numbers=pages,
                dpi=dpi,
                progress_callback=progress_callback,
            )

            if generic_result and "rows" in generic_result:
                table_extractions.append({
                    "table_name": target["section_name"],
                    "source_page": target["page_range"][0],
                    "extraction_method": "vlm_target",
                    "table_json": generic_result,
                    "confidence": target.get("confidence", 0.8),
                    "table_category": target["table_category"],
                    "vlm_priority": target["priority"],
                })
                generic_tables_extracted += 1
            else:
                _log(f"[Pipeline]    VLM extraction returned no data for {target['section_name']}")

        _log(f"[Pipeline]    {generic_tables_extracted} tables extracted via VLM target routing")

    except Exception as exc:
        logger.warning(f"Financial statement engine failed: {exc}")
        _log(f"[Pipeline]    Financial statement engine failed: {exc}")

    # ==================================================================
    # Layer 9: Validation
    # ==================================================================
    _log("[Pipeline] -- Layer 9: Validation --")
    from .validation_engine import validate_extraction, compute_quality_report

    validation_report = validate_extraction(
        taxonomy_mappings=taxonomy_mappings,
        detected_tables=detected_tables,
        extracted_tables=table_extractions,
        total_pages=len(pages_data),
        progress_callback=progress_callback,
    )

    # ==================================================================
    # Layer 9.5: Quality Report
    # ==================================================================
    _log("[Pipeline] -- Layer 9.5: Quality Report --")

    quality_report = compute_quality_report(
        master_sections=master_sections,
        taxonomy_mappings=taxonomy_mappings,
        detected_tables=detected_tables,
        vlm_targets=vlm_targets,
        completeness_report=validation_report,
        total_pages=len(pages_data),
        progress_callback=progress_callback,
    )
    _log(f"[Pipeline]    Quality score: {quality_report.overall_score}/10")

    # ==================================================================
    # Build final result (canonical + legacy)
    # ==================================================================
    elapsed = time.time() - t0

    # Master data summary
    final_summary = store.get_summary()
    metadata["master_data_summary"] = final_summary
    metadata["pipeline_elapsed_seconds"] = round(elapsed, 2)

    # Consolidation stats
    consolidation_ratio = len(master_sections) / max(len(taxonomy_mappings), 1)
    toc_anchor_count = sum(1 for s in master_sections if s.get("source") == "toc")
    taxonomy_sections = sum(1 for s in master_sections if s.get("source") == "taxonomy")
    merged_sections = sum(1 for s in master_sections if s.get("source") == "merged")

    # -- Build canonical DocumentRegistry --
    from .schemas import MasterSection, TableInventoryItem

    for s in master_sections:
        if isinstance(s, dict) and "section_name" not in s:
            s["section_name"] = s.get("normalized_section_name", s.get("raw_section_name", ""))

    section_registry = SectionRegistry(
        total_sections=len(master_sections),
        toc_sections=toc_anchor_count,
        taxonomy_sections=taxonomy_sections,
        merged_sections=merged_sections,
        hierarchy=section_hierarchy.get("hierarchy", {}),
        flat=[MasterSection(**s) for s in master_sections if isinstance(s, dict)],
    )

    # Table inventory summary
    table_by_category: dict[str, int] = {}
    vlm_required_count = 0
    inventory_items = []
    for t in detected_tables:
        tt = t.get("table_type", "other")
        table_by_category[tt] = table_by_category.get(tt, 0) + 1
        if t.get("needs_vlm", False):
            vlm_required_count += 1
        try:
            inventory_items.append(TableInventoryItem(**{k: v for k, v in t.items() if k in TableInventoryItem.model_fields}))
        except Exception:
            pass

    table_inventory_summary = TableInventorySummary(
        total_tables=len(detected_tables),
        by_category=table_by_category,
        vlm_required=vlm_required_count,
        all_items=inventory_items,
    )

    # Taxonomy summary
    found_categories = sorted(set(m.get("category", "") for m in taxonomy_mappings))
    taxonomy_summary = TaxonomySummary(
        categories_found=found_categories,
        coverage_pct=validation_report.coverage_pct,
        total_page_mappings=len(taxonomy_mappings),
        page_mappings=[TaxonomyMapping(**m) for m in taxonomy_mappings if isinstance(m, dict)],
    )

    # VLM target items
    vlm_target_items = []
    for t in vlm_targets:
        try:
            vlm_target_items.append(VLMTargetItem(**t))
        except Exception:
            pass

    # Document registry (canonical output)
    document_registry = DocumentRegistry(
        metadata=metadata,
        section_registry=section_registry,
        table_inventory=table_inventory_summary,
        taxonomy=taxonomy_summary,
        extractions={
            "text_extractions": text_extractions,
            "table_extractions": table_extractions,
        },
        quality_report=quality_report,
        vlm_targets=vlm_target_items,
        structured_intelligence=structured_intelligence,
        standalone=legacy_result.get("standalone", {}),
        consolidated=legacy_result.get("consolidated", {}),
    )

    # -- Build legacy result dict (backward compatibility) --
    result = {
        "metadata": metadata,
        "master_sections": master_sections,
        "table_inventory": detected_tables,
        "taxonomy_mappings": taxonomy_mappings,
        "text_extractions": text_extractions,
        "table_extractions": table_extractions,
        "validation_report": validation_report.model_dump(),
        "structured_intelligence": structured_intelligence,
        "evidence_map": evidence_map,
        "raw_pages_text": all_pages,
        "standalone": legacy_result.get("standalone", {}),
        "consolidated": legacy_result.get("consolidated", {}),
        "consolidation_stats": {
            "total_sections": len(master_sections),
            "taxonomy_mappings_input": len(taxonomy_mappings),
            "consolidation_ratio": round(consolidation_ratio, 3),
            "toc_anchored_sections": toc_anchor_count,
        },
        "section_hierarchy": section_hierarchy,
        "vlm_targets": vlm_targets,
        "vlm_target_summary": vlm_summary,
        # -- Canonical output (Phase 4) --
        "document_registry": document_registry.model_dump(),
        "quality_report": quality_report.model_dump(),
    }

    # Close the store
    store.close()

    _log(f"[Pipeline] === Pipeline Complete in {elapsed:.1f}s ===")
    _log(f"[Pipeline]   Pages: {len(pages_data)}")
    _log(f"[Pipeline]   Taxonomy mappings: {len(taxonomy_mappings)}")
    _log(f"[Pipeline]   Consolidated sections: {len(master_sections)} "
         f"(ratio: {consolidation_ratio:.2f}, TOC-anchored: {toc_anchor_count})")
    _log(f"[Pipeline]   Text extractions: {len(text_extractions)}")
    _log(f"[Pipeline]   Table extractions: {len(table_extractions)}")
    _log(f"[Pipeline]   Coverage: {validation_report.coverage_pct}%")
    _log(f"[Pipeline]   Quality score: {quality_report.overall_score}/10")
    _log(f"[Pipeline]   Validation issues: {len(validation_report.issues)}")

    return result
