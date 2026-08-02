import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db
from app.engine.model import from_row
from app.engine.pipeline import evaluate

companies = [
    '20 Microns',
    'Aarti Industries',
    'Mahindra EPC',
    'Roto Pumps',
    'Fiem Industries'
]

results = []
with db.connect() as conn:
    for cname in companies:
        rows = db.query(conn, "SELECT * FROM companies WHERE name LIKE ?", (cname + "%",))
        if rows:
            target = from_row(rows[0])
            res = evaluate(conn, target)
            val = res.get('valuation')
            if val:
                peer_names = [p['name'] for p in res.get('peers', [])] if res.get('peers') else []
                peers_list = ", ".join(peer_names)
                
                results.append({
                    'Company Name': target.name,
                    'Revenue (Cr)': target.revenue,
                    'EBITDA (Cr)': target.ebitda,
                    'EBITDA Margin': target.ebitda_margin,
                    'Net Debt (Cr)': target.effective_net_debt(),
                    'Cash (Cr)': target.cash,
                    'Headline Method': val.get('headline_method'),
                    'Valuation (EV Mid Cr)': val.get('equity_mid'),  # Equity Mid, mapping to Valuation
                    'Peers': peers_list
                })

df = pd.DataFrame(results)
output_dir = r"c:\Users\jalle\VSC\TV1_final\SRT\TV1_final_version\accuracy"
os.makedirs(output_dir, exist_ok=True)
out_path = os.path.join(output_dir, 'valuations_output_srt.xlsx')
df.to_excel(out_path, index=False)
print(f'Excel generated: {out_path}')
