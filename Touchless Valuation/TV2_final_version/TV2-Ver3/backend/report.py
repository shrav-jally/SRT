"""
report.py -- renders a CCM valuation result into a detailed,
self-contained HTML report (print-to-PDF ready).
"""

import html


def _esc(x):
    return html.escape("" if x is None else str(x))


def _cr(x, nd=0):
    if x is None:
        return "&mdash;"
    return "&#8377;" + f"{x:,.{nd}f}" + " Cr"


def _x(x, nd=2):
    return "&mdash;" if x is None else f"{x:,.{nd}f}x"


def _pct(x, nd=1):
    return "&mdash;" if x is None else f"{x*100:,.{nd}f}%"


_FIELD = {"EV/EBITDA": "ev_ebitda", "EV/Revenue": "ev_revenue", "P/E": "pe"}
_DRIVER_LABEL = {"EV/EBITDA": "EBITDA", "EV/Revenue": "Revenue", "P/E": "PAT"}

_METHOD_LABELS = {
    "EV/EBITDA": "EV/EBITDA \u2013 Profit-based",
    "EV/Revenue": "EV/Revenue \u2013 Sales-based",
    "P/E": "P/E \u2013 Earnings-based",
    "NAV": "NAV \u2013 Asset-based",
}

def _method_label(m):
    return _METHOD_LABELS.get(m, m)

_STYLE = """
:root{
  /* ── DDS Brand ── */
  --deloitte-green:#86BC25;--accessible-blue:#007CB0;--accessible-green:#26890D;
  --accessible-teal:#0D8390;--red:#DA291C;
  /* ── DDS Neutrals ── */
  --black:#000000;--white:#FFFFFF;
  --cool-gray-2:#D0D0CE;--cool-gray-4:#BBBCBC;--cool-gray-6:#A7A8AA;
  --cool-gray-7:#97999B;--cool-gray-9:#75787B;--cool-gray-10:#63666A;--cool-gray-11:#53565A;
  /* ── DDS Focus ── */
  --focus-color:#005587;
  /* ── Semantic aliases ── */
  --ink:var(--cool-gray-11);--muted:var(--cool-gray-10);--faint:var(--cool-gray-7);
  --line:var(--cool-gray-2);--band:#f5f5f5;--accent:var(--accessible-green);
  --green:var(--deloitte-green);--black-c:var(--black);
  --good:var(--accessible-green);--warn:#ED8B00;--bad:var(--red);
  --radius:4px;--radius-sm:2px;--radius-lg:6px;
  --font-family:"Open Sans",sans-serif;--font-mono:monospace;
}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);
  font-family:var(--font-family);font-size:13px;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:24px 30px 60px}
.logo-bar{display:flex;align-items:center;gap:2px;margin-bottom:18px}
.logo-bar .wordmark{font-size:20px;font-weight:700;color:var(--black-c);letter-spacing:-.02em}
.logo-bar .dot{width:8px;height:8px;border-radius:50%;background:var(--green);flex-shrink:0;margin-left:1px}
.cover{border-bottom:3px solid var(--green);padding-bottom:14px;margin-bottom:8px}
.cover .brand{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--green);margin-bottom:6px}
.cover h1{margin:0;font-size:21px;font-weight:700}
.cover .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
.cover .meta{color:var(--faint);font-size:11px;margin-top:8px;font-family:var(--font-mono)}
h2{font-size:14px;margin:24px 0 3px;color:var(--black-c);border-bottom:2px solid var(--green);padding-bottom:4px}
.purpose{color:var(--muted);font-size:11.5px;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}
th{background:var(--band);text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);font-weight:700;padding:7px 8px;border-bottom:2px solid var(--green)}
th:first-child,td:first-child{text-align:left}
td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums}
tr.med td{background:#86bc2518;font-weight:700}
tr.avg td{color:var(--muted)}
.kv{display:grid;grid-template-columns:1fr 1fr;gap:2px 22px}
.kv .row{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:5px 0}
.kv .row .k{color:var(--muted)} .kv .row .v{font-variant-numeric:tabular-nums;font-weight:600}
.calc{background:var(--band);border:1px solid var(--line);border-radius:var(--radius-lg);padding:12px 14px;margin:10px 0}
.calc .step{font-family:var(--font-mono);font-size:12px;padding:3px 0;color:var(--muted)}
.calc .step b{color:var(--ink)}
.calc .total{border-top:1px solid var(--cool-gray-4);margin-top:6px;padding-top:8px;font-size:13.5px}
.headline{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:10px 0}
.hcard{border:1px solid var(--line);border-radius:var(--radius-lg);padding:14px 16px}
.hcard.primary{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:linear-gradient(#fff,#f6faf1)}
.hcard .k{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700}
.hcard .big{font-size:23px;font-weight:800;margin-top:3px}
.hcard.primary .big{color:var(--accent)}
.hcard .rng{color:var(--muted);font-size:12px;margin-top:2px;font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:50rem}
.pill.tight{background:#26890D18;color:var(--good)}.pill.moderate{background:#ED8B0018;color:var(--warn)}
.pill.wide{background:#DA291C18;color:var(--bad)}
ol.cav{padding-left:18px;font-size:11.5px;color:var(--muted)} ol.cav li{margin:5px 0}
.prov{font-size:10.5px;color:var(--faint);margin-top:16px;border-top:1px solid var(--line);padding-top:10px}
.note{font-size:11px;color:var(--muted);margin-top:6px}
.confidential{margin-top:40px;border-top:2px solid var(--green);padding-top:12px;font-size:10px;color:var(--faint);line-height:1.6}
.confidential .stamp{font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:10px;margin-bottom:4px}
@media print{@page{margin:14mm}body{font-size:11.5px}h2{page-break-after:avoid}.headline,table{page-break-inside:avoid}}
"""


def render_report(result):
    s = result["subject"]
    nav = result["nav"]
    sc = result.get("screening", {})
    meta = result.get("meta", {})

    # Support multiple matrices
    matrices = result.get("matrices")
    primary_matrix = matrices[0] if matrices else result.get("matrix", "EV/EBITDA")
    ccm_by_matrix = result.get("ccm_by_matrix", {})

    # Primary values for header
    ccm = ccm_by_matrix.get(primary_matrix, result.get("ccm", {}))
    ms = ccm.get("multiple_summary", {})

    P = ['<div class="wrap">']

    # ---- Deloitte logo bar ----
    P.append('<div class="logo-bar"><span class="wordmark">Deloitte</span><span class="dot"></span></div>')

    # ---- cover ----
    P.append('<div class="cover">')
    P.append('<div class="brand">Touchless Valuation : E-Vardhan</div>')
    P.append(f'<h1>Indicative Valuation &mdash; {_esc(s.get("name") or "Company")}</h1>')
    matrix_label = ", ".join(f"<b>{_method_label(m)}</b>" for m in matrices) if len(matrices) > 1 else f"<b>{_method_label(primary_matrix)}</b>"
    P.append(f'<div class="sub">Comparable Companies '
             f'Method &middot; matrices {matrix_label} &middot; median '
             f'multiple &middot; range &plusmn;5%</div>')
    contact = " · ".join(filter(None, [
        s.get("contact_person"), s.get("designation"), s.get("email"),
        s.get("contact_number")]))
    if contact:
        P.append(f'<div class="sub">Prepared for: {_esc(contact)}</div>')
    P.append(f'<div class="meta">Valuation date {_esc(s.get("valuation_date") or "&mdash;")} '
             f'&middot; sub-sector {_esc(sc.get("sub_sector"))} '
             f'&middot; {ms.get("n", 0)} comparables &middot; automated tool</div>')
    disc_date = meta.get("disclaimer_accepted_date")
    if disc_date:
        P.append(f'<div class="meta" style="color:var(--good)">Disclaimer accepted: {_esc(disc_date)} &#10003;</div>')
    P.append('</div>')

    # ---- 1 subject financials ----
    P.append('<h2>1 &middot; Subject company &mdash; financial inputs</h2>')
    P.append('<div class="purpose">As provided by the user; all figures in INR Crore.</div>')

    def row(k, v):
        return f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
    P.append('<div class="kv">')
    P.append(row("LTM Revenue", _cr(s.get("revenue"))))
    P.append(row("LTM EBITDA", _cr(s.get("ebitda"))))
    P.append(row("LTM PAT", _cr(s.get("pat"))))
    P.append(row("Net worth (book equity)", _cr(s.get("net_worth"))))
    P.append(row("Cash & equivalents", _cr(s.get("cash"))))
    P.append(row("Surplus investments", _cr(s.get("surplus_investments"))))
    P.append(row("Debt", _cr(s.get("debt"))))
    P.append(row("Lease liabilities", _cr(s.get("lease_liabilities"))))
    P.append(row("Surplus assets", _cr(s.get("surplus_assets"))))
    P.append(row("Surplus liabilities", _cr(s.get("surplus_liabilities"))))
    if s.get("revenue") and s.get("ebitda") is not None:
        P.append(row("EBITDA margin", _pct(s["ebitda"] / s["revenue"])))
    if s.get("revenue") and s.get("pat") is not None:
        P.append(row("PAT margin", _pct(s["pat"] / s["revenue"])))
    P.append('</div>')

    # ---- 2 headline results ----
    P.append('<h2>2 &middot; Concluded values by method</h2>')

    # NAV card (shown once)
    P.append('<div class="headline">')

    # One headline card per CCM method
    for m in matrices:
        c = ccm_by_matrix.get(m, {})
        P.append(f'<div class="hcard primary"><div class="k">{_method_label(m)} (median)</div>'
                 f'<div class="big">{_cr(c.get("mid"))}</div>'
                 f'<div class="rng">median {_x(c.get("median_multiple"))} &middot; range '
                 f'{_cr(c.get("low"))} &ndash; {_cr(c.get("high"))} (&plusmn;5%)</div></div>')

    P.append('</div>')

    # ---- 3 comparables ----
    comps = result.get("selected_peers") or sc.get("comparables", [])
    thr = sc.get("thresholds_applied") or {}

    P.append(f'<h2>3 &middot; Comparable companies ({len(comps)})</h2>')
    if thr:
        parts = []
        for k, band in thr.items():
            lbl = k.replace("_", " ")
            rng = []
            if band.get("min") is not None:
                rng.append(f"min {band['min']}")
            if band.get("max") is not None:
                rng.append(f"max {band['max']}")
            parts.append(f"{lbl} ({', '.join(rng)})")
        P.append(f'<div class="purpose">Screened on: {_esc("; ".join(parts))} '
                 f'&middot; {sc.get("qualified")} qualified of {sc.get("pool_size")} '
                 f'in sub-sector &middot; top {len(comps)} used (max {sc.get("capped_at")}).</div>')
    else:
        P.append(f'<div class="purpose">All {sc.get("pool_size")} companies in the '
                 f'sub-sector (no thresholds applied) &middot; top {len(comps)} by '
                 f'size closeness (max {sc.get("capped_at")}).</div>')

    # Build column headers
    fin_headers = ['Revenue', 'EBITDA', 'PAT', 'EBITDA %', 'PAT %']
    fin_colspan = len(fin_headers)
    headers = ['Company'] + fin_headers
    for m in matrices:
        headers.append(_method_label(m))
    medians = []
    averages = []
    for m in matrices:
        ms = ccm_by_matrix.get(m, {}).get("multiple_summary", {})
        medians.append(_x(ms.get("median", "\u2014")))
        averages.append(_x(ms.get("average", "\u2014")))

    def fmt_row(c):
        parts = [f'<td>{_esc(c.get("name"))}</td>',
                 f'<td>{_cr(c.get("revenue"))}</td>',
                 f'<td>{_cr(c.get("ebitda"))}</td>',
                 f'<td>{_cr(c.get("pat"))}</td>',
                 f'<td>{_pct(c.get("ebitda_margin"))}</td>',
                 f'<td>{_pct(c.get("pat_margin"))}</td>']
        for m in matrices:
            if m == "EV/EBITDA":
                parts.append(f'<td>{_x(c.get("ev_ebitda"))}</td>')
            elif m == "EV/Revenue":
                parts.append(f'<td>{_x(c.get("ev_revenue"))}</td>')
            elif m == "P/E":
                parts.append(f'<td>{_x(c.get("pe"))}</td>')
            else:
                parts.append('\u2014')
        return '<tr>' + ''.join(parts) + '</tr>'

    P.append('<table><thead><tr>'
             + ''.join(f'<th>{h}</th>' for h in headers)
             + '</tr></thead><tbody>')
    for c in comps:
        P.append(fmt_row(c))

    med_parts = [f'<td><b>Median</b></td>', f'<td colspan="{fin_colspan}"></td>']
    for v in medians:
        med_parts.append(f'<td><b>{v}</b></td>')
    P.append('<tr class="med">' + ''.join(med_parts) + '</tr>')

    avg_parts = [f'<td><b>Average</b></td>', f'<td colspan="{fin_colspan}"></td>']
    for v in averages:
        avg_parts.append(f'<td><b>{v}</b></td>')
    P.append('<tr class="avg">' + ''.join(avg_parts) + '</tr>')
    P.append('</tbody></table>')

    # ---- 4 caveats ----
    P.append('<h2>4 &middot; Caveats</h2>')
    P.append('<ol class="cav">')
    for c in result.get("caveats", []):
        P.append(f'<li>{_esc(c)}</li>')
    P.append('</ol>')

    P.append(f'<div class="prov">Multiple source: {_esc(meta.get("multiple_source"))} '
             f'&middot; Data basis: {_esc(meta.get("as_of"))} &middot; Methods: '
             f'{_esc(" + ".join(meta.get("methods", [])))} &middot; Range: '
             f'{_esc(meta.get("range_basis"))} &middot; No control premium or DLOM '
             f'applied. Automated output &mdash; not a professional valuation report.</div>')

    # ---- Confidentiality footer ----
    P.append('<div class="confidential">')
    P.append('<div class="stamp">Confidential &mdash; Deloitte Internal</div>')
    P.append('This document is prepared by Deloitte Touche Tohmatsu Limited (\"Deloitte\") for internal use only. '
             'It is not intended to be and should not be used as a professional valuation report. '
             'The analysis is based on publicly available data and user-provided inputs; '
             'Deloitte makes no representation or warranty as to the accuracy or completeness thereof. '
             'No control premium or DLOM has been applied unless explicitly stated. '
             'Peer selection and screening thresholds affect reliability. '
             'This output is indicative and must not be used as a binding basis for any financial or investment decision without independent verification.')
    P.append('</div>')

    P.append('</div>')

    head = (f'<!doctype html><html class="digital" lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700;800&display=swap" rel="stylesheet">'
            f'<title>Valuation &mdash; {_esc(s.get("name") or "Company")}</title>'
            f'<style>{_STYLE}</style></head><body>')
    return head + "".join(P) + "</body></html>"
