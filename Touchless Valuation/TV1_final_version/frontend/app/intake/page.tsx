"use client";

import { useMemo, useState } from "react";
import Dashboard from "@/app/components/Dashboard";
import { IntakeQuestion, IntakeResponse, ProResult } from "@/lib/types";

type IntakeMessage = {
  role: "assistant" | "user";
  text: string;
};

const INITIAL_TARGET = {
  name: "",
  sector: "",
  industry: "",
  revenue: "",
  ebitda: "",
  ebit: "",
  pat: "",
  net_worth: "",
  total_debt: "",
  cash: "",
};

export default function IntakePage() {
  const [form, setForm] = useState(INITIAL_TARGET);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [chat, setChat] = useState<IntakeMessage[]>([]);
  const [question, setQuestion] = useState<IntakeQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ProResult | null>(null);
  const [error, setError] = useState("");

  const canStart = form.name.trim() && form.sector.trim();

  const displayTitle = useMemo(() => {
    if (result?.target?.name) return result.target.name;
    if (form.name.trim()) return form.name.trim();
    return "Guided Intake";
  }, [form.name, result?.target?.name]);

  async function startInterview() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const payload: Record<string, unknown> = {
        custom: {
          name: form.name.trim(),
          sector: form.sector.trim(),
        },
      };
      if (form.industry.trim()) payload.custom = { ...(payload.custom as Record<string, unknown>), industry: form.industry.trim() };
      for (const key of ["revenue", "ebitda", "ebit", "pat", "net_worth", "total_debt", "cash"] as const) {
        const value = form[key].trim();
        if (value) {
          (payload.custom as Record<string, unknown>)[key] = Number(value);
        }
      }

      const response = await fetch("/api/intake/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await response.json()) as IntakeResponse;
      if (!response.ok) throw new Error(data?.question?.question ?? "Could not start intake.");
      setThreadId(data.thread_id);
      setQuestion(data.question ?? null);
      setChat([
        { role: "assistant", text: data.question?.question ?? "Let's begin." },
      ]);
      setAnswer("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start intake.");
    } finally {
      setLoading(false);
    }
  }

  async function submitAnswer() {
    if (!threadId || !question) return;
    setLoading(true);
    setError("");
    const userAnswer = answer.trim();
    try {
      const response = await fetch("/api/intake/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId, answer: userAnswer }),
      });
      const data = (await response.json()) as IntakeResponse;
      if (!response.ok) throw new Error(data?.question?.question ?? "Could not submit answer.");

      setChat((messages) => [...messages, { role: "user", text: userAnswer || "Skip" }]);
      if (data.done && data.result) {
        setResult(data.result);
        setChat((messages) => [...messages, { role: "assistant", text: "Intake complete. The report is below." }]);
        setQuestion(null);
      } else {
        const nextQuestion = data.question;
        if (nextQuestion) {
          setQuestion(nextQuestion);
          setChat((messages) => [...messages, { role: "assistant", text: nextQuestion.question }]);
        }
      }
      setAnswer("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit answer.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#f4f5f7_0%,#eef2eb_100%)] px-5 py-8 text-[color:var(--ink)]">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="card border border-[#cde3d4] bg-white p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#046a38]">Guided valuation chat</div>
          <h1 className="mt-2 text-3xl font-bold text-[#0b2e1f]">{displayTitle}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
            Start with a minimal company profile, then answer the deterministic interview one question at a time.
          </p>
        </header>

        {!threadId ? (
          <section className="card border border-[#cde3d4] bg-white p-6">
            <h2 className="text-base font-semibold text-[#0b2e1f]">Company details</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {Object.entries(form).map(([key, value]) => (
                <label key={key} className="block">
                  <span className="mb-1 block text-xs font-medium text-[color:var(--muted)]">
                    {key.replace(/_/g, " ")}
                  </span>
                  <input
                    className="input"
                    value={value}
                    onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                    placeholder={key === "name" ? "Target Pvt Ltd" : "Optional"}
                  />
                </label>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button className="btn-primary" onClick={() => void startInterview()} disabled={!canStart || loading}>
                Start intake
              </button>
              <span className="text-xs text-[color:var(--muted)]">
                The backend interview accepts skip on optional fields.
              </span>
            </div>
            {error && <p className="mt-3 text-sm text-[color:var(--bad)]">{error}</p>}
          </section>
        ) : (
          <section className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
            <div className="card border border-[#cde3d4] bg-white p-6">
              <h2 className="text-base font-semibold text-[#0b2e1f]">Conversation</h2>
              <div className="mt-4 space-y-3">
                {chat.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
                      message.role === "assistant"
                        ? "bg-[#f2f7ef] text-[#0b2e1f]"
                        : "ml-8 bg-[#0b2e1f] text-white"
                    }`}
                  >
                    {message.text}
                  </div>
                ))}
              </div>
              {question && (
                <div className="mt-5 rounded-2xl border border-[#cde3d4] bg-[#f8fbf6] p-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--muted)]">
                    Question {question.step} of {question.total}
                  </div>
                  <p className="mt-2 text-sm text-[#0b2e1f]">{question.question}</p>
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                    <input
                      className="input flex-1"
                      value={answer}
                      onChange={(event) => setAnswer(event.target.value)}
                      placeholder="Type answer or leave blank to skip"
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void submitAnswer();
                      }}
                    />
                    <button className="btn-primary sm:min-w-32" onClick={() => void submitAnswer()} disabled={loading}>
                      Send
                    </button>
                  </div>
                </div>
              )}
              {error && <p className="mt-3 text-sm text-[color:var(--bad)]">{error}</p>}
            </div>

            <div className="space-y-4">
              <section className="card border border-[#cde3d4] bg-[#0b2e1f] p-6 text-white">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200/70">
                  Intake state
                </div>
                <div className="mt-3 text-sm leading-6 text-emerald-50/90">
                  Deterministic questions. No prompt drift. The finished result stays aligned to the valuation engine.
                </div>
                <div className="mt-5 flex gap-2 text-[11px] text-emerald-100/70">
                  <span className="rounded-full bg-white/10 px-2.5 py-1">skip optional</span>
                  <span className="rounded-full bg-white/10 px-2.5 py-1">validated answers</span>
                  <span className="rounded-full bg-white/10 px-2.5 py-1">same company model</span>
                </div>
              </section>

              {result && (
                <section className="card border border-[#cde3d4] bg-white p-4">
                  <Dashboard result={result} />
                </section>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
