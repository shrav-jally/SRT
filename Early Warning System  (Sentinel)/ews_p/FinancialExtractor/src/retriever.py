from __future__ import annotations

from typing import List

from langchain.schema import Document

from src.config import Config
from src.vectordb import VectorDB


class Retriever:
    def __init__(self, config: Config, vectordb: VectorDB) -> None:
        self.config = config
        self.vectordb = vectordb

    def get_relevant_chunks(self) -> List[Document]:
        index = self.vectordb.get_index()
        query = 'Extract financial statement sections and key entity values.'
        return index.similarity_search(query, k=self.config.top_k)
