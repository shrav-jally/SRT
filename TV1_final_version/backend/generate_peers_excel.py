import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db
from app.engine.model import from_row
from app.engine.pipeline import evaluate

def main():
    # Folder: TV1_final_version/peers
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    output_dir = os.path.join(base_dir, 'peers')
    os.makedirs(output_dir, exist_ok=True)
    
    with db.connect() as conn:
        # Get the 10 companies from the previous pipeline
        query = "SELECT * FROM companies WHERE valuation_grade=1 AND market_cap>0 AND ebitda IS NOT NULL AND revenue>0 AND pat IS NOT NULL LIMIT 10"
        rows = db.query(conn, query)
        
        for row in rows:
            target = from_row(row)
            # Evaluate to get peers, max_peers=15 as requested
            res = evaluate(conn, target, max_peers=15)
            
            peers = res.get("peers", [])
            peer_data = []
            
            for p in peers:
                p_info = {
                    "Peer Name": p.get("name"),
                    "Revenue (Cr)": p.get("revenue"),
                    "EBITDA (Cr)": p.get("ebitda"),
                    "EBITDA Margin": p.get("ebitda_margin"),
                    "PAT (Cr)": p.get("pat"),
                    "PAT Margin": p.get("pat_margin"),
                    "Net Worth (Cr)": p.get("net_worth"),
                    "Total Debt (Cr)": p.get("total_debt"),
                    "Market Cap (Cr)": p.get("market_cap"),
                    "Enterprise Value (Cr)": p.get("enterprise_value"),
                    "PE Ratio": p.get("pe"),
                    "EV/EBITDA": p.get("ev_ebitda"),
                    "EV/Revenue": p.get("ev_revenue"),
                    "Market Cap/Sales": p.get("mktcap_sales"),
                    "Sector": p.get("sector"),
                    "Industry": p.get("industry")
                }
                peer_data.append(p_info)
            
            if not peer_data:
                print(f"No peers found for {target.name}")
                continue
                
            df = pd.DataFrame(peer_data)
            
            # File name formatting
            safe_name = str(target.name).replace(' ', '_').replace('/', '_').replace('\\', '_')
            excel_path = os.path.join(output_dir, f"{safe_name}_peers.xlsx")
            
            # Write to Excel
            with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
                # Write dataframe starting from row 1 (which leaves row 0 blank)
                df.to_excel(writer, index=False, startrow=1)
                
                # Write the target company name in A1
                workbook = writer.book
                worksheet = writer.sheets['Sheet1']
                bold_format = workbook.add_format({'bold': True})
                worksheet.write('A1', f"{target.name}", bold_format)
                
            print(f'Excel generated: {excel_path}')

if __name__ == '__main__':
    main()
