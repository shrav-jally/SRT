from __future__ import annotations

from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from src.config import Config


class Chunker:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        return self.splitter.split_documents(documents)
