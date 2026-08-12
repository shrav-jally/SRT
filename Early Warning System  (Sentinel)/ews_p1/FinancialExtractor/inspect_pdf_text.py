
import pdfplumber
from pathlib import Path
from src.parser import preprocess_pdf_text

pdf_path = Path('input/sample_annual_report.pdf')
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ''
        print('PAGE', i)
        print(repr(text[:1000]))
        print('---')
        cleaned = preprocess_pdf_text(text)
        print('CLEANED', repr(cleaned[:1000]))
        print('====')
