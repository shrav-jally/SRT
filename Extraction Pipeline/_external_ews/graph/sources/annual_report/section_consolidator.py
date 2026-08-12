"""Section Consolidator — Generates the Section Registry from TOC and Headings.

This module builds the definitive Section Registry by establishing section boundaries
using high-confidence signals: Table of Contents (TOC) and explicit page headings.
It runs BEFORE taxonomy mapping to prevent fragmentation caused by stray keywords
in the body text.

Passes:
  1. TOC-Driven Anchors: Parse TOC to create `confirmed` sections.
  2. Heading-Driven Anchors: Scan pages for major headings to create `confirmed` sections.
  3. Gap Fill: Create unclassified blocks for remaining pages.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ===================================================================
# Data structures
# ===================================================================

@dataclass
class ConsolidatedSection:
    """A consolidated document section spanning one or more pages."""
    section_id: str
    raw_section_name: str
    normalized_section_name: str = ""
    section_type: str = ""
    section_subtype: str = ""
    category: str = ""
    subcategory: str = ""
    start_page: int = 0
    end_page: int = 0
    content_type: str = "text"
    extraction_strategy: str = "pdf_text"
    confidence: float = 0.0
    section_status: str = "confirmed"
    boundary_source: str = "toc"
    source: str = "taxonomy"
    toc_entry: str | None = None
    page_count: int = 0
    zone: str = "narrative"
    zone_confidence: float = 0.0

    def __post_init__(self):
        self.page_count = self.end_page - self.start_page + 1
        if not self.normalized_section_name:
            self.normalized_section_name = self.raw_section_name
            
        # Fix: set source from boundary_source for quality score
        if self.boundary_source:
            self.source = self.boundary_source
            
        # Fix: VLM targets get LOW priority if content_type isn't "table"
        if self.category == "Financial Statements" or self.section_type == "Financial Statements":
            self.content_type = "table"


# ===================================================================
# TOC & Heading Patterns mapping to Taxonomy
# ===================================================================

_BOUNDARY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # ── Company Information ──
    (re.compile(r"\bcompany\s+(?:profile|overview|information)\b", re.I), "Company Information", "Company Profile"),
    (re.compile(r"\bbusiness\s+overview\b", re.I), "Company Information", "Business Overview"),
    (re.compile(r"\bproducts?\s+(?:and|&)\s+services?\b", re.I), "Company Information", "Products & Services"),
    (re.compile(r"\b(?:subsidiaries|group\s+structure)\b", re.I), "Company Information", "Subsidiaries & Group Structure"),

    # ── Management & Governance ──
    (re.compile(r"\bboard\s+of\s+directors\b", re.I), "Management & Governance", "Board of Directors"),
    (re.compile(r"\bkey\s+manage(?:ment|rial)\s+personnel\b", re.I), "Management & Governance", "Key Management Personnel"),
    (re.compile(r"\bcorporate\s+governance\b", re.I), "Management & Governance", "Corporate Governance"),
    (re.compile(r"\bboard\s+committees?\b", re.I), "Management & Governance", "Board Committees"),

    # ── Shareholding Information ──
    (re.compile(r"\bshare\s+capital\b", re.I), "Shareholding Information", "Share Capital"),
    (re.compile(r"\bshareholding\s+pattern\b", re.I), "Shareholding Information", "Shareholding Pattern"),
    (re.compile(r"\b(?:major|top)\s+shareholders?\b", re.I), "Shareholding Information", "Major Shareholders"),
    (re.compile(r"\bdividend\s+(?:information|history|recommendation)\b", re.I), "Shareholding Information", "Dividend Information"),

    # ── Management Discussion & Analysis ──
    (re.compile(r"\bmanagement\s+discussion\s+(?:and|&)\s+analysis\b|\bmd\s*&\s*a\b", re.I), "Management Discussion & Analysis", "Business Review"),
    (re.compile(r"\bindustry\s+overview\b", re.I), "Management Discussion & Analysis", "Industry Overview"),
    (re.compile(r"\bbusiness\s+(?:review|performance)\b", re.I), "Management Discussion & Analysis", "Business Review"),
    (re.compile(r"\bopportunit(?:y|ies)\s+(?:and|&)\s+challenges?\b", re.I), "Management Discussion & Analysis", "Opportunities & Challenges"),
    (re.compile(r"\bfuture\s+outlook\b", re.I), "Management Discussion & Analysis", "Future Outlook"),

    # ── Financial Statements ──
    (re.compile(r"\bbalance\s+sheet\b", re.I), "Financial Statements", "Balance Sheet"),
    (re.compile(r"\b(?:statement\s+of\s+)?profit\s+(?:and|&)\s+loss\b", re.I), "Financial Statements", "Profit & Loss Statement"),
    (re.compile(r"\bcash\s+flow\s+statement\b", re.I), "Financial Statements", "Cash Flow Statement"),
    (re.compile(r"\bstatement\s+of\s+changes?\s+in\s+equity\b", re.I), "Financial Statements", "Statement of Changes in Equity"),
    (re.compile(r"\bfinancial\s+statements?\b", re.I), "Financial Statements", "Balance Sheet"),

    # ── Notes to Accounts ──
    (re.compile(r"\bnotes?\s+(?:to|forming\s+part\s+of)\s+(?:the\s+)?(?:financial\s+statements?|accounts)\b", re.I), "Notes to Accounts", "Accounting Policies"),
    (re.compile(r"\bsignificant\s+accounting\s+polic", re.I), "Notes to Accounts", "Accounting Policies"),
    (re.compile(r"\brelated\s+party\s+(?:transaction|disclosure)s?\b", re.I), "Notes to Accounts", "Related Party Transactions"),
    (re.compile(r"\bcontingent\s+liabilit(?:y|ies)\b", re.I), "Notes to Accounts", "Contingent Liabilities"),
    (re.compile(r"\bsegment\s+(?:information|reporting)\b", re.I), "Notes to Accounts", "Segment Information"),

    # ── Financial Analysis ──
    (re.compile(r"\bfinancial\s+ratios?\b", re.I), "Financial Analysis", "Financial Ratios"),
    (re.compile(r"\bworking\s+capital\s+(?:analysis|changes)\b", re.I), "Financial Analysis", "Working Capital Analysis"),
    (re.compile(r"\bdebt\s+analysis\b", re.I), "Financial Analysis", "Debt Analysis"),
    (re.compile(r"\bten\s+year\s+summary\b", re.I), "Financial Analysis", "Financial Ratios"),

    # ── Business Performance ──
    (re.compile(r"\brevenue\s+(?:and|&)?\s+sales\s+performance\b", re.I), "Business Performance", "Revenue & Sales Performance"),
    (re.compile(r"\bsegment\s+performance\b", re.I), "Business Performance", "Segment Performance"),
    (re.compile(r"\boperational\s+performance\b", re.I), "Business Performance", "Operational Performance"),
    (re.compile(r"\bkey\s+performance\s+indicators?\b|\bkpi\b", re.I), "Business Performance", "Key Performance Indicators (KPIs)"),

    # ── Risk Management ──
    (re.compile(r"\bbusiness\s+risks?\b", re.I), "Risk Management", "Business Risks"),
    (re.compile(r"\bfinancial\s+risks?\b", re.I), "Risk Management", "Financial Risks"),
    (re.compile(r"\boperational\s+risks?\b", re.I), "Risk Management", "Operational Risks"),
    (re.compile(r"\bregulatory\s+risks?\b", re.I), "Risk Management", "Regulatory Risks"),
    (re.compile(r"\brisk\s+management\b", re.I), "Risk Management", "Business Risks"),

    # ── Human Resources ──
    (re.compile(r"\bworkforce\s+information\b", re.I), "Human Resources", "Workforce Information"),
    (re.compile(r"\btraining\s+(?:and|&)\s+development\b", re.I), "Human Resources", "Training & Development"),
    (re.compile(r"\bemployee\s+welfare\b", re.I), "Human Resources", "Employee Welfare"),
    (re.compile(r"\bdiversity\s+(?:and|&)\s+inclusion\b", re.I), "Human Resources", "Diversity & Inclusion"),

    # ── ESG & Sustainability ──
    (re.compile(r"\benvironmental\b", re.I), "ESG & Sustainability", "Environmental"),
    (re.compile(r"\bsocial\b", re.I), "ESG & Sustainability", "Social"),
    (re.compile(r"\bgovernance\b", re.I), "ESG & Sustainability", "Governance"),
    (re.compile(r"\bsustainability\s+initiatives?\b|\bsustainability\s+report\b", re.I), "ESG & Sustainability", "Sustainability Initiatives"),
    (re.compile(r"\bbusiness\s+responsibility\s+(?:and\s+sustainability\s+)?report\b|\bbrsr\b", re.I), "ESG & Sustainability", "Sustainability Initiatives"),

    # ── CSR ──
    (re.compile(r"\bcsr\s+spending\b", re.I), "CSR", "CSR Spending"),
    (re.compile(r"\bcsr\s+projects?\b", re.I), "CSR", "CSR Projects"),
    (re.compile(r"\bcommunity\s+development\b", re.I), "CSR", "Community Development"),
    (re.compile(r"\bcorporate\s+social\s+responsibility\b", re.I), "CSR", "CSR Projects"),

    # ── Legal & Compliance ──
    (re.compile(r"\blitigations?\b", re.I), "Legal & Compliance", "Litigations"),
    (re.compile(r"\bregulatory\s+compliance\b", re.I), "Legal & Compliance", "Regulatory Compliance"),
    (re.compile(r"\bstatutory\s+compliance\b", re.I), "Legal & Compliance", "Statutory Compliance"),

    # ── Strategic Initiatives ──
    (re.compile(r"\bgrowth\s+strategy\b", re.I), "Strategic Initiatives", "Growth Strategy"),
    (re.compile(r"\bexpansion\s+plans?\b", re.I), "Strategic Initiatives", "Expansion Plans"),
    (re.compile(r"\bmergers?\s+(?:and|&)\s+acquisitions?\b", re.I), "Strategic Initiatives", "Mergers & Acquisitions"),
    (re.compile(r"\bdigital\s+transformation\b", re.I), "Strategic Initiatives", "Digital Transformation"),

    # ── Investor Information ──
    (re.compile(r"\bshare\s+price\s+performance\b", re.I), "Investor Information", "Share Price Performance"),
    (re.compile(r"\bmarket\s+capitalization\b", re.I), "Investor Information", "Market Capitalization"),
    (re.compile(r"\bshareholder\s+information\b", re.I), "Investor Information", "Shareholder Information"),
    (re.compile(r"\binvestor\s+relations\b", re.I), "Investor Information", "Investor Relations"),
    (re.compile(r"\bannual\s+general\s+meeting\b|\bagm\b", re.I), "Investor Information", "Investor Relations"),

    # ── Audit Information ──
    (re.compile(r"\bauditor'?s?\s+report\b", re.I), "Audit Information", "Auditor's Report"),
    (re.compile(r"\bkey\s+audit\s+matters?\b", re.I), "Audit Information", "Key Audit Matters"),
    (re.compile(r"\binternal\s+controls?\b", re.I), "Audit Information", "Internal Controls"),

    # ── Outlook & Guidance ──
    (re.compile(r"\bmanagement\s+guidance\b", re.I), "Outlook & Guidance", "Management Guidance"),
    (re.compile(r"\bgrowth\s+targets?\b", re.I), "Outlook & Guidance", "Growth Targets"),
    (re.compile(r"\bfuture\s+plans?\b", re.I), "Outlook & Guidance", "Future Plans"),
]

def _make_section_id(category: str, subcategory: str) -> str:
    safe_cat = re.sub(r"[^a-zA-Z0-9]+", "_", category.lower()).strip("_")
    safe_sub = re.sub(r"[^a-zA-Z0-9]+", "_", subcategory.lower()).strip("_")
    short_uuid = str(uuid.uuid4())[:8]
    return f"sec_{safe_cat}_{safe_sub}_{short_uuid}"


def _map_boundary_description(description: str) -> tuple[str, str]:
    """Map a TOC description or Heading to a (section_type, section_subtype) tuple."""
    for pattern, cat, sub in _BOUNDARY_PATTERNS:
        if pattern.search(description):
            return cat, sub
    return "", ""


# ===================================================================
# Main consolidation function (Section Registry First)
# ===================================================================

def build_section_registry(
    toc_hints: Any | None = None,
    all_pages: list[dict[str, Any]] | None = None,
    total_pages: int = 0,
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Build the definitive Section Registry from TOC and Headings.

    Replaces consolidate_sections. Runs BEFORE taxonomy classification.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    all_pages = all_pages or []
    if not total_pages and all_pages:
        total_pages = max(p.get("page_number", 0) for p in all_pages)

    _log(f"[Consolidator] Building Section Registry for {total_pages} pages")

    anchors: list[ConsolidatedSection] = []

    # ── Pass 1: TOC-Driven Anchors ──────────────────────────────────
    if toc_hints and hasattr(toc_hints, "raw_entries"):
        page_offset = getattr(toc_hints, "page_offset", None) or 0
        for entry in toc_hints.raw_entries:
            desc = getattr(entry, "description", "")
            printed_page = getattr(entry, "page_number", 0)
            if not desc or printed_page <= 0:
                continue

            pdf_page = printed_page + page_offset
            if pdf_page > total_pages or pdf_page < 1:
                continue

            sec_type, sec_subtype = _map_boundary_description(desc)
            if not sec_type:
                sec_type, sec_subtype = "Unclassified", desc

            # Avoid duplicates on same page
            if not any(a.start_page == pdf_page for a in anchors):
                anchors.append(ConsolidatedSection(
                    section_id=_make_section_id(sec_type, sec_subtype),
                    raw_section_name=desc,
                    section_type=sec_type,
                    section_subtype=sec_subtype,
                    category=sec_type,
                    subcategory=sec_subtype,
                    start_page=pdf_page,
                    confidence=0.90,
                    section_status="confirmed",
                    boundary_source="toc",
                    toc_entry=desc,
                ))
        _log(f"[Consolidator] Pass 1: Found {len(anchors)} TOC anchors")

    # ── Pass 2: Heading-Driven Anchors ──────────────────────────────
    toc_pages = {a.start_page for a in anchors}
    heading_anchors = 0
    for page in all_pages:
        pg_num = page["page_number"]
        if pg_num in toc_pages:
            continue
            
        heading = page.get("detected_heading", "").strip()
        if heading and len(heading) > 4:
            sec_type, sec_subtype = _map_boundary_description(heading)
            if sec_type:
                anchors.append(ConsolidatedSection(
                    section_id=_make_section_id(sec_type, sec_subtype),
                    raw_section_name=heading,
                    section_type=sec_type,
                    section_subtype=sec_subtype,
                    category=sec_type,
                    subcategory=sec_subtype,
                    start_page=pg_num,
                    confidence=0.85,
                    section_status="confirmed",
                    boundary_source="heading",
                ))
                heading_anchors += 1
                
    _log(f"[Consolidator] Pass 2: Found {heading_anchors} heading anchors")

    # Sort anchors by start_page
    anchors.sort(key=lambda a: a.start_page)

    # Find zone boundaries
    financial_start_page = next((a.start_page for a in anchors if a.section_type == "Financial Statements"), total_pages + 1)
    
    # ── Pass 3: Resolve Boundaries and Fill Gaps ────────────────────
    final_sections: list[ConsolidatedSection] = []
    
    # If document starts before first anchor, create a gap block
    if anchors and anchors[0].start_page > 1:
        final_sections.append(ConsolidatedSection(
            section_id=_make_section_id("Unclassified", "Opening Pages"),
            raw_section_name="Opening Pages",
            start_page=1,
            end_page=anchors[0].start_page - 1,
            confidence=0.5,
            section_status="inferred",
            boundary_source="classifier",
        ))

    for i, anchor in enumerate(anchors):
        if i < len(anchors) - 1:
            next_anchor = anchors[i + 1]
            anchor.end_page = next_anchor.start_page - 1
        else:
            anchor.end_page = total_pages
            
        anchor.page_count = anchor.end_page - anchor.start_page + 1
        
        # Only append if valid
        if anchor.end_page >= anchor.start_page:
            final_sections.append(anchor)

    # If no anchors found at all, create one giant block
    if not final_sections and total_pages > 0:
        final_sections.append(ConsolidatedSection(
            section_id=_make_section_id("Unclassified", "Full Document"),
            raw_section_name="Full Document",
            start_page=1,
            end_page=total_pages,
            confidence=0.5,
            section_status="inferred",
            boundary_source="classifier",
        ))

    # Apply zones
    current_zone = "narrative"
    current_zone_conf = 0.5
    for s in final_sections:
        if s.start_page >= financial_start_page:
            current_zone = "financial"
            current_zone_conf = 1.0
        elif s.section_type in ("Management & Governance", "Audit Information", "Legal & Compliance"):
            current_zone = "governance"
            current_zone_conf = 0.85
        
        s.zone = current_zone
        s.zone_confidence = current_zone_conf

    # Convert to dict for downstream compatibility
    result = []
    for s in final_sections:
        result.append({
            "section_id": s.section_id,
            "raw_section_name": s.raw_section_name,
            "normalized_section_name": s.normalized_section_name,
            "section_type": s.section_type,
            "section_subtype": s.section_subtype,
            "category": s.category,
            "subcategory": s.subcategory,
            "start_page": s.start_page,
            "end_page": s.end_page,
            "content_type": s.content_type,
            "extraction_strategy": s.extraction_strategy,
            "confidence": s.confidence,
            "section_status": s.section_status,
            "boundary_source": s.boundary_source,
            "source": s.source,
            "toc_entry": s.toc_entry,
            "page_count": s.page_count,
            "zone": s.zone,
            "zone_confidence": s.zone_confidence,
        })

    _log(f"[Consolidator] Final: {len(result)} sections in Section Registry")
    return result

def build_section_hierarchy(sections: list[dict[str, Any]], progress_callback=None) -> dict[str, Any]:
    """Build a nested hierarchy of sections for the canonical output."""
    hierarchy = {}
    total_cats = set()
    total_secs = 0

    for section in sections:
        cat = section.get("section_type") or section.get("category", "Unclassified")
        if cat not in hierarchy:
            hierarchy[cat] = []
            total_cats.add(cat)
        
        hierarchy[cat].append({
            "section_id": section.get("section_id"),
            "raw_section_name": section.get("raw_section_name"),
            "normalized_section_name": section.get("normalized_section_name"),
            "section_subtype": section.get("section_subtype") or section.get("subcategory"),
            "start_page": section.get("start_page"),
            "end_page": section.get("end_page"),
            "section_status": section.get("section_status"),
            "boundary_source": section.get("boundary_source"),
            "zone": section.get("zone"),
        })
        total_secs += 1

    return {
        "total_categories": len(total_cats),
        "total_sections": total_secs,
        "hierarchy": hierarchy,
    }
