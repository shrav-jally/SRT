"""
Central configuration. Everything that is environment- or path-dependent lives
here so the rest of the code never hard-codes a location or a magic threshold.

Postgres-readiness: the whole data layer is driven by DATABASE_URL. Today it
defaults to a local SQLite file (zero setup). Point DATABASE_URL at a
`postgresql://...` instance and nothing else changes.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- .env
# Minimal loader (no dependency): reads KEY=VALUE lines from the platform
# root .env (next to run.py) without overriding already-set variables.
_ROOT = Path(__file__).resolve().parent.parent.parent          # valuation-platform/
for _envfile in (_ROOT / ".env", Path(__file__).resolve().parent.parent / ".env"):
    if _envfile.is_file():
        for _line in _envfile.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ---------------------------------------------------------------- paths
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# The raw Capitaline (.xls) extracts. Kept in place (they are large) rather than
# copied into the repo. Override with SOURCE_DIR if you move them.
# Default to None — the ETL scripts will handle missing source gracefully.
SOURCE_DIR = Path(
    os.environ.get("SOURCE_DIR", "")
) or None

# ---------------------------------------------------------------- database
# sqlite:///absolute/path.db   or   postgresql://user:pass@host:5432/dbname
DEFAULT_SQLITE = f"sqlite:///{(DATA_DIR / 'comps.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE)

# ---------------------------------------------------------------- data rules
# Year-end (YYYYMM as an int, e.g. 202603) at/above which a published multiple
# is considered current enough to price a peer off. Companies whose latest
# reported year-end is older are kept in the DB but flagged non-current.
RECENT_YEAR_END = int(os.environ.get("RECENT_YEAR_END", "202303"))

# In this source, 0 in a metric/driver cell means "not applicable / not
# reported" (sector-tagged layout). These fields therefore treat 0 as NULL.
ZERO_IS_NULL_FIELDS = {
    "net_sales", "ebitda", "ebit", "pat", "pbt", "net_worth",
    "capital_employed", "market_cap", "enterprise_value",
    "total_income", "interest_earned", "net_interest_income",
    "pe", "ev_ebitda", "mktcap_sales", "pbv",
}
