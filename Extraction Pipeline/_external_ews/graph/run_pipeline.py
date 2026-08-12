import sys
import os
import time
import json
from pathlib import Path

# Fix Windows cp1252 terminal encoding for Unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add graph directory to sys path so imports work correctly
# whether run as `python run_pipeline.py` or `python graph/run_pipeline.py`
sys.path.insert(0, str(Path(__file__).parent))

from sources.annual_report.extraction_pipeline import run_full_extraction
from sources.annual_report.excel_builder import build_excel


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py <path_to_pdf> [--no-llm]")
        print("")
        print("Options:")
        print("  --no-llm   Use keyword/regex taxonomy instead of LLM")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    use_llm = "--no-llm" not in sys.argv

    print(f"Starting Full Extraction Pipeline on: {pdf_path.name}")
    print(f"  LLM taxonomy: {'enabled' if use_llm else 'disabled (keyword/regex only)'}")
    print("-" * 60)

    t0 = time.time()

    def _progress(msg: str):
        print(f"  {msg}")

    # Run the full 9-layer extraction pipeline
    result = run_full_extraction(
        pdf_path=pdf_path,
        use_llm_taxonomy=use_llm,
        dpi=150,
        progress_callback=_progress,
    )

    elapsed = time.time() - t0
    print("-" * 60)
    print(f"Extraction complete in {elapsed:.1f}s")

    # ── Print summary ──
    stats = result.get("consolidation_stats", {})
    quality = result.get("quality_report", {})
    vlm_summary = result.get("vlm_target_summary", {})

    print(f"  Pages: {result['metadata'].get('page_count', '?')}")
    print(f"  Taxonomy mappings: {stats.get('taxonomy_mappings_input', '?')}")
    print(f"  Consolidated sections: {stats.get('total_sections', '?')} "
          f"(ratio: {stats.get('consolidation_ratio', '?')}, "
          f"TOC-anchored: {stats.get('toc_anchored_sections', '?')})")
    print(f"  VLM targets: {vlm_summary.get('total_targets', '?')} "
          f"({vlm_summary.get('by_priority', {}).get('high', 0)} HIGH, "
          f"{vlm_summary.get('by_priority', {}).get('medium', 0)} MEDIUM, "
          f"{vlm_summary.get('by_priority', {}).get('low', 0)} LOW)")
    print(f"  Quality score: {quality.get('overall_score', '?')}/10")
    print(f"  Text extractions: {len(result.get('text_extractions', []))}")
    print(f"  Table extractions: {len(result.get('table_extractions', []))}")

    # ── Save JSON output ──
    out_json = pdf_path.with_name(f"{pdf_path.stem}_output.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved JSON output to: {out_json}")

    # ── Generate Excel output ──
    try:
        excel_bytes = build_excel(result)
        out_excel = pdf_path.with_name(f"{pdf_path.stem}_output.xlsx")
        with open(out_excel, "wb") as f:
            f.write(excel_bytes)
        print(f"  Saved Excel output to: {out_excel}")
    except Exception as exc:
        print(f"  Failed to generate Excel: {exc}")


if __name__ == "__main__":
    main()
