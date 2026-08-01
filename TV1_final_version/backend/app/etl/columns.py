"""
Verified 0-based column maps for the five Capitaline (.xls) extracts in
SOURCE_DIR. Indices were confirmed by reading the actual file headers.

The valuation-ratios and finance files lay out up to seven *price snapshots*
horizontally as (Latest), (Latest1) ... (Latest6) — all for the SAME year-end.
Block 0 (Latest) is the current snapshot; later blocks are fallbacks used only
when the current cell is 0 (0 == not-applicable / not-reported in this source).
"""

# -------- basic company info (taxonomy) --------
BASIC_FILE = "basic compnay info.xls"
BASIC = {
    "long_name": 2,
    "sector": 3,          # 84 distinct — the top-level group
    "industry": 4,        # 304 distinct — the sub-sector used for tight peers
    "macro_sector": 5,
}

# -------- finance (Latest block only; sector-aware) --------
FINANCE_FILE = "Finance data.xls"
FINANCE = {
    "net_worth": 3,
    "capital_employed": 4,
    "total_debt": 5,
    "net_debt": 6,
    "net_sales": 11,          # 0 for banks/NBFCs (they report interest income)
    "other_income": 12,
    "ebitda": 16,             # PBIDT (Latest)
    "pbdt": 18,
    "ebit": 19,               # PBIT (Latest)
    "pbt": 20,
    "pat": 21,
    "market_cap": 24,
    "enterprise_value": 26,
    "ebitda_margin_pct": 29,  # PBIDTM (%)
    "interest_earned": 40,    # banks/NBFCs
    "total_income": 41,       # banks/NBFCs — revenue proxy
    "net_interest_income": 43,
}

# -------- valuation ratios (7 horizontal snapshot blocks) --------
RATIOS_FILE = "valuation ratios.xls"
# Each metric's column across the 7 blocks, in current->older preference order.
RATIO_BLOCKS = {
    "year_end":      [2, 11, 20, 29, 38, 47, 56],
    "pe":            [3, 12, 21, 30, 39, 48, 57],
    "pbv":           [4, 13, 22, 31, 40, 49, 58],
    "ev_ebitda":     [6, 15, 24, 33, 42, 51, 60],
    "mktcap_sales":  [7, 16, 25, 34, 43, 52, 61],
    "mode":          [8, 19, 28, 37, 46, 55, 64],  # 'S'=standalone 'C'=consolidated
}

# -------- finance HISTORY (7 annual periods, newest first) --------
# Verified against real companies (e.g. KEI net worth 779->5786 monotone):
# block 0 = latest FY, block k = k years earlier. Block 1 is the bank-format
# variant and carries no Sales column for non-banks (None -> gap at t-1).
FINANCE_HISTORY = {
    "sales":            [11, None, 61, 87, 113, 140, 166],
    "ebitda":           [16, 44, 62, 88, 114, 141, 167],   # PBIDT
    "pat":              [21, 49, 67, 93, 119, 146, 172],
    "net_worth":        [3, 36, 56, 82, 108, 135, 161],
    "capital_employed": [4, 37, 57, 83, 109, 136, 162],
    "total_debt":       [5, 38, 58, 84, 110, 137, 163],
    "market_cap":       [24, 52, 70, 96, 122, 149, 175],
}
N_HISTORY = 7

# -------- cash & bank --------
CASH_FILE = "cash and bank.xls"
CASH = {"cash": 2}
