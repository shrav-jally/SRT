"""
Honest leave-one-out accuracy harness.

For every listed grade company that has the inputs, we hide it, value it purely
off its peers, and compare the tool's mid equity to the company's OWN market
cap. This measures true out-of-sample error — no anchor is fitted to make the
number look good. Reports the full error distribution, not a hand-picked set.

Run:  python -m app.validate            (full grade universe)
      python -m app.validate 400        (random sample of 400)
"""
from __future__ import annotations

import random
import statistics as stats
import sys

from . import db
from .engine.model import from_row
from .engine.pipeline import evaluate


def run(sample: int | None = None, seed: int = 7) -> dict:
    with db.connect() as conn:
        rows = db.query(
            conn,
            """SELECT * FROM companies
               WHERE valuation_grade=1 AND market_cap>0 AND ebitda IS NOT NULL
                 AND revenue>0 AND pat IS NOT NULL""",
        )
        if sample and sample < len(rows):
            random.Random(seed).shuffle(rows)
            rows = rows[:sample]

        deltas, headline_ct, byconf = [], {}, {}
        n_ok = n_skip = 0
        for row in rows:
            target = from_row(row)
            res = evaluate(conn, target, max_peers=8)
            if res["status"] != "ok":
                n_skip += 1
                continue
            v = res["valuation"]
            eq = v.get("equity_mid")
            if not eq or eq <= 0 or not target.market_cap:
                n_skip += 1
                continue
            delta = eq / target.market_cap - 1
            deltas.append(abs(delta))
            n_ok += 1
            hm = v["headline_method"]; headline_ct[hm] = headline_ct.get(hm, 0) + 1
            lab = v["confidence"]["label"]
            byconf.setdefault(lab, []).append(abs(delta))

    deltas.sort()
    def med(x): return round(100 * stats.median(x), 1) if x else None
    out = {
        "n_valued": n_ok, "n_skipped": n_skip,
        "median_abs_pct": med(deltas),
        "mean_abs_pct": round(100 * stats.mean(deltas), 1) if deltas else None,
        "p25_abs_pct": round(100 * deltas[len(deltas)//4], 1) if deltas else None,
        "p75_abs_pct": round(100 * deltas[3*len(deltas)//4], 1) if deltas else None,
        "within_25pct": round(100 * sum(d <= 0.25 for d in deltas) / len(deltas), 1) if deltas else None,
        "within_50pct": round(100 * sum(d <= 0.50 for d in deltas) / len(deltas), 1) if deltas else None,
        "headline_mix": headline_ct,
        "median_err_by_confidence": {k: med(v) for k, v in byconf.items()},
    }
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    import json
    print(json.dumps(run(n), indent=2))
