"""Taxonomy Classification Layer — Hybrid LLM-first + keyword/regex fallback.

Maps extracted section blocks into a predefined 17-category taxonomy.

Strategy:
  1. PRIMARY: Send section text chunks to Groq LLM for classification
  2. FALLBACK: If LLM fails → use keyword/regex pattern matching
  3. No fuzzy matching — strict keyword/regex only
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ===================================================================
# Full Taxonomy Definition (Priority API Scope)
# ===================================================================

TAXONOMY: dict[str, list[str]] = {
    "Company Information": [
        "Company Profile",
        "Business Overview",
        "Products & Services",
        "Subsidiaries & Group Structure",
    ],
    "Management & Governance": [
        "Board of Directors",
        "Key Management Personnel",
        "Corporate Governance",
        "Board Committees",
    ],
    "Shareholding Information": [
        "Share Capital",
        "Shareholding Pattern",
        "Major Shareholders",
        "Dividend Information",
    ],
    "Management Discussion & Analysis": [
        "Industry Overview",
        "Business Review",
        "Opportunities & Challenges",
        "Future Outlook",
    ],
    "Financial Statements": [
        "Balance Sheet",
        "Profit & Loss Statement",
        "Cash Flow Statement",
        "Statement of Changes in Equity",
    ],
    "Notes to Accounts": [
        "Accounting Policies",
        "Related Party Transactions",
        "Contingent Liabilities",
        "Segment Information",
    ],
    "Financial Analysis": [
        "Financial Ratios",
        "Working Capital Analysis",
        "Debt Analysis",
    ],
    "Business Performance": [
        "Revenue & Sales Performance",
        "Segment Performance",
        "Operational Performance",
        "Key Performance Indicators (KPIs)",
    ],
    "Risk Management": [
        "Business Risks",
        "Financial Risks",
        "Operational Risks",
        "Regulatory Risks",
    ],
    "Human Resources": [
        "Workforce Information",
        "Training & Development",
        "Employee Welfare",
        "Diversity & Inclusion",
    ],
    "ESG & Sustainability": [
        "Environmental",
        "Social",
        "Governance",
        "Sustainability Initiatives",
    ],
    "CSR": [
        "CSR Spending",
        "CSR Projects",
        "Community Development",
    ],
    "Legal & Compliance": [
        "Litigations",
        "Regulatory Compliance",
        "Statutory Compliance",
    ],
    "Strategic Initiatives": [
        "Growth Strategy",
        "Expansion Plans",
        "Mergers & Acquisitions",
        "Digital Transformation",
    ],
    "Investor Information": [
        "Share Price Performance",
        "Market Capitalization",
        "Shareholder Information",
        "Investor Relations",
    ],
    "Audit Information": [
        "Auditor's Report",
        "Key Audit Matters",
        "Internal Controls",
    ],
    "Outlook & Guidance": [
        "Management Guidance",
        "Growth Targets",
        "Future Plans",
    ],
}

ALL_CATEGORIES = list(TAXONOMY.keys())


# ===================================================================
# Keyword/Regex patterns for each category (fallback)
# ===================================================================

# Maps category → list of (compiled_regex_pattern, subcategory, confidence)
_CATEGORY_PATTERNS: dict[str, list[tuple[re.Pattern, str, float]]] = {
    "Company Information": [
        (re.compile(r"\bcompany\s+(?:profile|overview|information)\b", re.I), "Company Profile", 0.90),
        (re.compile(r"\bbusiness\s+overview\b", re.I), "Business Overview", 0.85),
        (re.compile(r"\bproducts?\s+(?:and|&)\s+services?\b", re.I), "Products & Services", 0.85),
        (re.compile(r"\b(?:subsidiaries|group\s+structure)\b", re.I), "Subsidiaries & Group Structure", 0.85),
    ],
    "Management & Governance": [
        (re.compile(r"\bboard\s+of\s+directors\b", re.I), "Board of Directors", 0.95),
        (re.compile(r"\bkey\s+manage(?:ment|rial)\s+personnel\b", re.I), "Key Management Personnel", 0.90),
        (re.compile(r"\bcorporate\s+governance\b", re.I), "Corporate Governance", 0.90),
        (re.compile(r"\bboard\s+committees?\b", re.I), "Board Committees", 0.90),
    ],
    "Shareholding Information": [
        (re.compile(r"\bshare\s+capital\b", re.I), "Share Capital", 0.85),
        (re.compile(r"\bshareholding\s+pattern\b", re.I), "Shareholding Pattern", 0.95),
        (re.compile(r"\b(?:major|top)\s+shareholders?\b", re.I), "Major Shareholders", 0.85),
        (re.compile(r"\bdividend\s+(?:information|history|recommendation)\b", re.I), "Dividend Information", 0.85),
    ],
    "Management Discussion & Analysis": [
        (re.compile(r"\bindustry\s+overview\b", re.I), "Industry Overview", 0.85),
        (re.compile(r"\bbusiness\s+(?:review|performance)\b", re.I), "Business Review", 0.85),
        (re.compile(r"\bopportunit(?:y|ies)\s+(?:and|&)\s+challenges?\b", re.I), "Opportunities & Challenges", 0.80),
        (re.compile(r"\bfuture\s+outlook\b", re.I), "Future Outlook", 0.80),
    ],
    "Financial Statements": [
        (re.compile(r"\bbalance\s+sheet\b", re.I), "Balance Sheet", 0.90),
        (re.compile(r"\b(?:statement\s+of\s+)?profit\s+(?:and|&)\s+loss\b", re.I), "Profit & Loss Statement", 0.90),
        (re.compile(r"\bcash\s+flow\s+statement\b", re.I), "Cash Flow Statement", 0.90),
        (re.compile(r"\bstatement\s+of\s+changes?\s+in\s+equity\b", re.I), "Statement of Changes in Equity", 0.90),
    ],
    "Notes to Accounts": [
        (re.compile(r"\baccounting\s+policies\b", re.I), "Accounting Policies", 0.85),
        (re.compile(r"\bcontingent\s+liabilit(?:y|ies)\b", re.I), "Contingent Liabilities", 0.85),
        (re.compile(r"\bsegment\s+(?:information|reporting)\b", re.I), "Segment Information", 0.85),
    ],
    "Financial Analysis": [
        (re.compile(r"\bfinancial\s+ratios?\b", re.I), "Financial Ratios", 0.90),
        (re.compile(r"\bworking\s+capital\s+(?:analysis|changes)\b", re.I), "Working Capital Analysis", 0.85),
        (re.compile(r"\bdebt\s+analysis\b", re.I), "Debt Analysis", 0.85),
    ],
    "Business Performance": [
        (re.compile(r"\brevenue\s+(?:and|&)?\s+sales\s+performance\b", re.I), "Revenue & Sales Performance", 0.85),
        (re.compile(r"\bsegment\s+performance\b", re.I), "Segment Performance", 0.85),
        (re.compile(r"\boperational\s+performance\b", re.I), "Operational Performance", 0.85),
        (re.compile(r"\bkey\s+performance\s+indicators?\b|\bkpi\b", re.I), "Key Performance Indicators (KPIs)", 0.80),
    ],
    "Risk Management": [
        (re.compile(r"\bbusiness\s+risks?\b", re.I), "Business Risks", 0.85),
        (re.compile(r"\bfinancial\s+risks?\b", re.I), "Financial Risks", 0.85),
        (re.compile(r"\boperational\s+risks?\b", re.I), "Operational Risks", 0.85),
        (re.compile(r"\bregulatory\s+risks?\b", re.I), "Regulatory Risks", 0.85),
    ],
    "Human Resources": [
        (re.compile(r"\bworkforce\s+information\b", re.I), "Workforce Information", 0.85),
        (re.compile(r"\btraining\s+(?:and|&)\s+development\b", re.I), "Training & Development", 0.85),
        (re.compile(r"\bemployee\s+welfare\b", re.I), "Employee Welfare", 0.85),
        (re.compile(r"\bdiversity\s+(?:and|&)\s+inclusion\b", re.I), "Diversity & Inclusion", 0.85),
    ],
    "ESG & Sustainability": [
        (re.compile(r"\benvironmental\b", re.I), "Environmental", 0.80),
        (re.compile(r"\bsocial\b", re.I), "Social", 0.80),
        (re.compile(r"\bgovernance\b", re.I), "Governance", 0.80),
        (re.compile(r"\bsustainability\s+initiatives?\b", re.I), "Sustainability Initiatives", 0.85),
    ],
    "CSR": [
        (re.compile(r"\bcsr\s+spending\b", re.I), "CSR Spending", 0.85),
        (re.compile(r"\bcsr\s+projects?\b", re.I), "CSR Projects", 0.85),
        (re.compile(r"\bcommunity\s+development\b", re.I), "Community Development", 0.85),
    ],
    "Legal & Compliance": [
        (re.compile(r"\blitigations?\b", re.I), "Litigations", 0.80),
        (re.compile(r"\bregulatory\s+compliance\b", re.I), "Regulatory Compliance", 0.85),
        (re.compile(r"\bstatutory\s+compliance\b", re.I), "Statutory Compliance", 0.85),
    ],
    "Strategic Initiatives": [
        (re.compile(r"\bgrowth\s+strategy\b", re.I), "Growth Strategy", 0.85),
        (re.compile(r"\bexpansion\s+plans?\b", re.I), "Expansion Plans", 0.85),
        (re.compile(r"\bmergers?\s+(?:and|&)\s+acquisitions?\b", re.I), "Mergers & Acquisitions", 0.85),
        (re.compile(r"\bdigital\s+transformation\b", re.I), "Digital Transformation", 0.85),
    ],
    "Investor Information": [
        (re.compile(r"\bshare\s+price\s+performance\b", re.I), "Share Price Performance", 0.85),
        (re.compile(r"\bmarket\s+capitalization\b", re.I), "Market Capitalization", 0.85),
        (re.compile(r"\bshareholder\s+information\b", re.I), "Shareholder Information", 0.85),
        (re.compile(r"\binvestor\s+relations\b", re.I), "Investor Relations", 0.85),
    ],
    "Audit Information": [
        (re.compile(r"\bauditor'?s?\s+report\b", re.I), "Auditor's Report", 0.90),
        (re.compile(r"\bkey\s+audit\s+matters?\b", re.I), "Key Audit Matters", 0.90),
        (re.compile(r"\binternal\s+controls?\b", re.I), "Internal Controls", 0.85),
    ],
    "Outlook & Guidance": [
        (re.compile(r"\bmanagement\s+guidance\b", re.I), "Management Guidance", 0.85),
        (re.compile(r"\bgrowth\s+targets?\b", re.I), "Growth Targets", 0.85),
        (re.compile(r"\bfuture\s+plans?\b", re.I), "Future Plans", 0.85),
    ],
}


# ===================================================================
# LLM Classification Prompt
# ===================================================================

_LLM_CLASSIFY_PROMPT = """You are a financial document classifier for Indian annual reports.

Given the following text representing a contiguous document section, classify it into the most relevant taxonomy category and subcategory.

TAXONOMY CATEGORIES:
{taxonomy_list}

SECTION TEXT (pages {start_page} to {end_page}, title: "{raw_section_name}"):
---
{section_text}
---

Classify this section into the most relevant category.

Return ONLY a JSON array of objects:
```json
[
  {{
    "section_type": "<exact category name from the list>",
    "section_subtype": "<exact subcategory name>",
    "confidence": <0.0 to 1.0>
  }}
]
```

Rules:
- Use EXACT section_type and section_subtype names from the taxonomy above.
- Confidence should reflect how strongly this section belongs to the category.
- If the section doesn't clearly fit any category, return an empty array []
- Return ONLY the JSON, no commentary.
"""


# ===================================================================
# Main Classification Functions
# ===================================================================

def classify_sections(
    sections: list[dict[str, Any]],
    all_pages: list[dict[str, Any]],
    progress_callback=None,
    use_llm: bool = True,
) -> list[dict[str, Any]]:
    """Classify entire section blocks into the taxonomy using hybrid LLM + keyword/regex approach.

    Strategy:
      1. Try LLM classification first for each section block.
      2. If LLM fails → fall back to keyword/regex.

    Parameters
    ----------
    sections : list[dict]
        Section registry entries (dict form of MasterSection).
    all_pages : list[dict]
        Page data dicts from the master data layer to pull text.
    progress_callback : callable, optional
        Progress message callback.
    use_llm : bool
        Whether to attempt LLM classification first (default True).

    Returns
    -------
    list[dict]
        The sections list with section_type, section_subtype, category, subcategory filled.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    llm_successes = 0
    regex_fallbacks = 0

    _log(f"[Taxonomy] Classifying {len(sections)} section blocks (hybrid: LLM-first + keyword/regex fallback)")

    # Group pages by number for quick lookup
    pages_by_num = {p["page_number"]: p.get("raw_text", "") for p in all_pages}

    for section in sections:
        start_page = section.get("start_page", 0)
        end_page = section.get("end_page", 0)
        raw_section_name = section.get("raw_section_name", "")
        zone = section.get("zone", "narrative")
        
        # Gather text for the block
        block_text = ""
        for p in range(start_page, end_page + 1):
            block_text += pages_by_num.get(p, "") + "\n"
            
        # Truncate text to avoid blowing up the LLM
        truncated_text = block_text[:3000]

        if not truncated_text.strip() and not raw_section_name.strip():
            continue

        best_match = None

        # ── PRIMARY: LLM classification ──
        if use_llm:
            try:
                llm_results = _classify_via_llm(
                    start_page, end_page, truncated_text, raw_section_name
                )
                if llm_results:
                    best_match = max(llm_results, key=lambda m: m.get("confidence", 0))
                    llm_successes += 1
            except Exception as exc:
                logger.debug(f"LLM classification failed for section {raw_section_name}: {exc}")

        # ── FALLBACK: Keyword/regex ──
        if not best_match:
            regex_results = _classify_via_keywords(truncated_text, raw_section_name, zone)
            if regex_results:
                best_match = max(regex_results, key=lambda m: m.get("confidence", 0))
                regex_fallbacks += 1

        if best_match:
            section["section_type"] = best_match.get("section_type", "")
            section["section_subtype"] = best_match.get("section_subtype", "")
            # Legacy fallback
            section["category"] = best_match.get("section_type", "")
            section["subcategory"] = best_match.get("section_subtype", "")
            
            # Normalize section name
            section["normalized_section_name"] = best_match.get("section_subtype", "")
            
            # Update confidence and status
            conf = best_match.get("confidence", 0.0)
            section["confidence"] = conf
            
            if conf < 0.75:
                section["section_status"] = "low_confidence"
            elif best_match.get("method") == "keyword_regex" and section.get("boundary_source") == "classifier":
                section["section_status"] = "inferred"
            # else keep it as 'confirmed' (from TOC or Heading)
        else:
            # Clean up unclassified names slightly
            cleaned = re.sub(r"^[0-9\.\s]+", "", raw_section_name) # Strip leading numbering
            cleaned = re.sub(r"[\.\-]+$", "", cleaned).strip()
            if cleaned:
                section["normalized_section_name"] = cleaned
            
    _log(f"[Taxonomy] Section Classification complete: "
         f"{llm_successes} blocks via LLM, {regex_fallbacks} blocks via keyword/regex")

    # ── POST-CLASSIFICATION MERGE PASS ──
    sections = _merge_adjacent_sections(sections)
    _log(f"[Taxonomy] After merging adjacent sections: {len(sections)} sections remaining")

    return sections

def _merge_adjacent_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent sections that share the same section_type and section_subtype."""
    if not sections:
        return []
        
    merged: list[dict[str, Any]] = []
    current = sections[0].copy()
    
    for next_sec in sections[1:]:
        same_type = current.get("section_type") == next_sec.get("section_type")
        same_subtype = current.get("section_subtype") == next_sec.get("section_subtype")
        
        # Don't merge unclassified blocks as they might be distinct
        is_classified = bool(current.get("section_type") and current.get("section_type") != "Unclassified")
        
        # Must be truly adjacent pages
        is_adjacent = current.get("end_page", 0) >= next_sec.get("start_page", 0) - 1
        
        if is_classified and same_type and same_subtype and is_adjacent:
            # Merge next_sec into current
            current["end_page"] = max(current["end_page"], next_sec.get("end_page", current["end_page"]))
            current["page_count"] = current["end_page"] - current["start_page"] + 1
            # Average out confidences roughly
            current["confidence"] = (current.get("confidence", 0.0) + next_sec.get("confidence", 0.0)) / 2
        else:
            merged.append(current)
            current = next_sec.copy()
            
    merged.append(current)
    return merged


def _classify_via_llm(
    start_page: int,
    end_page: int,
    block_text: str,
    section_name: str,
) -> list[dict[str, Any]]:
    """Classify a section block using the Groq LLM."""
    try:
        from .llm_config import get_llm
    except ImportError:
        logger.debug("LLM config not available, skipping LLM classification")
        return []

    # Build taxonomy list for the prompt
    taxonomy_lines = []
    for cat, subcats in TAXONOMY.items():
        taxonomy_lines.append(f"  {cat}:")
        for sc in subcats:
            taxonomy_lines.append(f"    - {sc}")
    taxonomy_str = "\n".join(taxonomy_lines)

    prompt = _LLM_CLASSIFY_PROMPT.format(
        taxonomy_list=taxonomy_str,
        start_page=start_page,
        end_page=end_page,
        raw_section_name=section_name,
        section_text=block_text,
    )

    logger.info("[Taxonomy] LLM classification invoked for section=%s", section_name)

    try:
        llm = get_llm(temperature=0.0, max_tokens=1024)
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        parsed = _extract_json_from_llm_response(response_text)

        if not parsed or not isinstance(parsed, list):
            return []

        mappings = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            section_type = item.get("section_type", item.get("category", ""))
            section_subtype = item.get("section_subtype", item.get("subcategory", ""))
            confidence = float(item.get("confidence", 0.0))

            if section_type not in TAXONOMY:
                continue
            if confidence < 0.5:
                continue

            mappings.append({
                "section_type": section_type,
                "section_subtype": section_subtype,
                "confidence": confidence,
                "method": "llm",
            })

        if mappings:
            best = max(mappings, key=lambda m: m["confidence"])
            logger.info(
                "[Taxonomy] LLM classification succeeded: %s/%s (conf=%.2f)",
                best["section_type"], best["section_subtype"], best["confidence"],
            )

        return mappings

    except Exception as exc:
        logger.warning("[Taxonomy] LLM classification failed for section=%s: %s", section_name, exc)
        return []


def _classify_via_keywords(
    block_text: str,
    raw_section_name: str,
    zone: str = "narrative"
) -> list[dict[str, Any]]:
    """Classify a section block using keyword/regex pattern matching.
    
    Since we classify entire blocks now, we only trust high confidence heading matches
    or very clear body matches. We lower body match confidence to avoid false positives.
    """
    mappings: list[dict[str, Any]] = []
    seen_categories: set[str] = set()

    # Body check uses first 1000 chars
    search_text = block_text[:1000]

    for category, patterns in _CATEGORY_PATTERNS.items():
        best_match: dict[str, Any] | None = None
        best_confidence = 0.0

        for pattern, subcategory, base_confidence in patterns:
            # Check heading first
            if raw_section_name and pattern.search(raw_section_name):
                confidence = min(base_confidence + 0.10, 1.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        "section_type": category,
                        "section_subtype": subcategory,
                        "confidence": confidence,
                        "method": "keyword_regex",
                    }

            # Check body text (reduce confidence for body-only matches)
            elif pattern.search(search_text):
                # We strictly lower body keyword match to prevent classifier leakage
                confidence = max(base_confidence - 0.20, 0.40) 
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        "section_type": category,
                        "section_subtype": subcategory,
                        "confidence": confidence,
                        "method": "keyword_regex",
                    }

        if best_match and category not in seen_categories:
            mappings.append(best_match)
            seen_categories.add(category)

    # ── Context-Aware Rules ──
    # Related Party Transactions: AGM Notice vs Notes to Accounts
    rpt_pattern = re.compile(r"\brelated\s+party\s+(?:transaction|disclosure)s?\b", re.I)
    if rpt_pattern.search(raw_section_name) or rpt_pattern.search(search_text):
        if zone == "financial":
            mappings.append({
                "section_type": "Notes to Accounts",
                "section_subtype": "Related Party Transactions",
                "confidence": 0.90,
                "method": "keyword_regex_context",
            })
        else:
            mappings.append({
                "section_type": "Investor Information",
                "section_subtype": "Related Party Mention", # Distinguish from full disclosure
                "confidence": 0.85,
                "method": "keyword_regex_context",
            })

    return mappings


def _extract_json_from_llm_response(text: str) -> Any:
    """Extract JSON from an LLM response that may contain markdown fences."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Try stripping markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass
            
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding outermost JSON array or object
    for open_ch, close_ch in [("[", "]"), ("{", "}")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    return None
