from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter

from src.config import Config
from src.utils import save_json


class DoclingParser:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.converter = DocumentConverter()

    def parse_pdf(self) -> str:
        if not self.config.input_pdf.exists():
            raise FileNotFoundError('Input PDF not found.')

        try:
            result = self.converter.convert(str(self.config.input_pdf))
        except Exception as error:
            raise RuntimeError('Docling parsing failed.') from error

        document = result.document
        markdown_text = document.export_to_markdown()
        self.config.output_md.write_text(markdown_text, encoding='utf-8')
        self.config.output_json.write_text(json.dumps(document.export_to_dict(), indent=2), encoding='utf-8')
        return markdown_text
