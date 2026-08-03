import sqlite3, pandas as pd
from pathlib import Path

SRC = Path(r"C:\tv1\tv_merge-main\realdata.db")
DST = Path(r"C:\tv1\tv_merge-main\unified_tv1_tv2.db")
DST.unlink(missing_ok=True)

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

# 1️⃣ determine usable companies
fin = pd.read_sql("SELECT * FROM fin", src)
latest = fin.sort_values("year_end").groupby("accord").last().reset_index()
tv1_ok = latest[(latest.revenue>0) & (latest.ebitda>0) & (latest.net_worth>0)]
val_ids = set(pd.read_sql("SELECT DISTINCT accord FROM valuation_ratios", src).accord)
cash = pd.read_sql("SELECT accord FROM cash_bank WHERE cash_bank>0", src).accord
tv2_ok = latest[latest.accord.isin(val_ids) & (latest.net_worth>0) & latest.accord.isin(cash)]
usable = pd.concat([tv1_ok, tv2_ok]).drop_duplicates("accord").accord.tolist()
print(f"Usable companies = {len(usable)}")
usable_set = set(usable)

# 2️⃣ copy five TV-1 tables filtered
for tbl in ["companies","fin","valuation_ratios","cash_bank","segment_details"]:
    df = pd.read_sql(f"SELECT * FROM {tbl}", src)
    if "accord" in df.columns:
        df = df[df.accord.isin(usable_set)]
    df.to_sql(tbl, dst, if_exists="replace", index=False)
    print(f"{tbl}: {len(df):,} rows")

# 3️⃣ indexes
idx_sql = """
CREATE INDEX idx_companies_accord   ON companies(accord);
CREATE INDEX idx_fin_accord         ON fin(accord);
CREATE INDEX idx_fin_year           ON fin(year_end);
CREATE INDEX idx_val_accord         ON valuation_ratios(accord);
CREATE INDEX idx_val_period         ON valuation_ratios(period_rank);
CREATE INDEX idx_cash_accord        ON cash_bank(accord);
CREATE INDEX idx_seg_accord         ON segment_details(accord);
"""
dst.executescript(idx_sql)

# 4️⃣ TV-2 comps view using a helper table of usable IDs
# create helper table
usable_df = pd.DataFrame({"accord": usable})
usable_df.to_sql("usable_ids", dst, if_exists="replace", index=False)
dst.execute("CREATE UNIQUE INDEX idx_usable_ids ON usable_ids(accord)")

drop_view = "DROP VIEW IF EXISTS comps;"
create_view = """
CREATE VIEW comps AS
WITH latest_fin AS (
    SELECT * FROM fin
    WHERE (accord, year_end) IN (SELECT accord, MAX(year_end) FROM fin GROUP BY accord)
),
latest_val AS (
    SELECT * FROM valuation_ratios
    WHERE (accord, period_rank) IN (SELECT accord, MAX(period_rank) FROM valuation_ratios GROUP BY accord)
),
seg_agg AS (
    SELECT accord, COUNT(*) AS seg_count,
           SUM(segment_assets) AS seg_assets,
           SUM(segment_liabilities) AS seg_liab
    FROM segment_details WHERE is_total = 0 GROUP BY accord
),
latest_cash AS (
    SELECT accord, cash_bank FROM cash_bank
)
SELECT
    f.accord AS code, c.name, c.sector, c.industry,
    f.revenue, f.ebitda, f.pat, f.net_worth, f.market_cap,
    v.pe, v.ev_ebitda,
    CASE WHEN f.market_cap>0 THEN f.revenue*1.0/f.market_cap ELSE NULL END AS ev_revenue,
    v.mode, f.year_end,
    lc.cash_bank AS cash,
    COALESCE(s.seg_count,0) AS seg_count,
    COALESCE(s.seg_assets,0) AS seg_assets,
    COALESCE(s.seg_liab,0)   AS seg_liab,
    (v.pe IS NOT NULL) AS has_pe,
    (v.ev_ebitda IS NOT NULL) AS has_eve,
    (v.pe IS NOT NULL OR v.ev_ebitda IS NOT NULL) AS has_multiple,
    1 AS valuation_ready, 1 AS screening_ready
FROM latest_fin f
JOIN companies c ON c.accord = f.accord
LEFT JOIN latest_val v ON v.accord = f.accord
LEFT JOIN seg_agg s ON s.accord = f.accord
JOIN latest_cash lc ON lc.accord = f.accord
JOIN usable_ids u ON u.accord = f.accord
"""
dst.execute(drop_view)
dst.execute(create_view)
dst.commit()
dst.close()
src.close()
print("✅ Unified DB ready →", DST)