import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db
from app.engine.model import from_row
from app.engine.pipeline import evaluate

results = []
with db.connect() as conn:
    rows = db.query(conn, "SELECT * FROM companies WHERE valuation_grade=1 AND market_cap>0 AND ebitda IS NOT NULL AND revenue>0 AND pat IS NOT NULL LIMIT 10")
    for row in rows:
        target = from_row(row)
        res = evaluate(conn, target, max_peers=8)
        val = res.get('valuation')
        if val and res["status"] == "ok":
            hm = val.get('headline_method')
            peer_names = [p['name'] for p in res.get('peers', [])] if res.get('peers') else []
            peers_list = ", ".join(peer_names)
            
            results.append({
                'Company Name': target.name,
                'Sector': target.sector,
                'Industry': target.industry,
                'Revenue (Cr)': target.revenue,
                'EBITDA (Cr)': target.ebitda,
                'EBIT (Cr)': target.ebit,
                'PAT (Cr)': target.pat,
                'Net Worth (Cr)': target.net_worth,
                'Total Debt (Cr)': target.total_debt,
                'Cash (Cr)': target.cash,
                'Net Debt (Cr)': target.net_debt,
                'EBITDA Margin': target.ebitda_margin,
                'PAT Margin': target.pat_margin,
                'Listed': target.listed,
                'Market Cap (Cr)': target.market_cap,
                'Headline Method': hm,
                'Valuation (EV Low Cr)': val.get('ev_low'),
                'Valuation (EV Mid Cr)': val.get('ev_mid'),
                'Valuation (EV High Cr)': val.get('ev_high'),
                'Equity (Low Cr)': val.get('equity_low'),
                'Equity (Mid Cr)': val.get('equity_mid'),
                'Equity (High Cr)': val.get('equity_high'),
                'Confidence Label': val.get('confidence', {}).get('label'),
                'Confidence Score': val.get('confidence', {}).get('score'),
                'Peers': peers_list
            })

os.makedirs('../accuracy', exist_ok=True)
output_path = os.path.abspath('../accuracy/tv1_final_valuations.xlsx')
df = pd.DataFrame(results)
df.to_excel(output_path, index=False)
print(f'Excel generated: {output_path}')
