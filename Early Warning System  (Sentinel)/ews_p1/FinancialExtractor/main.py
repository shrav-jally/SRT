from __future__ import annotations

import logging
from pathlib import Path

from src.chunker import chunk_text
from src.config import get_config
from src.extractor import extract_financial_entities
from src.parser import extract_text_from_pdf
from src.validator import validate_entities
from src.excel_writer import write_excel_output

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the financial entity extraction pipeline end to end."""
    print("===================================")
    print("Financial Entity Extraction")
    print("===================================")

    try:
        config = get_config()
        input_folder = config.input_folder
        output_folder = config.output_folder
        output_folder.mkdir(parents=True, exist_ok=True)

        pdf_files = sorted(input_folder.glob("*.pdf"))
        if not pdf_files:
            raise FileNotFoundError(f"No PDF files found in input folder: {input_folder}")

        pdf_path = pdf_files[0]
        logger.info("Processing PDF: %s", pdf_path)

        print("\nStep 1")
        print("Extract PDF using pdfplumber")
        print("↓")
        extracted_text = extract_text_from_pdf(pdf_path)
        annual_report_path = output_folder / "annual_report.txt"
        annual_report_path.write_text(extracted_text, encoding="utf-8")
        logger.info("Saved extracted text to %s", annual_report_path)

        print("\nStep 2")
        print("Chunk text")
        print("↓")
        chunks = chunk_text(extracted_text)
        logger.info("Created %d text chunks", len(chunks))

        print("\nStep 3")
        print("Send chunks to LLM")
        print("↓")
        entities_path = output_folder / "entities.json"
        extract_financial_entities(chunks, output_path=entities_path)
        logger.info("Wrote extracted entities to %s", entities_path)

        print("\nStep 4")
        print("Merge extracted JSON")
        print("↓")
        logger.info("Merged extracted JSON successfully")

        print("\nStep 5")
        print("Validate")
        print("↓")
        validated_entities_path = output_folder / "validated_entities.json"
        validate_entities(entities_path, validated_entities_path)
        logger.info("Validated entities written to %s", validated_entities_path)

        print("\nStep 6")
        print("Populate Excel")
        print("↓")
        template_path = config.template_folder / "financial_template.xlsx"
        output_excel_path = output_folder / "financial_output.xlsx"
        write_excel_output(validated_entities_path, template_path, output_excel_path)
        logger.info("Excel workbook written to %s", output_excel_path)

        print("\nDone.")
        print("Output files generated:")
        print(f"- {annual_report_path.name}")
        print(f"- {entities_path.name}")
        print(f"- {validated_entities_path.name}")
        print(f"- {output_excel_path.name}")
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.exception("Pipeline failed: %s", exc)
        print(f"Pipeline failed: {exc}")


if __name__ == "__main__":
    main()
