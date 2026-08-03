import pandas as pd
import sqlite3
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def get_codes(df):
    col = df.columns[0]
    return pd.to_numeric(df[col], errors='coerce')

def build_db():
    print("1. Extracting data...")
    # Load basic info for lookup
    basic_df = pd.read_excel("Cline backup files -For tool/basic compnay info.xls")
    sector_col = next((c for c in basic_df.columns if 'sector' in str(c).lower()), None)
    ind_col = next((c for c in basic_df.columns if 'industry' in str(c).lower()), None)
    
    basic_df['ind_clean'] = basic_df[ind_col].astype(str).str.strip().str.lower()
    basic_df['sec_clean'] = basic_df[sector_col].astype(str).str.strip()
    mapping_df = basic_df[(basic_df['ind_clean'] != 'nan') & (basic_df['sec_clean'] != 'nan')]
    industry_to_sector = dict(zip(mapping_df['ind_clean'], mapping_df['sec_clean']))

    # Load Industry mapping
    ind_df = pd.read_excel("Cline backup files -For tool/Basic data/Industry.xlsx")
    code_col_ind = ind_df.columns[0]
    ind_cat_col = next((c for c in ind_df.columns if 'industry' in str(c).lower()), None)
    ind_df['code'] = get_codes(ind_df)
    ind_df['industry'] = ind_df[ind_cat_col].astype(str).str.strip()
    ind_df['sector'] = ind_df['industry'].str.lower().map(industry_to_sector)

    # Load Valuation
    val_df = pd.read_excel("Cline backup files -For tool/valuation ratios.xls")
    val_df['code'] = get_codes(val_df)
    
    # Load Cash
    cash_df = pd.read_excel("Cline backup files -For tool/cash and bank.xls")
    cash_df['code'] = get_codes(cash_df)

    # Load Finance (Base table)
    fin_df = pd.read_excel("Cline backup files -For tool/Finance data.xls")
    fin_df['code'] = get_codes(fin_df)
    
    print("2. Transforming and Joining...")
    # Clean codes and drop un-joinable rows
    fin_df = fin_df.dropna(subset=['code'])
    ind_df = ind_df.dropna(subset=['code'])
    val_df = val_df.dropna(subset=['code'])
    cash_df = cash_df.dropna(subset=['code'])
    
    # Left join everything onto Finance
    merged = fin_df.merge(ind_df[['code', 'industry', 'sector']], on='code', how='left')
    merged = merged.merge(val_df[['code', '[Price Earning (P/E) (Latest)]', '[EV/EBIDTA (Latest)]', '[Market Cap/Sales (Latest)]', '[MODE (Latest)]', '[Year End (Latest)]']], on='code', how='left')
    merged = merged.merge(cash_df[['code', '[Cash and Bank Balance (Latest)]']], on='code', how='left')

    print("3. Mapping to Schema and Recovering Data...")
    # Rename columns to match db schema
    rename_map = {
        'CAPITALINE CODE': 'code_old', 
        'CO_NAME': 'name',
        '[Net Sales (Latest)]': 'revenue',
        '[PBIDT (Latest)]': 'ebitda',
        '[PAT (Latest)]': 'pat',
        '[Networth (Latest)]': 'net_worth',
        '[Total Debt (Latest)]': 'total_debt',
        '[Net Debt (Latest)]': 'net_debt',
        '[Market Capitalisation (Latest)]': 'market_cap',
        '[Enterprise Value (Latest)]': 'enterprise_value',
        '[Price Earning (P/E) (Latest)]': 'pe',
        '[EV/EBIDTA (Latest)]': 'ev_ebitda',
        '[Market Cap/Sales (Latest)]': 'mktcap_sales',
        '[MODE (Latest)]': 'mode',
        '[Year End (Latest)]': 'year_end',
        '[Cash and Bank Balance (Latest)]': 'cash'
    }
    
    merged = merged.rename(columns=rename_map)
    
    # Deriving ev_revenue
    merged['ev_revenue'] = merged['enterprise_value'] / merged['revenue']
    
    # RECOVER MISSING MULTIPLES (For the 396 companies missing in valuation file)
    # Recover EV/EBITDA
    mask_ev_ebitda = merged['ev_ebitda'].isna() & (merged['ebitda'] != 0) & (merged['ebitda'].notna())
    merged.loc[mask_ev_ebitda, 'ev_ebitda'] = merged.loc[mask_ev_ebitda, 'enterprise_value'] / merged.loc[mask_ev_ebitda, 'ebitda']
    
    # Recover Market Cap/Sales
    mask_mktcap_sales = merged['mktcap_sales'].isna() & (merged['revenue'] != 0) & (merged['revenue'].notna())
    merged.loc[mask_mktcap_sales, 'mktcap_sales'] = merged.loc[mask_mktcap_sales, 'market_cap'] / merged.loc[mask_mktcap_sales, 'revenue']
    
    # Recover P/E
    mask_pe = merged['pe'].isna() & (merged['pat'] != 0) & (merged['pat'].notna())
    merged.loc[mask_pe, 'pe'] = merged.loc[mask_pe, 'market_cap'] / merged.loc[mask_pe, 'pat']
    
    # Ensure code is integer
    merged['code'] = merged['code'].astype(int)
    
    # Select final columns
    final_cols = [
        'code', 'name', 'sector', 'industry', 'mode', 'year_end',
        'revenue', 'ebitda', 'pat', 'net_worth', 'total_debt', 'net_debt', 'cash',
        'market_cap', 'enterprise_value', 'pe', 'ev_ebitda', 'ev_revenue', 'mktcap_sales'
    ]
    
    for col in final_cols:
        if col not in merged.columns:
            merged[col] = np.nan
            
    final_df = merged[final_cols]
    
    # Replace infinities from calculations
    final_df = final_df.replace([np.inf, -np.inf], np.nan)
    
    # Clean object columns
    final_df['sector'] = final_df['sector'].replace('nan', np.nan)
    final_df['industry'] = final_df['industry'].replace('nan', np.nan)

    print("4. Loading to SQLite (comp_v3.db)...")
    conn = sqlite3.connect('database/comp_v3.db')
    final_df.to_sql('comps', conn, if_exists='replace', index=False)
    
    # Verify
    count = pd.read_sql("SELECT COUNT(*) FROM comps", conn).iloc[0, 0]
    print(f"Successfully loaded {count} rows into database/comp_v3.db (table: comps)")
    conn.close()

if __name__ == "__main__":
    build_db()
