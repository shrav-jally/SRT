from __future__ import annotations

import pickle
from pathlib import Path
from typing import List

from langchain.vectorstores import FAISS
from langchain.schema import Document

try:
    from langchain.embeddings import HuggingFaceEmbeddings
except ImportError:  # pragma: no cover
    HuggingFaceEmbeddings = None

try:
    from langchain.embeddings import FakeEmbeddings
except ImportError:  # pragma: no cover
    FakeEmbeddings = None

from src.config import Config


class VectorDB:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.index: FAISS | None = None

    def _get_embeddings(self):
        provider = self.config.embedding_provider.lower()
        if provider == 'huggingface':
            if HuggingFaceEmbeddings is None:
                raise RuntimeError('HuggingFaceEmbeddings is unavailable.')
            return HuggingFaceEmbeddings(model_name=self.config.embedding_model)

        if provider in {'fake', 'custom'}:
            if FakeEmbeddings is None:
                raise RuntimeError('FakeEmbeddings is unavailable.')
            return FakeEmbeddings()

        raise ValueError(f'Unsupported embedding provider: {self.config.embedding_provider}')

    def build_index(self, documents: List[Document]) -> None:
        embeddings = self._get_embeddings()
        if self.config.faiss_index_file.exists() and self.config.embeddings_file.exists():
            try:
                self.index = FAISS.load_local(str(self.config.vectorstore_dir), embeddings)
                return
            except Exception:
                pass

        self.index = FAISS.from_documents(documents, embeddings)
        self.index.save_local(str(self.config.vectorstore_dir))
        with open(self.config.embeddings_file, 'wb') as handle:
            pickle.dump(True, handle)

    def get_index(self) -> FAISS:
        if self.index is None:
            embeddings = self._get_embeddings()
            self.index = FAISS.load_local(str(self.config.vectorstore_dir), embeddings)
        return self.index
