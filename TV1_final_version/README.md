# MSME Valuation Platform — Three-Approach Engine

Automated company valuation for the Indian market, built the way a registered
valuer works (ICAI Valuation Standards / IBBI): **Income (DCF) · Market
(comparables) · Asset (NAV)**, triangulated — on **real published Capitaline
multiples** across 4,600+ listed comparables, with an optional **LLM analyst**
for the qualitative positioning step and a **LangGraph human-in-the-loop
intake agent** for analyst overrides.

---

## Quick start (one command)

```bash
git clone https://github.com/Chandana909/last.week.git
cd last.week
python run.py
```

That is all. `run.py` checks Python (3.10+), installs any missing Python
packages, asks once for an optional Groq key, and serves the whole platform at
**http://localhost:8000** (UI + API on one port — the browser opens
automatically). No Node/npm needed: the UI ships prebuilt.

---

## Configuration (detailed)

### 0. Dashboard sections

The result dashboard has four sections (one page, switchable):

| Section | Contents |
|---|---|
| **Overview** | concluded equity range, **actual market cap + deviation**, approach-weight bar, the three approach cards |
| **Comparables** | every peer with full financials — revenue, EBITDA, PAT, net worth, market cap, margins, EV/EBITDA, EV/Revenue, P/E, match score |
| **Calculations** | each of the three ratios with the complete working: peer spread (min–median–max), multiple used and its source, driver, EV, net-debt bridge, equity — plus the DCF assumption table and the NAV build-up |
| **Report & Audit** | independent LLM review (its own estimate + verdict + weight applied), qualitative positioning rationale, audit trail (peer selection, multiple handling, assumption provenance, weights, DLOM, equity bridge), caveats, print/PDF |

### 1. GROQ_API_KEY — enables the LLM analyst (optional)

The LLM analyst supplies the *qualitative* positioning step (brand / market
leadership / moat) of the market approach. Without a key the platform runs
fully deterministic and simply skips this step.

1. Create a free key at <https://console.groq.com/keys>
2. Either paste it when `run.py` asks on first launch (it is saved to `.env`),
   or create a file named `.env` in the repo root yourself:

   ```
   GROQ_API_KEY=gsk_your_key_here
   ```

3. Optional: choose the model with `GROQ_MODEL` (default
   `llama-3.3-70b-versatile`).

Two LLM calls are made per valuation:

| Call | Role | Weight in the number |
|---|---|---|
| **Qualitative positioning** | places the subject within the peer multiple range (brand, leadership, moat) and writes the rationale | **full** (`LLM_BLEND=1.0`) — validated to reduce error |
| **Independent review** | its own value estimate + verdict on the engine's range | **zero by default** — see below |

The review is *disclosed, not blended*: measured on validation, the LLM's own
estimates are materially worse than the engine's (unanchored recall of Indian
market caps errs ~73% median; blending raised error monotonically 58.6% →
62.7%). Enable blending if you want it:
`LLM_CHECK_WEIGHT_HIGH=0.4 LLM_CHECK_WEIGHT_MEDIUM=0.2 python run.py`.

**Never commit `.env`** — it is gitignored. A leaked key on GitHub is
auto-revoked by Groq's secret scanning.

### 1b. Live market data (screener.in) — on by default

For listed companies the platform fetches the **current** market cap and P/E
from screener.in and shows a live cross-check (current value, our conclusion vs
live, and how stale the stored snapshot is). It also computes a **market-drift
factor** — the measured gap between the stored fiscal-year snapshot and today's
market — and re-levels the peer multiples by it, so a valuation reflects
current pricing instead of the snapshot date. Measured on the stored universe:
the snapshot sits **~12% below live** (14 of 15 sampled names), and applying the
drift improved error against today's market caps (56.8% → 56.0% median,
within-50% 31% → 39%).

- refresh manually: `cd backend && python -m app.engine.live_market`
  (writes `backend/data/market_drift.json`; `run.py` refreshes it weekly)
- disable entirely: `LIVE_MARKET=0 python run.py`
- one request per company, cached in-process, never bulk-scraped

### 2. PORT (optional)

```
PORT=8733 python run.py        # default 8000
```

### 3. DATABASE_URL (optional — Postgres)

Default is the bundled SQLite file `backend/data/comps.db` (zero setup).
For PostgreSQL: `DATABASE_URL=postgresql://user:pass@host:5432/db`, install
`psycopg[binary]`, then rebuild the DB (next section).

### 4. Data source & rebuilding the comparables DB

**Primary input: `unified_tv1_tv2.db`** (repo root) — the curated unified
TV-1/TV-2 database: 20,143 usable companies, latest financials (incl. debt,
cash, real EBIT, market EV), 7-period ratio history and segments. The engine
DB `backend/data/comps.db` ships pre-built from it. To rebuild:

```bash
cd backend && python -m app.etl.from_unified
```

Note: the adapter reads `valuation_ratios` at `period_rank 0` (current) with
fallback — the unified `comps` view's own "latest" CTE picks the OLDEST
period, so the view is not used for multiples.

Legacy path: `python -m app.etl.build_db` rebuilds from the five raw
Capitaline `.xls` extracts (`SOURCE_DIR` env) — this is also what populates
the 7-year financial history that `from_unified` preserves.

### 5. VLM PDF extraction (placeholder)

`backend/app/routers/extraction.py` is a **blank interface**: plug your
vision-language extractor into `extract_financials()` and the PDF-upload
flow activates (the endpoint returns 501 until then).

---

## Data flow

```mermaid
flowchart TD
    subgraph SOURCES["Data sources"]
        XLS["5 Capitaline .xls extracts<br/>(sector-tagged, 0 = not applicable)"]
        PDF["Company PDF (annual report)"]
        USER["Manual entry / analyst"]
    end

    subgraph ETL["ETL — python -m app.etl.build_db"]
        UNION["UNION all company codes<br/>(never inner-join; blanks kept)"]
        ZERO["0 → NULL for metrics<br/>(keeps banks/NBFCs)"]
        HIST["7-year history extraction<br/>(171,904 rows)"]
    end

    DB[("comps.db<br/>53,602 companies · 4,666 grade<br/>SQLite | Postgres via DATABASE_URL")]

    subgraph ENGINE["Valuation engine (Python)"]
        PEERS["Peer discovery<br/>sub-sector tier → 5-10 tight comps"]
        AUTO["Auto-analyst<br/>growth = damped own CAGR<br/>margin = cycle-normalized<br/>WACC = build-up"]
        LLM["LLM analyst (Groq, optional)<br/>qualitative positioning percentile<br/>+ written rationale"]
        CCM["Market (CCM)<br/>real published multiples<br/>warranted regression + LLM position"]
        DCF["Income (DCF)<br/>FCFF on auto/analyst assumptions"]
        NAV["Asset (NAV)<br/>net worth + surplus items"]
        TRI["Triangulation<br/>profile weights · DLOM · range"]
    end

    subgraph AGENT["LangGraph intake agent"]
        Q["7-step interview<br/>(auto-derived defaults pre-filled)"]
    end

    subgraph UI["Next.js UI (prebuilt static, served by FastAPI)"]
        SEARCH["Search / private-company form"]
        RESULT["Triangulated result<br/>weight bar · approach cards · rationale"]
        REFINE["Refine wizard"]
    end

    XLS --> UNION --> ZERO --> HIST --> DB
    PDF -.->|"VLM stub (plug in)"| USER
    USER --> SEARCH
    DB --> PEERS --> CCM
    PEERS --> LLM --> CCM
    DB --> AUTO --> DCF
    CCM --> TRI
    DCF --> TRI
    NAV --> TRI
    DB --> NAV
    SEARCH -->|/api/value-pro| PEERS
    TRI --> RESULT --> REFINE --> Q -->|overrides| AUTO
    Q -->|re-run| TRI
```

---

## Architecture / tech stack

| Layer | Tech | Where |
|---|---|---|
| UI | **Next.js 16** (App Router, TS, Tailwind) — dev via `npm run dev`, shipped as a static export served by the backend | `frontend/` |
| API + engine + agents | **Python** FastAPI · LangGraph (intake agent) · scikit-learn (warranted multiple) · Groq LLM (qualitative positioning) | `backend/app/` |
| Data | **SQLite** now, **PostgreSQL** via `DATABASE_URL` (portable data layer) | `backend/data/comps.db` |

```
run.py                     ← the only command you need
backend/
  app/etl/build_db.py      maximal-coverage ETL (union, 0→NULL, 7-yr history)
  app/engine/
    peers.py               tight peer discovery (sub-sector tier)
    auto_analyst.py        history-derived DCF assumptions (with provenance)
    llm_analyst.py         Groq LLM qualitative positioning (optional)
    drivers.py             warranted-multiple regression
    approaches/            income.py (DCF) · market.py (CCM) · asset.py (NAV)
    triangulate.py         profile weights · DLOM · conclusion
    pipeline_pro.py        orchestrator
  app/agents/intake.py     LangGraph human-in-the-loop interview
  app/routers/             companies · intake · extraction (VLM stub)
frontend/                  Next.js source + prebuilt static export (out/)
```

For UI development: `cd frontend && npm install && npm run dev` (proxies
`/api/*` to the backend on :8000). Rebuild the shipped UI with
`BUILD_STATIC=1 npm run build`.

---

## Accuracy — measured honestly (leave-one-out vs real market caps)

Method: hide each listed company, value it with the full pipeline, compare the
conclusion to its actual market cap.

| Configuration | Median abs. error |
|---|---|
| naive peer-median comps (where this project started) | ~65% |
| + winsorized multiples, tight sub-sector peers | ~59% |
| + three-approach triangulation, auto-analyst, tuned weights | **~56%** |
| + LLM analyst at blend 0.5 (companies it recognizes) | **~47%** |
| + LLM analyst at FULL weight (`LLM_BLEND=1.0`, the default — error falls monotonically with LLM weight: 58.6→51.8→48.6→43.8% on the named validation set) | **~44%** |
| LLM with names masked (honest transfer test) | ~53% |
| HIGH-confidence / peers-priced-alike subset | ~47–50% |
| single company with true analyst inputs via the agent | can reach ±3–15% |

Key facts behind these numbers:

- The data is **internally perfect**: each company's own multiple × its EBITDA
  − net debt reproduces its own market cap with ~0% median error. The error is
  entirely cross-company: within one sub-sector, real peers trade **4× apart**
  (ACC at 6.8× EV/EBITDA vs Ambuja/UltraTech at 28–30×).
- The residual ~50% is the market's **brand/leadership premium and
  expectations** — not present in any financial statement. The LLM analyst
  recovers part of it for companies whose market standing it knows, and writes
  the rationale into the report like a valuer's workpaper note.
- Rejected after out-of-sample testing (each did not help or made it worse) —
  every one of these was measured, not assumed:

  | Attempt | Result |
  |---|---|
  | simple median-of-three-ratios (no triangulation) | 61.5% vs 60.6% current → kept current |
  | **cross-sectional model**: Ridge on log(market cap) from fundamentals only, 3,545 companies + sector effects, leave-one-out | 53.2% alone vs 56.4% peer-median; **added as a 4th approach → no gain** (59.6% vs 58.2% without) |
  | market-approach-only weighting (dropping the conservative DCF) | 71.4% alone vs 62.8% blended on a random sample → blend kept (the 15 famous names that suggested otherwise were not representative) |
  | LLM positioning blend level 0 → 1.0 | differences are **noise** — the direction flips between samples (seed 101: 0.25 best; seed 202: 1.0 best) → left at 1.0, no change on noise |
  | blending the LLM's own value estimate | monotonically worse (58.6% → 62.7%) → weight 0 |
  | global bias calibration (×1.54 on a measured −35% median bias) | 49.5% → 58.5% out-of-sample → rejected (error is right-skewed; scaling overshoots the cases already near) |
  | margin-percentile positioning · harmonic/geometric means · per-component de-biasing · log-space blending | no gain or worse |
- Professional valuations differ from traded prices by similar margins. The
  deliverable is a **defensible, fully documented valuation range** — every
  assumption carries provenance — not a prediction of the next traded price.

Reproduce: `cd backend && python -m app.validate 500`

---

## Caveats

Automated indicative valuation aligned to ICAI/IBBI methodology — **not** a
certified registered-valuer opinion. Multiples are real published Capitaline
figures used as-is; where inputs are missing the engine discloses and degrades
rather than inventing numbers.
