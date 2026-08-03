"""Validation Layer — validates extraction completeness and quality.

Checks for:
  - Missing mandatory taxonomy sections
  - Duplicate mappings
  - Incomplete tables
  - Confidence thresholds
  - Generates a comprehensive completeness report
  - Computes a QualityReport with composite 0-10 score
"""

from __future__ import annotations

import logging
from typing import Any

from .schemas import (
    CompletenessReport,
    QualityReport,
    ValidationIssue,
)
from .taxonomy import ALL_CATEGORIES, TAXONOMY

logger = logging.getLogger(__name__)


# ===================================================================
# Mandatory sections that MUST be present in a valid annual report
# ===================================================================

MANDATORY_CATEGORIES = [
    "Company Information",
    "Management & Governance",
    "Financial Statements",
    "Audit Information",
]

# Sections that are highly expected (not mandatory but flagged if missing)
EXPECTED_CATEGORIES = [
    "Shareholding Information",
    "Management Discussion & Analysis",
    "Notes to Accounts",
    "Legal & Compliance",
    "Investor Information",
]

# Minimum confidence threshold for a mapping to be considered valid
MIN_CONFIDENCE_THRESHOLD = 0.50

# Maximum allowed duplicate mappings per page per category
MAX_DUPLICATES_PER_PAGE = 3


# ===================================================================
# Main Validation Function
# ===================================================================

def validate_extraction(
    taxonomy_mappings: list[dict[str, Any]],
    detected_tables: list[dict[str, Any]],
    extracted_tables: list[dict[str, Any]],
    total_pages: int = 0,
    progress_callback=None,
) -> CompletenessReport:
    """Run all validation checks and generate a completeness report.

    Parameters
    ----------
    taxonomy_mappings : list[dict]
        All taxonomy mappings from the classification layer.
    detected_tables : list[dict]
        All detected tables from the table detection layer.
    extracted_tables : list[dict]
        All successfully extracted tables.
    total_pages : int
        Total number of pages in the document.
    progress_callback : callable, optional
        Progress callback.

    Returns
    -------
    CompletenessReport
        Full validation report with issues and metrics.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[Validation] Starting validation checks...")

    issues: list[ValidationIssue] = []

    # ── Check 1: Missing mandatory sections ──────────────────────────
    found_categories = set(m.get("category", "") for m in taxonomy_mappings)
    _check_missing_sections(found_categories, issues)

    # ── Check 2: Duplicate mappings ──────────────────────────────────
    _check_duplicates(taxonomy_mappings, issues)

    # ── Check 3: Incomplete tables ───────────────────────────────────
    _check_incomplete_tables(detected_tables, extracted_tables, issues)

    # ── Check 4: Low confidence mappings ─────────────────────────────
    _check_confidence_thresholds(taxonomy_mappings, issues)

    # ── Compute metrics ──────────────────────────────────────────────
    pages_classified = len(set(m.get("page_number", 0) for m in taxonomy_mappings))
    categories_found = len(found_categories)
    tables_detected = len(detected_tables)
    tables_extracted = len(extracted_tables)

    coverage_pct = (categories_found / len(ALL_CATEGORIES)) * 100 if ALL_CATEGORIES else 0.0

    # Overall confidence = average of all mapping confidences
    all_confidences = [m.get("confidence", 0.0) for m in taxonomy_mappings if m.get("confidence", 0.0) > 0]
    overall_confidence = sum(all_confidences) / max(len(all_confidences), 1)

    report = CompletenessReport(
        total_pages=total_pages,
        pages_classified=pages_classified,
        categories_found=categories_found,
        categories_expected=len(ALL_CATEGORIES),
        tables_detected=tables_detected,
        tables_extracted=tables_extracted,
        issues=[ValidationIssue(**i) if isinstance(i, dict) else i for i in issues],
        coverage_pct=round(coverage_pct, 1),
        overall_confidence=round(overall_confidence, 3),
    )

    # Summary log
    error_count = sum(1 for i in report.issues if i.severity == "error")
    warning_count = sum(1 for i in report.issues if i.severity == "warning")
    info_count = sum(1 for i in report.issues if i.severity == "info")

    _log(f"[Validation] Complete: {categories_found}/{len(ALL_CATEGORIES)} categories found "
         f"({coverage_pct:.1f}% coverage), {error_count} errors, "
         f"{warning_count} warnings, {info_count} info")

    return report


# ===================================================================
# Individual validation checks
# ===================================================================

def _check_missing_sections(
    found_categories: set[str],
    issues: list[ValidationIssue],
) -> None:
    """Check for missing mandatory and expected sections."""
    # Mandatory
    for cat in MANDATORY_CATEGORIES:
        if cat not in found_categories:
            issues.append(ValidationIssue(
                issue_type="missing_section",
                severity="error",
                description=f"Mandatory section '{cat}' not found in the document.",
                category=cat,
            ))

    # Expected (warning)
    for cat in EXPECTED_CATEGORIES:
        if cat not in found_categories:
            issues.append(ValidationIssue(
                issue_type="missing_section",
                severity="warning",
                description=f"Expected section '{cat}' not found in the document.",
                category=cat,
            ))

    # All other categories (info)
    all_missing = set(ALL_CATEGORIES) - found_categories - set(MANDATORY_CATEGORIES) - set(EXPECTED_CATEGORIES)
    for cat in all_missing:
        issues.append(ValidationIssue(
            issue_type="missing_section",
            severity="info",
            description=f"Optional section '{cat}' not found in the document.",
            category=cat,
        ))


def _check_duplicates(
    taxonomy_mappings: list[dict[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    """Check for excessive duplicate mappings."""
    # Group by (page_number, category)
    page_cat_counts: dict[tuple[int, str], int] = {}
    for m in taxonomy_mappings:
        key = (m.get("page_number", 0), m.get("category", ""))
        page_cat_counts[key] = page_cat_counts.get(key, 0) + 1

    for (page_num, category), count in page_cat_counts.items():
        if count > MAX_DUPLICATES_PER_PAGE:
            issues.append(ValidationIssue(
                issue_type="duplicate_mapping",
                severity="warning",
                description=(
                    f"Page {page_num} has {count} duplicate mappings "
                    f"for category '{category}' (max {MAX_DUPLICATES_PER_PAGE})."
                ),
                category=category,
                page=page_num,
            ))


def _check_incomplete_tables(
    detected_tables: list[dict[str, Any]],
    extracted_tables: list[dict[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    """Check for tables that were detected but not successfully extracted."""
    detected_pages = set(
        (d.get("page_number", 0), d.get("table_type", ""))
        for d in detected_tables
    )
    extracted_pages = set()
    for e in extracted_tables:
        # Match by page and type
        source_page = e.get("source_page", 0)
        table_name = e.get("table_name", "").lower().replace(" ", "_")
        extracted_pages.add((source_page, table_name))

    for page_num, table_type in detected_pages:
        # Check if this table was extracted
        found = any(
            p == page_num and (t == table_type or t in table_type or table_type in t)
            for p, t in extracted_pages
        )
        if not found:
            issues.append(ValidationIssue(
                issue_type="incomplete_table",
                severity="warning",
                description=(
                    f"Table '{table_type}' detected on page {page_num} "
                    f"but not successfully extracted."
                ),
                category="Financial Statements",
                page=page_num,
            ))


def _check_confidence_thresholds(
    taxonomy_mappings: list[dict[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    """Flag mappings with confidence below the threshold."""
    low_confidence_count = 0
    for m in taxonomy_mappings:
        confidence = m.get("confidence", 0.0)
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            low_confidence_count += 1

    if low_confidence_count > 0:
        issues.append(ValidationIssue(
            issue_type="low_confidence",
            severity="info",
            description=(
                f"{low_confidence_count} taxonomy mapping(s) have confidence "
                f"below {MIN_CONFIDENCE_THRESHOLD} threshold."
            ),
        ))


# ===================================================================
# Quality Report (Phase 4)
# ===================================================================

def compute_quality_report(
    master_sections: list[dict[str, Any]],
    taxonomy_mappings: list[dict[str, Any]],
    detected_tables: list[dict[str, Any]],
    vlm_targets: list[dict[str, Any]],
    completeness_report: CompletenessReport,
    total_pages: int = 0,
    progress_callback=None,
) -> QualityReport:
    """Compute a composite quality report with a 0-10 overall score.

    The overall score is a weighted average of five component scores:

    +--------------------------------------+--------+---------------------------+
    | Component                            | Weight | Ideal                     |
    +======================================+========+===========================+
    | Section consolidation ratio          | 0.25   | ≤ 0.25 (335→80)           |
    | TOC coverage                         | 0.20   | ≥ 60% of sections TOC-anc |
    | Taxonomy coverage                    | 0.20   | ≥ 90% of pages classified |
    | Table false-positive estimate        | 0.15   | ≤ 10% FP rate             |
    | VLM target coverage                  | 0.20   | HIGH targets extracted    |
    +--------------------------------------+--------+---------------------------+

    Parameters
    ----------
    master_sections : list[dict]
        Consolidated sections from the section consolidator.
    taxonomy_mappings : list[dict]
        Per-page taxonomy mappings.
    detected_tables : list[dict]
        Detected tables from table_detector.
    vlm_targets : list[dict]
        VLM target dicts from vlm_targets.generate_vlm_targets().
    completeness_report : CompletenessReport
        The existing completeness report with issues.
    total_pages : int
        Total pages in the document.
    progress_callback : callable, optional
        Progress callback.

    Returns
    -------
    QualityReport
        Quality report with composite score and component breakdown.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[QualityReport] Computing extraction quality metrics...")

    # ── 1. Section Consolidation Ratio ──
    n_sections = len(master_sections)
    n_mappings = len(taxonomy_mappings)
    consolidation_ratio = n_sections / max(n_mappings, 1)

    # Score: ratio ≤ 0.25 → 10, ratio ≥ 1.0 → 0
    # Linear interpolation between 0.25 and 1.0
    if consolidation_ratio <= 0.25:
        consolidation_score = 10.0
    elif consolidation_ratio >= 1.0:
        consolidation_score = 0.0
    else:
        consolidation_score = 10.0 * (1.0 - (consolidation_ratio - 0.25) / 0.75)

    # ── 2. TOC Coverage ──
    toc_sections = sum(1 for s in master_sections if s.get("source") == "toc")
    toc_coverage_pct = (toc_sections / max(n_sections, 1)) * 100

    # Score: ≥ 60% → 10, 0% → 0
    if toc_coverage_pct >= 60.0:
        toc_score = 10.0
    else:
        toc_score = (toc_coverage_pct / 60.0) * 10.0

    # ── 3. Taxonomy Coverage ──
    pages_classified = completeness_report.pages_classified
    taxonomy_coverage_pct = (pages_classified / max(total_pages, 1)) * 100

    # Score: ≥ 90% → 10, 0% → 0
    if taxonomy_coverage_pct >= 90.0:
        taxonomy_score = 10.0
    elif taxonomy_coverage_pct >= 50.0:
        taxonomy_score = 5.0 + (taxonomy_coverage_pct - 50.0) / 40.0 * 5.0
    else:
        taxonomy_score = (taxonomy_coverage_pct / 50.0) * 5.0

    # ── 4. Table False Positive Estimate ──
    # Heuristic: tables detected on pages that don't belong to a "Financial Statements"
    # or "Notes to Accounts" section are likely false positives
    financial_page_ranges: list[tuple[int, int]] = []
    for section in master_sections:
        if section.get("category") in (
            "Financial Statements", "Notes to Accounts",
            "Shareholding Information", "Related Party Transactions",
        ) or section.get("section_type") in (
            "Financial Statements", "Notes to Accounts",
            "Shareholding Information", "Related Party Transactions",
        ):
            financial_page_ranges.append(
                (section.get("start_page", 0), section.get("end_page", 0))
            )

    fp_count = 0
    for t in detected_tables:
        pg = t.get("page_no", 0)
        # Check if this table's page falls within a financial section
        in_financial_section = any(
            start <= pg <= end for start, end in financial_page_ranges
        )
        if not in_financial_section:
            fp_count += 1

    table_fp_rate = fp_count / max(len(detected_tables), 1)

    # Score: ≤ 10% → 10, ≥ 50% → 0
    if table_fp_rate <= 0.10:
        fp_score = 10.0
    elif table_fp_rate >= 0.50:
        fp_score = 0.0
    else:
        fp_score = 10.0 * (1.0 - (table_fp_rate - 0.10) / 0.40)

    # ── 5. VLM Target Coverage ──
    high_priority = sum(1 for t in vlm_targets if t.get("priority") == "high")
    medium_priority = sum(1 for t in vlm_targets if t.get("priority") == "medium")

    # Score: having HIGH targets means the system correctly identified
    # critical extraction points. More HIGH targets (up to a point) = better.
    # Ideal: 4-8 HIGH targets (BS, P&L, CF × standalone + consolidated)
    if high_priority >= 4:
        vlm_score = 10.0
    elif high_priority >= 2:
        vlm_score = 7.0
    elif high_priority >= 1:
        vlm_score = 4.0
    else:
        vlm_score = 1.0

    # ── Composite Score ──
    overall_score = (
        consolidation_score * 0.25
        + toc_score * 0.20
        + taxonomy_score * 0.20
        + fp_score * 0.15
        + vlm_score * 0.20
    )

    # Collect issues from completeness report
    issues = completeness_report.issues

    report = QualityReport(
        section_consolidation_ratio=round(consolidation_ratio, 3),
        toc_coverage_pct=round(toc_coverage_pct, 1),
        taxonomy_coverage_pct=round(taxonomy_coverage_pct, 1),
        table_false_positive_rate=round(table_fp_rate, 3),
        vlm_target_count=len(vlm_targets),
        high_priority_vlm_targets=high_priority,
        medium_priority_vlm_targets=medium_priority,
        issues=issues,
        overall_score=round(overall_score, 1),
    )

    _log(f"[QualityReport] Overall score: {overall_score:.1f}/10 "
         f"(consolidation={consolidation_score:.1f}, toc={toc_score:.1f}, "
         f"taxonomy={taxonomy_score:.1f}, fp={fp_score:.1f}, vlm={vlm_score:.1f})")

    return report
