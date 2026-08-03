"""Runnable CLI Entrypoint for Product 1 (Canonicalizer) + Product 2 (Custom Spec Engine).

Supports both single PDF files and directories of multiple PDFs.

Usage:
    Single PDF:
        python -m demo.run_custom_extraction --pdf cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf --spec sample_custom_spec.json

    Batch PDF Directory:
        python -m demo.run_custom_extraction --dir "C:\\Users\\miahmed.ext\\Downloads\\all pdfs" --spec sample_custom_spec.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from canonicalizer import canonicalize_pdf, save_canonical_document
from extractors.custom_spec import (
    export_custom_extraction_to_excel,
    extract_from_custom_spec,
    load_custom_spec,
)


def process_single_pdf(pdf_path: Path, spec_path: Path, output_base_dir: Path | None = None) -> dict:
    """Process a single PDF through Product 1 and Product 2."""
    t0 = time.time()
    print("=" * 80)
    print("      ENTERPRISE TWO-LAYER DOCUMENT UNDERSTANDING ARCHITECTURE DEMO")
    print("=" * 80)
    print(f"  Input PDF : {pdf_path.name}")
    print(f"  Input Spec: {spec_path.name}")
    print("-" * 80)

    # ---------------------------------------------------------
    # STEP 1: Product 1 (Canonicalizer v0)
    # ---------------------------------------------------------
    print("\n[PRODUCT 1] Building CanonicalDocument v0...")
    canonical_doc = canonicalize_pdf(pdf_path=pdf_path, use_llm_taxonomy=False)

    doc_dir = output_base_dir / canonical_doc.document_id if output_base_dir else Path("output") / canonical_doc.document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    canonical_json_path = doc_dir / "canonical_document.v0.json"
    print(f"  [OK] CanonicalDocument generated ({len(canonical_doc.pages)} pages, "
          f"{len(canonical_doc.sections)} sections, {len(canonical_doc.tables)} tables)")
    print(f"  [OK] Canonical JSON saved to: {canonical_json_path}")

    # ---------------------------------------------------------
    # STEP 2: Product 2 (Generic Schema-Driven Extractor)
    # ---------------------------------------------------------
    print("\n[PRODUCT 2] Executing Custom Spec Engine against Canonical JSON...")
    spec_doc = load_custom_spec(spec_path)
    print(f"  Loaded Spec '{spec_doc.spec_id}': {len(spec_doc.fields)} fields requested")

    result_doc = extract_from_custom_spec(canonical_doc=canonical_doc, spec=spec_doc)

    # ---------------------------------------------------------
    # STEP 3: Save Output JSON & Excel
    # ---------------------------------------------------------
    result_json_path = doc_dir / "custom_extraction_result.json"
    result_excel_path = doc_dir / "custom_extraction_result.xlsx"

    with open(result_json_path, "w", encoding="utf-8") as f:
        f.write(result_doc.model_dump_json(indent=2))

    export_custom_extraction_to_excel(result_doc, output_path=result_excel_path)

    elapsed = time.time() - t0

    # ---------------------------------------------------------
    # STEP 4: Print Single Summary Table
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("                      EXTRACTION SUMMARY REPORT")
    print("=" * 80)
    print(f"{'FIELD ID':<22} | {'MODE':<15} | {'STATUS':<10} | {'CONF':<5} | {'RAW VALUE / SUMMARY'}")
    print("-" * 80)

    for res in result_doc.results:
        f_id = res.field_id[:20]
        mode = res.extraction_mode.value[:14]
        status = res.status.value
        conf = f"{res.confidence * 100:.0f}%"
        val = str(res.value_raw or res.explanation or "-")[:32].replace("\n", " ")

        print(f"{f_id:<22} | {mode:<15} | {status:<10} | {conf:<5} | {val}")

    print("-" * 80)
    summary_stats = result_doc.summary
    print(f"Total Requested: {summary_stats.get('total_fields_requested')} | "
          f"FOUND: {summary_stats.get('fields_found')} | "
          f"NOT FOUND: {summary_stats.get('fields_not_found')} | "
          f"Completion Rate: {summary_stats.get('completion_rate_pct')}%")
    print(f"Elapsed Time   : {elapsed:.2f}s")
    print("-" * 80)
    print(f"JSON Result : {result_json_path}")
    print(f"Excel Result: {result_excel_path}")
    print("=" * 80 + "\n")

    return {
        "file_name": pdf_path.name,
        "pages": len(canonical_doc.pages),
        "sections": len(canonical_doc.sections),
        "tables": len(canonical_doc.tables),
        "found": summary_stats.get("fields_found", 0),
        "total": summary_stats.get("total_fields_requested", 0),
        "completion_rate_pct": summary_stats.get("completion_rate_pct", 0.0),
        "elapsed_seconds": round(elapsed, 2),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Enterprise Two-Layer Custom Extraction Engine (Batch or Single PDF)"
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Path to single annual report PDF file or directory",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Path to directory containing multiple PDF files",
    )
    parser.add_argument(
        "--spec",
        type=str,
        default="sample_custom_spec.json",
        help="Path to user-defined custom extraction spec JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional custom output directory",
    )

    args = parser.parse_args()
    spec_path = Path(args.spec)

    if not spec_path.exists():
        print(f"Error: Spec file not found at {spec_path}")
        sys.exit(1)

    # Determine PDF targets
    pdf_files: list[Path] = []

    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"Error: Directory not found at {dir_path}")
            sys.exit(1)
        pdf_files = sorted(list(dir_path.glob("*.pdf")))
    elif args.pdf:
        target_path = Path(args.pdf)
        if target_path.is_dir():
            pdf_files = sorted(list(target_path.glob("*.pdf")))
        elif target_path.is_file():
            pdf_files = [target_path]
        else:
            print(f"Error: Path not found at {target_path}")
            sys.exit(1)
    else:
        # Default fallback to sample PDF if exists
        sample_pdf = Path("cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf")
        if sample_pdf.exists():
            pdf_files = [sample_pdf]
        else:
            print("Error: Please specify --pdf <file_or_dir> or --dir <folder_path>")
            sys.exit(1)

    output_base_dir = Path(args.output_dir) if args.output_dir else Path("output")

    print(f"\nStarting Batch Extraction for {len(pdf_files)} PDF(s)...")

    batch_summary = []
    for idx, pdf_f in enumerate(pdf_files, start=1):
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {pdf_f.name}")
        try:
            res_info = process_single_pdf(pdf_f, spec_path, output_base_dir=output_base_dir)
            batch_summary.append(res_info)
        except Exception as exc:
            print(f"Error processing {pdf_f.name}: {exc}")
            batch_summary.append({
                "file_name": pdf_f.name,
                "pages": 0,
                "sections": 0,
                "tables": 0,
                "found": 0,
                "total": 10,
                "completion_rate_pct": 0.0,
                "elapsed_seconds": 0.0,
                "error": str(exc),
            })

    # Print Batch Benchmark Summary Table
    if len(batch_summary) > 1:
        print("\n" + "=" * 95)
        print("                  BATCH DOCUMENT EXTRACTION BENCHMARK SUMMARY")
        print("=" * 95)
        print(f"{'PDF FILE NAME':<35} | {'PAGES':<6} | {'SECS':<5} | {'TBLS':<5} | {'FOUND':<6} | {'RATE (%)':<8} | {'TIME'}")
        print("-" * 95)

        for s in batch_summary:
            fn = s["file_name"][:33]
            pgs = s["pages"]
            secs = s["sections"]
            tbls = s["tables"]
            found = f"{s['found']}/{s['total']}"
            rate = f"{s['completion_rate_pct']:.1f}%"
            tm = f"{s['elapsed_seconds']}s"

            print(f"{fn:<35} | {pgs:<6} | {secs:<5} | {tbls:<5} | {found:<6} | {rate:<8} | {tm}")

        print("=" * 95 + "\n")


if __name__ == "__main__":
    main()
