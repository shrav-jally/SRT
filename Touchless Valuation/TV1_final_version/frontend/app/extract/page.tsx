"use client";

import { useMemo, useState } from "react";

const MODES = [
  { id: "full", label: "Full pipeline (ZIP)", endpoint: "/api/extract/full" },
  { id: "json", label: "Legacy JSON", endpoint: "/api/extract" },
  { id: "excel", label: "Excel workbook", endpoint: "/api/extract/excel" },
  { id: "zip", label: "JSON + Excel ZIP", endpoint: "/api/extract/zip" },
] as const;

type ModeId = (typeof MODES)[number]["id"];

export default function ExtractPage() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ModeId>("full");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("Upload an annual report PDF to begin.");
  const [preview, setPreview] = useState<string>("");

  const selected = useMemo(() => MODES.find((item) => item.id === mode)!, [mode]);

  async function runExtraction() {
    if (!file) return;
    setLoading(true);
    setPreview("");
    setMessage(`Running ${selected.label.toLowerCase()}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(selected.endpoint, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Extraction failed.");
      }

      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await response.json();
        setPreview(JSON.stringify(data, null, 2));
        setMessage("JSON result ready.");
        return;
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const disposition = response.headers.get("content-disposition") || "";
      const match = /filename="([^"]+)"/.exec(disposition);
      anchor.download = match?.[1] ?? `${file.name.replace(/\.pdf$/i, "")}_${mode}.bin`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      setMessage("Download started.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Extraction failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 bg-[linear-gradient(180deg,#f4f5f7_0%,#eef2eb_100%)] px-5 py-8 text-[color:var(--ink)]">
      <div className="mx-auto max-w-5xl space-y-6">
        <section className="card border border-[#cde3d4] bg-white p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#046a38]">Annual report extraction</div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="card border border-[#cde3d4] bg-white p-6">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-[color:var(--muted)]">Annual report PDF</span>
              <input
                type="file"
                accept="application/pdf"
                className="input"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>

            <div className="mt-4 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--muted)]">Mode</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {MODES.map((item) => (
                  <button
                    key={item.id}
                    className={`rounded-2xl border px-4 py-3 text-left transition ${
                      mode === item.id
                        ? "border-[#86bc25] bg-[#edf5ea] text-[#0b2e1f]"
                        : "border-[color:var(--line)] bg-white text-[color:var(--muted)] hover:border-[#86bc25] hover:text-[#0b2e1f]"
                    }`}
                    onClick={() => setMode(item.id)}
                    type="button"
                  >
                    <div className="text-sm font-semibold">{item.label}</div>
                    <div className="mt-1 text-xs leading-5 opacity-80">{item.endpoint}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button className="btn-primary" onClick={() => void runExtraction()} disabled={!file || loading}>
                {loading ? "Running…" : "Run extraction"}
              </button>
              <button className="dds-btn dds-btn_secondary" onClick={() => window.location.assign("/")}>Back to landing</button>
            </div>

            <p className="mt-4 text-sm text-[color:var(--muted)]">{message}</p>
          </div>

          <div className="card border border-[#cde3d4] bg-white p-6 text-[#0b2e1f]">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#046a38]">Output</div>
            <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
              JSON results appear inline for quick inspection. Streamed downloads trigger automatically for workbook and ZIP outputs.
            </p>
            {preview ? (
              <pre className="mt-4 max-h-[34rem] overflow-auto rounded-2xl border border-[color:var(--line)] bg-[#f7fbf4] p-4 text-[11px] leading-5 text-[#0b2e1f] whitespace-pre-wrap">
{preview}
              </pre>
            ) : (
              <div className="mt-4 rounded-2xl border border-[color:var(--line)] bg-[#f7fbf4] p-4 text-sm text-[color:var(--muted)]">
                The full pipeline exposes the canonical annual-report extraction structure from the qwen-onprem branch.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
