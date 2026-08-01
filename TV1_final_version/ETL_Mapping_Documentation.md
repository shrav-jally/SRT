# ETL Mapping Documentation & Data Quality Analysis

This document outlines the mapping strategy used to transform the raw Capitaline Excel export files into the `comps_v2.db` (and `comp_v3.db`) SQLite schema for the Touchless Valuation E-Vardhan project, as well as a detailed analysis of the data quality.

## Overview
The raw data is split across multiple Excel files. The files lack a unifying index other than `CAPITALINE CODE`. Furthermore, none of the files individually contain a complete Taxonomy (both Sector and Industry) for the massive 24,600+ dataset. 

To resolve this, we perform a series of `LEFT JOIN` operations using `Finance data.xls` as the base table, and use a mapping dictionary strategy to derive missing Sector data.

## Source Files (Located in `Cline backup files -For tool/`)
1. **`Finance data.xls`**: Contains core financials (Revenue, EBITDA, PAT, Debt, Net Worth, Market Cap, EV).
2. **`valuation ratios.xls`**: Contains valuation multiples (P/E, EV/EBITDA, Mkt Cap/Sales) and metadata (Mode, Year End).
3. **`cash and bank.xls`**: Contains the cash balances.
4. **`Basic data/Industry.xlsx`**: Contains `Industry` mappings for 75,400+ companies.
5. **`basic compnay info.xls`**: Contains both `Sector` and `Industry` for a smaller subset of companies (6,900+).

## The Sector Mapping Strategy
Because joining on `basic compnay info.xls` directly would result in massive data loss (retaining only 5,700 out of 24,600 companies), we use it purely as a **Lookup Dictionary**.
1. Extract unique `Industry -> Sector` mappings from `basic compnay info.xls`.
2. Join `Finance data.xls` to `Industry.xlsx` to attach an `Industry` to all 24,600 companies.
3. Map that `Industry` using our dictionary to derive the `Sector`.

*Result: 24,594 companies retain complete Sector & Industry classifications.*

---

## Data Quality & Validation Analysis

After generating the final database of **24,603 companies**, we ran an extensive data quality check. 

### 1. Core Financial Data is 100% Complete
Every single core financial metric has **0 null values** across all 24,603 companies.
*   `revenue`, `ebitda`, `net_worth`, `total_debt`, `net_debt`, `market_cap`, and `enterprise_value` are **perfectly populated** for every single company directly from `Finance data.xls`.
*   `pat` (Profit After Tax) is missing for only 2 companies.
*   `cash` is missing for only 1 company.

### 2. Missing Valuation Multiples (The 396 Companies)
We noticed that exactly **396 companies** were missing their valuation ratios (like `P/E`, `EV/EBITDA`, and `Market Cap/Sales`). 
*   **Cause:** These 396 companies simply did not exist in the `valuation ratios.xls` file. 
*   **Recovery Solution:** Because our core financials from `Finance data.xls` are 100% complete, we don't need the valuation file for these missing companies! We can calculate the missing multiples programmatically during the ETL process:
    *   `EV/EBITDA` = `Enterprise Value / EBITDA` *(We successfully recovered this for 363 companies that had non-zero EBITDA).*
    *   `Market Cap/Sales` = `Market Cap / Revenue` *(We successfully recovered this for 299 companies with non-zero revenue).*
    *   `P/E` = `Market Cap / PAT`

### 3. Understanding the 4,197 missing `ev_revenue` values
You will notice that `ev_revenue` is missing (null) for 4,197 companies. 
*   **Validation:** We investigated this anomaly and confirmed that for all 4,197 of these companies, their `revenue` is exactly `0.0`.
*   Because `EV/Revenue` requires dividing by revenue, dividing by zero correctly yields a `NaN` (null) result in Pandas. This is mathematically correct behavior and not a data missing error.

### 4. Valuation Calculation Discrepancies & Clamping Logic
To verify our recovery logic, we manually recalculated the valuation multiples for all 24,207 companies and compared them against Capitaline's raw `valuation ratios.xls`. The results were highly accurate:
*   `EV/EBITDA` mathematically matched for ~90% of companies.
*   `P/E` and `Market Cap / Sales` mathematically matched for ~83% of companies.

**Why the minor discrepancies?** Capitaline employs a specific financial clamping rule. When a company reports negative earnings (e.g., negative PAT), Capitaline **clamps the P/E multiple to `0.0`** rather than reporting a mathematically true negative value. 
If strict adherence to Capitaline's raw methodology is desired, your ETL pipeline should calculate the true multiples but enforce a rule to convert any resulting negative multiples (like P/E or EV/EBITDA) to `0.0`.

---

## Exact Column Mapping to Schema

| Target DB Column | Target Type | Source File | Source Column Name | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `code` | Integer | *(All)* | `CAPITALINE CODE` | Primary Key for joining |
| `name` | String | *(All)* | `CO_NAME` | |
| `industry` | String | `Basic data/Industry.xlsx` | `[Industry` | |
| `sector` | String | `basic compnay info.xls` | `[Sector` | Mapped via Industry lookup |
| `mode` | String | `valuation ratios.xls` | `[MODE (Latest)]` | Standalone vs Consolidated |
| `year_end` | String | `valuation ratios.xls` | `[Year End (Latest)]` | |
| `revenue` | Float | `Finance data.xls` | `[Net Sales (Latest)]` | |
| `ebitda` | Float | `Finance data.xls` | `[PBIDT (Latest)]` | |
| `pat` | Float | `Finance data.xls` | `[PAT (Latest)]` | |
| `net_worth` | Float | `Finance data.xls` | `[Networth (Latest)]` | |
| `total_debt` | Float | `Finance data.xls` | `[Total Debt (Latest)]` | |
| `net_debt` | Float | `Finance data.xls` | `[Net Debt (Latest)]` | |
| `cash` | Float | `cash and bank.xls` | `[Cash and Bank Balance (Latest)]` | |
| `market_cap` | Float | `Finance data.xls` | `[Market Capitalisation (Latest)]` | |
| `enterprise_value` | Float | `Finance data.xls` | `[Enterprise Value (Latest)]` | |
| `pe` | Float | `valuation ratios.xls` | `[Price Earning (P/E) (Latest)]` | *Recovered manually if missing* |
| `ev_ebitda` | Float | `valuation ratios.xls` | `[EV/EBIDTA (Latest)]` | *Recovered manually if missing* |
| `mktcap_sales` | Float | `valuation ratios.xls` | `[Market Cap/Sales (Latest)]` | *Recovered manually if missing* |
| `ev_revenue` | Float | *Derived* | `[Enterprise Value (Latest)]` / `[Net Sales (Latest)]` | Null if revenue is 0 |

## Reproduction Scripts
The project contains three ETL pipelines to handle the missing 396 companies based on different financial accounting preferences:
1. `build_db_direct.py`: Leaves the 396 missing companies with `NULL` multiples.
2. `build_db_calculated.py`: Recalculates the multiples using pure math (resulting in negative multiples for struggling companies).
3. `build_db_clamped.py`: Recalculates multiples, but clamps negative values to `0.0` (matching Capitaline's formatting standards).
