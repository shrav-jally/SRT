"""Content Extractor — Subcategory-level extraction with regex pre-extractors,
evidence tracking, canonical schemas, and entity registry.

Architecture:
  1. Regex pre-extractors run first (high confidence, deterministic)
  2. LLM fallback if regex fails or returns insufficient results
  3. All results wrapped in EvidenceBackedResult with full evidence chain
  4. Canonical Pydantic schemas validate entity structure
  5. ENTITY_REGISTRY centralizes type management
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel

from .llm_utils import llm_call_with_retry
from .rag_chunker import get_relevant_chunks

logger = logging.getLogger(__name__)


# =====================================================================
# Evidence Tracking (GAP 0C)
# =====================================================================

@dataclass
class ExtractionEvidence:
    """Evidence trail for an extracted value."""
    source_page: int | None = None
    source_section: str = ""
    source_text_snippet: str = ""   # Context around the match (±50 chars)
    extraction_method: str = ""     # "regex_din", "regex_name", "llm", "heuristic"
    confidence: float = 0.0


@dataclass
class EvidenceBackedResult:
    """An extraction result with full evidence chain.

    Attributes
    ----------
    value : Any
        The extracted data — typically a dict or list.
    evidence : ExtractionEvidence
        Provenance metadata for debugging and confidence scoring.
    """
    value: Any = None
    evidence: ExtractionEvidence = field(default_factory=ExtractionEvidence)


def _capture_evidence_snippet(text: str, match: re.Match, context_chars: int = 50) -> str:
    """Capture text surrounding a regex match for evidence.

    Takes *context_chars* characters before and after the match to
    provide meaningful context for debugging.
    """
    start = max(match.start() - context_chars, 0)
    end = min(match.end() + context_chars, len(text))
    return text[start:end]


# =====================================================================
# Canonical Entity Schemas (GAP 0D)
# =====================================================================

class BoardMember(BaseModel):
    """Canonical schema for a board director."""
    name: Optional[str] = None
    designation: Optional[str] = None
    type: Optional[str] = None           # "Executive", "Non-Executive", "Independent"
    din: Optional[str] = None            # Director Identification Number
    appointment_date: Optional[str] = None
    source_page: int | None = None


class KMPEntry(BaseModel):
    """Canonical schema for a Key Management Personnel entry."""
    name: Optional[str] = None
    designation: Optional[str] = None
    din: Optional[str] = None
    source_page: int | None = None


class CommitteeEntry(BaseModel):
    """Canonical schema for a board committee."""
    name: Optional[str] = None
    chairperson: Optional[str] = None
    members_count: int | None = None
    meetings_held: int | None = None


class SubsidiaryEntry(BaseModel):
    """Canonical schema for a subsidiary / associate / JV."""
    name: Optional[str] = None
    country: Optional[str] = None
    ownership_pct: float | None = None
    entity_type: Optional[str] = None    # "Subsidiary", "Associate", "Joint Venture"


class DividendEntry(BaseModel):
    """Canonical schema for a dividend declaration."""
    dividend_per_share: Optional[str] = None
    dividend_pct: Optional[str] = None
    fiscal_year: Optional[str] = None
    declaration_date: Optional[str] = None


class AuditorEntry(BaseModel):
    """Canonical schema for auditor information."""
    auditor_name: Optional[str] = None
    auditor_opinion: Optional[str] = None
    key_audit_matters: list[str] = []
    emphasis_of_matter: Optional[str] = None


# =====================================================================
# Entity Registry (GAP 0I)
# =====================================================================

ENTITY_REGISTRY: dict[str, type[BaseModel]] = {
    "board_members": BoardMember,
    "kmp": KMPEntry,
    "committees": CommitteeEntry,
    "subsidiaries": SubsidiaryEntry,
    "dividend": DividendEntry,
    "auditor": AuditorEntry,
}


def validate_entity_list(entity_type: str, raw_items: list[dict]) -> list[dict]:
    """Validate a list of entity dicts against the canonical schema.

    Uses :data:`ENTITY_REGISTRY` to find the right model.
    Logs validation failures but **never drops data** — on failure
    the original dict is kept unchanged.
    """
    model_class = ENTITY_REGISTRY.get(entity_type)
    if not model_class:
        return raw_items

    validated = []
    for item in raw_items:
        try:
            validated.append(model_class(**item).model_dump())
        except Exception as exc:
            logger.warning(f"{entity_type} schema validation failed for {item}: {exc}")
            validated.append(item)

    return validated


# =====================================================================
# LLM Helper
# =====================================================================

def _extract_json_from_llm(llm: Any, prompt: str, max_retries: int = 2) -> dict | list | None:
    """Helper to extract JSON from the LLM response."""
    if not llm:
        logger.warning("[ContentExtractor] No LLM provided for extraction.")
        return None

    try:
        response_text = llm_call_with_retry(llm, prompt, max_retries=max_retries)
        if not response_text:
            return None

        # Try to find a JSON block in the response
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        json_str = match.group(1) if match else response_text

        # Clean up in case there are stray characters
        json_str = json_str.strip()
        if not json_str:
            return None

        return json.loads(json_str)
    except Exception as exc:
        logger.error(f"[ContentExtractor] LLM JSON extraction failed: {exc}")
        return None


# =====================================================================
# Regex Pre-Extractors (GAP 0A)
# =====================================================================

def _pre_extract_board_members(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Attempt regex-based extraction of board members before LLM fallback.

    Common patterns in Indian annual reports:
    - Tabular: ``DIN: 0XXXXXXX | Name | Designation | Category``
    - List: ``Shri/Smt/Ms Name, Designation (Category)``
    """
    members: list[dict] = []
    representative_snippet = ""
    method = "regex_name"

    # Pattern 1: DIN-based extraction (very high confidence)
    din_pattern = re.compile(
        r'(?:DIN[:\s]*)?(\d{8})\s*[|,\t]\s*'
        r'([A-Z][A-Za-z\s\.]+?)\s*[|,\t]\s*'
        r'([A-Za-z\s\.\-&]+?)\s*[|,\t]\s*'
        r'(Executive|Non-?Executive|Independent|Nominee|Alternate)',
        re.I,
    )
    for match in din_pattern.finditer(text):
        members.append({
            "din": match.group(1),
            "name": match.group(2).strip(),
            "designation": match.group(3).strip(),
            "type": match.group(4).strip(),
            "extraction_method": "regex_din",
        })
        if not representative_snippet:
            representative_snippet = _capture_evidence_snippet(text, match)

    if members:
        method = "regex_din"
    else:
        # Pattern 2: Shri/Smt prefix
        name_pattern = re.compile(
            r'(?:Shri|Smt|Ms|Mr|Dr)\.?\s+([A-Z][A-Za-z\s\.]+?)(?:,|\s{2,})\s*'
            r'([A-Za-z\s\.\-&]+?)(?:\s*\((Independent|Non-?Executive|Executive|Nominee)\))?',
            re.I,
        )
        for match in name_pattern.finditer(text):
            name = match.group(1).strip()
            if len(name) > 2 and not any(m["name"] == name for m in members):
                members.append({
                    "name": name,
                    "designation": match.group(2).strip(),
                    "type": match.group(3).strip() if match.group(3) else "Not Specified",
                    "extraction_method": "regex_name",
                })
                if not representative_snippet:
                    representative_snippet = _capture_evidence_snippet(text, match)

    if not members:
        return None

    # Validate against canonical schema
    validated = validate_entity_list("board_members", members)

    return EvidenceBackedResult(
        value=validated,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=representative_snippet,
            extraction_method=method,
            confidence=0.95 if method == "regex_din" else 0.90,
        ),
    )


def _pre_extract_kmp(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Regex-based KMP extraction."""
    kmp_list: list[dict] = []
    representative_snippet = ""

    kmp_pattern = re.compile(
        r'(?:Shri|Smt|Ms|Mr|Dr)\.?\s+([A-Z][A-Za-z\s\.]+?)(?:,|\s*[-–]\s*)'
        r'(Chief[\s-]?Financial\s+Officer|Company\s+Secretary|'
        r'Managing\s+Director|CEO|CFO|CS|Whole[\s-]time\s+Director)',
        re.I,
    )
    for match in kmp_pattern.finditer(text):
        kmp_list.append({
            "name": match.group(1).strip(),
            "designation": match.group(2).strip(),
            "extraction_method": "regex_kmp",
        })
        if not representative_snippet:
            representative_snippet = _capture_evidence_snippet(text, match)

    if not kmp_list:
        return None

    validated = validate_entity_list("kmp", kmp_list)

    return EvidenceBackedResult(
        value=validated,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=representative_snippet,
            extraction_method="regex_kmp",
            confidence=0.90,
        ),
    )


def _pre_extract_committees(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Regex-based committee name extraction."""
    committees: list[str] = []
    representative_snippet = ""

    committee_pattern = re.compile(
        r'(Audit\s+Committee|Nomination\s+and\s+Remuneration\s+Committee|'
        r'NRC|Stakeholders?\s*(?:Relationship\s+)?Committee|CSR\s+Committee|'
        r'Risk\s+Management\s+Committee|Vigilance\s+Committee|'
        r'Share\s+Transfer\s+Committee|Investor\s+Grievance\s+Committee)',
        re.I,
    )
    for match in committee_pattern.finditer(text):
        name = match.group(0).strip().title()
        if name not in committees:
            committees.append(name)
        if not representative_snippet:
            representative_snippet = _capture_evidence_snippet(text, match)

    if not committees:
        return None

    # Validate as committee entries
    committee_dicts = [{"name": c} for c in committees]
    validated = validate_entity_list("committees", committee_dicts)
    # Extract just the names back for backward compatibility
    validated_names = [c.get("name", c) if isinstance(c, dict) else c for c in validated]

    return EvidenceBackedResult(
        value=validated_names,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=representative_snippet,
            extraction_method="regex_committee",
            confidence=0.90,
        ),
    )


def _pre_extract_subsidiaries(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Regex-based subsidiary extraction from annexure tables."""
    subsidiaries: list[str] = []
    representative_snippet = ""

    # Pattern 1: numbered list with company names ending in Ltd/Limited/Pte etc.
    sub_pattern = re.compile(
        r'(?:Sl\.?\s*No\.?|S\.?\s*No\.?)\s*\d+[\s.|,)\-]+'
        r'([A-Z][A-Za-z\s\.&\-]+(?:Ltd|Limited|Pte|LLC|Inc|GmbH|SA|AG))',
        re.I,
    )
    for match in sub_pattern.finditer(text):
        name = match.group(1).strip()
        if len(name) > 5 and name not in subsidiaries:
            subsidiaries.append(name)
        if not representative_snippet:
            representative_snippet = _capture_evidence_snippet(text, match)

    # Pattern 2: company names in "Subsidiary/Associate/JV" context
    if not subsidiaries:
        context_pattern = re.compile(
            r'([A-Z][A-Za-z\s\.&\-]+(?:Ltd|Limited|Pte|LLC|Inc|GmbH|SA|AG))'
            r'\s*[-–]\s*(?:Subsidiary|Associate|Joint\s+Venture|Wholly\s+owned)',
            re.I,
        )
        for match in context_pattern.finditer(text):
            name = match.group(1).strip()
            if len(name) > 5 and name not in subsidiaries:
                subsidiaries.append(name)
            if not representative_snippet:
                representative_snippet = _capture_evidence_snippet(text, match)

    if not subsidiaries:
        # Check for explicit "no subsidiaries" statement
        no_sub_pattern = re.compile(
            r'(?:the\s+company\s+does\s+not\s+have\s+any\s+subsidiar|'
            r'no\s+subsidiar|'
            r'company\s+has\s+no\s+subsidiar)',
            re.I,
        )
        if no_sub_pattern.search(text):
            return EvidenceBackedResult(
                value={"subsidiaries": [], "no_subsidiaries_statement": True},
                evidence=ExtractionEvidence(
                    source_page=source_page,
                    source_section=source_section,
                    source_text_snippet="Company has no subsidiaries as disclosed",
                    extraction_method="regex_no_subsidiary",
                    confidence=0.95,
                ),
            )
        return None

    # Validate against canonical schema
    sub_dicts = [{"name": s, "entity_type": "Subsidiary"} for s in subsidiaries]
    validated = validate_entity_list("subsidiaries", sub_dicts)
    validated_names = [s.get("name", s) if isinstance(s, dict) else s for s in validated]

    return EvidenceBackedResult(
        value={"subsidiaries": validated_names},
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=representative_snippet,
            extraction_method="regex_subsidiary",
            confidence=0.85,
        ),
    )


def _pre_extract_dividend(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Regex-based dividend extraction — prioritized over LLM."""
    # Pattern 1: "Dividend of Rs. X.XX per share"
    div_pattern = re.compile(
        r'dividend\s+(?:of\s+)?(?:Rs\.?|INR)\s*([\d,]+\.?\d*)\s*'
        r'(?:per\s+equity\s+share|per\s+share|/-)',
        re.I,
    )
    match = div_pattern.search(text)
    if match:
        snippet = _capture_evidence_snippet(text, match)
        return EvidenceBackedResult(
            value={"dividend_declared": match.group(1)},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=snippet,
                extraction_method="regex_dividend",
                confidence=0.85,
            ),
        )

    # Pattern 2: "X% dividend"
    pct_pattern = re.compile(r'(\d+)%\s*dividend', re.I)
    match = pct_pattern.search(text)
    if match:
        snippet = _capture_evidence_snippet(text, match)
        return EvidenceBackedResult(
            value={"dividend_declared": f"{match.group(1)}%"},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=snippet,
                extraction_method="regex_dividend",
                confidence=0.85,
            ),
        )

    # Pattern 3: "Recommended a dividend of Rs./- X"
    rec_pattern = re.compile(
        r'recommend(?:ed|s|ing)?\s+(?:a\s+)?dividend\s+(?:of\s+)?'
        r'(?:Rs\.?|INR)\s*([\d,]+\.?\d*)',
        re.I,
    )
    match = rec_pattern.search(text)
    if match:
        snippet = _capture_evidence_snippet(text, match)
        return EvidenceBackedResult(
            value={"dividend_declared": match.group(1)},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=snippet,
                extraction_method="regex_dividend",
                confidence=0.85,
            ),
        )

    return None


def _pre_extract_auditor(
    text: str,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Regex-based auditor opinion extraction."""
    text_lower = text.lower()
    opinion: str | None = None
    representative_snippet = ""

    if "unqualified" in text_lower or "true and fair" in text_lower:
        opinion = "Unqualified"
    elif "qualified" in text_lower and "except for" in text_lower:
        opinion = "Qualified"
    elif "adverse" in text_lower:
        opinion = "Adverse"
    elif "disclaimer" in text_lower:
        opinion = "Disclaimer"

    # Extract auditor firm name
    auditor_pattern = re.compile(
        r'(?:M/s\.?\s*)?([A-Z][A-Za-z\s\.&]+'
        r'(?:Associates|Partners|Co\.|LLP|Chartered\s+Accountants))',
        re.I,
    )
    match = auditor_pattern.search(text)
    auditor_name = match.group(1).strip() if match else None
    if match:
        representative_snippet = _capture_evidence_snippet(text, match)

    if opinion or auditor_name:
        result: dict[str, Any] = {}
        if opinion:
            result["auditor_opinion"] = opinion
        if auditor_name:
            result["auditor_name"] = auditor_name

        return EvidenceBackedResult(
            value=result,
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=representative_snippet or f"Auditor opinion: {opinion}",
                extraction_method="regex_auditor",
                confidence=0.85,
            ),
        )

    return None


# =====================================================================
# Router
# =====================================================================

def extract_subcategory_content(
    category: str,
    subcategory: str,
    text: str,
    llm: Any = None,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Route to the appropriate subcategory extraction logic.

    Returns an :class:`EvidenceBackedResult` with structured data and
    evidence chain, or ``None`` if no extractor matches.
    """
    # Use RAG/Semantic Chunking to avoid massive token costs while preserving relevance
    truncated_text = get_relevant_chunks(text, subcategory, top_k=5)

    sub_lower = subcategory.lower()

    # Import the exact alias mapping rules to reliably route Unclassified sections
    try:
        from .workbook_population import MAPPING_RULES
    except ImportError:
        MAPPING_RULES = {}

    def _clean_str(s: str) -> str:
        s = s.lower()
        s = re.sub(r'\b(the|and|of|in|to)\b', '', s)
        s = re.sub(r'[^a-z0-9]', '', s)
        return s

    def matches_target(target_name: str) -> bool:
        aliases = MAPPING_RULES.get(target_name, [target_name.lower()])
        clean_sub = _clean_str(subcategory)
        for alias in aliases:
            clean_alias = _clean_str(alias)
            if clean_alias and (clean_alias in clean_sub or clean_sub in clean_alias):
                return True
        return False

    text_head = truncated_text.lower()[:500]

    # Explicit Target Routing (Strict matching first to avoid schema bleeding)
    # Define mapping of canonical targets to their dedicated extractor functions
    TARGET_EXTRACTORS = {
        "Board of Directors": _extract_board_of_directors,
        "Key Management Personnel": _extract_kmp,
        "Board Committees": _extract_committees,
        "Corporate Governance": _extract_corporate_governance,
        "Share Capital": _extract_share_capital,
        "Shareholding Pattern": _extract_shareholding_pattern,
        "Major Shareholders": _extract_shareholding_pattern,
        "Dividend Information": _extract_dividend,
        "Company Profile": _extract_company_profile,
        "Business Overview": _extract_business_overview,
        "Business Review": _extract_business_overview,
        "Products & Services": _extract_products_services,
        "Subsidiaries & Group Structure": _extract_subsidiaries,
        "Industry Overview": _extract_mda,
        "Opportunities & Challenges": _extract_mda,
        "Future Outlook": _extract_mda,
        "Investor Information": _extract_investor_information,
        "Outlook & Guidance": _extract_outlook_guidance,
        "Financial Analysis": _extract_financial_analysis,
        "Business Performance": _extract_business_performance,
        "Risk Management": _extract_risk_management,
        "Legal & Compliance": _extract_legal_compliance,
        "Strategic Initiatives": _extract_strategic_initiatives,
        "ESG & Sustainability": _extract_esg_sustainability,
        "CSR": _extract_csr,
        "Human Resources": _extract_human_resources,
        "Audit Information": _extract_auditor_report,
    }

    # 1. Try Strict Match
    for target_key, extractor_fn in TARGET_EXTRACTORS.items():
        if matches_target(target_key):
            return extractor_fn(truncated_text, llm, source_page, source_section)
    
    # 2. Fallback to broad text heuristics if strict match fails
    if (category == "Management & Governance" and "board" in sub_lower) or "board of directors" in text_head:
        return _extract_board_of_directors(truncated_text, llm, source_page, source_section)
    elif (category == "Management & Governance" and ("kmp" in sub_lower or "personnel" in sub_lower)) or "key management personnel" in text_head:
        return _extract_kmp(truncated_text, llm, source_page, source_section)
    elif (category == "Management & Governance" and "committee" in sub_lower) or "audit committee" in text_head or "remuneration committee" in text_head:
        return _extract_committees(truncated_text, llm, source_page, source_section)
    elif category == "Management & Governance" or "corporate governance" in text_head:
        return _extract_corporate_governance(truncated_text, llm, source_page, source_section)

    elif (category == "Shareholding Information" and "capital" in sub_lower) or "share capital" in text_head:
        return _extract_share_capital(truncated_text, llm, source_page, source_section)
    elif (category == "Shareholding Information" and "pattern" in sub_lower) or "shareholding pattern" in text_head:
        return _extract_shareholding_pattern(truncated_text, llm, source_page, source_section)
    elif (category == "Shareholding Information" and "dividend" in sub_lower) or "dividend" in text_head:
        return _extract_dividend(truncated_text, llm, source_page, source_section)

    elif (category == "Company Information" and "profile" in sub_lower) or "company profile" in text_head or "about the company" in text_head:
        return _extract_company_profile(truncated_text, llm, source_page, source_section)
    elif (category == "Company Information" and "overview" in sub_lower) or "business review" in text_head:
        return _extract_business_overview(truncated_text, llm, source_page, source_section)
    elif (category == "Company Information" and ("product" in sub_lower or "service" in sub_lower)) or "product offering" in text_head:
        return _extract_products_services(truncated_text, llm, source_page, source_section)
    elif (category == "Company Information" and "subsidiari" in sub_lower) or "subsidiaries" in text_head:
        return _extract_subsidiaries(truncated_text, llm, source_page, source_section)

    elif ("management discussion" in sub_lower or "md&a" in sub_lower
          or category == "Management Discussion & Analysis"
          or "management discussion and analysis" in text_head or "md&a" in text_head):
        return _extract_mda(truncated_text, llm, source_page, source_section)

    elif category == "Investor Information" or "investor" in sub_lower:
        return _extract_investor_information(truncated_text, llm, source_page, source_section)
    elif category == "Outlook & Guidance" or "guidance" in sub_lower:
        return _extract_outlook_guidance(truncated_text, llm, source_page, source_section)
    elif category == "Financial Analysis" or "financial analysis" in sub_lower:
        return _extract_financial_analysis(truncated_text, llm, source_page, source_section)
    elif category == "Business Performance" or "performance" in sub_lower:
        return _extract_business_performance(truncated_text, llm, source_page, source_section)
    elif category == "Risk Management" or "risk" in sub_lower:
        return _extract_risk_management(truncated_text, llm, source_page, source_section)
    elif category == "Legal & Compliance" or "legal" in sub_lower or "compliance" in sub_lower:
        return _extract_legal_compliance(truncated_text, llm, source_page, source_section)
    elif category == "Strategic Initiatives" or "strategic" in sub_lower:
        return _extract_strategic_initiatives(truncated_text, llm, source_page, source_section)
    elif category == "ESG & Sustainability" or "esg" in sub_lower or "sustainability" in sub_lower:
        return _extract_esg_sustainability(truncated_text, llm, source_page, source_section)
    elif category == "CSR" or "corporate social responsibility" in sub_lower or "csr" in sub_lower:
        return _extract_csr(truncated_text, llm, source_page, source_section)
    elif category == "Human Resources" or "human resource" in sub_lower or "employee" in sub_lower:
        return _extract_human_resources(truncated_text, llm, source_page, source_section)

    elif "auditor" in sub_lower or "audit report" in sub_lower or "auditor's report" in text_head or category == "Audit Information":
        return _extract_auditor_report(truncated_text, llm, source_page, source_section)
    elif "segment" in sub_lower or "segment information" in text_head or "segment reporting" in text_head:
        return _extract_segment_info(truncated_text, llm, source_page, source_section)
    elif "mgt-9" in sub_lower or ("management discussion" in sub_lower and "extract" in text_head):
        return _extract_mgt9(truncated_text, llm, source_page, source_section)
    elif ("foreign" in sub_lower and "currency" in sub_lower) or ("export" in sub_lower and "earning" in text_head) or "foreign exchange" in text_head:
        return _extract_forex_earnings(truncated_text, llm, source_page, source_section)

    return None


# =====================================================================
# Governance Multi-Extract (FIX 4)
# =====================================================================

def extract_governance_multi(
    text: str,
    llm: Any = None,
    source_page: int | None = None,
    source_section: str = "",
) -> dict[str, EvidenceBackedResult]:
    """Run all governance extractors on the same text and merge results.

    Corporate Governance Report sections in Indian annual reports typically
    contain Board composition, KMP disclosure, Committee details, AND
    governance narrative — all in one section.  The standard router only
    sends the text to ``_extract_corporate_governance()``, losing Board,
    KMP, and Committee data.  This function runs all four extractors and
    returns a dict keyed by WORKBOOK_TARGETS field names.

    Returns
    -------
    dict[str, EvidenceBackedResult]
        Keys are target field names: "Board of Directors",
        "Key Management Personnel", "Board Committees",
        "Corporate Governance".  Only non-None results are included.
    """
    truncated = text[:20000]
    results: dict[str, EvidenceBackedResult] = {}

    # Board of Directors
    board_result = _extract_board_of_directors(truncated, llm, source_page, source_section)
    if board_result and board_result.value:
        results["Board of Directors"] = board_result
        logger.info("[GovernanceMulti] Board: method=%s members=%d",
                    board_result.evidence.extraction_method,
                    len(board_result.value) if isinstance(board_result.value, list) else 1)

    # Key Management Personnel
    kmp_result = _extract_kmp(truncated, llm, source_page, source_section)
    if kmp_result and kmp_result.value:
        results["Key Management Personnel"] = kmp_result
        logger.info("[GovernanceMulti] KMP: method=%s count=%d",
                    kmp_result.evidence.extraction_method,
                    len(kmp_result.value) if isinstance(kmp_result.value, list) else 1)

    # Board Committees
    committees_result = _extract_committees(truncated, llm, source_page, source_section)
    if committees_result and committees_result.value:
        results["Board Committees"] = committees_result
        logger.info("[GovernanceMulti] Committees: method=%s count=%d",
                    committees_result.evidence.extraction_method,
                    len(committees_result.value) if isinstance(committees_result.value, list) else 1)

    # Corporate Governance narrative
    gov_result = _extract_corporate_governance(truncated, llm, source_page, source_section)
    if gov_result and gov_result.value:
        results["Corporate Governance"] = gov_result
        logger.info("[GovernanceMulti] Governance: method=%s", gov_result.evidence.extraction_method)

    logger.info("[GovernanceMulti] Extracted %d governance sub-fields from section '%s'",
                len(results), source_section)
    return results


# =====================================================================
# Extractors — Regex-first, LLM-fallback, Evidence-backed
# =====================================================================

def _extract_board_of_directors(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract board members: regex first, LLM fallback."""
    # Try deterministic extraction first
    pre_result = _pre_extract_board_members(text, source_page, source_section)
    if pre_result and isinstance(pre_result.value, list) and len(pre_result.value) >= 2:
        logger.info("[Board] method=%s members=%d section=%s",
                    pre_result.evidence.extraction_method, len(pre_result.value), source_section)
        return pre_result

    # Fall back to LLM
    prompt = f"""You are a financial analyst extracting the Board of Directors from an annual report.
Extract the board members as a JSON list of objects. Do not include any other text.
Each object should have:
- "name": string
- "designation": string
- "type": string (e.g. "Executive", "Non-Executive", "Independent")
- "din": string (Director Identification Number, 8 digits, if available)

Text:
{text}

Output JSON list:
"""
    result = _extract_json_from_llm(llm, prompt)
    if isinstance(result, list) and len(result) > 0:
        for item in result:
            item.setdefault("extraction_method", "llm")
        validated = validate_entity_list("board_members", result)
        # If regex found some but < 2, merge with LLM results
        if pre_result and isinstance(pre_result.value, list):
            regex_names = {m.get("name", "") for m in pre_result.value}
            merged = list(pre_result.value)
            for item in validated:
                if item.get("name", "") not in regex_names:
                    merged.append(item)
            validated = merged
        logger.info("[Board] method=llm members=%d section=%s", len(validated), source_section)

        return EvidenceBackedResult(
            value=validated,
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=text[:200],
                extraction_method="llm",
                confidence=0.70,
            ),
        )

    # Return regex result even if < 2 members
    return pre_result


def _extract_kmp(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract KMP: regex first, LLM fallback."""
    pre_result = _pre_extract_kmp(text, source_page, source_section)
    if pre_result and isinstance(pre_result.value, list) and len(pre_result.value) >= 1:
        logger.info("[KMP] method=%s count=%d section=%s",
                    pre_result.evidence.extraction_method, len(pre_result.value), source_section)
        return pre_result

    prompt = f"""Extract the Key Management Personnel (KMP) from the text.
Output a JSON list of objects, each with "name" and "designation".

Text:
{text}

Output JSON list:
"""
    result = _extract_json_from_llm(llm, prompt)
    if isinstance(result, list) and len(result) > 0:
        for item in result:
            item.setdefault("extraction_method", "llm")
        validated = validate_entity_list("kmp", result)
        logger.info("[KMP] method=llm count=%d section=%s", len(validated), source_section)
        return EvidenceBackedResult(
            value=validated,
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=text[:200],
                extraction_method="llm",
                confidence=0.70,
            ),
        )

    return pre_result


def _extract_committees(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract board committees: regex first, LLM fallback."""
    pre_result = _pre_extract_committees(text, source_page, source_section)
    if pre_result and isinstance(pre_result.value, list) and len(pre_result.value) >= 1:
        logger.info("[Committee] method=%s count=%d section=%s",
                    pre_result.evidence.extraction_method, len(pre_result.value), source_section)
        return pre_result

    prompt = f"""Extract the names of the Board Committees mentioned in the text (e.g. Audit Committee, CSR Committee).
Output a simple JSON list of strings.

Text:
{text}

Output JSON list:
"""
    result = _extract_json_from_llm(llm, prompt)
    if isinstance(result, list) and len(result) > 0:
        # Validate as committee entries
        committee_dicts = [{"name": c} for c in result if isinstance(c, str)]
        validated = validate_entity_list("committees", committee_dicts)
        validated_names = [c.get("name", c) if isinstance(c, dict) else c for c in validated]
        logger.info("[Committee] method=llm count=%d section=%s", len(validated_names), source_section)
        return EvidenceBackedResult(
            value=validated_names,
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=text[:200],
                extraction_method="llm",
                confidence=0.70,
            ),
        )

    return pre_result


def _extract_corporate_governance(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract corporate governance info."""
    prompt = f"""You are a corporate governance analyst. Extract a brief summary of the corporate governance practices, policies, and philosophy of the company.
Output a JSON object with:
- "governance_philosophy": string (brief summary)
- "policies": list of strings (e.g., Whistle Blower Policy, Code of Conduct)
If no details are found, return {{}}.

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    logger.info("[CorpGov] method=llm keys=%s section=%s",
                list(value.keys()) if isinstance(value, dict) else "none", source_section)
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_share_capital(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract share capital details."""
    prompt = f"""Extract the Share Capital details from the text.
Output a JSON object with:
- "authorized_capital": string/number
- "paidup_capital": string/number

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_shareholding_pattern(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract shareholding pattern."""
    prompt = f"""Extract the Shareholding Pattern percentage breakdown from the text.
Output a JSON object with:
- "promoter": string (percentage)
- "public": string (percentage)
- "institutions": string (percentage)

If a value is not found, use null.

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_dividend(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract dividend: regex first, LLM fallback."""
    # Try regex pre-extractor first
    pre_result = _pre_extract_dividend(text, source_page, source_section)
    if pre_result:
        logger.info("[Dividend] method=%s value=%s section=%s",
                    pre_result.evidence.extraction_method,
                    str(pre_result.value)[:80], source_section)
        return pre_result

    # LLM fallback
    prompt = f"""Extract the declared dividend (per share or percentage) from the text.
Output a JSON object with a single key "dividend_declared". If not found, output {{}}.

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    logger.info("[Dividend] method=llm value=%s section=%s",
                str(value)[:80], source_section)
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_company_profile(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract company profile with CIN-derived registration year."""
    result: dict[str, Any] = {}
    method = "llm"
    snippet = text[:200]

    # Step 1: Extract CIN deterministically
    cin_match = re.search(r'U\d{5}[A-Z]{2}(\d{4})[A-Z]{3}\d{6}', text)
    if cin_match:
        result["cin"] = cin_match.group(0)
        result["registration_year"] = cin_match.group(1)  # Year from CIN
        result["registration_year_source"] = "cin_derived"
        method = "regex_cin"
        snippet = _capture_evidence_snippet(text, cin_match)
        # NOTE: Do NOT set incorporation_year from CIN.
        # CIN year = registration year, which may differ from incorporation year.

    # Step 2: Extract explicit incorporation year from text
    incorp_pattern = re.compile(
        r'(?:incorporated|incorporation)\s+(?:in\s+the\s+year\s+)?(?:of\s+)?(\d{4})',
        re.I,
    )
    incorp_match = incorp_pattern.search(text)
    if incorp_match:
        result["incorporation"] = incorp_match.group(1)
        result["incorporation_source"] = "text_explicit"
        if method == "llm":
            method = "regex_incorp"
            snippet = _capture_evidence_snippet(text, incorp_match)

    # Step 3: Extract registered office from address patterns
    office_pattern = re.compile(
        r'(?:registered\s+office|regd\.?\s+office|head\s+office)[:\s]*'
        r'([A-Z][A-Za-z\s,\.]+'
        r'(?:Maharashtra|Karnataka|Tamil\s+Nadu|Gujarat|Rajasthan|'
        r'Delhi|West\s+Bengal|Telangana|Andhra\s+Pradesh))',
        re.I,
    )
    office_match = office_pattern.search(text)
    if office_match:
        result["registered_office"] = office_match.group(1).strip()
        if method == "llm":
            snippet = _capture_evidence_snippet(text, office_match)

    # Step 4: LLM for remaining fields (business_description, certifications)
    # Only ask LLM for fields NOT already deterministically extracted
    llm_prompt = f"""Extract the Company Profile details from the text.
Exclude incorporation year and CIN if they are already found via other methods.
Output a JSON object with:
- "business_description": string (short summary)
- "manufacturing_locations": list of strings
- "certifications": list of strings
"""
    if "incorporation" not in result:
        llm_prompt += "- \"incorporation\": string (year or details)\n"

    llm_prompt += f"""
Text:
{text}

Output JSON object:
"""
    llm_result = _extract_json_from_llm(llm, llm_prompt)
    if isinstance(llm_result, dict):
        # Merge: deterministic values override LLM values
        merged = {**llm_result, **result}
        result = merged

    confidence = 0.95 if method.startswith("regex") else 0.70

    return EvidenceBackedResult(
        value=result,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=snippet,
            extraction_method=method,
            confidence=confidence,
        ),
    )


def _extract_business_overview(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract business overview."""
    prompt = f"""Extract the Business Overview from the text.
Output a JSON object with:
- "business_model": string
- "operating_segments": list of strings
- "key_markets": list of strings

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_products_services(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract products and services."""
    prompt = f"""You are analyzing the Products & Services section of an Indian company annual report.
Extract the following into a JSON object:
- "product_list": list of strings (specific product names, e.g., "TMT Bars", "Structural Steel", "Wire Rods")
- "service_list": list of strings (specific service names if any)
- "business_verticals": list of strings (e.g., "Steel", "Power", "Infrastructure")
- "key_customers": list of strings (if customer segments are mentioned, e.g., "Railways", "Construction")
- "revenue_by_vertical": dict mapping vertical name to revenue figure as string (if disclosed)

If a field is not found, use an empty list or null. Do NOT fabricate data.

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_subsidiaries(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract subsidiaries: regex first, LLM fallback.

    Also detects explicit "no subsidiaries" statements for GAP 0H.
    """
    # Try regex pre-extractor first
    pre_result = _pre_extract_subsidiaries(text, source_page, source_section)
    if pre_result:
        subs = pre_result.value.get("subsidiaries", []) if isinstance(pre_result.value, dict) else []
        if subs or pre_result.value.get("no_subsidiaries_statement"):
            logger.debug(f"[ContentExtractor] Subsidiaries: regex extracted {len(subs)} entries")
            return pre_result

    # LLM fallback
    prompt = f"""Extract the Subsidiaries and Group Structure from the text.
Output a JSON object with:
- "subsidiaries": list of strings
- "associates": list of strings
- "jvs": list of strings (Joint Ventures)
- "no_subsidiaries_statement": boolean (true if the company explicitly states it has no subsidiaries)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    if isinstance(result, dict):
        # Validate subsidiary names against schema
        if result.get("subsidiaries"):
            sub_dicts = [
                {"name": s, "entity_type": "Subsidiary"}
                for s in result["subsidiaries"]
                if isinstance(s, str)
            ]
            validated = validate_entity_list("subsidiaries", sub_dicts)
            result["subsidiaries"] = [
                s.get("name", s) if isinstance(s, dict) else s
                for s in validated
            ]

        return EvidenceBackedResult(
            value=result,
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=text[:200],
                extraction_method="llm",
                confidence=0.70,
            ),
        )

    return pre_result


def _extract_mda(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract MD&A information."""
    prompt = f"""You are a financial analyst reading the Management Discussion & Analysis (MD&A) section.
Extract the key points into a structured JSON object. Focus on the most important highlights.
Output a JSON object with:
- "industry_overview": string (summary of industry trends)
- "business_review": string (summary of operational/financial performance, e.g., revenue growth, EBITDA)
- "opportunities_and_risks": list of strings (growth drivers, competition, raw material costs, etc.)
- "future_outlook": string (guidance, targets for next FY, expansion plans)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


# =====================================================================
# Sprint 2: Financial Metadata Extractors
# =====================================================================

def _extract_auditor_report(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract auditor opinion: regex first, LLM fallback."""
    # Try regex pre-extractor first
    pre_result = _pre_extract_auditor(text, source_page, source_section)
    if pre_result:
        logger.debug("[ContentExtractor] Auditor: regex extracted")
        # If regex found opinion but not KAMs, try LLM for KAMs
        if llm and isinstance(pre_result.value, dict) and not pre_result.value.get("key_audit_matters"):
            kam_prompt = f"""Extract the Key Audit Matters from the Auditor's Report text.
Output a JSON object with:
- "key_audit_matters": list of strings (brief descriptions of each KAM)
- "emphasis_of_matter": string or null (any emphasis of matter paragraph summary)

Text:
{text}

Output JSON object:
"""
            kam_result = _extract_json_from_llm(llm, kam_prompt)
            if isinstance(kam_result, dict) and kam_result.get("key_audit_matters"):
                pre_result.value["key_audit_matters"] = kam_result["key_audit_matters"]
                if kam_result.get("emphasis_of_matter"):
                    pre_result.value["emphasis_of_matter"] = kam_result["emphasis_of_matter"]
        return pre_result

    # LLM fallback
    prompt = f"""You are a financial auditor analyst. Extract the following from the Auditor's Report text:
Output a JSON object with:
- "auditor_opinion": string (one of: "Unqualified", "Qualified", "Adverse", "Disclaimer", or "Not Determined")
- "auditor_name": string (name of the audit firm)
- "key_audit_matters": list of strings (brief descriptions of each KAM)
- "emphasis_of_matter": string or null (any emphasis of matter paragraph summary)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    if isinstance(result, dict):
        validated_data = result
    else:
        # Heuristic fallback
        text_lower = text.lower()
        opinion = "Not Determined"
        if "unqualified" in text_lower or "true and fair" in text_lower:
            opinion = "Unqualified"
        elif "qualified" in text_lower and "except for" in text_lower:
            opinion = "Qualified"
        elif "adverse" in text_lower:
            opinion = "Adverse"
        elif "disclaimer" in text_lower:
            opinion = "Disclaimer"
        validated_data = {"auditor_opinion": opinion, "key_audit_matters": []}

    return EvidenceBackedResult(
        value=validated_data,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_segment_info(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract segment reporting information."""
    if not llm:
        return EvidenceBackedResult(
            value={"segments": [], "segment_note": ""},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                extraction_method="heuristic",
                confidence=0.50,
            ),
        )

    prompt = f"""You are a financial analyst. Extract the segment reporting information from the text.
Output a JSON object with:
- "segments": list of strings (names of operating segments)
- "primary_segment_format": string (e.g., "Business Segment", "Geographical Segment")
- "segment_revenue_summary": dict mapping segment name to revenue figure (as string)
- "inter_segment_elimination": string or null

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_mgt9(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract MGT-9 data including NIC code."""
    if not llm:
        return EvidenceBackedResult(
            value={"nic_code": "", "principal_activity": ""},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                extraction_method="heuristic",
                confidence=0.50,
            ),
        )

    prompt = f"""You are a financial analyst. Extract the following from the MGT-9 / Management Discussion section:
Output a JSON object with:
- "nic_code": string (NIC-2008 code if mentioned, e.g., "25200")
- "principal_business_activity": string (main business activity description)
- "change_in_nature_of_business": string or null (if any change disclosed)
- "ratio_of_remuneration": string or null (if disclosed)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_forex_earnings(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    """Extract foreign exchange / export earnings: regex first, LLM fallback."""
    # Heuristic: search for forex patterns
    forex_pattern = re.compile(
        r'(?:foreign\s+(?:exchange|currency)\s+(?:earnings?|revenue|income)|'
        r'export\s+(?:earnings?|revenue|sales|FOB).*?)[\s:]*'
        r'(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)',
        re.I,
    )
    match = forex_pattern.search(text)
    if match:
        snippet = _capture_evidence_snippet(text, match)
        return EvidenceBackedResult(
            value={"forex_earnings": match.group(1), "exporter_flag": True},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                source_text_snippet=snippet,
                extraction_method="regex_forex",
                confidence=0.85,
            ),
        )

    if not llm:
        return EvidenceBackedResult(
            value={"forex_earnings": "", "exporter_flag": False},
            evidence=ExtractionEvidence(
                source_page=source_page,
                source_section=source_section,
                extraction_method="heuristic",
                confidence=0.50,
            ),
        )

    prompt = f"""You are a financial analyst. Extract the foreign exchange / export earnings from the text.
Output a JSON object with:
- "forex_earnings": string (the amount of foreign currency earnings or export revenue, with currency unit)
- "exporter_flag": boolean (true if the company has export earnings)
- "currency_of_earnings": string (e.g., "USD", "EUR", or "INR equivalent")

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {"forex_earnings": "", "exporter_flag": False}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


# =====================================================================
# Priorities 3-7 Extractors
# =====================================================================

def _extract_investor_information(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a financial analyst. Extract Investor Information from the text.
Output a JSON object with:
- "stock_exchanges": list of strings (where the company is listed)
- "market_capitalization": string (if disclosed)
- "pe_ratio": string (if disclosed)
- "eps": string (Earnings Per Share, if disclosed)
- "registrar": string (Registrar & Transfer Agent name)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_outlook_guidance(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a financial analyst. Extract Outlook & Guidance from the text.
Output a JSON object with:
- "revenue_guidance": string (forward-looking revenue projections)
- "margin_guidance": string (forward-looking margin/profit projections)
- "capex_guidance": string (capital expenditure plans)
- "key_growth_drivers": list of strings (factors driving future growth)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_financial_analysis(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a financial analyst. Extract Financial Analysis highlights.
Output a JSON object with:
- "revenue_growth": string (percentage or value)
- "ebitda_margin": string
- "net_profit_margin": string
- "debt_to_equity": string
- "roce": string (Return on Capital Employed)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_business_performance(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a financial analyst. Extract Business Performance highlights.
Output a JSON object with:
- "production_volume": string (if applicable)
- "sales_volume": string (if applicable)
- "capacity_utilization": string
- "key_operational_achievements": list of strings

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_risk_management(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a risk analyst. Extract Risk Management information.
Output a JSON object with:
- "key_risks": list of strings (major risks identified)
- "mitigation_strategies": list of strings (how risks are managed)
- "risk_management_framework": string (brief description of framework)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_legal_compliance(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a compliance officer. Extract Legal & Compliance information.
Output a JSON object with:
- "pending_litigations": list of strings (major legal cases or disputes)
- "regulatory_actions": list of strings (fines, penalties, notices)
- "compliance_status": string (summary of adherence to laws)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_strategic_initiatives(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a strategy analyst. Extract Strategic Initiatives.
Output a JSON object with:
- "mergers_and_acquisitions": list of strings (M&A activity)
- "expansion_plans": list of strings (new markets, facilities)
- "digital_transformation": list of strings (IT, automation initiatives)
- "r_and_d_initiatives": list of strings (Research and Development)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_esg_sustainability(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are an ESG analyst. Extract ESG & Sustainability information.
Output a JSON object with:
- "environmental_initiatives": list of strings (emissions reduction, water conservation, etc.)
- "renewable_energy_share": string (percentage or MW if disclosed)
- "sustainability_goals": list of strings (future targets, net-zero goals)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_csr(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are a CSR analyst. Extract Corporate Social Responsibility (CSR) details.
Output a JSON object with:
- "csr_expenditure": string (amount spent on CSR)
- "key_csr_projects": list of strings (education, healthcare, rural development)
- "beneficiaries": string (number of people impacted, if disclosed)

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )


def _extract_human_resources(
    text: str, llm: Any,
    source_page: int | None = None,
    source_section: str = "",
) -> EvidenceBackedResult | None:
    prompt = f"""You are an HR analyst. Extract Human Resources metrics and information.
Output a JSON object with:
- "total_employees": string (number of permanent/total employees)
- "attrition_rate": string (percentage, if disclosed)
- "training_hours": string (total or per employee)
- "diversity_metrics": dict mapping metric to value (e.g., "women_percentage": "15%")
- "key_hr_initiatives": list of strings

Text:
{text}

Output JSON object:
"""
    result = _extract_json_from_llm(llm, prompt)
    value = result if isinstance(result, dict) else {}
    return EvidenceBackedResult(
        value=value,
        evidence=ExtractionEvidence(
            source_page=source_page,
            source_section=source_section,
            source_text_snippet=text[:200],
            extraction_method="llm",
            confidence=0.70,
        ),
    )
