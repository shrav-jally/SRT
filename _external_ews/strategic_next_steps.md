# What To Do Next — Strategic Analysis

## Where You Are Right Now

You have a **solid foundation** that already maps cleanly to the Perplexity-recommended architecture:

| Perplexity Recommendation | What You've Built | Status |
|---|---|---|
| Versioned Pydantic contracts | `contracts/` — 6 schemas, JSON exports, tested | ✅ Done |
| CanonicalDocument v0 adapter | `canonicalizer/` — 8 modules, emits canonical JSON | ✅ Done |
| Custom Extraction Spec Engine | `extractors/custom_spec/` — direct mapping + inference + exporter | ✅ Done |
| Sample spec JSON | `sample_custom_spec.json` — 10 enterprise fields | ✅ Done |
| Runnable demo CLI | `demo/run_custom_extraction.py` | ✅ Done |
| Contract tests | `tests/contract/` — 2 test suites passing | ✅ Done |
| Phase 0 audit | `docs/current_architecture_audit.md` | ✅ Done |

> [!IMPORTANT]
> **You are at the end of Phase 2 / Milestone C–D.** The two-layer architecture (Canonicalizer → Spec Engine) is code-complete for a demo. The Perplexity chat mapped out ~10 phases — you've completed 0, 1, 2, and the custom spec pivot.

---

## The Three Options You Asked About

### Option 1: Test How Good The Current Version Is

**Verdict: Do this FIRST, but keep it tight (2–3 hours)**

Why it matters:
- You've never run the full demo pipeline end-to-end on the company laptop with the Qwen VLM connected
- The demo run we tried locally failed on LLM connection errors (expected — the VLM is company-hosted)
- The Perplexity chat explicitly says: *"Do not refactor blindly. Tag the current state... create a benchmark runner"*
- You need to know your **actual** completion rate before demoing

What to do:
1. Run `python -m demo.run_custom_extraction` on the company laptop with VLM access
2. Inspect the canonical JSON — are sections, tables, and tokens populated correctly?
3. Check: How many of the 10 sample spec fields come back as `FOUND` vs `NOT_FOUND`?
4. Record a baseline: *"X/10 fields extracted, Y confidence, Z seconds runtime"*

> [!TIP]
> This gives you a **real number to pitch**: "Our system extracts X fields with full provenance in Z seconds. Uncertain fields are flagged for review, never silently guessed."

---

### Option 2: Build a UI

**Verdict: YES — build a lightweight demo UI. This is the highest-impact next step for the demo.**

Why:
- Right now you have a CLI-only demo. For a presentation, a visual interface is **dramatically** more compelling
- The Perplexity chat's demo pitch is: *"Step 1: We convert the report into canonical JSON. Step 2: Any team defines its extraction schema. Step 3: Structured outputs with provenance. Step 4: Direct fields are deterministic; fuzzy ones go through controlled inference."* — all of this screams for a visual flow
- You already have a FastAPI app (`app.py`) — adding a frontend is incremental
- A UI lets you **live-demo** uploading a PDF, selecting/editing a spec, running extraction, and browsing results with provenance

What to build (keep it to ~4–6 hours):
1. **Upload page**: Drag-and-drop PDF → triggers canonicalization → shows canonical JSON summary (pages, sections, tables found)
2. **Spec editor**: Load/edit the `sample_custom_spec.json` fields in a simple table view
3. **Run extraction**: Button that triggers `extract_from_custom_spec()` → shows results table
4. **Results view**: Color-coded status badges (green=FOUND, red=NOT_FOUND, yellow=AMBIGUOUS), expandable provenance (page number, section, confidence, explanation)
5. **Export buttons**: Download JSON + Excel

> [!IMPORTANT]
> The UI doesn't need to be production-grade. A single-page FastAPI + vanilla HTML/JS app is enough. The point is to make the demo **visual and interactive** rather than terminal output.

---

### Option 3: Improve Current Architecture

**Verdict: NOT NOW — only fix things that directly impact the demo**

The Perplexity chat is explicit: *"Do not try to perfect all tables. Do not try to rebuild the whole architecture. Build a convincing vertical slice."*

Post-demo improvements to queue (in priority order):
1. **VLM parallelization** — 5x speedup (300s → 60s) by running VLM calls concurrently
2. **Numeric validation layer** — the pdfplumber guardrail that cross-checks VLM numbers against PDF text
3. **Better table structure** — cell-level reconstruction for borderless tables  
4. **DocLayout-YOLO integration** — replace heuristic table detection with a proper layout model
5. **Financial Statements Extractor** — dedicated BS/PL/CF extractor with synonym registry (the MSME path from Phase 4–5)

None of these are needed for tomorrow's demo.

---

## Recommended Execution Plan (Next 8–10 Hours)

```
Hour 0–1:   Test on company laptop with VLM
            → Get real completion rate numbers
            → Fix any import/path issues

Hour 1–2:   Fix any broken fields in direct_mapping / inference
            → Tune the search logic if fields are NOT_FOUND that should be FOUND
            → Adjust synonyms in sample_custom_spec.json

Hour 2–7:   Build the demo UI
            → FastAPI routes for canonicalize + extract
            → Single-page HTML/JS frontend
            → Upload → Spec → Results → Export flow
            → Color-coded status, expandable provenance

Hour 7–8:   Polish and rehearse
            → Run full demo end-to-end 2–3 times
            → Screenshot the flow for backup slides
            → Prepare talking points around the 4-step pitch
```

## The Demo Pitch (from Perplexity, refined)

1. **"We convert the full annual report into an auditable canonical JSON"** → Show the canonical document summary (124 pages, 34 sections, 21 tables)
2. **"Any business team can define its own extraction schema"** → Show the spec editor with 10 fields across Financial Data, Governance, Demographics
3. **"The system returns structured outputs with provenance and confidence"** → Show the results table with green/red/yellow status badges
4. **"Direct fields are deterministic; inference fields go through controlled LLM"** → Show a DIRECT_MAPPING field (Balance Sheet) vs an INFERENCE_BASED field (Business Outlook)
5. **"Nothing is silently guessed — uncertain fields are flagged for review"** → Highlight a NOT_FOUND or AMBIGUOUS field with its explanation

---

## Bottom Line

**Build the UI.** You have the engine. What you're missing is the presentation layer that makes it demoable. Testing on the company laptop is a prerequisite (1 hour), but the UI is where you'll spend most of your remaining time and where it'll have the most impact.
