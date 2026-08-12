# Financial Entity Extraction Pipeline

## Overview
This project builds an end-to-end Financial Entity Extraction Pipeline for annual report PDFs. It parses the PDF using Docling, converts it to markdown and JSON, indexes chunked document embeddings in FAISS, retrieves relevant sections, extracts structured financial entities with an LLM, validates the output, and populates an Excel template.

## Architecture
- `parser.py`: parses PDF to markdown and JSON using Docling.
- `loader.py`: loads markdown into LangChain Documents.
- `chunker.py`: splits the document into overlapping chunks.
- `vectordb.py`: builds/persists FAISS index with embeddings.
- `retriever.py`: retrieves top-k relevant chunks.
- `extractor.py`: extracts financial JSON via an LLM.
- `validator.py`: cleans and validates extracted entities.
- `excel_writer.py`: populates the Excel template.
- `main.py`: orchestrates the entire pipeline.

## Installation
1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Create `.env` from the template and set `OPENAI_API_KEY`.

## Folder Structure
```
FinancialExtractor/
  input/
    AnnualReport.pdf
  output/
  templates/
    financial_template.xlsx
  vectorstore/
  src/
    __init__.py
    parser.py
    loader.py
    chunker.py
    vectordb.py
    retriever.py
    extractor.py
    validator.py
    excel_writer.py
    config.py
    utils.py
  .env
  main.py
  requirements.txt
  README.md
```

## Running
1. Place `AnnualReport.pdf` inside `input/`.
2. Place `financial_template.xlsx` inside `templates/`.
3. Run:
   ```bash
   python main.py
   ```
4. Outputs are written to `output/` and `vectorstore/`.

## Expected Outputs
- `output/annual_report.md`
- `output/annual_report.json`
- `output/entities.json`
- `output/validated_entities.json`
- `output/financial_output.xlsx`

## Troubleshooting
- `OPENAI_API_KEY missing`: set the key in `.env`.
- `AnnualReport.pdf not found`: place PDF in `input/`.
- `Excel template missing`: place file in `templates/`.
- `Docling parsing failed`: ensure Docling is installed in the current venv.
