"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type SearchHit = {
  code: number;
  name: string;
  sector: string | null;
  industry: string | null;
  valuation_grade: boolean;
};

type SuggestionState = {
  status: "idle" | "searching" | "listed" | "unlisted";
  hits: SearchHit[];
  selected?: SearchHit;
  query: string;
};

export default function Home() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<SuggestionState>({
    status: "idle",
    hits: [],
    query: "",
  });

  useEffect(() => {
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, []);

  async function searchCompany() {
    const query = state.query.trim();
    if (!query) return;

    setState((current) => ({ ...current, status: "searching" }));
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const hits = (await response.json()) as SearchHit[];

    if (hits.length > 0) {
      setState({ status: "listed", hits, selected: hits[0], query });
      return;
    }

    setState({ status: "unlisted", hits: [], query });
  }

  function openListedReport(hit?: SearchHit) {
    const company = hit ?? state.selected;
    if (!company) return;
    sessionStorage.setItem("tv1_pending_code", String(company.code));
    setOpen(false);
    router.push("/reports");
  }

  const suggestionCopy = useMemo(() => {
    if (state.status === "listed") {
      return state.selected
        ? `${state.selected.name} matched the database. Open the report workspace or choose a different match.`
        : "A listed company matched the database.";
    }
    if (state.status === "unlisted") {
      return "No listed match found. Choose annual-report extraction or guided intake.";
    }
    if (state.status === "searching") {
      return "Checking the listed universe...";
    }
    return "Start with a company name. The flow will route listed targets to reports and unlisted targets to extraction or intake.";
  }, [state.selected, state.status]);

  return (
    <div className="flex-1 bg-[radial-gradient(circle_at_top_left,_rgba(134,188,37,0.18),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(4,106,56,0.18),_transparent_32%),linear-gradient(180deg,#f4f5f7_0%,#eef2eb_100%)] text-[color:var(--ink)]">


      <main className="mx-auto max-w-6xl px-5 pb-16 pt-12 md:pt-16">
        <section className="flex flex-col items-center text-center gap-12">
          <div className="space-y-8 flex flex-col items-center">
            <div className="max-w-2xl space-y-5">
              <h1 className="text-4xl font-extrabold tracking-tight text-[#0b2e1f] md:text-6xl">
                Touchless valuation from search to report.
              </h1>
            </div>

            <div className="flex justify-center gap-3">
              <button
                className="dds-btn dds-btn_lg dds-btn_green rounded-full px-7 shadow-md"
                onClick={() => setOpen(true)}
              >
                Start valuation
              </button>
            </div>
          </div>

          <aside className="card w-full max-w-2xl overflow-hidden border border-[#cde3d4] bg-white p-6 shadow-sm">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#046a38]">
              Flow snapshot
            </div>
            <div className="mt-4 space-y-4 text-left">
              <FlowRow step="01" title="Search listed company" detail="Autocomplete against the database universe." />
              <FlowRow step="02" title="Open report workspace" detail="Triangulated valuation, audit trail, and board-ready output." />
              <FlowRow step="03" title="Unlisted fallback" detail="Annual-report extraction or guided intake questions." />
              <FlowRow step="04" title="Save / print" detail="Generate the clean PDF-ready report with provenance." />
            </div>
          </aside>
        </section>
      </main>

      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 backdrop-blur-sm md:items-center">
          <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-[#d5e4d6] bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-[color:var(--line)] px-6 py-4">
              <div>
                <div className="text-sm font-semibold text-[#0b2e1f]">Start valuation</div>
                <div className="text-xs text-[color:var(--muted)]">A quick chat that routes you to the right flow.</div>
              </div>
              <button className="dds-btn dds-btn_sm dds-btn_silent" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <div className="rounded-2xl bg-[#f2f7ef] p-4 text-sm text-[#0b2e1f]">
                {suggestionCopy}
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-semibold uppercase tracking-wider text-[color:var(--muted)]">
                  Company name
                </label>
                <div className="flex flex-col gap-3 md:flex-row">
                  <input
                    className="input flex-1"
                    value={state.query}
                    onChange={(event) => setState((current) => ({ ...current, query: event.target.value }))}
                    placeholder="Type a company name to continue"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void searchCompany();
                    }}
                  />
                  <button className="btn-primary md:min-w-36" onClick={() => void searchCompany()}>
                    Continue
                  </button>
                </div>
              </div>

              {state.status === "listed" && state.selected && (
                <div className="rounded-2xl border border-[#cde3d4] bg-white p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-[#0b2e1f]">{state.selected.name}</div>
                      <div className="text-xs text-[color:var(--muted)]">
                        {state.selected.sector ?? "Listed target"}
                        {state.selected.industry ? ` · ${state.selected.industry}` : ""}
                      </div>
                    </div>
                    <button className="dds-btn dds-btn_sm dds-btn_green" onClick={() => openListedReport()}>
                      Open report
                    </button>
                  </div>
                </div>
              )}

              {state.status === "unlisted" && (
                <div className="grid gap-3 md:grid-cols-2">
                  <button
                    className="rounded-2xl border border-[#cde3d4] bg-[#f7fbf4] p-4 text-left transition hover:border-[#86bc25]"
                    onClick={() => {
                      setOpen(false);
                      router.push("/extract");
                    }}
                  >
                    <div className="text-sm font-semibold text-[#0b2e1f]">Annual report extraction</div>
                    <p className="mt-1 text-xs leading-5 text-[color:var(--muted)]">
                      Upload the PDF and run the extraction pipeline first.
                    </p>
                  </button>
                  <button
                    className="rounded-2xl border border-[#cde3d4] bg-[#f7fbf4] p-4 text-left transition hover:border-[#86bc25]"
                    onClick={() => {
                      setOpen(false);
                      router.push("/intake");
                    }}
                  >
                    <div className="text-sm font-semibold text-[#0b2e1f]">Guided question chat</div>
                    <p className="mt-1 text-xs leading-5 text-[color:var(--muted)]">
                      Answer deterministic questions and flow into valuation.
                    </p>
                  </button>
                </div>
              )}

            </div>
          </div>
        </div>
      )}

      <div className="pointer-events-none fixed inset-x-0 bottom-0 h-24 bg-gradient-to-t from-[#f4f5f7] to-transparent" />
    </div>
  );
}

function FlowRow({ step, title, detail }: { step: string; title: string; detail: string }) {
  return (
    <div className="flex gap-4 rounded-2xl border border-[color:var(--line)] bg-[#f7fbf4] p-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#86bc25] text-sm font-bold text-[#0b2e1f]">
        {step}
      </div>
      <div>
        <div className="text-sm font-semibold text-[#0b2e1f]">{title}</div>
        <p className="mt-1 text-xs leading-5 text-[color:var(--muted)]">{detail}</p>
      </div>
    </div>
  );
}
