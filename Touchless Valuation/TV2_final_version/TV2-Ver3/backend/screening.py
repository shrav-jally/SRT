"""
screening.py - comparable-company screening for the CCM valuation tool.
"""

from database import load_comparables

MAX_COMPARABLES = 10

_CRITERIA = {
    "revenue": ("revenue", False),
    "ebitda": ("ebitda", False),
    "pat": ("pat", False),
    "ebitda_margin": ("ebitda_margin", True),
    "pat_margin": ("pat_margin", True),
}


def _passes(value, band):
    """band = {'min': x?, 'max': y?}; None bounds are open."""
    if value is None:
        return False
    lo, hi = band.get("min"), band.get("max")
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def screen(sub_sector, thresholds=None, subject=None, all=False):
    """Return qualifying comparables for one or more sub-sectors (comma-separated)."""
    thresholds = thresholds or {}
    all_comps = load_comparables()
    if not sub_sector or sub_sector in ("all", ""):
        pool = all_comps
    else:
        # Support multiple sub-sectors: "IT Services,IT Consulting" → match any
        sub_names = [s.strip() for s in sub_sector.split(",") if s.strip()]
        if not sub_names:
            pool = all_comps
        else:
            pool = [c for c in all_comps if (c.get("sub_sector") or "").strip() in sub_names]

    applied = {}
    for key, band in thresholds.items():
        if key not in _CRITERIA:
            continue
        if band is None or (band.get("min") is None and band.get("max") is None):
            continue
        applied[key] = band

    qualified = []
    for c in pool:
        ok = True
        reasons = []
        for key, band in applied.items():
            field, _ = _CRITERIA[key]
            if not _passes(c.get(field), band):
                ok = False
                break
            reasons.append(key)
        if ok:
            c = dict(c)
            c["qualified_on"] = reasons or ["sub_sector"]
            qualified.append(c)

    if subject and subject.get("revenue"):
        r0 = subject["revenue"]
        qualified.sort(key=lambda c: abs((c["revenue"] or 0) - r0))
    else:
        qualified.sort(key=lambda c: -(c["revenue"] or 0))

    selected = qualified[:MAX_COMPARABLES] if not all else qualified
    return {
        "sub_sector": sub_sector,
        "thresholds_applied": applied,
        "pool_size": len(pool),
        "qualified": len(qualified),
        "returned": len(selected),
        "capped_at": MAX_COMPARABLES,
        "comparables": selected,
    }
