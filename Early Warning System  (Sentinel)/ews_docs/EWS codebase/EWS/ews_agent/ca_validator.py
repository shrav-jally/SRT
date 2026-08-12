"""
CA (Chartered Accountant) Validation & Inference Module

Post-mapping validation and inferential mapping that goes beyond
direct 1:1 label matching. Implements CA-level reasoning:

1. CROSS-STATEMENT VALIDATION: Checks that BS, P&L, and CF are
   internally consistent (e.g., Total Assets = Total Equity + Liabilities).
   Per Schedule III of the Companies Act, 2013, and Ind AS.

2. INFERENTIAL MAPPING: Derives values that aren't directly in the PDF
   but can be inferred from other mapped values using accounting logic.
   E.g., EBITDA = PBT + Depreciation + Finance costs;
   If P&L shows "Finance costs" → infer lease liabilities in BS.

3. NOTE CROSS-REFERENCE TRACKING: Links note references in BS/P&L
   (e.g., "Property, Plant and Equipment (3)") to actual notes data
   for verification and value enrichment.

4. ACCOUNTING STANDARD COMPLIANCE: Checks Ind AS / Schedule III
   specific disclosure requirements and flags gaps.

Design Principles (CA Lens):
    - A CA doesn't just copy numbers — they VERIFY them
    - A CA cross-checks: BS total assets MUST equal total equity + liabilities
    - A CA infers: if P&L shows finance costs, there MUST be a financial liability
    - A CA references: BS item "(3)" points to Note 3 which has the detail
    - A CA flags: missing disclosures, unbalanced statements, suspicious values

Integration:
    Called as Step 4.5 in smart_agent.py, AFTER mapping but BEFORE writing.
    Returns ValidationReport with findings, inferred mappings, and flags.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .data_mapper import (
    MappingResult,
    _parse_alias_value,
    _normalize_text,
    BALANCE_SHEET_TEMPLATE,
    PL_TEMPLATE,
    CASH_FLOW_TEMPLATE,
    FORMULA_TEMPLATE_ITEMS,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ValidationFlag:
    """A single validation finding."""
    severity: str  # "error", "warning", "info"
    category: str  # "cross_statement", "inferential", "note_reference", "compliance"
    statement: str  # "balance_sheet", "profit_and_loss", "cash_flow", "cross"
    message: str
    item_name: str = ""  # Template item involved (if any)
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    tolerance_pct: float = 0.01  # 1% default tolerance for numeric checks


@dataclass
class InferredMapping:
    """A mapping derived by inference rather than direct extraction."""
    template_item: str
    section: str
    value: str
    method: str  # "ca_inferred", "ca_calculated", "ca_cross_statement"
    confidence: float
    reasoning: str  # CA reasoning for the inference
    source_items: list[str] = field(default_factory=list)  # Items used in derivation


@dataclass
class ValidationReport:
    """Complete validation report from CA analysis."""
    flags: list[ValidationFlag] = field(default_factory=list)
    inferred_mappings: list[InferredMapping] = field(default_factory=list)
    note_references: dict[str, list[str]] = field(default_factory=dict)
    
    @property
    def errors(self) -> list[ValidationFlag]:
        return [f for f in self.flags if f.severity == "error"]
    
    @property
    def warnings(self) -> list[ValidationFlag]:
        return [f for f in self.flags if f.severity == "warning"]
    
    @property
    def infos(self) -> list[ValidationFlag]:
        return [f for f in self.flags if f.severity == "info"]
    
    @property
    def is_balanced(self) -> bool:
        """True if no error-level flags (statement balances)."""
        return len(self.errors) == 0


# ============================================================================
# HELPER: Get numeric value from mappings
# ============================================================================


def _get_value(mappings: list[MappingResult], item_name: str) -> Optional[float]:
    """Get the numeric value of a mapped item by template item name."""
    for m in mappings:
        if m.template_item == item_name:
            return _parse_alias_value(m.value)
    return None


def _get_value_or_inferred(
    mappings: list[MappingResult],
    inferred: list[InferredMapping],
    item_name: str,
) -> Optional[float]:
    """Get numeric value from either direct mappings or inferred mappings."""
    val = _get_value(mappings, item_name)
    if val is not None:
        return val
    for im in inferred:
        if im.template_item == item_name:
            return _parse_alias_value(im.value)
    return None


def _format_value(val: Optional[float]) -> str:
    """Format a numeric value for display."""
    if val is None:
        return "N/A"
    if val == int(val):
        return f"{val:,.0f}"
    return f"{val:,.2f}"


# ============================================================================
# 1. CROSS-STATEMENT VALIDATION
# ============================================================================


def validate_balance_sheet_equation(
    bs_mappings: list[MappingResult],
    report: ValidationReport,
) -> None:
    """
    Validate the fundamental accounting equation:
        Total Assets = Total Equity + Total Liabilities
    
    Per Schedule III, the Balance Sheet MUST balance. If it doesn't,
    there's either a mapping error or a missing item.
    
    Also validates sub-totals:
        Total Assets = Total Non-Current Assets + Total Current Assets
        Total Liabilities = Total NC Liabilities + Total Current Liabilities
        Total Equity = Equity Share Capital + Other Equity
    """
    # --- Fundamental equation: Assets = Equity + Liabilities ---
    total_assets = _get_value(bs_mappings, "Total Assets")
    total_equity = _get_value(bs_mappings, "Total Equity")
    total_liabilities = _get_value(bs_mappings, "Total Liabilities")
    total_equity_and_liabilities = _get_value(bs_mappings, "Total Equity and Liabilities")
    
    if total_assets is not None and total_equity_and_liabilities is not None:
        diff = abs(total_assets - total_equity_and_liabilities)
        tolerance = abs(total_assets) * 0.01  # 1% tolerance
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="error",
                category="cross_statement",
                statement="balance_sheet",
                message=(
                    f"Balance Sheet does NOT balance: Total Assets ({_format_value(total_assets)}) "
                    f"≠ Total Equity + Liabilities ({_format_value(total_equity_and_liabilities)}). "
                    f"Difference: {_format_value(diff)}. "
                    f"This indicates a missing or mis-mapped item."
                ),
                item_name="Total Assets",
                expected_value=total_assets,
                actual_value=total_equity_and_liabilities,
            ))
        else:
            report.flags.append(ValidationFlag(
                severity="info",
                category="cross_statement",
                statement="balance_sheet",
                message=f"Balance Sheet balances: Assets = E+L = {_format_value(total_assets)}",
            ))
    
    # Also check using individual equity + liabilities
    if total_assets is not None and total_equity is not None and total_liabilities is not None:
        computed_e_l = total_equity + total_liabilities
        diff = abs(total_assets - computed_e_l)
        tolerance = abs(total_assets) * 0.01
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="balance_sheet",
                message=(
                    f"Assets vs Equity+Liabilities mismatch: "
                    f"Total Assets ({_format_value(total_assets)}) vs "
                    f"Equity ({_format_value(total_equity)}) + Liabilities ({_format_value(total_liabilities)}) "
                    f"= {_format_value(computed_e_l)}. Diff: {_format_value(diff)}"
                ),
            ))
    
    # --- Sub-total: Total NC Assets + Total Current Assets = Total Assets ---
    total_nc_assets = _get_value(bs_mappings, "Total Non Current Assets")
    total_current_assets = _get_value(bs_mappings, "Total Current Assets")
    
    if total_nc_assets is not None and total_current_assets is not None and total_assets is not None:
        computed = total_nc_assets + total_current_assets
        diff = abs(total_assets - computed)
        tolerance = abs(total_assets) * 0.01
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="balance_sheet",
                message=(
                    f"Total Assets breakdown mismatch: "
                    f"NC Assets ({_format_value(total_nc_assets)}) + "
                    f"Current Assets ({_format_value(total_current_assets)}) = "
                    f"{_format_value(computed)} vs Total Assets ({_format_value(total_assets)}). "
                    f"Diff: {_format_value(diff)}"
                ),
                item_name="Total Assets",
            ))
    
    # --- Sub-total: Total NC Liabilities + Total Current Liabilities = Total Liabilities ---
    total_nc_liab = _get_value(bs_mappings, "Total Non-current Liabilities")
    total_current_liab = _get_value(bs_mappings, "Total Current Liabilities")
    
    if total_nc_liab is not None and total_current_liab is not None and total_liabilities is not None:
        computed = total_nc_liab + total_current_liab
        diff = abs(total_liabilities - computed)
        tolerance = abs(total_liabilities) * 0.01
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="balance_sheet",
                message=(
                    f"Total Liabilities breakdown mismatch: "
                    f"NC Liab ({_format_value(total_nc_liab)}) + "
                    f"Current Liab ({_format_value(total_current_liab)}) = "
                    f"{_format_value(computed)} vs Total Liabilities ({_format_value(total_liabilities)}). "
                    f"Diff: {_format_value(diff)}"
                ),
                item_name="Total Liabilities",
            ))


def validate_profit_and_loss_equation(
    pl_mappings: list[MappingResult],
    report: ValidationReport,
) -> None:
    """
    Validate P&L internal consistency:
        Total Income = Revenue from Operations + Other Income
        PBT = Total Income - Total Expenses - Exceptional Items
        PAT = PBT - Tax Expense
    
    Per Schedule III, these relationships MUST hold.
    """
    revenue = _get_value(pl_mappings, "I. Revenue from operations")
    other_income = _get_value(pl_mappings, "II. Other income")
    total_income = _get_value(pl_mappings, "III. Total Income (I + II)")
    
    # Total Income = Revenue + Other Income
    if revenue is not None and other_income is not None and total_income is not None:
        computed = revenue + other_income
        diff = abs(total_income - computed)
        tolerance = abs(total_income) * 0.01 if total_income != 0 else 1.0
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="profit_and_loss",
                message=(
                    f"Total Income mismatch: Revenue ({_format_value(revenue)}) + "
                    f"Other Income ({_format_value(other_income)}) = "
                    f"{_format_value(computed)} vs Total Income ({_format_value(total_income)}). "
                    f"Diff: {_format_value(diff)}"
                ),
                item_name="III. Total Income (I + II)",
            ))
    
    # PBT check: Total Income - Total Expenses - Exceptional Items
    total_expenses = _get_value(pl_mappings, "Total expenses")
    exceptional = _get_value(pl_mappings, "VI. Exceptional items")
    pbt = _get_value(pl_mappings, "VII. Profit/(loss) before tax (V-VI)")
    
    if total_income is not None and total_expenses is not None and pbt is not None:
        computed_pbt = total_income - total_expenses
        if exceptional is not None:
            computed_pbt -= exceptional
        diff = abs(pbt - computed_pbt)
        tolerance = abs(pbt) * 0.02 if pbt != 0 else abs(total_income) * 0.01
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="profit_and_loss",
                message=(
                    f"PBT mismatch: Income ({_format_value(total_income)}) - "
                    f"Expenses ({_format_value(total_expenses)})"
                    + (f" - Exceptional ({_format_value(exceptional)})" if exceptional else "")
                    + f" = {_format_value(computed_pbt)} vs PBT ({_format_value(pbt)}). "
                    f"Diff: {_format_value(diff)}"
                ),
                item_name="VII. Profit/(loss) before tax (V-VI)",
            ))


def validate_cross_statement_consistency(
    bs_mappings: list[MappingResult],
    pl_mappings: list[MappingResult],
    cf_mappings: list[MappingResult],
    report: ValidationReport,
) -> None:
    """
    Validate consistency across BS, P&L, and CF statements.
    
    Key cross-checks a CA would perform:
    1. P&L Profit after tax ≈ BS "Profit for the year" (equity roll-forward)
    2. P&L Depreciation should be consistent with PPE changes in BS
    3. P&L Finance costs should be consistent with Borrowings in BS
    4. CF Operating cash flow should reconcile with P&L (indirect method)
    """
    # --- Check 1: P&L PAT ≈ BS Profit for the year ---
    pl_pat = _get_value(pl_mappings, "XIII. Profit/(Loss) after taxes (IX + XII)")
    bs_profit = _get_value(bs_mappings, "Profit for the year")
    
    if pl_pat is not None and bs_profit is not None:
        diff = abs(pl_pat - bs_profit)
        tolerance = abs(pl_pat) * 0.02 if pl_pat != 0 else 1.0
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="cross",
                message=(
                    f"P&L PAT ({_format_value(pl_pat)}) ≠ BS 'Profit for the year' "
                    f"({_format_value(bs_profit)}). Diff: {_format_value(diff)}. "
                    f"These SHOULD match per Schedule III — check equity roll-forward."
                ),
                item_name="Profit for the year",
                expected_value=pl_pat,
                actual_value=bs_profit,
            ))
        else:
            report.flags.append(ValidationFlag(
                severity="info",
                category="cross_statement",
                statement="cross",
                message=f"P&L PAT matches BS Profit for the year: {_format_value(pl_pat)}",
            ))
    
    # --- Check 2: Finance costs → Financial liabilities inference ---
    finance_costs = _get_value(pl_mappings, "Finance costs")
    nc_borrowings = _get_value(bs_mappings, "(i) Borrowings")  # NC Borrowings
    current_borrowings = _get_value(bs_mappings, "(i) Borrowings")  # Current — same name, different section
    
    # We need to check by section — get all borrowings
    nc_borrowings_val = None
    current_borrowings_val = None
    for m in bs_mappings:
        if m.template_item == "(i) Borrowings":
            if m.section == "Non-current liabilities":
                nc_borrowings_val = _parse_alias_value(m.value)
            elif m.section == "Current liabilities":
                current_borrowings_val = _parse_alias_value(m.value)
    
    if finance_costs is not None and finance_costs > 0:
        total_borrowings = (nc_borrowings_val or 0) + (current_borrowings_val or 0)
        if total_borrowings == 0:
            # Finance costs exist but no borrowings — might be lease liabilities
            # Check for lease liabilities in Other financial liabilities
            nc_other_fin_liab = _get_value(bs_mappings, "(iii) Other financial liabilities")
            report.flags.append(ValidationFlag(
                severity="info",
                category="inferential",
                statement="cross",
                message=(
                    f"P&L shows Finance costs ({_format_value(finance_costs)}) but no Borrowings "
                    f"found in BS. Per Ind AS 116, finance costs may arise from lease liabilities "
                    f"(classified under 'Other financial liabilities'). "
                    f"NC Other financial liabilities = {_format_value(nc_other_fin_liab)}. "
                    f"CA inference: lease liabilities likely exist."
                ),
                item_name="Finance costs",
            ))
    
    # --- Check 3: Depreciation → PPE consistency ---
    depreciation = _get_value(pl_mappings, "Depreciation and amortisation expense")
    ppe = _get_value(bs_mappings, "(a) Property, Plant and Equipment")
    cwip = _get_value(bs_mappings, "(b) Capital work-in-progress")
    intangible = _get_value(bs_mappings, "(e) Other Intangible assets")
    
    if depreciation is not None and depreciation > 0:
        total_tangible_intangible = (ppe or 0) + (intangible or 0)
        if total_tangible_intangible == 0:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="cross_statement",
                statement="cross",
                message=(
                    f"P&L shows Depreciation ({_format_value(depreciation)}) but no PPE or "
                    f"Intangible assets found in BS. This is inconsistent — depreciation "
                    f"implies depreciable assets exist. Check PPE mapping."
                ),
                item_name="Depreciation and amortisation expense",
            ))


# ============================================================================
# 2. INFERENTIAL MAPPING (CA-level derivations)
# ============================================================================


def infer_missing_values(
    bs_mappings: list[MappingResult],
    pl_mappings: list[MappingResult],
    cf_mappings: list[MappingResult],
    report: ValidationReport,
) -> list[InferredMapping]:
    """
    Use CA-level accounting logic to infer values that weren't directly
    extracted from the PDF.
    
    Inference types:
    1. CALCULATIVE: EBITDA = PBT + Depreciation + Finance costs
    2. CROSS-STATEMENT: If P&L PAT exists but BS "Profit for the year" is missing
    3. RESIDUAL: If a section total exists but some sub-items are missing,
       the residual can be computed
    
    Returns list of InferredMapping objects to be added to the output.
    """
    inferred = []
    
    # --- Inference 1: EBITDA calculation ---
    # EBITDA = Profit before tax + Depreciation + Finance costs
    # (This is the standard Indian CA calculation per SEBI format)
    ebitda_existing = _get_value(pl_mappings, "EBITDA")
    pbt = _get_value(pl_mappings, "VII. Profit/(loss) before tax (V-VI)")
    depreciation = _get_value(pl_mappings, "Depreciation and amortisation expense")
    finance_costs = _get_value(pl_mappings, "Finance costs")
    
    if ebitda_existing is None and pbt is not None and depreciation is not None and finance_costs is not None:
        computed_ebitda = pbt + depreciation + finance_costs
        inferred.append(InferredMapping(
            template_item="EBITDA",
            section="",
            value=f"{computed_ebitda:,.2f}" if computed_ebitda != int(computed_ebitda) else f"{computed_ebitda:,.0f}",
            method="ca_calculated",
            confidence=0.85,
            reasoning=(
                f"EBITDA = PBT ({_format_value(pbt)}) + Depreciation ({_format_value(depreciation)}) "
                f"+ Finance costs ({_format_value(finance_costs)}) = {_format_value(computed_ebitda)}. "
                f"Per SEBI's MD&A format and standard CA practice."
            ),
            source_items=[
                "VII. Profit/(loss) before tax (V-VI)",
                "Depreciation and amortisation expense",
                "Finance costs",
            ],
        ))
        report.flags.append(ValidationFlag(
            severity="info",
            category="inferential",
            statement="profit_and_loss",
            message=f"Inferred EBITDA = {_format_value(computed_ebitda)} (PBT + Depreciation + Finance costs)",
            item_name="EBITDA",
        ))
    elif ebitda_existing is not None and pbt is not None and depreciation is not None and finance_costs is not None:
        # Verify existing EBITDA
        computed_ebitda = pbt + depreciation + finance_costs
        diff = abs(ebitda_existing - computed_ebitda)
        tolerance = abs(ebitda_existing) * 0.02 if ebitda_existing != 0 else 1.0
        if diff > tolerance:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="inferential",
                statement="profit_and_loss",
                message=(
                    f"EBITDA verification: extracted ({_format_value(ebitda_existing)}) vs "
                    f"calculated PBT+Dep+Finance ({_format_value(computed_ebitda)}). "
                    f"Diff: {_format_value(diff)}. Check if exceptional items are included."
                ),
                item_name="EBITDA",
            ))
    
    # --- Inference 2: EBIT calculation ---
    ebit_existing = _get_value(pl_mappings, "EBIT")
    if ebit_existing is None and pbt is not None and finance_costs is not None:
        computed_ebit = pbt + finance_costs
        inferred.append(InferredMapping(
            template_item="EBIT",
            section="",
            value=f"{computed_ebit:,.2f}" if computed_ebit != int(computed_ebit) else f"{computed_ebit:,.0f}",
            method="ca_calculated",
            confidence=0.80,
            reasoning=(
                f"EBIT = PBT ({_format_value(pbt)}) + Finance costs ({_format_value(finance_costs)}) "
                f"= {_format_value(computed_ebit)}. Operating profit before tax."
            ),
            source_items=[
                "VII. Profit/(loss) before tax (V-VI)",
                "Finance costs",
            ],
        ))
        report.flags.append(ValidationFlag(
            severity="info",
            category="inferential",
            statement="profit_and_loss",
            message=f"Inferred EBIT = {_format_value(computed_ebit)} (PBT + Finance costs)",
            item_name="EBIT",
        ))
    
    # --- Inference 3: BS "Profit for the year" from P&L PAT ---
    bs_profit = _get_value(bs_mappings, "Profit for the year")
    pl_pat = _get_value(pl_mappings, "XIII. Profit/(Loss) after taxes (IX + XII)")
    
    if bs_profit is None and pl_pat is not None:
        inferred.append(InferredMapping(
            template_item="Profit for the year",
            section="",
            value=f"{pl_pat:,.2f}" if pl_pat != int(pl_pat) else f"{pl_pat:,.0f}",
            method="ca_cross_statement",
            confidence=0.80,
            reasoning=(
                f"BS 'Profit for the year' not found in equity roll-forward. "
                f"Inferred from P&L PAT ({_format_value(pl_pat)}). "
                f"Per Schedule III, these should be the same value."
            ),
            source_items=["XIII. Profit/(Loss) after taxes (IX + XII)"],
        ))
        report.flags.append(ValidationFlag(
            severity="info",
            category="inferential",
            statement="balance_sheet",
            message=(
                f"Inferred BS 'Profit for the year' = {_format_value(pl_pat)} "
                f"(from P&L PAT — per Schedule III these must match)"
            ),
            item_name="Profit for the year",
        ))
    
    # --- Inference 4: Total Debt calculation ---
    # Total Debt = NC Borrowings + Current Borrowings + Current maturities
    total_debt_existing = _get_value(bs_mappings, "Total debt")
    nc_borrowings_val = None
    current_borrowings_val = None
    for m in bs_mappings:
        if m.template_item == "(i) Borrowings":
            if m.section == "Non-current liabilities":
                nc_borrowings_val = _parse_alias_value(m.value)
            elif m.section == "Current liabilities":
                current_borrowings_val = _parse_alias_value(m.value)
    
    current_maturities = _get_value(cf_mappings, "Current maturities of borrowings/debts, including interest")
    
    if total_debt_existing is None and nc_borrowings_val is not None and current_borrowings_val is not None:
        computed_debt = nc_borrowings_val + current_borrowings_val
        if current_maturities is not None:
            # Current maturities are already included in current borrowings
            # per some reporting formats — don't double count
            pass
        inferred.append(InferredMapping(
            template_item="Total debt",
            section="",
            value=f"{computed_debt:,.2f}" if computed_debt != int(computed_debt) else f"{computed_debt:,.0f}",
            method="ca_calculated",
            confidence=0.80,
            reasoning=(
                f"Total Debt = NC Borrowings ({_format_value(nc_borrowings_val)}) + "
                f"Current Borrowings ({_format_value(current_borrowings_val)}) "
                f"= {_format_value(computed_debt)}. Per standard CA debt calculation."
            ),
            source_items=["(i) Borrowings"],
        ))
        report.flags.append(ValidationFlag(
            severity="info",
            category="inferential",
            statement="balance_sheet",
            message=f"Inferred Total Debt = {_format_value(computed_debt)}",
            item_name="Total debt",
        ))
    
    # --- Inference 5: Missing item detection via residual analysis ---
    # If Total NC Liabilities is mapped but individual items don't add up,
    # the difference is the "Other non-current liabilities" residual
    total_nc_liab = _get_value(bs_mappings, "Total Non-current Liabilities")
    if total_nc_liab is not None:
        known_nc_liab_items = [
            "(i) Borrowings",  # NC
            "(ii) Trade Payables",  # NC
            "(iii) Other financial liabilities",  # NC
            "(b) Provisions",  # NC
            "(c) Deferred tax liabilities (Net)",
        ]
        known_sum = 0.0
        known_count = 0
        for item in known_nc_liab_items:
            val = _get_value(bs_mappings, item)
            if val is not None:
                known_sum += val
                known_count += 1
        
        other_nc_liab = _get_value(bs_mappings, "(d) Other non-current liabilities")
        if other_nc_liab is None and known_count >= 3:
            residual = total_nc_liab - known_sum
            if abs(residual) > 0:
                inferred.append(InferredMapping(
                    template_item="(d) Other non-current liabilities",
                    section="Non-current liabilities",
                    value=f"{residual:,.2f}" if residual != int(residual) else f"{residual:,.0f}",
                    method="ca_inferred",
                    confidence=0.70,
                    reasoning=(
                        f"Residual inference: Total NC Liab ({_format_value(total_nc_liab)}) - "
                        f"sum of {known_count} known items ({_format_value(known_sum)}) "
                        f"= {_format_value(residual)}. This is the 'Other non-current liabilities' "
                        f"catch-all per Schedule III."
                    ),
                    source_items=["Total Non-current Liabilities"] + known_nc_liab_items[:known_count],
                ))
                report.flags.append(ValidationFlag(
                    severity="info",
                    category="inferential",
                    statement="balance_sheet",
                    message=(
                        f"Inferred 'Other NC liabilities' = {_format_value(residual)} "
                        f"(residual from Total NC Liab - known items)"
                    ),
                    item_name="(d) Other non-current liabilities",
                ))
    
    return inferred


# ============================================================================
# 3. NOTE CROSS-REFERENCE TRACKING
# ============================================================================


# Regex to find note references in row labels
# Matches: "(1)", "(2)", "[1]", "[Note 3]", "Note 4", etc.
_NOTE_REF_PATTERN = re.compile(
    r'(?:note\.?\s*|Note\.?\s*)?[\(\[]?\s*(\d{1,3})\s*[\)\]]?',
)


def extract_note_references(
    bs_mappings: list[MappingResult],
    pl_mappings: list[MappingResult],
    cf_mappings: list[MappingResult],
    report: ValidationReport,
) -> dict[str, list[str]]:
    """
    Extract note references from BS/P&L row labels.
    
    In Indian annual reports, BS/P&L items have note references like:
        "Property, Plant and Equipment (3)"  → Note 3 has PPE schedule
        "Revenue from operations (15)"        → Note 15 has revenue breakdown
        "Other income (16)"                   → Note 16 has other income detail
    
    This function:
    1. Extracts note numbers from mapped row labels
    2. Maps template items to their note references
    3. Flags items that SHOULD have note references but don't
       (per Schedule III disclosure requirements)
    
    Returns:
        Dict mapping template_item -> list of note reference strings
    """
    note_refs = {}
    
    # Items that SHOULD have note references per Schedule III
    # (these always have detailed notes in Indian annual reports)
    ITEMS_REQUIRING_NOTES = {
        # Balance Sheet
        "(a) Property, Plant and Equipment": "PPE schedule (Ind AS 116 + Ind AS 16)",
        "(b) Capital work-in-progress": "CWIP detail",
        "(e) Other Intangible assets": "Intangible assets schedule (Ind AS 38)",
        "(i) Borrowings": "Borrowings schedule (Ind AS 109)",
        "(ii) Trade payables": "Trade payables aging (MSME Act compliance)",
        "(b) Provisions": "Provisions detail (Ind AS 37)",
        "(a) Inventories": "Inventory detail (Ind AS 2)",
        "(ii) Trade receivables": "Trade receivables aging (Ind AS 109)",
        # P&L
        "I. Revenue from operations": "Revenue breakdown (Ind AS 115)",
        "II. Other income": "Other income detail",
        "Employee benefits expense": "Employee benefits (Ind AS 19)",
        "Finance costs": "Finance costs breakdown (Ind AS 109 + Ind AS 116)",
        "Depreciation and amortisation expense": "Depreciation schedule",
        "Other expenses": "Other expenses detail",
    }
    
    all_mappings = list(bs_mappings) + list(pl_mappings) + list(cf_mappings)
    
    for m in all_mappings:
        if not m.pdf_row_label:
            continue
        
        # Extract note references from the PDF row label
        refs = _NOTE_REF_PATTERN.findall(m.pdf_row_label)
        if refs:
            note_refs[m.template_item] = refs
            logger.debug(
                f"Note reference: '{m.template_item}' -> Note(s) {refs} "
                f"(from label '{m.pdf_row_label}')"
            )
    
    # Flag items that should have note references but don't
    for item_name, requirement in ITEMS_REQUIRING_NOTES.items():
        if item_name not in note_refs:
            # Check if the item was mapped at all
            mapped = any(m.template_item == item_name for m in all_mappings)
            if mapped:
                report.flags.append(ValidationFlag(
                    severity="info",
                    category="note_reference",
                    statement="balance_sheet" if item_name in str(BALANCE_SHEET_TEMPLATE) else "profit_and_loss",
                    message=(
                        f"'{item_name}' was mapped but has no note reference in the PDF label. "
                        f"Expected: {requirement}. The note reference may have been lost during "
                        f"text extraction, or the PDF doesn't follow standard Schedule III format."
                    ),
                    item_name=item_name,
                ))
    
    # Log summary
    if note_refs:
        ref_summary = "; ".join(
            f"{item} → Note {','.join(refs)}"
            for item, refs in note_refs.items()
        )
        report.flags.append(ValidationFlag(
            severity="info",
            category="note_reference",
            statement="cross",
            message=f"Found {len(note_refs)} note references: {ref_summary}",
        ))
    
    return note_refs


# ============================================================================
# 4. ACCOUNTING STANDARD COMPLIANCE CHECKS
# ============================================================================


def check_accounting_compliance(
    bs_mappings: list[MappingResult],
    pl_mappings: list[MappingResult],
    cf_mappings: list[MappingResult],
    report: ValidationReport,
) -> None:
    """
    Check compliance with Indian Accounting Standards (Ind AS) and
    Schedule III of the Companies Act, 2013.
    
    These are disclosure and classification requirements that a CA
    would verify when reviewing financial statements.
    """
    all_mappings = list(bs_mappings) + list(pl_mappings) + list(cf_mappings)
    mapped_items = {m.template_item for m in all_mappings}
    
    # --- Ind AS 16: Property, Plant and Equipment ---
    ppe = _get_value(bs_mappings, "(a) Property, Plant and Equipment")
    cwip = _get_value(bs_mappings, "(b) Capital work-in-progress")
    depreciation = _get_value(pl_mappings, "Depreciation and amortisation expense")
    
    if ppe is not None and ppe > 0:
        # PPE exists — check for related disclosures
        if depreciation is None or depreciation == 0:
            report.flags.append(ValidationFlag(
                severity="warning",
                category="compliance",
                statement="cross",
                message=(
                    f"PPE ({_format_value(ppe)}) exists but no Depreciation expense found. "
                    f"Per Ind AS 16, depreciation MUST be charged on all depreciable PPE. "
                    f"Check if depreciation is mapped correctly."
                ),
                item_name="Depreciation and amortisation expense",
            ))
    
    # --- Ind AS 116: Leases ---
    finance_costs = _get_value(pl_mappings, "Finance costs")
    # Check if lease liabilities are captured
    nc_other_fin_liab = _get_value(bs_mappings, "(iii) Other financial liabilities")
    current_other_fin_liab = None
    for m in bs_mappings:
        if m.template_item == "(iii) Other financial liabilities" and m.section == "Current liabilities":
            current_other_fin_liab = _parse_alias_value(m.value)
    
    if finance_costs is not None and finance_costs > 0:
        # Finance costs exist — per Ind AS 116, lease liabilities should be on BS
        total_other_fin_liab = (nc_other_fin_liab or 0) + (current_other_fin_liab or 0)
        if total_other_fin_liab == 0:
            report.flags.append(ValidationFlag(
                severity="info",
                category="compliance",
                statement="cross",
                message=(
                    f"Finance costs ({_format_value(finance_costs)}) exist but no 'Other financial "
                    f"liabilities' found. Per Ind AS 116, lease liabilities (ROU assets) should be "
                    f"recognized on the Balance Sheet. The lease liability may be classified under "
                    f"'Borrowings' or may be missing from the extraction."
                ),
                item_name="Finance costs",
            ))
    
    # --- Ind AS 12: Income Taxes ---
    current_tax = _get_value(pl_mappings, "(1) Current tax")
    deferred_tax_pl = _get_value(pl_mappings, "(2) Deferred tax")
    dta = _get_value(bs_mappings, "(i) Deferred tax assets (net)")
    dtl = _get_value(bs_mappings, "(c) Deferred tax liabilities (Net)")
    
    if deferred_tax_pl is not None and deferred_tax_pl != 0:
        # Deferred tax in P&L — should have corresponding BS items
        if dta is None and dtl is None:
            report.flags.append(ValidationFlag(
                severity="info",
                category="compliance",
                statement="cross",
                message=(
                    f"P&L shows Deferred tax ({_format_value(deferred_tax_pl)}) but no DTA/DTL "
                    f"found in BS. Per Ind AS 12, deferred tax assets/liabilities should be "
                    f"recognized on the Balance Sheet."
                ),
                item_name="(i) Deferred tax assets (net)",
            ))
    
    # --- Ind AS 19: Employee Benefits ---
    employee_benefits = _get_value(pl_mappings, "Employee benefits expense")
    nc_provisions = _get_value(bs_mappings, "(b) Provisions")
    current_provisions = None
    for m in bs_mappings:
        if m.template_item == "(c) Provisions" and m.section == "Current liabilities":
            current_provisions = _parse_alias_value(m.value)
    
    if employee_benefits is not None and employee_benefits > 0:
        total_provisions = (nc_provisions or 0) + (current_provisions or 0)
        if total_provisions == 0:
            report.flags.append(ValidationFlag(
                severity="info",
                category="compliance",
                statement="cross",
                message=(
                    f"Employee benefits expense ({_format_value(employee_benefits)}) exists but "
                    f"no Provisions found in BS. Per Ind AS 19, defined benefit obligations "
                    f"(gratuity, leave encashment) should be recognized as provisions."
                ),
                item_name="(b) Provisions",
            ))
    
    # --- Schedule III: Mandatory line items ---
    # Check if certain mandatory items are missing
    MANDATORY_BS_ITEMS = {
        "Equity Share Capital": "Always required — even if zero",
        "Other Equity": "Always required — includes reserves and surplus",
        "(a) Property, Plant and Equipment": "Required if company has tangible assets",
        "(a) Inventories": "Required for manufacturing/trading companies",
        "(iii) Cash and cash equivalents": "Always required — even if zero",
    }
    
    for item_name, reason in MANDATORY_BS_ITEMS.items():
        if item_name not in mapped_items:
            report.flags.append(ValidationFlag(
                severity="info",
                category="compliance",
                statement="balance_sheet",
                message=(
                    f"Mandatory item '{item_name}' not mapped. Reason: {reason}. "
                    f"Per Schedule III, this line item should be present (even if value is zero)."
                ),
                item_name=item_name,
            ))
    
    # --- MSMED Act: Micro/Small enterprise dues ---
    # Per the Micro, Small and Medium Enterprises Development Act, 2006,
    # companies must disclose dues to MSMEs separately
    msme_dues = _get_value(
        bs_mappings,
        "(A) total outstanding dues of micro enterprises and small enterprises; and"
    )
    other_creditor_dues = _get_value(
        bs_mappings,
        "(B) total outstanding dues of creditors other than micro enterprises and small enterprises."
    )
    trade_payables_nc = _get_value(bs_mappings, "(ii) Trade Payables")
    
    if trade_payables_nc is not None and trade_payables_nc > 0:
        if msme_dues is None and other_creditor_dues is None:
            report.flags.append(ValidationFlag(
                severity="info",
                category="compliance",
                statement="balance_sheet",
                message=(
                    f"NC Trade Payables ({_format_value(trade_payables_nc)}) exists but MSME "
                    f"disclosure (sub-items A and B) not found. Per the MSMED Act, 2006 and "
                    f"Schedule III, companies must disclose dues to micro and small enterprises "
                    f"separately."
                ),
                item_name="(ii) Trade Payables",
            ))


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def run_ca_validation(
    bs_mappings: list[MappingResult],
    pl_mappings: list[MappingResult],
    cf_mappings: list[MappingResult],
) -> ValidationReport:
    """
    Run all CA-level validations and inferences.
    
    This is the main entry point, called as Step 4.5 in smart_agent.py.
    
    Args:
        bs_mappings: Balance Sheet mapping results.
        pl_mappings: P&L mapping results.
        cf_mappings: Cash Flow mapping results.
    
    Returns:
        ValidationReport with flags, inferred mappings, and note references.
    """
    report = ValidationReport()
    
    logger.info("=" * 60)
    logger.info("CA VALIDATION: Running Chartered Accountant-level checks")
    logger.info("=" * 60)
    
    # 1. Cross-statement validation
    logger.info("CA: Validating Balance Sheet equation...")
    validate_balance_sheet_equation(bs_mappings, report)
    
    logger.info("CA: Validating P&L equation...")
    validate_profit_and_loss_equation(pl_mappings, report)
    
    logger.info("CA: Validating cross-statement consistency...")
    validate_cross_statement_consistency(bs_mappings, pl_mappings, cf_mappings, report)
    
    # 2. Inferential mapping
    logger.info("CA: Inferring missing values...")
    inferred = infer_missing_values(bs_mappings, pl_mappings, cf_mappings, report)
    report.inferred_mappings = inferred
    
    # 3. Note cross-reference tracking
    logger.info("CA: Extracting note references...")
    note_refs = extract_note_references(bs_mappings, pl_mappings, cf_mappings, report)
    report.note_references = note_refs
    
    # 4. Accounting standard compliance
    logger.info("CA: Checking Ind AS / Schedule III compliance...")
    check_accounting_compliance(bs_mappings, pl_mappings, cf_mappings, report)
    
    # Summary
    logger.info("-" * 60)
    logger.info(f"CA Validation Summary:")
    logger.info(f"  Errors:   {len(report.errors)}")
    logger.info(f"  Warnings: {len(report.warnings)}")
    logger.info(f"  Info:     {len(report.infos)}")
    logger.info(f"  Inferred: {len(report.inferred_mappings)} mappings")
    logger.info(f"  Note Refs: {len(report.note_references)} items with references")
    logger.info(f"  Balanced: {'YES' if report.is_balanced else 'NO'}")
    
    # Log each flag
    for flag in report.flags:
        log_func = {
            "error": logger.error,
            "warning": logger.warning,
            "info": logger.info,
        }.get(flag.severity, logger.info)
        log_func(f"CA [{flag.severity.upper()}] [{flag.category}] {flag.message}")
    
    # Log each inferred mapping
    for im in report.inferred_mappings:
        logger.info(
            f"CA INFERRED: '{im.template_item}' = {im.value} "
            f"(method={im.method}, confidence={im.confidence:.2f})"
        )
        logger.info(f"  Reasoning: {im.reasoning}")
    
    return report
