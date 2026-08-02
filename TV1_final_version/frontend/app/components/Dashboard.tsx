"use client";

import { useState } from "react";
import { Approach, Calculation, Peer, ProResult } from "@/lib/types";
import { cr, mult, pct } from "@/lib/format";

type Tab = "overview" | "comparables" | "calculations" | "report";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "overview", label: "Overview", hint: "Conclusion & approaches" },
  { id: "comparables", label: "Comparables", hint: "Peer set & financials" },
  { id: "calculations", label: "Calculations", hint: "Three ratios, full working" },
  { id: "report", label: "Full Report", hint: "Comprehensive valuation report" },
];

const WEIGHT_COLOR: Record<string, string> = {
  "Income (DCF)": "#046a38",
  "Market (CCM)": "#86bc25",
  "Asset (NAV)": "#c9a227",
};

/* ================================================================ main */
export default function Dashboard({ result }: { result: ProResult }) {
  const [tab, setTab] = useState<Tab>("overview");
  const t = result.target;
  const con = result.conclusion;

  if (result.status === "no_match")
    return <p className="text-sm text-[color:var(--bad)]">No company matches that.</p>;
  if (result.status === "insufficient_peers")
    return (
      <p className="text-sm text-[color:var(--warn-ink)]">
        {result.message ?? "Not enough comparable companies."}
      </p>
    );

  return (
    <div>
      {/* company banner */}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-[color:var(--line)] pb-4">
        <div>
          <h3 className="text-xl font-bold">{t.name}</h3>
          <p className="text-sm text-[color:var(--muted)]">
            {t.sector}
            {t.industry ? ` · ${t.industry}` : ""}
            {t.listed ? " · Listed" : " · Private"}
          </p>
        </div>
        <div className="flex flex-wrap gap-6 text-right">
          <Stat label="Revenue" value={cr(t.revenue)} />
          <Stat label="EBITDA" value={cr(t.ebitda)} />
          <Stat label="PAT" value={cr(t.pat)} />
          {result.live_market ? (
            <Stat
              label="Live market cap"
              value={cr(result.live_market.market_cap_cr)}
              strong
            />
          ) : t.market_cap ? (
            <Stat label="Actual market cap" value={cr(t.market_cap as number)} strong />
          ) : null}
        </div>
      </div>

      {/* section nav */}
      <div className="mb-5 flex flex-wrap gap-1 border-b border-[color:var(--line)]">
        {TABS.map((s) => (
          <button
            key={s.id}
            onClick={() => setTab(s.id)}
            title={s.hint}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold transition ${
              tab === s.id
                ? "border-[#046a38] text-[#046a38]"
                : "border-transparent text-[color:var(--muted)] hover:text-[color:var(--ink)]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewSection result={result} con={con} />}
      {tab === "comparables" && <ComparablesSection result={result} />}
      {tab === "calculations" && <Calculations result={result} />}
      {tab === "report" && <FullReport result={result} con={con} />}
    </div>
  );
}

/* ================================================================ overview */
function OverviewSection({ result, con }: { result: ProResult; con: ProResult["conclusion"] }) {
  return (
    <section className="space-y-5">
      {con.status === "ok" ? (
        <div className="rounded-xl border border-[#cde3d4] bg-gradient-to-r from-[#f2f9f4] to-white p-5">
          <div className="flex flex-wrap items-end gap-x-10 gap-y-3">
            <Figure label="Low" value={cr(con.equity_low)} muted />
            <Figure label="Concluded equity value" value={cr(con.equity_mid)} big />
            <Figure label="High" value={cr(con.equity_high)} muted />
          </div>
          {con.weights && (
            <div className="mt-4">
              <div className="flex h-2 w-full overflow-hidden rounded-full">
                {Object.entries(con.weights).map(([k, w]) => (
                  <div
                    key={k}
                    style={{ width: `${w * 100}%`, background: WEIGHT_COLOR[k] }}
                    title={`${k}: ${(w * 100).toFixed(0)}%`}
                  />
                ))}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-x-4 text-[11px] text-[color:var(--muted)]">
                {Object.entries(con.weights).map(([k, w]) => (
                  <span key={k} className="inline-flex items-center gap-1.5">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ background: WEIGHT_COLOR[k] }}
                    />
                    {k} {(w * 100).toFixed(0)}%
                  </span>
                ))}
                {con.adjustments?.length ? <span>· {con.adjustments.join(", ")}</span> : null}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-[#f0dfae] bg-[color:var(--warn-bg)] p-4 text-sm text-[color:var(--warn-ink)]">
          Equity withheld — {con.reason}. EV ≈ {cr(con.ev_mid)}. Supply
          borrowings & cash to bridge EV → equity.
        </div>
      )}

      {/* live market cross-check */}
      {result.live_market && (
        <div className="rounded-xl border border-[color:var(--line)] bg-white p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-[11px] font-bold uppercase tracking-wide text-[color:var(--muted)]">
              Live market Check · fetched from {result.live_market.source}
            </p>
            <a
              href={result.live_market.url}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-semibold text-[#046a38] underline"
            >
              view source →
            </a>
          </div>
          <div className="mt-2 flex flex-wrap gap-6">
            <MiniStat
              label="Current market cap"
              value={cr(result.live_market.market_cap_cr)}
              strong
            />
            {result.live_market.pe != null && (
              <MiniStat label="Current P/E" value={mult(result.live_market.pe)} />
            )}
            {result.live_market.vs_conclusion_pct != null && (
              <MiniStat
                label="Our conclusion vs live"
                value={`${result.live_market.vs_conclusion_pct > 0 ? "+" : ""}${result.live_market.vs_conclusion_pct}%`}
              />
            )}
            {result.live_market.snapshot_staleness_pct != null && (
              <MiniStat
                label="Stored snapshot vs live"
                value={`${result.live_market.snapshot_staleness_pct > 0 ? "+" : ""}${result.live_market.snapshot_staleness_pct}%`}
              />
            )}
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {result.approaches.map((a) => (
          <ApproachCard key={a.approach} a={a} />
        ))}
      </div>
    </section>
  );
}

/* ================================================================ comparables */
function ComparablesSection({ result }: { result: ProResult }) {
  return (
    <section className="space-y-3">
      <p className="text-sm text-[color:var(--muted)]">
        {result.peers.length} comparable companies ·{" "}
        {result.peer_discovery?.tier === "sub-sector"
          ? "tight set (same sub-sector)"
          : "sector-level set"}
        {result.peer_discovery?.pool
          ? ` · screened from ${result.peer_discovery.pool} candidates`
          : ""}
      </p>
      <PeerFinancialTable peers={result.peers} />
      <p className="text-[11px] text-[color:var(--muted)]">
        Multiples are real published Capitaline figures used as-is. &quot;Match&quot; is
        the similarity score driving peer ranking (sub-sector, size, margin).
      </p>
    </section>
  );
}

/* ---- peer financials table (reusable) ---- */
function PeerFinancialTable({ peers, highlight }: { peers: Peer[]; highlight?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-[color:var(--line)]">
      <table className="table-pro">
        <thead>
          <tr>
            <th className="text-left">Company</th>
            <th className="text-left">Sub-sector</th>
            <th className="text-right">Revenue</th>
            <th className="text-right">EBITDA</th>
            <th className="text-right">PAT</th>
            <th className="text-right">Net Worth</th>
            <th className="text-right">Total Debt</th>
            <th className="text-right">Cash</th>
            <th className="text-right">Market Cap</th>
            <th className="text-right">EV</th>
            <th className="text-right">EBITDA %</th>
            <th className="text-right">PAT %</th>
            <th className="text-right">EV/EBITDA</th>
            <th className="text-right">EV/Rev</th>
            <th className="text-right">P/E</th>
            <th className="text-right">MCap/Sales</th>
            <th className="text-right">Match</th>
          </tr>
        </thead>
        <tbody>
          {peers.map((p, i) => (
            <tr key={p.code} className={highlight && i % 2 === 0 ? "bg-[#fafcfa]" : ""}>
              <td className="whitespace-nowrap font-medium">{p.name}</td>
              <td className="whitespace-nowrap text-[color:var(--muted)]">{p.industry}</td>
              <td className="text-right">{cr(p.revenue)}</td>
              <td className="text-right">{cr(p.ebitda)}</td>
              <td className="text-right">{cr(p.pat)}</td>
              <td className="text-right">{cr(p.net_worth)}</td>
              <td className="text-right">{cr(p.total_debt)}</td>
              <td className="text-right">{cr(p.cash)}</td>
              <td className="text-right">{cr(p.market_cap)}</td>
              <td className="text-right">{cr(p.enterprise_value)}</td>
              <td className="text-right">{pct(p.ebitda_margin)}</td>
              <td className="text-right">{pct(p.pat_margin)}</td>
              <td className="text-right">{mult(p.ev_ebitda)}</td>
              <td className="text-right">{mult(p.ev_revenue)}</td>
              <td className="text-right">{mult(p.pe)}</td>
              <td className="text-right">{mult(p.mktcap_sales)}</td>
              <td className="text-right font-semibold">{(p.score * 100).toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ================================================================ calculations */
function Calculations({ result }: { result: ProResult }) {
  const ccm = result.approaches.find((a) => a.approach === "Market (CCM)");
  const calcs: Calculation[] = ccm?.calculations ?? [];
  const dcf = result.approaches.find((a) => a.approach === "Income (DCF)");
  const nav = result.approaches.find((a) => a.approach === "Asset (NAV)");

  return (
    <section className="space-y-5">
      <div>
        <h4 className="mb-1 text-sm font-bold">
          Market approach — valuation on three ratios
        </h4>
        <p className="mb-3 text-xs text-[color:var(--muted)]">
          Each ratio is applied to the subject&apos;s own driver. The peer spread shows
          how much genuine dispersion exists in the comparable set.
        </p>
        <div className="space-y-3">
          {calcs.map((c) => (
            <CalcCard c={c} key={c.ratio} />
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {dcf?.status === "ok" && dcf.assumptions && (
          <div className="rounded-xl border border-[color:var(--line)] p-4">
            <p className="text-sm font-bold">Income approach — DCF</p>
            <DcfTable assumptions={dcf.assumptions} equityMid={dcf.equity_mid} />
          </div>
        )}
        {nav?.status === "ok" && nav.components && (
          <div className="rounded-xl border border-[color:var(--line)] p-4">
            <p className="text-sm font-bold">Asset approach — NAV</p>
            <NavTable components={nav.components} equityMid={nav.equity_mid} />
          </div>
        )}
      </div>
    </section>
  );
}

/* ================================================================ full report */
function FullReport({ result, con }: { result: ProResult; con: ProResult["conclusion"] }) {
  const t = result.target;
  const chk = result.llm_check;
  const ccm = result.approaches.find((a) => a.approach === "Market (CCM)");
  const dcf = result.approaches.find((a) => a.approach === "Income (DCF)");
  const nav = result.approaches.find((a) => a.approach === "Asset (NAV)");
  const calcs: Calculation[] = ccm?.calculations ?? [];
  const llmPos = ccm?.headline?.multiple_basis as
    | { llm_rationale?: string; llm_percentile?: number; llm_confidence?: string }
    | undefined;
  const dcfNote = (
    result.approaches.find((a) => a.approach === "Income (DCF)")?.assumptions as
      | { note?: string }
      | undefined
  )?.note;

  const VERDICT_STYLE: Record<string, string> = {
    fair: "bg-[#eef7f1] text-[#067647] border-[#cde3d4]",
    high: "bg-[color:var(--warn-bg)] text-[color:var(--warn-ink)] border-[#f0dfae]",
    low: "bg-[color:var(--warn-bg)] text-[color:var(--warn-ink)] border-[#f0dfae]",
  };

  return (
    <section className="space-y-6 print:text-black">
      {/* ----- REPORT HEADER ----- */}
      <div className="rounded-xl border-2 border-[#046a38] bg-[#0b2e1f] p-6 text-white print:bg-white print:text-black print:border-gray-300">
        <div className="flex items-center gap-3 mb-1">
          <svg viewBox="0 0 200 40" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ height: 24, width: "auto" }}>
            <circle cx="12" cy="20" r="6" fill="#86BC25" />
            <text x="26" y="26" fill="white" fontFamily="Open Sans, sans-serif" fontWeight="700" fontSize="18">Deloitte</text>
          </svg>
        </div>
        <h2 className="text-2xl font-extrabold mt-2">Valuation Report</h2>
        <p className="text-sm text-emerald-200 print:text-gray-500 mt-1">
          Deloitte Touchless Valuation TV 1 — Three-approach triangulated valuation
        </p>
        <div className="mt-3 flex flex-wrap gap-6 text-sm">
          <span className="font-semibold">{t.name}</span>
          <span>{t.sector}{t.industry ? ` · ${t.industry}` : ""}</span>
          <span>{t.listed ? "Listed" : "Private"}</span>
          <span>Revenue {cr(t.revenue)}</span>
          <span>EBITDA {cr(t.ebitda)}</span>
        </div>
      </div>

      {/* ----- 1. EXECUTIVE SUMMARY ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          1. Executive Summary
        </h3>
        {con.status === "ok" ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-x-10 gap-y-3">
              <Figure label="Equity Low" value={cr(con.equity_low)} muted />
              <Figure label="Concluded Equity Value" value={cr(con.equity_mid)} big />
              <Figure label="Equity High" value={cr(con.equity_high)} muted />
              {con.ev_mid && (
                <Figure label="Enterprise Value" value={cr(con.ev_mid)} />
              )}
            </div>
            {con.weights && (
              <div className="mt-3">
                <p className="text-xs font-semibold text-[color:var(--muted)] mb-2">Approach Weights</p>
                <div className="flex h-3 w-full max-w-md overflow-hidden rounded-full">
                  {Object.entries(con.weights).map(([k, w]) => (
                    <div
                      key={k}
                      style={{ width: `${w * 100}%`, background: WEIGHT_COLOR[k] }}
                      title={`${k}: ${(w * 100).toFixed(0)}%`}
                    />
                  ))}
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 text-[11px] text-[color:var(--muted)]">
                  {Object.entries(con.weights).map(([k, w]) => (
                    <span key={k} className="inline-flex items-center gap-1.5">
                      <span className="inline-block h-2 w-2 rounded-full" style={{ background: WEIGHT_COLOR[k] }} />
                      {k} {(w * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            )}
            {con.dlom && (
              <p className="text-sm text-[color:var(--muted)]">
                DLOM: <span className="font-semibold">{(con.dlom * 100).toFixed(0)}%</span> discount for lack of marketability
              </p>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-[#f0dfae] bg-[color:var(--warn-bg)] p-4 text-sm text-[color:var(--warn-ink)]">
            Equity withheld — {con.reason}. EV ≈ {cr(con.ev_mid)}. Supply
            borrowings & cash to bridge EV → equity.
          </div>
        )}
      </div>

      {/* ----- 2. TARGET COMPANY PROFILE ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          2. Target Company Profile
        </h3>
        <div className="grid gap-3 sm:grid-cols-4">
          <MiniStat label="Company" value={t.name} strong />
          <MiniStat label="Sector" value={t.sector ?? "—"} />
          <MiniStat label="Sub-sector" value={t.industry ?? "—"} />
          <MiniStat label="Type" value={t.listed ? "Listed" : "Private"} />
          <MiniStat label="Revenue" value={cr(t.revenue)} strong />
          <MiniStat label="EBITDA" value={cr(t.ebitda)} />
          <MiniStat label="EBITDA Margin" value={t.ebitda_margin != null ? pct(t.ebitda_margin) : "—"} />
          <MiniStat label="PAT" value={cr(t.pat)} />
          <MiniStat label="Net Worth" value={cr(t.net_worth as number | null)} />
          <MiniStat label="Total Debt" value={cr(t.total_debt as number | null)} />
          <MiniStat label="Cash" value={cr(t.cash as number | null)} />
          <MiniStat label="Net Debt" value={cr(t.net_debt_effective)} />
          {t.market_cap ? <MiniStat label="Market Cap" value={cr(t.market_cap as number)} strong /> : null}
        </div>
      </div>

      {/* ----- 3. COMPARABLE COMPANIES ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-2">
          3. Comparable Companies
        </h3>
        <p className="text-sm text-[color:var(--muted)] mb-4">
          {result.peers.length} comparable companies selected ·{" "}
          {result.peer_discovery?.tier === "sub-sector" ? "tight set (same sub-sector)" : "sector-level set"}
          {result.peer_discovery?.pool ? ` · screened from ${result.peer_discovery.pool} candidates` : ""}
        </p>
        <PeerFinancialTable peers={result.peers} highlight />
      </div>

      {/* ----- 4. MARKET APPROACH — CCM ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          4. Market Approach — Comparable Company Multiples (CCM)
        </h3>
        {ccm?.status === "ok" ? (
          <div className="space-y-4">
            {/* approach summary */}
            <div className="flex flex-wrap gap-6 items-end">
              <Figure label="Equity Low" value={cr(ccm.equity_low)} muted />
              <Figure label="Equity Mid" value={cr(ccm.equity_mid)} big />
              <Figure label="Equity High" value={cr(ccm.equity_high)} muted />
              {ccm.ev_mid && <Figure label="EV" value={cr(ccm.ev_mid)} />}
            </div>
            {ccm.headline && (
              <div className="mt-2 rounded-lg bg-[#fafcfa] p-3 text-sm">
                <span className="font-semibold">Headline multiple:</span>{" "}
                {ccm.headline.multiple_kind} = {mult(ccm.headline.multiple)}
                {ccm.headline.multiple_basis && (
                  <>
                    {" "}({ccm.headline.multiple_basis.method}
                    {ccm.headline.multiple_basis.n != null && `, n=${ccm.headline.multiple_basis.n}`}
                    {ccm.headline.multiple_basis.peer_median != null && `, peer median=${mult(ccm.headline.multiple_basis.peer_median)}`}
                    {ccm.headline.multiple_basis.regression_multiple != null && `, regression=${mult(ccm.headline.multiple_basis.regression_multiple)}`}
                    {ccm.headline.multiple_basis.r2 != null && `, R²=${(ccm.headline.multiple_basis.r2 * 100).toFixed(0)}%`})
                  </>
                )}
              </div>
            )}

            {/* ratio cards */}
            <p className="text-xs font-semibold text-[color:var(--muted)] mt-4 mb-2">
              Detailed ratio application
            </p>
            <div className="space-y-3">
              {calcs.map((c) => (
                <CalcCard c={c} key={c.ratio} />
              ))}
            </div>

            {/* supporting multiples */}
            {ccm.supporting && ccm.supporting.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-[color:var(--muted)] mb-2">Supporting multiples</p>
                <div className="overflow-x-auto rounded-xl border border-[color:var(--line)]">
                  <table className="table-pro">
                    <thead>
                      <tr>
                        <th>Multiple</th>
                        <th className="text-right">Value</th>
                        <th className="text-right">Equity Mid</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ccm.supporting.map((s, i) => (
                        <tr key={i}>
                          <td className="font-medium">{s.multiple_kind}</td>
                          <td className="text-right">{mult(s.multiple)}</td>
                          <td className="text-right">{s.equity_mid != null ? cr(s.equity_mid) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-[color:var(--muted)]">Not applied — {ccm?.reason}</p>
        )}
      </div>

      {/* ----- 5. INCOME APPROACH — DCF ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          5. Income Approach — Discounted Cash Flow (DCF)
        </h3>
        {dcf?.status === "ok" && dcf.assumptions ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-6 items-end">
              <Figure label="Equity Low" value={cr(dcf.equity_low)} muted />
              <Figure label="Equity Mid" value={cr(dcf.equity_mid)} big />
              <Figure label="Equity High" value={cr(dcf.equity_high)} muted />
              {dcf.ev_mid && <Figure label="EV" value={cr(dcf.ev_mid)} />}
            </div>
            <DcfTable assumptions={dcf.assumptions} equityMid={dcf.equity_mid} detailed />
          </div>
        ) : (
          <p className="text-sm text-[color:var(--muted)]">Not applied — {dcf?.reason}</p>
        )}
      </div>

      {/* ----- 6. ASSET APPROACH — NAV ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          6. Asset Approach — Net Asset Value (NAV)
        </h3>
        {nav?.status === "ok" && nav.components ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-6 items-end">
              <Figure label="Equity Low" value={cr(nav.equity_low)} muted />
              <Figure label="Equity Mid" value={cr(nav.equity_mid)} big />
              <Figure label="Equity High" value={cr(nav.equity_high)} muted />
              {nav.ev_mid && <Figure label="EV" value={cr(nav.ev_mid)} />}
            </div>
            <NavTable components={nav.components} equityMid={nav.equity_mid} detailed />
          </div>
        ) : (
          <p className="text-sm text-[color:var(--muted)]">Not applied — {nav?.reason}</p>
        )}
      </div>

      {/* ----- 7. TRIANGULATION & CONCLUSION ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          7. Triangulation & Conclusion
        </h3>
        <div className="space-y-4">
          {/* approach comparison table */}
          <div className="overflow-x-auto rounded-xl border border-[color:var(--line)]">
            <table className="table-pro">
              <thead>
                <tr>
                  <th>Approach</th>
                  <th className="text-right">Equity Low</th>
                  <th className="text-right">Equity Mid</th>
                  <th className="text-right">Equity High</th>
                  <th className="text-right">Weight</th>
                  <th className="text-right">EV Mid</th>
                </tr>
              </thead>
              <tbody>
                {result.approaches.map((a) => (
                  <tr key={a.approach}>
                    <td className="font-medium">
                      <span className="inline-block h-2 w-2 rounded-full mr-1.5" style={{ background: WEIGHT_COLOR[a.approach] ?? "#999" }} />
                      {a.approach}
                    </td>
                    <td className="text-right">{a.status === "ok" ? cr(a.equity_low) : "—"}</td>
                    <td className="text-right font-semibold">{a.status === "ok" ? cr(a.equity_mid) : "—"}</td>
                    <td className="text-right">{a.status === "ok" ? cr(a.equity_high) : "—"}</td>
                    <td className="text-right">{con.weights?.[a.approach] != null ? `${(con.weights[a.approach] * 100).toFixed(0)}%` : "—"}</td>
                    <td className="text-right">{a.status === "ok" && a.ev_mid ? cr(a.ev_mid) : "—"}</td>
                  </tr>
                ))}
                <tr className="border-t-2 border-[color:var(--line)] font-bold">
                  <td>Triangulated Conclusion</td>
                  <td className="text-right">{cr(con.equity_low)}</td>
                  <td className="text-right text-[#046a38]">{cr(con.equity_mid)}</td>
                  <td className="text-right">{cr(con.equity_high)}</td>
                  <td className="text-right">100%</td>
                  <td className="text-right">{cr(con.ev_mid)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {con.dlom && (
            <p className="text-sm">
              <span className="font-semibold">DLOM applied:</span>{" "}
              {(con.dlom * 100).toFixed(0)}% discount for lack of marketability (private/illiquid)
            </p>
          )}
          {con.adjustments && con.adjustments.length > 0 && (
            <p className="text-sm">
              <span className="font-semibold">Adjustments:</span> {con.adjustments.join(", ")}
            </p>
          )}
        </div>
      </div>

      {/* ----- 8. LLM SECOND OPINION ----- */}
      {chk && (
        <div className="rounded-xl border border-[color:var(--line)] p-5">
          <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
            8. Independent LLM Review
          </h3>
          <div className={`rounded-xl border p-4 ${VERDICT_STYLE[chk.verdict] ?? ""}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-[11px] font-bold uppercase tracking-wide">
                Verdict: engine looks {chk.verdict}
              </p>
              <span className="text-[11px]">
                model {chk.model} · self-rated {chk.confidence} knowledge
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-6">
              <MiniStat label="Engine conclusion" value={cr(chk.engine_equity_mid)} />
              <MiniStat label="LLM estimate" value={cr(chk.estimate_cr)} />
              <MiniStat
                label="Weight applied to LLM"
                value={`${(chk.weight_applied * 100).toFixed(0)}%`}
              />
            </div>
            <p className="mt-2 text-sm">{chk.comment}</p>
            {chk.weight_applied === 0 && (
              <p className="mt-2 text-[11px] opacity-80">
                Reported as a disclosed second opinion only — not blended into the
                number.
              </p>
            )}
          </div>
          {llmPos?.llm_rationale && (
            <div className="mt-3 rounded-xl border border-[color:var(--line)] bg-[color:var(--accent-soft)] p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-[#3d6b0f]">
                Qualitative positioning · P
                {Math.round((llmPos.llm_percentile ?? 0.5) * 100)} of peer range ·{" "}
                {llmPos.llm_confidence} confidence
              </p>
              <p className="mt-1 text-sm text-[#2c4a1a]">{llmPos.llm_rationale}</p>
            </div>
          )}
        </div>
      )}

      {/* ----- 9. AUDIT TRAIL ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          9. Audit Trail
        </h3>
        <ul className="space-y-1.5 text-xs text-[color:var(--muted)]">
          <Trail label="Peer selection">
            {result.peer_discovery?.tier === "sub-sector"
              ? "same sub-sector (tight tier)"
              : "sector-level tier"}{" "}
            · {result.peers.length} used of {result.peer_discovery?.pool ?? "—"}{" "}
            screened
          </Trail>
          <Trail label="Multiples">
            real published Capitaline figures, winsorized and Tukey-trimmed; used
            as-is (never recomputed)
          </Trail>
          {(() => {
            const d = (ccm?.headline?.multiple_basis as
              | { market_drift_applied?: number }
              | undefined)?.market_drift_applied;
            return d ? (
              <Trail label="Market drift">
                peer multiples re-levelled ×{d} to today&apos;s market (snapshot
                staleness measured live from screener.in)
              </Trail>
            ) : null;
          })()}
          {result.live_market && (
            <Trail label="Live cross-check">
              current market cap {cr(result.live_market.market_cap_cr)} from{" "}
              {result.live_market.source}
              {result.live_market.snapshot_staleness_pct != null
                ? ` · stored snapshot ${result.live_market.snapshot_staleness_pct}% vs live`
                : ""}
            </Trail>
          )}
          {dcfNote && <Trail label="DCF assumptions">{dcfNote}</Trail>}
          <Trail label="Approach weights">
            {con.weights
              ? Object.entries(con.weights)
                  .map(([k, w]) => `${k} ${(w * 100).toFixed(0)}%`)
                  .join(" · ")
              : "—"}
          </Trail>
          {con.dlom ? (
            <Trail label="DLOM">
              {(con.dlom * 100).toFixed(0)}% discount for lack of marketability
              (private, illiquid)
            </Trail>
          ) : null}
          <Trail label="Equity bridge">
            {con.equity_requires
              ? `withheld — requires ${con.equity_requires.join(", ")}`
              : "net debt known; EV bridged to equity (no assumption made)"}
          </Trail>
        </ul>
      </div>

      {/* ----- 10. BASIS & CAVEATS ----- */}
      <div className="rounded-xl border border-[color:var(--line)] p-5">
        <h3 className="text-base font-bold border-b border-[color:var(--line)] pb-2 mb-4">
          10. Basis & Caveats
        </h3>
        <ul className="list-disc space-y-1 pl-5 text-xs text-[color:var(--muted)]">
          {result.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
        <p className="mt-4 text-[11px] text-[color:var(--muted)]">
          Indicative screening valuation aligned to ICAI/IBBI methodology — not
          a certified registered-valuer opinion. Prepared by Deloitte Touchless
          Valuation TV 1.
        </p>
      </div>

      {/* ----- print button ----- */}
      <div className="flex gap-3 print:hidden">
        <button
          onClick={() => window.print()}
          className="btn-primary"
        >
          Print / Save as PDF
        </button>
      </div>
    </section>
  );
}

/* ================================================================ shared sub-components */

function CalcCard({ c }: { c: Calculation }) {
  return (
    <div className="rounded-xl border border-[color:var(--line)] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-bold">{c.ratio}</span>
        {c.applies ? (
          <span className="text-xs text-[color:var(--muted)]">
            peers n={c.peer_stats?.n} · spread {mult(c.peer_stats?.min)} –{" "}
            {mult(c.peer_stats?.max)} · median {mult(c.peer_stats?.median)}
          </span>
        ) : (
          <span className="text-xs text-[color:var(--warn-ink)]">
            not applied — {c.reason}
          </span>
        )}
      </div>
      {c.applies && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat
              label={`Multiple used (${c.multiple_source})`}
              value={mult(c.multiple_used)}
            />
            <MiniStat
              label={c.driver_label ?? "Driver"}
              value={cr(c.driver_value)}
            />
            <MiniStat
              label="Enterprise value"
              value={c.enterprise_value != null ? cr(c.enterprise_value) : "n/a"}
            />
            <MiniStat
              label="Equity value"
              value={cr(c.equity_value)}
              strong
            />
          </div>
          {/* peer stats detail */}
          {c.peer_stats && (
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5 text-xs">
              <div>
                <span className="text-[color:var(--muted)]">Peer count</span>
                <p className="font-semibold">{c.peer_stats.n}</p>
              </div>
              <div>
                <span className="text-[color:var(--muted)]">Min</span>
                <p className="font-semibold">{mult(c.peer_stats.min)}</p>
              </div>
              <div>
                <span className="text-[color:var(--muted)]">Median</span>
                <p className="font-semibold">{mult(c.peer_stats.median)}</p>
              </div>
              <div>
                <span className="text-[color:var(--muted)]">Max</span>
                <p className="font-semibold">{mult(c.peer_stats.max)}</p>
              </div>
              <div>
                <span className="text-[color:var(--muted)]">Multiple used</span>
                <p className="font-semibold">{mult(c.multiple_used)} ({c.multiple_source})</p>
              </div>
            </div>
          )}
          <p className="mt-3 rounded-lg bg-[#fafcfa] p-2 font-mono text-[11px] text-[color:var(--muted)]">
            {c.formula}
          </p>
        </>
      )}
    </div>
  );
}

function DcfTable({ assumptions, equityMid }: { assumptions: Record<string, unknown>; equityMid?: number; detailed?: boolean }) {
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="border-b border-[color:var(--line)]">
          <th className="py-1 text-left font-semibold">Parameter</th>
          <th className="py-1 text-right font-semibold">Value</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(assumptions)
          .filter(([k]) => k !== "note")
          .map(([k, v]) => (
            <tr key={k}>
              <td className="py-1 text-[color:var(--muted)]">
                {k.replace(/_/g, " ")}
              </td>
              <td className="py-1 text-right font-medium">
                {typeof v === "number" && v < 1 && v > -1
                  ? `${(v * 100).toFixed(1)}%`
                  : typeof v === "number"
                  ? cr(v)
                  : String(v)}
              </td>
            </tr>
          ))}
        <tr className="border-t-2 border-[color:var(--line)]">
          <td className="pt-2 font-bold">Equity value</td>
          <td className="pt-2 text-right font-bold text-[#046a38]">{cr(equityMid)}</td>
        </tr>
      </tbody>
    </table>
  );
}

function NavTable({ components, equityMid }: { components: Record<string, number>; equityMid?: number; detailed?: boolean }) {
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="border-b border-[color:var(--line)]">
          <th className="py-1 text-left font-semibold">Component</th>
          <th className="py-1 text-right font-semibold">Value (₹ Cr)</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(components).map(([k, v]) => (
          <tr key={k}>
            <td className="py-1 text-[color:var(--muted)]">
              {k.replace(/_/g, " ")}
            </td>
            <td className="py-1 text-right font-medium">{cr(v)}</td>
          </tr>
        ))}
        <tr className="border-t-2 border-[color:var(--line)]">
          <td className="pt-2 font-bold">Equity value</td>
          <td className="pt-2 text-right font-bold text-[#046a38]">{cr(equityMid)}</td>
        </tr>
      </tbody>
    </table>
  );
}

/* ------------------------------------------------- approach card (overview) */
function ApproachCard({ a }: { a: Approach }) {
  const BLURB: Record<string, string> = {
    "Income (DCF)": "Own forecast cash flows, discounted",
    "Market (CCM)": "Peer multiples · fundamentals + positioning",
    "Asset (NAV)": "Net worth + surplus items",
  };
  return (
    <div className="card p-4">
      <p className="text-sm font-bold">{a.approach}</p>
      <p className="mb-2 text-[11px] text-[color:var(--muted)]">{BLURB[a.approach]}</p>
      {a.status === "ok" ? (
        <>
          <p className="text-xl font-bold text-[#0b2e1f]">{cr(a.equity_mid)}</p>
          {a.approach === "Market (CCM)" && a.headline && (
            <p className="mt-1 text-xs text-[color:var(--muted)]">
              {a.headline.multiple_kind} {mult(a.headline.multiple)}
            </p>
          )}
          {a.approach === "Income (DCF)" && a.assumptions && (
            <p className="mt-1 text-xs text-[color:var(--muted)]">
              g{" "}
              {((a.assumptions as Record<string, number>).growth_initial * 100).toFixed(1)}
              % · WACC{" "}
              {((a.assumptions as Record<string, number>).wacc * 100).toFixed(1)}%
            </p>
          )}
          {a.approach === "Asset (NAV)" && a.components && (
            <p className="mt-1 text-xs text-[color:var(--muted)]">
              Net worth {cr(a.components.net_worth)}
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-[color:var(--muted)]">Not used — {a.reason}</p>
      )}
    </div>
  );
}

function Trail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li>
      <span className="font-semibold text-[color:var(--ink)]">{label}:</span>{" "}
      {children}
    </li>
  );
}

function Stat({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-[color:var(--muted)]">
        {label}
      </p>
      <p className={`text-sm ${strong ? "font-bold text-[#046a38]" : "font-semibold"}`}>
        {value}
      </p>
    </div>
  );
}

function MiniStat({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-[color:var(--muted)]">
        {label}
      </p>
      <p className={`text-sm ${strong ? "font-bold text-[#046a38]" : "font-semibold"}`}>
        {value}
      </p>
    </div>
  );
}

function Figure({
  label,
  value,
  big,
  muted,
}: {
  label: string;
  value: string;
  big?: boolean;
  muted?: boolean;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-[color:var(--muted)]">
        {label}
      </p>
      <p
        className={
          big
            ? "text-3xl font-extrabold text-[#0b2e1f]"
            : muted
            ? "text-lg font-semibold text-[color:var(--muted)]"
            : "text-lg font-semibold"
        }
      >
        {value}
      </p>
    </div>
  );
}
