from __future__ import annotations

from pathlib import Path
from typing import List

from langchain.schema import Document

from src.config import Config


class MarkdownLoader:
    def __init__(self, config: Config) -> None:
        self.config = config

    def load_markdown(self) -> List[Document]:
        if not self.config.output_md.exists():
            raise FileNotFoundError('Markdown file not found.')

        text = self.config.output_md.read_text(encoding='utf-8')
        return [Document(page_content=text, metadata={'source': str(self.config.output_md)})]
