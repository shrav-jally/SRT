import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db

with db.connect() as conn:
    rows = db.query(conn, "SELECT name FROM companies WHERE name LIKE ?", ('%Mahindra%',))
    print([r['name'] for r in rows])
