"""
LLM analyst — the qualitative-judgment step of a CA's valuation, as a model call.

The measured residual error of every quantitative method here is the market's
brand / leadership / moat premium: within one sub-sector, the leader trades at
2x the median multiple and nothing in the financial statements says which
company that is. A valuer closes this with qualitative judgment; this node
gives the engine the same faculty.

Given the target's profile and its peers' multiple distribution, the LLM
returns WHERE in the peer range this company should price (a percentile) plus a
written rationale — which is surfaced in the report exactly like a valuer's
workpaper note. Deterministic fallback: no key / API error -> the engine runs
identically to before (median positioning), with the LLM step marked skipped.

Provider: Groq (OpenAI-compatible). Key from GROQ_API_KEY (loaded from .env by
run.py / config). Model: llama-3.3-70b-versatile.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
TIMEOUT = 25

SYSTEM = """You are a senior Indian equity/valuation analyst. Your task: place
a company WITHIN its listed-peer multiple range.

CRITICAL: If you recognize the company, USE EVERYTHING YOU KNOW about it —
brand strength, market share, distribution reach, pricing power, moat,
promoter/governance record, growth narrative. The Indian market awards
dominant consumer brands and category leaders multiples at the TOP of (or
above) their peer range (e.g. category-leading franchises routinely trade at
P75-P90 of peers), and penalizes commodity converters, B2B undifferentiated
players and governance question marks to P10-P30. Do NOT default to the
median when you actually know the company's standing — being falsely neutral
is an error, exactly like a valuer ignoring that the subject is the market
leader. If you genuinely do not recognize the company, judge from the supplied
figures alone and stay nearer the median.

Respond ONLY with JSON: {"percentile": <0.10-0.90>, "rationale": "<2-3
sentences naming the specific qualitative factors>", "confidence":
"low|medium|high"}."""


def available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


def _call(messages: list[dict]) -> Optional[str]:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return None
    body = json.dumps({
        "model": MODEL, "messages": messages,
        "temperature": 0.2, "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 # Cloudflare fronting Groq 403s the default Python-urllib UA
                 "User-Agent": "valuation-platform/3.0 (+python-stdlib)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out = json.loads(r.read().decode())
        return out["choices"][0]["message"]["content"]
    except Exception:
        return None


CHECK_SYSTEM = """You are a senior Indian equity analyst performing a sanity
check on a valuation produced by a quantitative engine. Two tasks:

1. INDEPENDENT ESTIMATE: give your own estimate of the company's fair equity
value in Rs CRORE. If you recognize this listed company, anchor on what you
know of its actual market capitalization and trading history. If it is
unknown/private, estimate from the supplied financials and sector norms.

2. VERDICT on the engine's range: "low" (engine materially undervalues),
"fair" (within reason), or "high" (materially overvalues).

Respond ONLY with JSON:
{"estimate_cr": <number>, "confidence": "high|medium|low",
 "verdict": "low|fair|high", "comment": "<1-2 sentences>"}
confidence = how well you actually know this company (high only if you
recognize it and recall its approximate market value)."""


def check(target, engine_low: float, engine_mid: float, engine_high: float) -> Optional[dict]:
    """Independent LLM estimate + verdict on the engine's computed range."""
    if not available():
        return None
    margin = f"{target.ebitda_margin:.1%}" if target.ebitda_margin is not None else "n/a"
    user = f"""Company: {target.name}
Sector / sub-sector: {target.sector} / {target.industry or 'n/a'} · listed: {target.listed}
Latest financials (Rs Cr): revenue {target.revenue or 0:,.0f}, EBITDA {target.ebitda or 0:,.0f} ({margin} margin), PAT {target.pat or 0:,.0f}, net worth {target.net_worth or 0:,.0f}

Engine's computed equity range (Rs Cr): low {engine_low:,.0f} · mid {engine_mid:,.0f} · high {engine_high:,.0f}

Your independent estimate and verdict?"""
    raw = _call([{"role": "system", "content": CHECK_SYSTEM},
                 {"role": "user", "content": user}])
    if not raw:
        return None
    try:
        d = json.loads(raw)
        est = float(d["estimate_cr"])
        if est <= 0:
            return None
        conf = str(d.get("confidence", "low")).lower()
        return {"estimate_cr": round(est, 1),
                "confidence": conf if conf in ("high", "medium", "low") else "low",
                "verdict": str(d.get("verdict", "fair")).lower(),
                "comment": str(d.get("comment", ""))[:400],
                "model": MODEL}
    except Exception:
        return None


def position(target, peers: list[dict], *, mask_name: bool = False) -> Optional[dict]:
    """Return {percentile, rationale, confidence, model} or None on failure."""
    if not available() or not peers:
        return None
    import statistics as stats
    mults = sorted(p["ev_ebitda"] for p in peers if p.get("ev_ebitda"))
    if len(mults) < 3:
        return None
    name = "the target company" if mask_name else target.name
    margin = f"{target.ebitda_margin:.1%}" if target.ebitda_margin is not None else "n/a"
    peer_lines = "\n".join(
        f"- {'peer' if mask_name else p['name']}: revenue ₹{p.get('revenue') or 0:,.0f} Cr, "
        f"margin {(p.get('ebitda_margin') or 0):.1%}, EV/EBITDA {p.get('ev_ebitda')}"
        for p in peers[:8])
    user = f"""Company to position: {name}
Sector / sub-sector: {target.sector} / {target.industry or 'n/a'}
Revenue: ₹{target.revenue or 0:,.0f} Cr · EBITDA margin: {margin} · listed: {target.listed}

Peer multiple distribution (EV/EBITDA): min {mults[0]:.1f}, median {stats.median(mults):.1f}, max {mults[-1]:.1f}
Peers:
{peer_lines}

Where should this company price within the peer range, and why?"""
    raw = _call([{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": user}])
    if not raw:
        return None
    try:
        d = json.loads(raw)
        pct = float(d["percentile"])
        pct = min(max(pct, 0.10), 0.90)
        return {"percentile": round(pct, 3),
                "rationale": str(d.get("rationale", ""))[:500],
                "confidence": d.get("confidence", "medium"),
                "model": MODEL}
    except Exception:
        return None
