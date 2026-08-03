# Touchless Valuation : E-Vardhan

## Quick Start

```bash
# Install dependencies
npm run setup

# Start both servers
npm start
```

App runs at http://localhost:3000

- **Frontend** (Express): http://localhost:3000 — serves `index.html` + API proxy
- **Backend** (FastAPI): http://localhost:5899 — valuation engine (internal; use port 3000 for browser access)
- **Database** (SQLite3): `database/comps_v2.db` — 3,772 companies across 84 sectors
- **User DB** (SQLite3): `database/TV_E-Vardhan.db` — users, trial logs, company mirror

## Docker

```bash
docker compose up --build
```

## Project Structure

```
├── frontend/
│   ├── server.js          # Express server + API proxy
│   ├── index.html         # Single-page application
│   ├── Dockerfile
│   └── package.json
├── backend/
│   ├── app.py             # FastAPI application
│   ├── screening.py       # Comparable screening
│   ├── valuation.py       # CCM valuation core
│   ├── report.py          # HTML report renderer
│   ├── Dockerfile
│   └── requirements.txt
├── database/
│   ├── data.py            # SQLite3 data access (comps_v2.db)
│   ├── user_db.py         # User tracking & access control (TV_E-Vardhan.db)
│   ├── comps_v2.db        # Company database (3,772 companies)
│   ├── TV_E-Vardhan.db    # User + trial + company mirror (3 tables)
│   └── __init__.py
├── docker-compose.yml
├── package.json           # Root: concurrently for parallel servers
└── README.md
```

## Databases

### `comps_v2.db` — Company Comparables (read-only for tool logic)
- Source: Capitaline (Cline) extracts
- 3,772+ listed Indian companies across 84+ sectors

### `TV_E-Vardhan.db` — User Tracking & Access Control (read-write)
Designed for future PostgreSQL migration. Three tables:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `companies` | Mirror of comps_v2.db with all financials | `code`, `name`, `sector`, `industry`, `revenue`, `ebitda`, `pat`, `net_worth`, `total_debt`, `cash`, `market_cap`, `enterprise_value`, `pe`, `ev_ebitda`, `ev_revenue`, `year_end` |
| `users` | Access control — only active users may log in | `username`, `password_hash`, `full_name`, `role`, `is_active`, `last_login`, `created_at` |
| `transaction_data` | Structured log of every user action per UUID | Step 1: `company_name`, `sector`, `sub_sector`, `revenue`, `ebitda`, `pat`, `net_worth`, `total_debt`, `cash`, `valuation_matrices` · Step 2: `screen_sector`, `screen_sub_sector`, `threshold_revenue_min/max`, `threshold_ebitda_min/max`, `threshold_pat_min/max` · Step 3: `peers_selected`, `peer_count` · Step 4: `ev_ebitda_median`, `ev_revenue_median`, `pe_median`, `concluded_value`, `value_min`, `value_max` · Catch-all: `input_data` (JSON) |

**Seeded user:** `demo@valuetech.com` (created automatically on first startup)

## API Endpoints (:5899)

### Tool Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/tool/sectors` | Sector/sub-sector tree |
| GET | `/api/tool/dataset-meta` | Dataset metadata |
| POST | `/api/tool/screen` | Screen comparables |
| POST | `/api/tool/value` | Run CCM valuation |
| POST | `/api/tool/report` | Generate HTML report |
| POST | `/api/tool/reset-cache` | Reload database cache |

### Auth & Trial Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Check user access (username → user record or 401); updates `last_login` |
| POST | `/api/trial/new-uuid` | Generate a fresh UUID for a new trial session |
| POST | `/api/trial/log` | Log a transaction step with structured fields (company inputs, screening filters, peer selections, valuation results) |

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/overview` | DB overview (table counts) |
| GET | `/api/admin/users` | List all users |
| POST | `/api/admin/users` | Add a new user (`{username, role, full_name}`) |
| DELETE | `/api/admin/users` | Delete a user (`{username}`) |
| GET | `/api/admin/transaction-data` | List transaction data (optional `?username=`, `?uuid=`, `?step_number=`) |
| GET | `/api/admin/search-data` | Alias for `/api/admin/transaction-data` (backward-compatible) |
| GET | `/api/admin/companies` | List all companies (mirror table) |
| POST | `/api/admin/refresh-companies` | Re-populate companies from comps_v2.db |

## Method

Comparable Companies Method (CCM) — median multiples:
- **EV/EBITDA** – Profit-based
- **EV/Revenue** – Sales-based
- **P/E** – Earnings-based

Range: concluded value ±5%
