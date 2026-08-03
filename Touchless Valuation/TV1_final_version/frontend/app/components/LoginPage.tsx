"use client";

import { useState } from "react";

export default function LoginPage({ onLogin }: { onLogin: (username: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!username.trim()) {
      setError("Please enter a username.");
      return;
    }

    setLoading(true);
    // Mock: simulate a brief network delay, then accept any credentials
    await new Promise((r) => setTimeout(r, 600));
    setLoading(false);
    onLogin(username.trim());
  }

  return (
    <div className="flex min-h-[calc(100vh-56px)] items-center justify-center bg-[#0b2e1f] px-4">
      {/* Circular motif background decoration */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-32 -left-32 h-96 w-96 rounded-full opacity-[0.07]"
          style={{ background: "radial-gradient(circle, #86BC25 0%, transparent 70%)" }}
        />
        <div
          className="absolute -bottom-48 -right-48 h-[500px] w-[500px] rounded-full opacity-[0.05]"
          style={{ background: "radial-gradient(circle, #86BC25 0%, transparent 70%)" }}
        />
      </div>

      <div className="relative z-10 w-full max-w-md">
        {/* Logo & title */}
        <div className="mb-8 text-center">
          {/* Deloitte wordmark */}
          <svg
            viewBox="0 0 200 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="mx-auto mb-4"
            style={{ height: 36, width: "auto" }}
          >
            <circle cx="12" cy="20" r="6" fill="#86BC25" />
            <text
              x="26"
              y="27"
              fill="white"
              fontFamily="Open Sans, sans-serif"
              fontWeight="700"
              fontSize="20"
            >
              Deloitte
            </text>
          </svg>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Touchless Valuation
          </h1>
          <div className="mt-2 inline-flex items-center gap-2">
            <span className="rounded bg-[#86bc25] px-2 py-0.5 text-[11px] font-bold text-[#0b2e1f]">
              TV 1
            </span>
            <span className="text-xs text-emerald-200/60">
              Income · Market · Asset — triangulated
            </span>
          </div>
        </div>

        {/* Login card */}
        <div className="rounded-xl border border-white/10 bg-white/[0.06] p-8 shadow-lg backdrop-blur-sm">
          <h2 className="mb-6 text-center text-lg font-semibold text-white">
            Sign in to your account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Username */}
            <div>
              <label
                htmlFor="username"
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-emerald-200/70"
              >
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                className="w-full rounded-md border border-white/15 bg-white/[0.08] px-4 py-3 text-sm text-white placeholder-white/30 outline-none transition focus:border-[#86BC25] focus:ring-1 focus:ring-[#86BC25]/40"
              />
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-emerald-200/70"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full rounded-md border border-white/15 bg-white/[0.08] px-4 py-3 text-sm text-white placeholder-white/30 outline-none transition focus:border-[#86BC25] focus:ring-1 focus:ring-[#86BC25]/40"
              />
            </div>

            {/* Error message */}
            {error && (
              <p className="rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-300">
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="dds-btn dds-btn_lg dds-btn_fluid-width rounded-md border-[#86BC25] text-[#86BC25] hover:bg-[#86BC25] hover:text-[#0b2e1f] disabled:opacity-50"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeDasharray="60"
                      strokeLinecap="round"
                    />
                  </svg>
                  Signing in…
                </span>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          {/* Disclaimer */}
          <p className="mt-6 text-center text-[10px] text-emerald-200/40 leading-relaxed">
            Authorized Deloitte personnel only. All activity is logged.<br />
            Indicative screening valuation — not a certified registered-valuer opinion.
          </p>
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-[10px] text-emerald-200/30">
          © {new Date().getFullYear()} Deloitte Development LLC. All rights reserved.
        </p>
      </div>
    </div>
  );
}
