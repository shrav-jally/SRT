"use client";

import { useEffect, useRef, useState } from "react";
import { ProResult, SearchHit, SectorNode } from "@/lib/types";
import Dashboard from "@/app/components/Dashboard";
import LoginPage from "@/app/components/LoginPage";

type Mode = "listed" | "private";

type Assumptions = {
  growth_initial: string;
  growth_terminal: string;
  ebit_margin: string;
  wacc: string;
  surplus_assets: string;
};

export default function Home() {
  /* ---- auth state ---- */
  const [user, setUser] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);

  // hydrate from sessionStorage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem("tv1_user");
    if (stored) setUser(stored);
    setAuthReady(true);
  }, []);

  function handleLogin(username: string) {
    sessionStorage.setItem("tv1_user", username);
    setUser(username);
  }

  function handleLogout() {
    sessionStorage.removeItem("tv1_user");
    setUser(null);
  }

  /* ---- valuation state ---- */
  const [mode, setMode] = useState<Mode>("listed");
  const [result, setResult] = useState<ProResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [assump, setAssump] = useState<Assumptions | null>(null);
  const [lastReq, setLastReq] = useState<{
    url: string;
    body: Record<string, unknown>;
  } | null>(null);

  // when a valuation lands, surface the assumptions it used (editable, step 2)
  function onResult(r: ProResult) {
    setResult(r);
    const dcf = r.approaches?.find((a) => a.approach === "Income (DCF)");
    const a = dcf?.assumptions as Record<string, number> | undefined;
    if (a) {
      setAssump({
        growth_initial: (a.growth_initial * 100).toFixed(1),
        growth_terminal: (a.growth_terminal * 100).toFixed(1),
        ebit_margin: a.ebit_margin != null ? (a.ebit_margin * 100).toFixed(1) : "",
        wacc: (a.wacc * 100).toFixed(1),
        surplus_assets: "0",
      });
    } else {
      setAssump(null);
    }
  }

  async function runValuation(url: string, body: Record<string, unknown>) {
    setLoading(true);
    setLastReq({ url, body });
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      onResult(await r.json());
    } finally {
      setLoading(false);
    }
  }

  async function revalue() {
    if (!lastReq || !assump) return;
    const overrides = {
      dcf: {
        growth_initial: Number(assump.growth_initial) / 100,
        growth_terminal: Number(assump.growth_terminal) / 100,
        ...(assump.ebit_margin !== "" && {
          ebit_margin: Number(assump.ebit_margin) / 100,
        }),
        wacc: Number(assump.wacc) / 100,
        note: "analyst inputs (edited on page)",
      },
      asset: { surplus_assets: Number(assump.surplus_assets) || 0 },
    };
    await runValuation(lastReq.url, { ...lastReq.body, overrides });
  }

  // show login page until authenticated
  if (!authReady) return null;
  if (!user) return <LoginPage onLogin={handleLogin} />;

  return (
    <div className="min-h-screen">
      {/* header band */}
      <header className="bg-[#0b2e1f] px-6 py-4 text-white">
        <div className="mx-auto flex max-w-5xl items-baseline justify-between">
          <div>
            <span className="text-lg font-bold tracking-tight">
              Deloitte Touchless Valuation
            </span>
            <span className="ml-2 rounded bg-[#86bc25] px-1.5 py-0.5 text-[10px] font-bold text-[#0b2e1f]">
              TV 1
            </span>
          </div>
          <div className="flex items-baseline gap-4">
            <span className="text-xs text-emerald-100/70">
              Income · Market · Asset — triangulated | 4,200+ listed Indian
              comparables
            </span>
            <button
              onClick={handleLogout}
              className="dds-btn dds-btn_sm rounded border-white/20 text-white/60 hover:border-white/40 hover:text-white"
              title="Sign out"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-5 py-8">
        {/* ---------------- step 1 · company ---------------- */}
        <section className="card p-6">
          <div className="mb-4 flex items-center gap-3">
            <span className="step-badge">1</span>
            <h2 className="text-base font-semibold">Company</h2>
            <div className="ml-auto inline-flex rounded-lg border border-[color:var(--line)] p-0.5 text-sm">
              {(["listed", "private"] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`rounded-md px-4 py-1.5 font-medium transition ${
                    mode === m
                      ? "bg-[#046a38] text-white"
                      : "text-[color:var(--muted)] hover:text-[color:var(--ink)]"
                  }`}
                >
                  {m === "listed" ? "Listed" : "Private"}
                </button>
              ))}
            </div>
          </div>
          {mode === "listed" ? (
            <ListedSearch
              disabled={loading}
              onPick={(h) =>
                runValuation("/api/value-pro", { code: h.code, max_peers: 8 })
              }
            />
          ) : (
            <PrivateForm
              disabled={loading}
              onSubmit={(target) =>
                runValuation("/api/value-pro-custom", { target, max_peers: 8 })
              }
            />
          )}
        </section>

        {/* ---------------- step 2 · assumptions ---------------- */}
        <section className={`card p-6 ${!assump ? "opacity-50" : ""}`}>
          <div className="mb-1 flex items-center gap-3">
            <span className="step-badge">2</span>
            <h2 className="text-base font-semibold">Assumptions</h2>
            {assump && (
              <span className="rounded-full bg-[color:var(--accent-soft)] px-2.5 py-0.5 text-[11px] font-semibold text-[#3d6b0f]">
                auto-derived from the company's own history — edit &amp; re-value
              </span>
            )}
          </div>
          {assump ? (
            <>
              <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-5">
                <Field label="Growth next yr (%)">
                  <input
                    className="input"
                    type="number"
                    value={assump.growth_initial}
                    onChange={(e) =>
                      setAssump({ ...assump, growth_initial: e.target.value })
                    }
                  />
                </Field>
                <Field label="Terminal growth (%)">
                  <input
                    className="input"
                    type="number"
                    value={assump.growth_terminal}
                    onChange={(e) =>
                      setAssump({ ...assump, growth_terminal: e.target.value })
                    }
                  />
                </Field>
                <Field label="EBIT margin (%)">
                  <input
                    className="input"
                    type="number"
                    value={assump.ebit_margin}
                    onChange={(e) =>
                      setAssump({ ...assump, ebit_margin: e.target.value })
                    }
                  />
                </Field>
                <Field label="WACC (%)">
                  <input
                    className="input"
                    type="number"
                    value={assump.wacc}
                    onChange={(e) => setAssump({ ...assump, wacc: e.target.value })}
                  />
                </Field>
                <Field label="Surplus assets (₹ Cr)">
                  <input
                    className="input"
                    type="number"
                    value={assump.surplus_assets}
                    onChange={(e) =>
                      setAssump({ ...assump, surplus_assets: e.target.value })
                    }
                  />
                </Field>
              </div>
              <button onClick={revalue} disabled={loading} className="btn-primary mt-4">
                Re-value with these assumptions
              </button>
            </>
          ) : (
            <p className="mt-2 text-sm text-[color:var(--muted)]">
              Select a company above — its growth, margin and discount rate are
              derived automatically and become editable here.
            </p>
          )}
        </section>

        {/* ---------------- step 3 · conclusion ---------------- */}
        <section className={`card p-6 ${!result && !loading ? "opacity-50" : ""}`}>
          <div className="mb-4 flex items-center gap-3">
            <span className="step-badge">3</span>
            <h2 className="text-base font-semibold">Valuation conclusion</h2>
          </div>
          {loading && (
            <p className="text-sm text-[color:var(--muted)]">
              Running Income · Market · Asset triangulation…
            </p>
          )}
          {!loading && result && <Dashboard result={result} />}
          {!loading && !result && (
            <p className="text-sm text-[color:var(--muted)]">
              The triangulated range, the three approaches, the LLM analyst's
              note and the comparable set appear here.
            </p>
          )}
        </section>

        <footer className="pb-6 text-center text-[11px] text-[color:var(--muted)]">
          Indicative screening valuation aligned to ICAI/IBBI methodology — not
          a certified registered-valuer opinion.
        </footer>
      </main>
    </div>
  );
}

/* ----------------------------------------------- listed search */
function ListedSearch({
  onPick,
  disabled,
}: {
  onPick: (h: SearchHit) => void;
  disabled: boolean;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    timer.current = setTimeout(async () => {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      setHits(await r.json());
      setOpen(true);
    }, 200);
  }, [q]);

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
        placeholder="Search a listed company — e.g. Balaji Amines, ACC, KEI…"
        className="input"
      />
      {open && hits.length > 0 && (
        <ul className="card absolute z-10 mt-1 max-h-72 w-full overflow-auto">
          {hits.map((h) => (
            <li key={h.code}>
              <button
                onClick={() => {
                  setOpen(false);
                  setQ(h.name);
                  onPick(h);
                }}
                disabled={disabled}
                className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm hover:bg-[color:var(--accent-soft)] disabled:opacity-50"
              >
                <span>
                  <span className="font-medium">{h.name}</span>
                  <span className="ml-2 text-xs text-[color:var(--muted)]">
                    {h.sector}
                  </span>
                </span>
                {!h.valuation_grade && (
                  <span className="text-[11px] text-[color:var(--warn-ink)]">
                    no current multiple
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ----------------------------------------------- private form */
const NUM_FIELDS: { key: string; label: string }[] = [
  { key: "revenue", label: "Revenue (₹ Cr)" },
  { key: "ebitda", label: "EBITDA (₹ Cr)" },
  { key: "pat", label: "PAT (₹ Cr)" },
  { key: "net_worth", label: "Net worth (₹ Cr)" },
  { key: "total_debt", label: "Total debt (₹ Cr)" },
  { key: "cash", label: "Cash (₹ Cr)" },
];

function PrivateForm({
  onSubmit,
  disabled,
}: {
  onSubmit: (target: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  const [sectors, setSectors] = useState<SectorNode[]>([]);
  const [name, setName] = useState("");
  const [sector, setSector] = useState("");
  const [industry, setIndustry] = useState("");
  const [nums, setNums] = useState<Record<string, string>>({});

  useEffect(() => {
    fetch("/api/sectors")
      .then((r) => r.json())
      .then(setSectors)
      .catch(() => setSectors([]));
  }, []);

  const industries = sectors.find((s) => s.sector === sector)?.industries ?? [];
  const canSubmit = sector && (nums.ebitda || nums.revenue || nums.pat);

  function submit() {
    const target: Record<string, unknown> = {
      name: name || "Target company",
      sector,
      source: "user",
    };
    if (industry) target.industry = industry;
    for (const f of NUM_FIELDS) {
      const v = nums[f.key];
      if (v !== undefined && v !== "") target[f.key] = Number(v);
    }
    onSubmit(target);
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Company name">
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Target Pvt Ltd"
          />
        </Field>
        <Field label="Sector">
          <select
            className="input"
            value={sector}
            onChange={(e) => {
              setSector(e.target.value);
              setIndustry("");
            }}
          >
            <option value="">Select sector…</option>
            {sectors.map((s) => (
              <option key={s.sector} value={s.sector}>
                {s.sector} ({s.n})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sub-sector (tightens peers)">
          <select
            className="input"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            disabled={!sector}
          >
            <option value="">Any in sector</option>
            {industries.map((i) => (
              <option key={i.industry} value={i.industry}>
                {i.industry} ({i.n})
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-6">
        {NUM_FIELDS.map((f) => (
          <Field key={f.key} label={f.label}>
            <input
              className="input"
              type="number"
              value={nums[f.key] ?? ""}
              onChange={(e) => setNums((n) => ({ ...n, [f.key]: e.target.value }))}
            />
          </Field>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={submit} disabled={!canSubmit || disabled} className="btn-primary">
          Value this company
        </button>
        <span className="text-xs text-[color:var(--muted)]">
          📄 PDF auto-extraction (VLM) plugs in here later
        </span>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[color:var(--muted)]">
        {label}
      </span>
      {children}
    </label>
  );
}
